#!/usr/bin/env python3
"""
Batch Ingest hàng loạt file JSON CVE
"""

import asyncio
import httpx
import json
from pathlib import Path
from tqdm import tqdm

API_URL = "http://localhost:8000/ingest/document"
MAX_CONCURRENT = 5  # Số file upload song song (tùy RAM máy bạn)

async def ingest_file(client: httpx.AsyncClient, file_path: Path):
    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "application/json")}
            response = await client.post(API_URL, files=files)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ OK  | {file_path.name} → Document ID: {data.get('document_id')}")
            return data.get('document_id')
        else:
            print(f"❌ FAIL | {file_path.name} → {response.status_code} {response.text}")
            return None
    except Exception as e:
        print(f"❌ ERROR | {file_path.name} → {e}")
        return None

async def batch_ingest_cve(folder_path: str):
    path = Path(folder_path)
    json_files = list(path.glob("**/*.json"))  # quét tất cả file .json trong thư mục và thư mục con
    
    print(f"🔍 Tìm thấy {len(json_files)} file JSON CVE")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        tasks = [ingest_file(client, f) for f in json_files]
        
        # Chạy với giới hạn concurrent
        for i in tqdm(range(0, len(tasks), MAX_CONCURRENT), desc="Uploading"):
            batch = tasks[i:i + MAX_CONCURRENT]
            await asyncio.gather(*batch)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        folder = sys.argv[1]
    else:
        folder = input("Nhập đường dẫn thư mục chứa các file JSON CVE: ").strip()
    if folder:
        asyncio.run(batch_ingest_cve(folder))
        print("Vui lòng nhập đường dẫn thư mục!")