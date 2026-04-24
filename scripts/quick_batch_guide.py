#!/usr/bin/env python3
"""Quick batch operations for GraphRAG - Start here!"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logger import logger
from app.utils.batch_loader import get_data_statistics


async def print_quick_guide():
    """Print quick start guide."""
    guide = """
╔════════════════════════════════════════════════════════════════╗
║     🚀 GraphRAG Batch Operations - QUICK START                ║
╚════════════════════════════════════════════════════════════════╝

📊 AVAILABLE DATA:
"""
    print(guide)
    
    # Show statistics
    stats = await get_data_statistics()
    
    if stats["cwe_xml"]:
        print(f"  ✅ CWE XML: {stats['cwe_xml']['filename']} ({stats['cwe_xml']['size_mb']:.1f} MB)")
    if stats["nvd_cve_json"]:
        print(f"  ✅ NVD CVE: {stats['nvd_cve_json']['filename']} ({stats['nvd_cve_json']['size_mb']:.1f} MB)")
    if stats["cve_v5_files_count"]:
        print(f"  ✅ CVE v5: {stats['cve_v5_files_count']:,} files")
    
    commands = """

📝 COMMON COMMANDS:

1️⃣  View Available Data:
    python scripts/batch_ingest_all.py --mode stats

2️⃣  Ingest CWE XML (Weaknesses):
    python scripts/batch_ingest_all.py --mode cwe

3️⃣  Ingest NVD CVE JSON (Vulnerabilities):
    python scripts/batch_ingest_all.py --mode nvd

4️⃣  Ingest CVE v5 Files (Sample - 10 files):
    python scripts/batch_ingest_all.py --mode cv5 --limit 10

5️⃣  Ingest ALL CVE v5 Files:
    python scripts/batch_ingest_all.py --mode cv5

6️⃣  Ingest ALL Data (CWE + NVD + CV5):
    python scripts/batch_ingest_all.py --mode all

🎯 RECOMMENDED WORKFLOW:

Step 1: Check available data
  $ python scripts/batch_ingest_all.py --mode stats

Step 2: Test with small sample (10 CVE files)
  $ python scripts/batch_ingest_all.py --mode cv5 --limit 10

Step 3: Check ingestion results in database

Step 4: Run full ingestion
  $ python scripts/batch_ingest_all.py --mode all

📚 MORE DETAILS:
  - See CVE_JSON_SUPPORT.md for full documentation
  - Check logs at logs/graphrag.log

🔧 ADVANCED OPTIONS:
  --limit N           Limit number of files to process
  --cve-dir PATH      Custom CVE directory path

💡 TIPS:
  - Use --limit for large batches to monitor progress
  - Check logs/graphrag.log for detailed processing logs
  - First run may take time due to LLM extraction
  - Duplicate files are automatically skipped

════════════════════════════════════════════════════════════════
"""
    print(commands)


if __name__ == "__main__":
    asyncio.run(print_quick_guide())
