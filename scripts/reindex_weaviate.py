"""
Batch re-index all PostgreSQL chunks into Weaviate.

Run inside Docker backend container:
    docker compose exec backend python scripts/reindex_weaviate.py

Options:
    --batch N   chunks per progress report (default 20)
    --limit N   max chunks to process (default: all)
    --dry-run   test embedding only, no Weaviate write
"""
import sys
import os
import argparse
import requests
import psycopg2
import psycopg2.extras
import weaviate
from datetime import datetime

# ── Config from environment (same as app/config/settings.py) ──────────────────
PG_HOST     = os.getenv("POSTGRES_HOST", "postgres")
PG_PORT     = int(os.getenv("POSTGRES_PORT", 5432))
PG_DB       = os.getenv("POSTGRES_DB", "pentest_graphrag")
PG_USER     = os.getenv("POSTGRES_USER", "graphrag_user")
PG_PASS     = os.getenv("POSTGRES_PASSWORD", "password")

OLLAMA_URL  = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

WV_HOST     = os.getenv("WEAVIATE_HOST", "weaviate")
WV_PORT     = int(os.getenv("WEAVIATE_PORT", 8080))
WV_GRPC     = int(os.getenv("WEAVIATE_GRPC_PORT", 50051))
COLLECTION  = "docs_chunks"


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def embed(text: str) -> list[float]:
    """Call Ollama /api/embeddings and return vector."""
    resp = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text[:3000]},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def ensure_collection(wv_client):
    """Create docs_chunks collection if missing."""
    if wv_client.collections.exists(COLLECTION):
        log(f"Collection '{COLLECTION}' already exists.")
        return
    wv_client.collections.create(
        name=COLLECTION,
        vectorizer_config=None,   # manual vectors
        properties=[
            {"name": "content",   "dataType": ["text"]},
            {"name": "chunk_id",  "dataType": ["int"]},
            {"name": "document_id","dataType": ["int"]},
            {"name": "chunk_index","dataType": ["int"]},
        ],
    )
    log(f"Created collection '{COLLECTION}'.")


def main():
    parser = argparse.ArgumentParser(description="Re-index PostgreSQL chunks → Weaviate")
    parser.add_argument("--batch", type=int, default=20,  help="progress report every N chunks")
    parser.add_argument("--limit", type=int, default=None, help="max chunks to process")
    parser.add_argument("--dry-run", action="store_true",  help="test embedding, skip Weaviate write")
    args = parser.parse_args()

    # ── 1. Connect to Weaviate ─────────────────────────────────────────────────
    log("Connecting to Weaviate …")
    wv = weaviate.connect_to_local(host=WV_HOST, port=WV_PORT, grpc_port=WV_GRPC)
    if not args.dry_run:
        ensure_collection(wv)
        col = wv.collections.get(COLLECTION)

    # ── 2. Connect to PostgreSQL ───────────────────────────────────────────────
    log("Connecting to PostgreSQL …")
    pg = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=PG_PASS,
    )
    cur = pg.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # ── 3. Fetch chunks without vector ────────────────────────────────────────
    query = "SELECT id, content, document_id, chunk_index FROM chunks WHERE weaviate_uuid IS NULL ORDER BY id"
    if args.limit:
        query += f" LIMIT {args.limit}"
    cur.execute(query)
    rows = cur.fetchall()
    total = len(rows)
    log(f"Found {total} chunks to index (dry_run={args.dry_run})")

    if total == 0:
        log("Nothing to do — all chunks already indexed.")
        cur.close(); pg.close(); wv.close()
        return

    # ── 4. Embed & upsert ─────────────────────────────────────────────────────
    # Test embedding model first
    log(f"Testing embedding model '{EMBED_MODEL}' …")
    try:
        test_vec = embed("test connection")
        log(f"Embedding OK — vector dim: {len(test_vec)}")
    except Exception as e:
        log(f"ERROR: Ollama embedding failed: {e}")
        log(f"  Check OLLAMA_BASE_URL={OLLAMA_URL} and model name '{EMBED_MODEL}'")
        sys.exit(1)

    success = 0
    failed  = 0
    skipped = 0

    for i, row in enumerate(rows):
        chunk_id  = row["id"]
        content   = (row["content"] or "").strip()
        doc_id    = row["document_id"]
        chunk_idx = row["chunk_index"]

        if not content:
            skipped += 1
            continue

        try:
            vector = embed(content)

            if not args.dry_run:
                # Insert into Weaviate (uuid derived from chunk_id for idempotency)
                import uuid
                wv_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"chunk-{chunk_id}"))
                col.data.insert(
                    properties={
                        "content":     content,
                        "chunk_id":    chunk_id,
                        "document_id": doc_id or 0,
                        "chunk_index": chunk_idx or 0,
                    },
                    vector=vector,
                    uuid=wv_uuid,
                )

                # Update PostgreSQL with uuid
                cur.execute(
                    "UPDATE chunks SET weaviate_uuid = %s WHERE id = %s",
                    (wv_uuid, chunk_id)
                )
                if (i + 1) % 50 == 0:
                    pg.commit()  # commit every 50 rows

            success += 1

        except Exception as e:
            failed += 1
            log(f"  SKIP chunk {chunk_id}: {e}")
            if failed >= 20:
                log("20 consecutive errors — aborting. Check Ollama / Weaviate.")
                break

        if (i + 1) % args.batch == 0 or (i + 1) == total:
            pct = (i + 1) / total * 100
            log(f"  {i+1}/{total} ({pct:.0f}%)  ok={success}  skip={skipped}  err={failed}")

    # Final commit
    if not args.dry_run:
        pg.commit()

    cur.close()
    pg.close()
    wv.close()

    log(f"\n{'='*50}")
    log(f"DONE — indexed={success}, skipped={skipped}, failed={failed} / {total}")
    if not args.dry_run:
        log(f"Verify: curl 'http://localhost:8080/v1/objects?class={COLLECTION}&limit=1'")


if __name__ == "__main__":
    main()
