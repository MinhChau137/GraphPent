"""LLM Adapter cho Ollama - CWE XML v4 (fix missing 'type' error)."""

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

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=5, max=40))
    async def extract_entities_and_relations(self, chunk_text: str, chunk_id: int) -> ExtractionResult:
        """Extraction CWE XML - fix missing 'type'."""

        system_prompt = """
You are a Security Knowledge Graph expert specializing in MITRE CWE XML analysis.

Task: Extract entities and relations from CWE XML, focusing on vulnerability types with meaningful names.

**MANDATORY RULES:**
- Every entity MUST have 4 fields: id, type, name, provenance
- type must be one of: Weakness, Mitigation, Consequence, DetectionMethod, Platform, Phase, Reference, Example, VulnerabilityType
- For VulnerabilityType entities: Extract specific vulnerability types like "SQL Injection", "Cross-Site Scripting (XSS)", "Buffer Overflow" from the CWE descriptions. Create meaningful names like "SQL Injection Vulnerability" instead of just CWE IDs.
- Do not create entities for empty values or "n/a"
- ID must be stable: cwe-1007, mitigation-cwe-1007-1, vulnerability-sql-injection, ...

Return ONLY clean JSON in this schema, no other text:
{
  "entities": [
    {
      "id": "...",
      "type": "VulnerabilityType",
      "name": "SQL Injection Vulnerability",
      "properties": { ... },
      "provenance": { ... }
    }
  ],
  "relations": [ ... ]
}
"""

        user_content = f"CWE XML chunk {chunk_id}:\n\n{chunk_text[:2000]}"

        try:
            response = await self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                format="json",
                options={"temperature": 0.0, "num_ctx": 16384, "num_predict": 4096}
            )

            raw_output = response['message']['content'].strip()
            logger.info("Raw LLM output received", chunk_id=chunk_id, raw_length=len(raw_output))
            
            try:
                parsed = json.loads(self._repair_json(raw_output))
                logger.info("JSON parsed successfully", chunk_id=chunk_id)

                # === STRONG FALLBACK ===
                for e in parsed.get("entities", []):
                    # Fix ID
                    if not e.get("id"):
                        e["id"] = str(uuid.uuid4())

                    # Fix name
                    if not e.get("name"):
                        e["name"] = e.get("Name") or e.get("value") or f"unknown-entity"

                    # FIX TYPE (rất quan trọng)
                    if not e.get("type"):
                        name_lower = str(e.get("name", "")).lower()
                        if "weakness" in name_lower or e.get("ID") or "cwe" in name_lower:
                            e["type"] = "Weakness"
                        elif "mitigation" in name_lower:
                            e["type"] = "Mitigation"
                        elif "consequence" in name_lower:
                            e["type"] = "Consequence"
                        elif "detection" in name_lower:
                            e["type"] = "DetectionMethod"
                        elif "platform" in name_lower or "technology" in name_lower:
                            e["type"] = "Platform"
                        elif "vulnerability" in name_lower or "injection" in name_lower or "xss" in name_lower or "overflow" in name_lower:
                            e["type"] = "VulnerabilityType"
                        else:
                            e["type"] = "Weakness"  # default an toàn nhất

                    # Provenance
                    if not e.get("provenance") or isinstance(e.get("provenance"), str):
                        e["provenance"] = {
                            "source_type": "cwe_xml",
                            "source_field": "Weakness",
                            "confidence": 0.92,
                            "xml_element_id": f"chunk_{chunk_id}"
                        }

                # Fix relations
                for r in parsed.get("relations", []):
                    if 'source' in r and 'source_id' not in r:
                        r['source_id'] = r.pop('source')
                    if 'target' in r and 'target_id' not in r:
                        r['target_id'] = r.pop('target')
                    if 'source_id' not in r:
                        r['source_id'] = str(uuid.uuid4())
                    if 'target_id' not in r:
                        r['target_id'] = str(uuid.uuid4())
                    
                    # Fix type field - LLM might return 'relation_type' instead of 'type'
                    if 'relation_type' in r and 'type' not in r:
                        r['type'] = r.pop('relation_type')
                    if 'type' not in r:
                        r['type'] = 'RelatedTo'  # default relation type

                    if not r.get("provenance"):
                        r["provenance"] = {
                            "source_type": "cwe_xml",
                            "source_field": "Related_Weaknesses",
                            "confidence": 0.85,
                            "xml_element_id": f"chunk_{chunk_id}"
                        }

                logger.info("Creating ExtractionResult", chunk_id=chunk_id, entities_count=len(parsed.get("entities", [])), relations_count=len(parsed.get("relations", [])))
                result = ExtractionResult(
                    entities=[Entity(**e) for e in parsed.get("entities", [])],
                    relations=[Relation(**r) for r in parsed.get("relations", [])],
                    raw_llm_output=raw_output,
                    chunk_id=chunk_id
                )

                logger.info("✅ Extraction successful", 
                           chunk_id=chunk_id, 
                           entities_count=len(result.entities),
                           relations_count=len(result.relations))
                return result
            except NameError as e:
                logger.error("NameError in LLM processing", error=str(e), raw_sample=raw_output[:500])
                return ExtractionResult(error=f"NameError: {str(e)}", chunk_id=chunk_id)
            except Exception as inner_e:
                logger.error("Inner exception in LLM processing", error=str(inner_e), error_type=type(inner_e).__name__, raw_sample=raw_output[:500])
                return ExtractionResult(error=f"Inner error: {str(inner_e)}", chunk_id=chunk_id)

        except Exception as e:
            logger.error("LLM extraction failed", chunk_id=chunk_id, error=str(e), error_type=type(e).__name__)
            return ExtractionResult(error=str(e), chunk_id=chunk_id)

    def _repair_json(self, raw: str) -> str:
        raw = re.sub(r'^```json\s*|\s*```$', '', raw.strip(), flags=re.MULTILINE).strip()
        if not raw.startswith('{'):
            raw = '{' + raw
        if not raw.endswith('}'):
            raw = raw + '}'
        return raw