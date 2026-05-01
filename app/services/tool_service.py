"""Pentest Tool Service - Complete CVE & Nuclei Integration (Phase 9)."""

import httpx
import json
import subprocess
from typing import Dict, List, Optional, Tuple
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config.settings import settings
from app.core.logger import logger
from app.core.security import audit_log, validate_target
from app.adapters.neo4j_client import Neo4jAdapter
from app.domain.schemas.extraction import Entity, Relation
from datetime import datetime
import re

class PentestToolService:
    """Phase 9: Complete tool service for CVE analysis and security scanning."""
    
    def __init__(self):
        self.neo4j = Neo4jAdapter()
        self.nuclei_endpoint = settings.NUCLEI_ENDPOINT if hasattr(settings, 'NUCLEI_ENDPOINT') else "http://nuclei:8080"
        self.cvss_keywords = {
            "critical": ["remote code execution", "rce", "unauthenticated access"],
            "high": ["denial of service", "buffer overflow", "sql injection"],
            "medium": ["information disclosure", "weak authentication"],
            "low": ["configuration issue", "best practice violation"]
        }

    # ============ CVE ANALYSIS ============

    async def analyze_cve_exploitable(self, cve_json: Dict) -> Dict:
        """
        Analyze CVE JSON for exploitability potential.
        Returns exploitability score, CVSS prediction, and recommendations.
        """
        cve_id = cve_json.get("cveMetadata", {}).get("cveId", "UNKNOWN")
        
        try:
            # Extract core information
            cve_description = self._extract_cve_description(cve_json)
            affected_products = self._extract_affected_products(cve_json)
            references = self._extract_references(cve_json)
            
            # Analyze exploitability
            exploitability_score = self._calculate_exploitability_score(cve_description)
            attack_vector = self._determine_attack_vector(cve_description)
            severity = self._predict_severity(cve_description, exploitability_score)
            
            # Recommendation
            recommendation = self._generate_recommendation(
                exploitability_score, 
                attack_vector, 
                affected_products
            )
            
            analysis_result = {
                "cve_id": cve_id,
                "exploitability_score": exploitability_score,  # 0.0-1.0
                "attack_vector": attack_vector,  # "network", "local", "physical"
                "severity": severity,  # "critical", "high", "medium", "low"
                "affected_products": affected_products,
                "description": cve_description[:500],
                "references": references[:3],
                "recommend_nuclei_scan": exploitability_score > 0.6,
                "recommendation": recommendation
            }
            
            logger.info("✅ CVE analysis completed", cve_id=cve_id, 
                       score=exploitability_score, severity=severity)
            await audit_log("cve_analyze", {"cve_id": cve_id, "score": exploitability_score})
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"❌ CVE analysis failed: {e}")
            return {
                "cve_id": cve_id,
                "error": str(e),
                "exploitability_score": 0.0
            }

    def _extract_cve_description(self, cve_json: Dict) -> str:
        """Extract description from CVE JSON."""
        containers = cve_json.get("containers", {}).get("cna", {})
        descriptions = containers.get("descriptions", [])
        if descriptions:
            return descriptions[0].get("value", "")
        return ""

    def _extract_affected_products(self, cve_json: Dict) -> List[Dict]:
        """Extract affected products/vendors."""
        containers = cve_json.get("containers", {}).get("cna", {})
        affected = containers.get("affected", [])
        
        products = []
        for item in affected[:5]:  # Limit to 5
            product = {
                "vendor": item.get("vendor", "N/A"),
                "product": item.get("product", "N/A"),
                "versions": []
            }
            versions = item.get("versions", [])
            for ver in versions[:3]:
                product["versions"].append(ver.get("version", "N/A"))
            products.append(product)
        
        return products

    def _extract_references(self, cve_json: Dict) -> List[str]:
        """Extract reference URLs."""
        containers = cve_json.get("containers", {}).get("cna", {})
        references = containers.get("references", [])
        
        refs = []
        for ref in references:
            url = ref.get("url")
            if url:
                refs.append(url)
        return refs

    def _calculate_exploitability_score(self, description: str) -> float:
        """
        Calculate exploitability score (0.0-1.0) based on description keywords.
        """
        description_lower = description.lower()
        score = 0.5  # Base score
        
        # Boost for high-risk keywords
        high_risk = ["remote", "rce", "arbitrary code execution", "unauthenticated", "pre-auth"]
        for keyword in high_risk:
            if keyword in description_lower:
                score += 0.15
        
        # Reduce for low-risk
        low_risk = ["information disclosure", "dos", "information leak"]
        for keyword in low_risk:
            if keyword in description_lower:
                score -= 0.1
        
        # Clamp between 0 and 1
        return max(0.0, min(1.0, score))

    def _determine_attack_vector(self, description: str) -> str:
        """Determine attack vector from description."""
        description_lower = description.lower()
        
        if any(word in description_lower for word in ["remote", "network", "internet", "http"]):
            return "network"
        elif any(word in description_lower for word in ["local", "privileged"]):
            return "local"
        else:
            return "unknown"

    def _predict_severity(self, description: str, score: float) -> str:
        """Predict CVSS severity level."""
        description_lower = description.lower()
        
        if score > 0.8:
            return "critical"
        elif score > 0.6:
            return "high"
        elif score > 0.4:
            return "medium"
        else:
            return "low"

    def _generate_recommendation(self, score: float, attack_vector: str, products: List) -> str:
        """Generate actionable recommendation."""
        if score > 0.8:
            return f"CRITICAL: Run Nuclei scan immediately. Attack vector: {attack_vector}"
        elif score > 0.6:
            return f"HIGH: Recommend Nuclei scan. Affected products: {', '.join([p.get('product', 'N/A') for p in products[:2]])}"
        else:
            return "Consider for future scans. Monitor for patches."

    # ============ NUCLEI SCANNING ============

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def run_nuclei_scan(
        self,
        target: str,
        templates: Optional[List[str]] = None,
        severity: Optional[str] = None
    ) -> Dict:
        """
        Run Nuclei scan against target.
        In lab: Using subprocess (requires local Nuclei)
        In production: Would use HTTP API to Nuclei service
        """
        # Validate target
        try:
            await validate_target(target)
        except Exception as e:
            logger.error(f"Target validation failed: {e}")
            raise PermissionError(f"Target {target} not permitted")
        
        logger.info("🔍 Starting Nuclei scan", target=target, templates=templates, severity=severity)
        
        try:
            # Try subprocess (local Nuclei)
            nuclei_result = await self._run_nuclei_subprocess(
                target=target,
                templates=templates,
                severity=severity
            )
            
            await audit_log("nuclei_scan_complete", {
                "target": target,
                "results": len(nuclei_result.get("findings", []))
            })
            
            return nuclei_result
            
        except FileNotFoundError:
            logger.warning("Nuclei not installed locally, trying HTTP API...")
            
            # Try HTTP API
            try:
                nuclei_result = await self._run_nuclei_http(
                    target=target,
                    templates=templates,
                    severity=severity
                )
                return nuclei_result
            except Exception as e:
                logger.error(f"Nuclei HTTP API failed: {e}")
                return {
                    "status": "error",
                    "message": "Nuclei not available (install locally or deploy service)",
                    "error": str(e)
                }

    async def _run_nuclei_subprocess(
        self,
        target: str,
        templates: Optional[List[str]] = None,
        severity: Optional[str] = None
    ) -> Dict:
        """Run Nuclei using local subprocess."""
        cmd = ["nuclei", "-target", target, "-json"]
        
        if templates:
            for template in templates[:5]:  # Limit templates
                cmd.extend(["-template", template])
        
        if severity:
            cmd.extend(["-severity", severity])
        
        logger.debug(f"Executing: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=settings.MAX_TOOL_TIMEOUT
            )
            
            findings = []
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        try:
                            finding = json.loads(line)
                            findings.append({
                                "template": finding.get("template-id"),
                                "type": finding.get("type"),
                                "severity": finding.get("info", {}).get("severity"),
                                "description": finding.get("info", {}).get("description"),
                                "matched_at": finding.get("matched-at"),
                                "extracted_results": finding.get("extracted-results")
                            })
                        except json.JSONDecodeError:
                            pass
            
            return {
                "status": "success",
                "target": target,
                "findings": findings,
                "total": len(findings),
                "timestamp": datetime.now().isoformat()
            }
            
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "error": f"Nuclei scan exceeded {settings.MAX_TOOL_TIMEOUT}s"}
        except Exception as e:
            logger.error(f"Nuclei subprocess failed: {e}")
            raise

    async def _run_nuclei_http(
        self,
        target: str,
        templates: Optional[List[str]] = None,
        severity: Optional[str] = None
    ) -> Dict:
        """Run Nuclei via HTTP API service."""
        payload = {
            "target": target,
            "templates": templates or [],
            "severity": severity,
            "timeout": settings.MAX_TOOL_TIMEOUT,
            "json": True
        }
        
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.nuclei_endpoint}/scan",
                    json=payload
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"Nuclei HTTP call failed: {e}")
            raise

    # ============ CVE + NUCLEI INTEGRATION ============

    async def analyze_and_scan_cve(
        self,
        cve_id: str,
        cve_json: Optional[Dict] = None,
        target: Optional[str] = None
    ) -> Dict:
        """
        End-to-end: Analyze CVE and optionally run Nuclei scan if permitted.
        """
        logger.info("🔗 CVE Analysis + Nuclei Integration", cve_id=cve_id, target=target)
        
        # Step 1: Analyze CVE
        if cve_json:
            cve_analysis = await self.analyze_cve_exploitable(cve_json)
        else:
            cve_analysis = {
                "cve_id": cve_id,
                "exploitability_score": 0.5,
                "severity": "unknown"
            }
        
        # Step 2: Run Nuclei if recommended and target provided
        nuclei_results = None
        if target and cve_analysis.get("recommend_nuclei_scan", False):
            try:
                nuclei_results = await self.run_nuclei_scan(
                    target=target,
                    templates=[f"cves/2023/{cve_id.lower()}"],
                    severity=cve_analysis.get("severity")
                )
            except Exception as e:
                logger.warning(f"Nuclei scan skipped: {e}")
        
        # Step 3: Correlate findings
        correlation = {
            "cve_id": cve_id,
            "analysis": cve_analysis,
            "scan_results": nuclei_results,
            "correlation_summary": self._correlate_findings(cve_analysis, nuclei_results)
        }
        
        await audit_log("cve_scan_complete", {"cve_id": cve_id, "target": target})
        
        return correlation

    def _correlate_findings(self, cve_analysis: Dict, nuclei_results: Optional[Dict]) -> Dict:
        """Correlate CVE analysis with Nuclei findings."""
        summary = {
            "cve_vulnerable": cve_analysis.get("exploitability_score", 0) > 0.6,
            "nuclei_findings": (nuclei_results or {}).get("total", 0),
            "risk_level": "HIGH" if nuclei_results and nuclei_results.get("findings") else "MEDIUM",
            "recommendation": ""
        }
        
        if nuclei_results and nuclei_results.get("findings"):
            summary["recommendation"] = f"Target is vulnerable! {nuclei_results['total']} issues found by Nuclei."
        else:
            summary["recommendation"] = "Monitor for available patches."
        
        return summary