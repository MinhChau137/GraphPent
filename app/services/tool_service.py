"""Pentest Tool Service - CVE-focused (Phase 9)."""

import httpx
import json
from typing import Dict, List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config.settings import settings
from app.core.logger import logger
from app.core.security import audit_log, validate_target
from app.adapters.neo4j_client import Neo4jAdapter
from app.domain.schemas.extraction import Entity, Relation

class PentestToolService:
    def __init__(self):
        self.neo4j = Neo4jAdapter()
        self.nuclei_api_url = "http://nuclei:8080"  # sẽ thêm service Nuclei trong docker-compose sau

    async def analyze_cve_exploitable(self, cve_json: Dict) -> Dict:
        """Phân tích CVE JSON xem có khả năng khai thác không."""
        cve_id = cve_json.get("cveMetadata", {}).get("cveId", "UNKNOWN")
        description = ""
        
        # Extract description từ nhiều vị trí có thể có trong CVE JSON
        containers = cve_json.get("containers", {}).get("cna", {})
        descriptions = containers.get("descriptions", [])
        if descriptions:
            description = descriptions[0].get("value", "")

        is_exploitable = any(keyword in description.lower() for keyword in [
            "remote", "denial of service", "buffer overflow", "arbitrary code", 
            "rce", "command injection", "sql injection", "exploit"
        ])

        await audit_log("cve_analyze", {"cve_id": cve_id, "is_exploitable": is_exploitable})

        return {
            "cve_id": cve_id,
            "is_exploitable": is_exploitable,
            "description": description[:500],
            "recommend_tool": "nuclei" if is_exploitable else None
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def run_nuclei_for_cve(self, cve_id: str, target: str, templates: List[str] = None) -> Dict:
        """Chạy Nuclei chỉ cho CVE cụ thể - SAFE LAB ONLY."""
        await validate_target(target)

        if not settings.is_target_allowed(target):
            raise PermissionError(f"Target {target} not in ALLOWED_TARGETS")

        # Default templates cho CVE
        if not templates:
            templates = [f"cve/{cve_id}"]

        payload = {
            "target": target,
            "templates": templates,
            "timeout": settings.MAX_TOOL_TIMEOUT,
            "rate_limit": settings.RATE_LIMIT_PER_MIN
        }

        await audit_log("nuclei_run_start", {"cve_id": cve_id, "target": target})

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(f"{self.nuclei_api_url}/scan", json=payload)
                resp.raise_for_status()
                result = resp.json()

            # Update graph với finding mới
            finding_entity = Entity(
                type="Finding",
                name=f"Nuclei Finding - {cve_id}",
                properties={"cve_id": cve_id, "severity": result.get("severity", "medium")}
            )
            await self.neo4j.upsert_entities_and_relations(
                entities=[finding_entity],
                relations=[]
            )

            logger.info("Nuclei CVE scan completed", cve_id=cve_id, target=target)
            return {"status": "success", "cve_id": cve_id, "result": result}

        except Exception as e:
            logger.error("Nuclei scan failed", cve_id=cve_id, error=str(e))
            await audit_log("nuclei_run_failed", {"cve_id": cve_id, "error": str(e)})
            return {"status": "failed", "error": str(e)}