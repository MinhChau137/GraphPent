#!/usr/bin/env python3
"""
Optimized End-to-End Batch Pipeline
Data: CVE JSON (cvelistV5) + CWE XML + NVD JSON
Strategy:
  1. Filter CVEs by year >= START_YEAR and file size (skip near-empty)
  2. Fix: use extract_all_chunks(document_id) not extract_from_chunk
  3. Resume: skip already-processed files via progress log
  4. Controlled concurrency: LLM_CONCURRENCY parallel LLM calls at most
  5. Graceful error handling with retries
"""

import asyncio
import json
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── Must be run inside container (has app/ in PYTHONPATH) ──────────────────
sys.path.insert(0, "/app")

from app.services.ingestion_service import IngestionService
from app.services.extraction_service import ExtractionService
from app.core.logger import logger

# ── Config ─────────────────────────────────────────────────────────────────
START_YEAR      = 2018          # Ignore CVEs older than this year
MIN_FILE_BYTES  = 800           # Skip near-empty CVE files (< 800 bytes)
LLM_CONCURRENCY = 3             # Max parallel LLM extraction calls
PROGRESS_LOG    = Path("/app/batch_progress.jsonl")   # Resume log
RESULTS_LOG     = Path("/app/batch_results.jsonl")


# ══════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════

def _load_done_set() -> set:
    """Return set of filenames already successfully processed."""
    done = set()
    if PROGRESS_LOG.exists():
        for line in PROGRESS_LOG.read_text().splitlines():
            try:
                rec = json.loads(line)
                if rec.get("status") == "success":
                    done.add(rec["file"])
            except Exception:
                pass
    return done


def _log_result(rec: dict):
    with open(RESULTS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if rec.get("status") == "success":
        with open(PROGRESS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"file": rec["file"], "status": "success"}) + "\n")


def _filter_cve_files(folder: Path) -> list[Path]:
    """Return CVE files filtered by year and minimum size.
    Scans only year subdirectories >= START_YEAR to avoid globbing entire repo.
    """
    kept = []
    year_dirs = [d for d in folder.iterdir() if d.is_dir() and d.name.isdigit() and len(d.name) == 4 and int(d.name) >= START_YEAR]
    if not year_dirs:
        # Fallback: flat folder without year subdirs
        for f in folder.glob("*.json"):
            if f.stat().st_size >= MIN_FILE_BYTES:
                kept.append(f)
        return sorted(kept)

    for year_dir in sorted(year_dirs):
        for f in year_dir.glob("**/*.json"):
            if f.stat().st_size >= MIN_FILE_BYTES:
                kept.append(f)
    return sorted(kept)


# ══════════════════════════════════════════════════════════════════════════
# Core pipeline
# ══════════════════════════════════════════════════════════════════════════

