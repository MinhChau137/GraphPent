"""LLM Adapter cho Ollama - Security Knowledge Graph (CWE + CVE + Nmap)"""

import uuid
import json
import re
from ollama import AsyncClient
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config.settings import settings
from app.core.logger import logger
from app.domain.schemas.extraction import ExtractionResult, Entity, Relation


class LLMClient:
    def __init__(self):
        self.client = AsyncClient(host=settings.OLLAMA_BASE_URL.rstrip("/"))
        self.model = settings.OLLAMA_MODEL

    def _safe_json_loads(self, raw_output: str) -> dict:
        """Repair và parse JSON output từ LLM một cách robust."""
        repaired = self._repair_json(raw_output)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            # Clean control characters
            sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', repaired)
            sanitized = re.sub(r'\t', ' ', sanitized)
            return json.loads(sanitized)

    @staticmethod
    def _detect_data_type(chunk_text: str) -> str:
        text_lower = chunk_text.lower()
        if "<weakness" in text_lower or "cwe-" in text_lower or "weakness" in text_lower:
            return "cwe"
        elif "cve-" in text_lower or '"cve"' in text_lower or "cvss" in text_lower:
            return "cve"
        elif "nmap" in text_lower or "host" in text_lower and "port" in text_lower:
            return "nmap"
        return "generic"

    # ====================== CWE EXTRACTION ======================
    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=5, max=40))
    async def extract_entities_and_relations(self, chunk_text: str, chunk_id: int) -> ExtractionResult:
        """Extract từ CWE XML."""
        system_prompt = """
You are a Security Knowledge Graph expert specializing in MITRE CWE.

**MISSION:** Extract high-quality entities and rich relationships for a connected graph.

**CORE ENTITY TYPES:**
1. Weakness (CWE)
2. Mitigation
3. AffectedPlatform
4. Consequence
5. Weakness (for cross-reference only)

**MUST EXTRACT:**
- Weakness (cwe_id, name, description, severity)
- At least 1 Mitigation
- All Related Weaknesses (PARENT_OF, CHILD_OF, RELATED_TO)

**RELATIONSHIPS (ưu tiên cao):**
- MITIGATED_BY, AFFECTS, HAS_CONSEQUENCE, RELATED_TO, PARENT_OF, CHILD_OF
- Always create relations even if target not in current chunk.

**JSON SCHEMA:**
{
  "entities": [...],
  "relations": [...]
}
**CRITICAL:** Return ONLY valid JSON. Aim for maximum connectivity.
"""

        user_content = f"CWE XML Chunk {chunk_id}:\n\n{chunk_text[:2200]}"

        response = await self.client.chat(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
            format="json",
            options={"temperature": 0.0, "num_ctx": 8192, "num_predict": 3072}
        )

        return await self._process_llm_response(response, chunk_id, source_type="cwe_xml")

    # ====================== CVE / NVD EXTRACTION ======================
    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=5, max=40))
    async def extract_entities_and_relations_from_cve(self, chunk_text: str, chunk_id: int) -> ExtractionResult:
        """Extract từ CVE/NVD JSON."""
        system_prompt = """
You are a Security Knowledge Graph expert specializing in NVD/CVE.

**MISSION:** Extract Vulnerability and link strongly to CWE, products, mitigations.

**CORE ENTITY TYPES:**
1. Vulnerability
2. AffectedProduct / CPE
3. CWE (weakness)
4. Mitigation

**KEY RELATIONSHIPS:**
- HAS_WEAKNESS (Vulnerability → CWE)
- IMPACTS / AFFECTS (Vulnerability → AffectedProduct)
- RESOLVED_BY / MITIGATED_BY
- HAS_CONSEQUENCE

**STRATEGY:** Create cross-references aggressively (e.g. to CWE-79 even if not in chunk).

Return ONLY JSON.
"""

        user_content = f"CVE/NVD Chunk {chunk_id}:\n\n{chunk_text[:2200]}"

        response = await self.client.chat(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
            format="json",
            options={"temperature": 0.0, "num_ctx": 8192, "num_predict": 3072}
        )

        return await self._process_llm_response(response, chunk_id, source_type="cve_json")

    # ====================== NMAP EXTRACTION (Mới) ======================
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=30))
    async def extract_from_nmap(self, chunk_text: str, chunk_id: int) -> ExtractionResult:
        """Extract Host & Service từ Nmap output (XML/JSON)."""
        system_prompt = """
You are a Network Security Graph expert. Parse Nmap output.

**ENTITIES:**
- Host (ip, hostname, os)
- Service (port, name, product, version, cpe)

**RELATIONSHIPS:**
- Host --HAS_SERVICE--> Service
- Service --POTENTIALLY_VULNERABLE_TO--> Vulnerability (nếu vulners script có CVE)
- Service --MATCHES_CPE--> AffectedProduct

Return ONLY JSON with entities + relations. Use id format: host-10.0.0.1, service-tcp-80-nginx.
"""

        user_content = f"Nmap output chunk {chunk_id}:\n\n{chunk_text[:3000]}"

        response = await self.client.chat(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
            format="json",
            options={"temperature": 0.1, "num_ctx": 8192}
        )

        return await self._process_llm_response(response, chunk_id, source_type="nmap")

    # ====================== COMMON PROCESSOR ======================
    async def _process_llm_response(self, response, chunk_id: int, source_type: str) -> ExtractionResult:
        raw_output = response['message']['content'].strip()
        logger.info(f"Raw LLM output received [{source_type}]", chunk_id=chunk_id, length=len(raw_output))

        try:
            parsed = self._safe_json_loads(raw_output)

            # === STRONG POST-PROCESSING & FIXES ===
            for e in parsed.get("entities", []):
                # ID standardization
                if not e.get("id"):
                    e["id"] = str(uuid.uuid4())[:12]

                # Name fallback
                if not e.get("name"):
                    e["name"] = (e.get("cwe_id") or e.get("cve_id") or 
                                e.get("name") or e.get("product_name") or "unknown")

                # Type normalization
                if not e.get("type"):
                    name_lower = str(e.get("name", "")).lower()
                    if "cwe" in name_lower or "weakness" in name_lower:
                        e["type"] = "Weakness"
                    elif "cve" in name_lower:
                        e["type"] = "Vulnerability"
                    elif "host" in name_lower or "ip" in name_lower:
                        e["type"] = "Host"
                    elif any(x in name_lower for x in ["service", "port", "nginx", "apache"]):
                        e["type"] = "Service"
                    elif "mitigation" in name_lower or "fix" in name_lower:
                        e["type"] = "Mitigation"
                    elif "product" in name_lower or "cpe" in name_lower:
                        e["type"] = "AffectedProduct"
                    else:
                        e["type"] = "Weakness" if source_type == "cwe_xml" else "Vulnerability"

                # Provenance
                if not e.get("provenance"):
                    e["provenance"] = {
                        "source_type": source_type,
                        "chunk_id": chunk_id,
                        "confidence": 0.90
                    }

            # Fix relations
            for r in parsed.get("relations", []):
                if 'source' in r and 'source_id' not in r:
                    r['source_id'] = r.pop('source')
                if 'target' in r and 'target_id' not in r:
                    r['target_id'] = r.pop('target')

                r.setdefault("type", "RELATED_TO")
                if not r.get("provenance"):
                    r["provenance"] = {"source_type": source_type, "chunk_id": chunk_id, "confidence": 0.85}

            result = ExtractionResult(
                entities=[Entity(**e) for e in parsed.get("entities", [])],
                relations=[Relation(**r) for r in parsed.get("relations", [])],
                raw_llm_output=raw_output,
                chunk_id=chunk_id
            )

            logger.info(f"✅ Extraction successful [{source_type}]", 
                       chunk_id=chunk_id, 
                       entities=len(result.entities),
                       relations=len(result.relations))
            return result

        except Exception as e:
            logger.error(f"Processing failed [{source_type}]", chunk_id=chunk_id, error=str(e))
            return ExtractionResult(error=str(e), chunk_id=chunk_id)

    def _repair_json(self, raw: str) -> str:
        """JSON repair robust hơn."""
        raw = re.sub(r'^```json\s*|\s*```$', '', raw.strip(), flags=re.MULTILINE)
        raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', raw)

        # Fix common issues
        raw = re.sub(r'(}\s*)\n(\s*")', r'\1,\n\2', raw)
        raw = re.sub(r',(\s*[}\]])', r'\1', raw)

        if not raw.startswith('{'):
            raw = '{' + raw
        if not raw.endswith('}'):
            raw = raw + '}'

        return raw

    # Raw completion helper
    async def _raw_completion(self, prompt: str, temperature: float = 0.0) -> str:
        response = await self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": temperature, "num_ctx": 8192}
        )
        return response['message']['content'] or ""