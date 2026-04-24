"""Batch data loader for CWE XML and CVE JSON files."""

import os
import json
import asyncio
from pathlib import Path
from typing import List, Dict, AsyncGenerator
from app.core.logger import logger


class BatchDataLoader:
    """Load data from directories containing CWE XML and CVE JSON files."""
    
    def __init__(self):
        self.base_data_dir = Path("data")
    
    async def load_cwe_xml(self, filepath: str = None) -> Dict:
        """Load CWE XML file."""
        if filepath is None:
            filepath = self.base_data_dir / "cwec_v4.19.1.xml"
        
        if not os.path.exists(filepath):
            logger.warning(f"CWE XML file not found: {filepath}")
            return None
        
        try:
            with open(filepath, "rb") as f:
                data = f.read()
            logger.info(f"Loaded CWE XML file: {filepath}", size_bytes=len(data))
            return {
                "filename": Path(filepath).name,
                "content_type": "application/xml",
                "data": data,
                "source": "cwe_xml"
            }
        except Exception as e:
            logger.error(f"Failed to load CWE XML: {filepath}", error=str(e))
            return None
    
    async def load_nvd_cve_json(self, filepath: str = None) -> Dict:
        """Load NVD CVE JSON file."""
        if filepath is None:
            filepath = self.base_data_dir / "nvdcve-2.0-modified.json"
        
        if not os.path.exists(filepath):
            logger.warning(f"NVD CVE JSON file not found: {filepath}")
            return None
        
        try:
            with open(filepath, "rb") as f:
                data = f.read()
            logger.info(f"Loaded NVD CVE JSON file: {filepath}", size_bytes=len(data))
            return {
                "filename": Path(filepath).name,
                "content_type": "application/json",
                "data": data,
                "source": "nvd_cve_json"
            }
        except Exception as e:
            logger.error(f"Failed to load NVD CVE JSON: {filepath}", error=str(e))
            return None
    
    async def load_cve_v5_files(self, base_path: str = None) -> AsyncGenerator[Dict, None]:
        """Stream individual CVE v5 JSON files from directory structure."""
        if base_path is None:
            base_path = self.base_data_dir / "cvelistV5-main" / "cvelistV5-main" / "cves"
        
        base_path = Path(base_path)
        if not base_path.exists():
            logger.warning(f"CVE v5 base directory not found: {base_path}")
            return
        
        # Traverse directory structure: YYYY/xxxx/CVE-YYYY-XXXX.json
        for year_dir in sorted(base_path.glob("*/"), key=lambda x: x.name):
            if not year_dir.is_dir():
                continue
            
            for group_dir in sorted(year_dir.glob("*/"), key=lambda x: x.name):
                if not group_dir.is_dir():
                    continue
                
                for cve_file in sorted(group_dir.glob("CVE-*.json")):
                    if not cve_file.is_file():
                        continue
                    
                    try:
                        with open(cve_file, "rb") as f:
                            data = f.read()
                        
                        logger.debug(f"Loaded CVE v5 file: {cve_file.name}", size_bytes=len(data))
                        yield {
                            "filename": cve_file.name,
                            "content_type": "application/json",
                            "data": data,
                            "source": "cve_v5_json",
                            "filepath": str(cve_file.relative_to(base_path))
                        }
                    except Exception as e:
                        logger.error(f"Failed to load CVE v5 file: {cve_file}", error=str(e))
                        continue
    
    async def load_all_cve_v5_files(self, base_path: str = None) -> List[Dict]:
        """Load all CVE v5 files into memory."""
        files = []
        async for file_data in self.load_cve_v5_files(base_path):
            files.append(file_data)
        return files
    
    async def count_cve_v5_files(self, base_path: str = None) -> int:
        """Count total CVE v5 JSON files."""
        if base_path is None:
            base_path = self.base_data_dir / "cvelistV5-main" / "cvelistV5-main" / "cves"
        
        base_path = Path(base_path)
        count = 0
        for cve_file in base_path.glob("**/CVE-*.json"):
            count += 1
        return count
    
    async def load_delta_changes(self) -> Dict:
        """Load CVE delta changes (incremental updates)."""
        filepath = self.base_data_dir / "cvelistV5-main" / "cvelistV5-main" / "cves" / "delta.json"
        
        if not os.path.exists(filepath):
            logger.warning(f"Delta file not found: {filepath}")
            return None
        
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            
            new_count = len(data.get("new", []))
            updated_count = len(data.get("updated", []))
            
            logger.info(
                f"Loaded CVE delta changes",
                new_cves=new_count,
                updated_cves=updated_count,
                fetch_time=data.get("fetchTime")
            )
            
            return {
                "filename": "delta.json",
                "new_cves": new_count,
                "updated_cves": updated_count,
                "data": data
            }
        except Exception as e:
            logger.error(f"Failed to load delta changes: {filepath}", error=str(e))
            return None


async def get_data_statistics() -> Dict:
    """Get statistics about available data."""
    loader = BatchDataLoader()
    stats = {
        "cwe_xml": None,
        "nvd_cve_json": None,
        "cve_v5_files_count": 0,
        "cve_delta": None
    }
    
    # Check CWE XML
    try:
        cwe = await loader.load_cwe_xml()
        if cwe:
            stats["cwe_xml"] = {
                "filename": cwe["filename"],
                "size_mb": len(cwe["data"]) / (1024 * 1024)
            }
    except Exception as e:
        logger.error("Failed to check CWE XML", error=str(e))
    
    # Check NVD CVE JSON
    try:
        nvd = await loader.load_nvd_cve_json()
        if nvd:
            stats["nvd_cve_json"] = {
                "filename": nvd["filename"],
                "size_mb": len(nvd["data"]) / (1024 * 1024)
            }
    except Exception as e:
        logger.error("Failed to check NVD CVE JSON", error=str(e))
    
    # Count CVE v5 files
    try:
        count = await loader.count_cve_v5_files()
        stats["cve_v5_files_count"] = count
    except Exception as e:
        logger.error("Failed to count CVE v5 files", error=str(e))
    
    # Check delta
    try:
        delta = await loader.load_delta_changes()
        if delta:
            stats["cve_delta"] = {
                "new": delta["new_cves"],
                "updated": delta["updated_cves"]
            }
    except Exception as e:
        logger.error("Failed to check delta changes", error=str(e))
    
    return stats