async def process_one(
    file_path: Path,
    ingestion_svc: IngestionService,
    extraction_svc: ExtractionService,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Ingest → extract_all_chunks → return stats. Semaphore limits LLM calls."""
    rec = {"file": file_path.name, "path": str(file_path), "status": "error"}
    try:
        content = file_path.read_bytes()

        # 1. Ingest (dedup by SHA-256 — safe to re-run)
        ingest = await ingestion_svc.ingest_document(
            file_bytes=content,
            filename=file_path.name,
            content_type="application/json",
            metadata={"source": "cve-batch", "year": file_path.parts[-3] if len(file_path.parts) >= 3 else "unknown"},
        )
        doc_id = ingest["document_id"]

        if ingest["status"] == "duplicate":
            rec.update({"status": "skipped_duplicate", "document_id": doc_id})
            return rec

        # 2. Extract all chunks (fix: was incorrectly using document_id as chunk_id)
        async with semaphore:
            extract = await extraction_svc.extract_all_chunks(doc_id)

        rec.update({
            "status": "success",
            "document_id": doc_id,
            "chunks": ingest["chunks_count"],
            "entities": extract.get("total_entities", 0),
            "relations": extract.get("total_relations", 0),
        })

    except Exception as exc:
        rec["error"] = str(exc)
        logger.error("Pipeline error", file=file_path.name, error=str(exc))

    return rec


async def run_batch(files: list[Path], label: str):
    ingestion_svc = IngestionService()
    extraction_svc = ExtractionService()
    semaphore = asyncio.Semaphore(LLM_CONCURRENCY)
    done_set = _load_done_set()

    pending = [f for f in files if f.name not in done_set]
    skipped_upfront = len(files) - len(pending)

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  Total files    : {len(files)}")
    print(f"  Already done   : {skipped_upfront}")
    print(f"  To process     : {len(pending)}")
    print(f"  LLM concurrency: {LLM_CONCURRENCY}")
    print(f"{'='*60}\n")

    success = skipped_dup = errors = 0
    t0 = time.perf_counter()

    # Process in mini-batches so we get live progress without flooding memory
    BATCH = LLM_CONCURRENCY * 4
    for i in range(0, len(pending), BATCH):
        chunk = pending[i:i + BATCH]
        tasks = [process_one(f, ingestion_svc, extraction_svc, semaphore) for f in chunk]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                errors += 1
                continue
            _log_result(r)
            st = r.get("status", "error")
            if st == "success":
                success += 1
            elif st == "skipped_duplicate":
                skipped_dup += 1
            else:
                errors += 1

        done_total = i + len(chunk)
        elapsed = time.perf_counter() - t0
        rate = done_total / elapsed if elapsed > 0 else 0
        eta_s = (len(pending) - done_total) / rate if rate > 0 else 0
        print(
            f"  [{done_total:>5}/{len(pending)}]  "
            f"ok={success}  dup={skipped_dup+skipped_upfront}  "
            f"err={errors}  "
            f"rate={rate:.1f}/s  ETA={eta_s/60:.1f}min"
        )

    print(f"\n  Done. {success} new, {skipped_dup+skipped_upfront} duplicates, {errors} errors.")


# ══════════════════════════════════════════════════════════════════════════
# Entry points per data type
# ══════════════════════════════════════════════════════════════════════════

async def run_cve(data_dir: Path, max_files: Optional[int]):
    """Process individual CVE JSON files from cvelistV5."""
    cve_root = data_dir / "cvelistV5-main" / "cvelistV5-main" / "cves"
    if not cve_root.exists():
        # Fallback: scan entire data_dir
        cve_root = data_dir
    files = _filter_cve_files(cve_root)
    if max_files:
        files = files[:max_files]
    await run_batch(files, f"CVE pipeline  (year>={START_YEAR})")


async def run_nvd(data_dir: Path):
    """Ingest the consolidated NVD JSON as a single document."""
    nvd_file = data_dir / "nvdcve-2.0-modified.json"
    if not nvd_file.exists():
        print("NVD file not found, skipping.")
        return
    await run_batch([nvd_file], "NVD consolidated JSON")


async def run_cwe(data_dir: Path):
    """Ingest the CWE XML file."""
    cwe_file = data_dir / "cwec_v4.19.1.xml"
    if not cwe_file.exists():
        # Try any .xml file
        xmls = list(data_dir.glob("*.xml"))
        if not xmls:
            print("CWE XML not found, skipping.")
            return
        cwe_file = xmls[0]

    ingestion_svc = IngestionService()
    extraction_svc = ExtractionService()
    semaphore = asyncio.Semaphore(LLM_CONCURRENCY)

    print(f"\n{'='*60}")
    print(f"  CWE XML pipeline: {cwe_file.name}  ({cwe_file.stat().st_size // 1024} KB)")
    print(f"{'='*60}\n")

    rec = await process_one(cwe_file, ingestion_svc, extraction_svc, semaphore)
    _log_result(rec)
    print(f"  Result: {rec['status']}  entities={rec.get('entities',0)}  relations={rec.get('relations',0)}")


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Optimized GraphPent data pipeline")
    parser.add_argument(
        "--mode",
        choices=["cve", "nvd", "cwe", "all"],
        default="all",
        help="Which dataset to process (default: all, recommended order: cwe → nvd → cve)",
    )
    parser.add_argument(
        "--data-dir",
        default="/app/data",
        help="Path to data directory inside container (default: /app/data)",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Limit number of CVE files (useful for testing, e.g. --max-files 100)",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=START_YEAR,
        help=f"Process CVEs from this year onwards (default: {START_YEAR})",
    )
    args = parser.parse_args()

    START_YEAR = args.year
    data_dir = Path(args.data_dir)

    if not data_dir.exists():
        print(f"ERROR: data dir not found: {data_dir}")
        sys.exit(1)

    async def main():
        if args.mode in ("cwe", "all"):
            await run_cwe(data_dir)
        if args.mode in ("nvd", "all"):
            await run_nvd(data_dir)
        if args.mode in ("cve", "all"):
            await run_cve(data_dir, args.max_files)
        print(f"\nProgress log : {PROGRESS_LOG}")
        print(f"Results log  : {RESULTS_LOG}")

    asyncio.run(main())
