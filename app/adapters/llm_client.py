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

    def _safe_json_loads(self, raw_output: str) -> dict:
        repaired = self._repair_json(raw_output)

        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', repaired)
            sanitized = re.sub(r'\t', ' ', sanitized)
            return json.loads(sanitized)
    
    def _detect_data_type(self, chunk_text: str) -> str:
        """Detect if chunk contains CWE XML or CVE JSON data."""
        text_lower = chunk_text.lower()
        if "cwe-" in text_lower or "weakness" in text_lower or "<weakness" in text_lower:
            return "cwe"
        elif "cve-" in text_lower or "cvss" in text_lower or "affected" in text_lower:
            return "cve"
        else:
            return "generic"

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=5, max=40))
    async def extract_entities_and_relations(self, chunk_text: str, chunk_id: int) -> ExtractionResult:
        """Extraction CWE XML - Optimized v2 with quality focus."""

        system_prompt = """
You are a Security Knowledge Graph expert specializing in MITRE CWE XML analysis.

**MISSION:** Extract high-quality weakness entities AND their relationships. Balance accuracy with graph connectivity.

---
## CORE ENTITY TYPES (4 types ONLY)
1. **Weakness** - Security vulnerability pattern (CWE-based)
2. **Mitigation** - Recommended fix/prevention strategy
3. **AffectedPlatform** - Technology/language vulnerable to this weakness
4. **Consequence** - Measurable impact (only if severe/clear)

---
## EXTRACTION PRIORITY
**PRIORITY 1 - MUST EXTRACT:** Weakness (clear name + CWE-ID + description) + ≥1 Mitigation + relationships
**PRIORITY 2 - EXTRACT IF CLEAR:** Affected platforms, consequences, more relationships
**PRIORITY 3 - SKIP:** Generic descriptions, examples, empty values

---
## RELATIONSHIP TYPES & EXTRACTION
Extract ALL meaningful relationships:

**MITIGATED_BY**: Weakness → Mitigation
- When text says "mitigation is...", "fix is...", "prevent by...", etc.
- HIGH CONFIDENCE (0.85-0.95)
- Example: SQL Injection --MITIGATED_BY--> Use parameterized queries

**AFFECTS**: Weakness → AffectedPlatform  
- When text mentions "affects Java", "vulnerable in Web servers", etc.
- MEDIUM CONFIDENCE (0.75-0.85)
- Example: CWE-89 --AFFECTS--> Web Applications

**HAS_CONSEQUENCE**: Weakness → Consequence
- When text describes impact/consequence
- MEDIUM-HIGH CONFIDENCE (0.75-0.90)
- Example: SQL Injection --HAS_CONSEQUENCE--> Data Breach

**RELATED_TO**: Weakness → Weakness (cross-references)
- When text says "similar to CWE-X", "variant of", etc.
- MEDIUM CONFIDENCE (0.75-0.80)
- Example: CWE-89 --RELATED_TO--> CWE-90

**EXTRACTION STRATEGY:** Create relations even if target entity not in this chunk!
- If text references "CWE-X" mitigation but CWE-X not extracted here, still create relation to "cwe-X"
- System will link external entities during graph build
- Enable cross-chunk connectivity

---
## PROPERTIES SCHEMA (Required by type)
**Weakness:** cwe_id, description, severity_level (high|medium|low), attack_vector (network|local|adjacent)
**Mitigation:** title, description, effectiveness_level (high|medium|low)
**AffectedPlatform:** platform_name, technology_type (Java|PHP|C/C++|etc)

---
## CONFIDENCE RULES
**Entity Confidence:**
✓ Confidence >= 0.85: Descriptive name, ≥2 properties, clear data
✓ Confidence < 0.80: Reject (too low quality)

**Relation Confidence:**
✓ Confidence >= 0.75: Acceptable (even if cross-chunk)
✓ Confidence < 0.75: Reject

---
## JSON SCHEMA (MAXIMIZING RELATIONS)
{
  "entities": [
    {"id": "cwe-89", "type": "Weakness", "name": "SQL Injection", "properties": {...}, "provenance": {"source_type": "cwe_xml", "confidence": 0.95}},
    {"id": "mit-param", "type": "Mitigation", "name": "Parameterized Queries", "properties": {...}, "provenance": {"source_type": "cwe_xml", "confidence": 0.90}},
    {"id": "platform-web", "type": "AffectedPlatform", "name": "Web Applications", "properties": {...}, "provenance": {"source_type": "cwe_xml", "confidence": 0.85}}
  ],
  "relations": [
    {"id": "rel-1", "type": "MITIGATED_BY", "source_id": "cwe-89", "target_id": "mit-param", "provenance": {"source_type": "cwe_xml", "confidence": 0.92}},
    {"id": "rel-2", "type": "AFFECTS", "source_id": "cwe-89", "target_id": "platform-web", "provenance": {"source_type": "cwe_xml", "confidence": 0.88}},
    {"id": "rel-3", "type": "RELATED_TO", "source_id": "cwe-89", "target_id": "cwe-90", "provenance": {"source_type": "cwe_xml", "confidence": 0.75}}
  ]
}

**CRITICAL:** Return ONLY JSON! Extract ALL entities and relations you can identify. Aim for ≥1 relation per entity!
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
                options={"temperature": 0.0, "num_ctx": 4096, "num_predict": 2048}
            )

            raw_output = response['message']['content'].strip()
            logger.info("Raw LLM output received", chunk_id=chunk_id, raw_length=len(raw_output))
            
            try:
                parsed = self._safe_json_loads(raw_output)
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
                    if r.get('source_id') is None or str(r.get('source_id')).strip() == '':
                        r['source_id'] = str(uuid.uuid4())
                    if r.get('target_id') is None or str(r.get('target_id')).strip() == '':
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
        """Robust JSON repair handling complex malformations."""
        # Remove markdown code blocks
        raw = re.sub(r'^```json\s*|\s*```$', '', raw.strip(), flags=re.MULTILINE).strip()

        def escape_control_chars(text: str) -> str:
            fixed = []
            in_string = False
            escape_next = False

            for char in text:
                if escape_next:
                    fixed.append(char)
                    escape_next = False
                    continue

                if char == '\\' and in_string:
                    fixed.append(char)
                    escape_next = True
                    continue

                if char == '"':
                    in_string = not in_string
                    fixed.append(char)
                    continue

                if in_string:
                    if char == '\n':
                        fixed.append('\\n')
                        continue
                    if char == '\r':
                        fixed.append('\\r')
                        continue
                    if char == '\t':
                        fixed.append('\\t')
                        continue
                    if ord(char) < 0x20:
                        fixed.append(f'\\u{ord(char):04x}')
                        continue

                fixed.append(char)

            return ''.join(fixed)

        raw = escape_control_chars(raw)
        
        # Strategy 1: Try to find and close unterminated strings
        in_string = False
        escape_next = False
        fixed = []
        
        for i, char in enumerate(raw):
            if escape_next:
                fixed.append(char)
                escape_next = False
                continue
            
            if char == '\\' and in_string:
                fixed.append(char)
                escape_next = True
                continue
            
            if char == '"':
                in_string = not in_string
            
            fixed.append(char)
        
        raw = ''.join(fixed)
        
        # Strategy 2: If string is still open, try to close it intelligently
        if in_string:
            # Find the last complete value (} or ]) and insert quote before it
            for end_char in ['}', ']', ',']:
                last_idx = raw.rfind(end_char)
                if last_idx > 0:
                    raw = raw[:last_idx] + '"' + raw[last_idx:]
                    in_string = False
                    break
            if in_string:
                raw = raw + '"'
        
        # Strategy 3: Fix missing commas between properties
        # Look for patterns like: "}\\n  \"" and ensure comma exists
        raw = re.sub(r'("\s*)\n(\s*")', r'\1,\n\2', raw)
        raw = re.sub(r'(}\s*)\n(\s*")', r'\1,\n\2', raw)
        
        # Strategy 4: Remove any trailing commas before closing braces/brackets
        raw = re.sub(r',(\s*[}\]])', r'\1', raw)
        
        # Strategy 5: Add outer braces if missing
        if not raw.startswith('{'):
            raw = '{' + raw
        if not raw.endswith('}'):
            raw = raw + '}'
        
        return raw

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=5, max=40))
    async def extract_entities_and_relations_from_cve(self, chunk_text: str, chunk_id: int) -> ExtractionResult:
        """Extraction CVE (NVD or v5 format) - Optimized v2 with relation focus."""

        system_prompt = """
You are a Security Knowledge Graph expert specializing in CVE vulnerability intelligence.

**MISSION:** Extract CVE entities AND relationships for graph connectivity. Balance accuracy with graph coverage.

---
## CORE ENTITY TYPES (5 types ONLY)
1. **Vulnerability** - CVE record (cve_id, published_date, cvss_score, cvss_severity, attack_vector, description)
2. **AffectedProduct** - Software/hardware impacted (vendor, product_name, affected_versions, status)
3. **CWE** - Underlying weakness (cwe_id, cwe_name, description)
4. **Mitigation** - Recommended fix/workaround (title, description, patch_version)
5. **Reference** - Information source (url, reference_type) - ONLY if critical

---
## EXTRACTION PRIORITY
**PRIORITY 1 - MUST EXTRACT:** Vulnerability + AffectedProduct + CWE (if mentioned) + relationships
**PRIORITY 2 - EXTRACT IF CLEAR:** Mitigation, more relationships
**PRIORITY 3 - SKIP:** Generic references, conflicting versions

---
## RELATIONSHIP EXTRACTION (MAXIMIZE CONNECTIVITY!)
Create relationships aggressively - allow external references:

**HAS_WEAKNESS**: Vulnerability → CWE
- When CVE mentions "related to CWE-X", "caused by CWE-X", "weakness is..."
- HIGH CONFIDENCE (0.85-0.95)
- Example: CVE-2023-44487 --HAS_WEAKNESS--> CWE-400

**IMPACTS**: Vulnerability → AffectedProduct
- When CVE says "affects Product X", "vulnerable in Version Y"
- HIGH CONFIDENCE (0.85-0.95)
- Example: CVE-2023-44487 --IMPACTS--> Nginx 1.25

**RESOLVED_BY**: Vulnerability → Mitigation
- When text mentions "patched in", "fixed by", "upgrade to"
- MEDIUM-HIGH CONFIDENCE (0.80-0.90)
- Example: CVE-2023-44487 --RESOLVED_BY--> Upgrade to Nginx 1.25.3

**VERSION_OF**: Product → Product
- When text mentions version relationships "version X of Y"
- MEDIUM CONFIDENCE (0.75-0.85)
- Example: Nginx 1.25.3 --VERSION_OF--> Nginx

**STRATEGY:** Create relations to external entities (e.g., CWE-400) even if not in chunk!
- Backend will link entities across chunks
- Enables rich cross-references
- MINIMUM confidence: 0.75

---
## PROPERTIES SCHEMA (Required by type)
**Vulnerability:** cve_id (YYYY-NNNNN), description, cvss_score (0-10), cvss_severity (LOW|MEDIUM|HIGH|CRITICAL), attack_vector (NETWORK|LOCAL|PHYSICAL), published_date (YYYY-MM-DD)
**AffectedProduct:** vendor, product_name, affected_versions (array), status (vulnerable|patched), patched_version
**CWE:** cwe_id (CWE-NNNNN), cwe_name, description

---
## ENTITY CONFIDENCE RULES
**High Confidence (0.85-0.95):**
✓ All required properties present
✓ Specific identifiers (CVE-YYYY-NNNNN, CWE-NNNNN)
✓ Clear descriptions

**Reject (< 0.80):**
✗ Missing critical properties
✗ Vague or generic data
✗ Conflicting information

---
## RELATIONSHIP CONFIDENCE RULES
**Confident (0.80-0.95):** Direct mentions, clear cause-effect
**Acceptable (0.75-0.80):** Inferred or indirect references
**Reject (< 0.75):** Too speculative

---
## JSON SCHEMA (MAXIMIZING RELATIONS & CROSS-REFERENCES)
{
  "entities": [
    {"id": "cve-2023-44487", "type": "Vulnerability", "name": "HTTP/2 Rapid Reset", "properties": {...}, "provenance": {"source_type": "cve_json", "confidence": 0.95}},
    {"id": "product-nginx-1.25", "type": "AffectedProduct", "name": "Nginx 1.25.0-1.25.2", "properties": {...}, "provenance": {"source_type": "cve_json", "confidence": 0.93}},
    {"id": "cwe-400", "type": "CWE", "name": "Uncontrolled Resource Consumption", "properties": {...}, "provenance": {"source_type": "cve_json", "confidence": 0.90}}
  ],
  "relations": [
    {"id": "rel-1", "type": "IMPACTS", "source_id": "cve-2023-44487", "target_id": "product-nginx-1.25", "provenance": {"source_type": "cve_json", "confidence": 0.95}},
    {"id": "rel-2", "type": "HAS_WEAKNESS", "source_id": "cve-2023-44487", "target_id": "cwe-400", "provenance": {"source_type": "cve_json", "confidence": 0.92}},
    {"id": "rel-3", "type": "RESOLVED_BY", "source_id": "cve-2023-44487", "target_id": "mitigation-upgrade-nginx", "provenance": {"source_type": "cve_json", "confidence": 0.85}}
  ]
}

**CRITICAL:** Return ONLY JSON! Extract ALL entities and relations. Aim for ≥1 relation per entity. Allow cross-chunk references!
"""

        user_content = f"CVE data chunk {chunk_id}:\n\n{chunk_text[:2000]}"

        try:
            response = await self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                format="json",
                options={"temperature": 0.0, "num_ctx": 4096, "num_predict": 2048}
            )

            raw_output = response['message']['content'].strip()
            logger.info("Raw CVE LLM output received", chunk_id=chunk_id, raw_length=len(raw_output))
            
            try:
                parsed = self._safe_json_loads(raw_output)
                logger.info("CVE JSON parsed successfully", chunk_id=chunk_id)

                # === STRONG FALLBACK for CVE ===
                for e in parsed.get("entities", []):
                    # Fix ID
                    if not e.get("id"):
                        e["id"] = f"cve-{str(uuid.uuid4())[:8]}"

                    # Fix name
                    if not e.get("name"):
                        e["name"] = e.get("cve_id") or e.get("cve") or f"unknown-entity"

                    # FIX TYPE
                    if not e.get("type"):
                        name_lower = str(e.get("name", "")).lower()
                        if "cve-" in name_lower:
                            e["type"] = "Vulnerability"
                        elif "cwe-" in name_lower or "weakness" in name_lower:
                            e["type"] = "CWE"
                        elif "cvss" in name_lower or "score" in name_lower:
                            e["type"] = "CVSS_Score"
                        elif "product" in name_lower or "vendor" in name_lower or "version" in name_lower:
                            e["type"] = "AffectedProduct"
                        elif "mitigation" in name_lower or "fix" in name_lower:
                            e["type"] = "Mitigation"
                        elif "reference" in name_lower or "url" in name_lower:
                            e["type"] = "Reference"
                        else:
                            e["type"] = "Vulnerability"

                    # Provenance
                    if not e.get("provenance") or isinstance(e.get("provenance"), str):
                        e["provenance"] = {
                            "source_type": "cve_json",
                            "source_field": "CVE_Record",
                            "confidence": 0.90,
                            "xml_element_id": f"chunk_{chunk_id}"
                        }

                # Fix relations
                for r in parsed.get("relations", []):
                    if 'source' in r and 'source_id' not in r:
                        r['source_id'] = r.pop('source')
                    if 'target' in r and 'target_id' not in r:
                        r['target_id'] = r.pop('target')
                    if r.get('source_id') is None or str(r.get('source_id')).strip() == '':
                        r['source_id'] = str(uuid.uuid4())
                    if r.get('target_id') is None or str(r.get('target_id')).strip() == '':
                        r['target_id'] = str(uuid.uuid4())
                    
                    if 'relation_type' in r and 'type' not in r:
                        r['type'] = r.pop('relation_type')
                    if 'type' not in r:
                        r['type'] = 'RELATED_TO'

                    if not r.get("provenance"):
                        r["provenance"] = {
                            "source_type": "cve_json",
                            "source_field": "CVE_Relations",
                            "confidence": 0.85,
                            "xml_element_id": f"chunk_{chunk_id}"
                        }

                logger.info("Creating CVE ExtractionResult", chunk_id=chunk_id, entities_count=len(parsed.get("entities", [])), relations_count=len(parsed.get("relations", [])))
                result = ExtractionResult(
                    entities=[Entity(**e) for e in parsed.get("entities", [])],
                    relations=[Relation(**r) for r in parsed.get("relations", [])],
                    raw_llm_output=raw_output,
                    chunk_id=chunk_id
                )

                logger.info("✅ CVE Extraction successful", 
                           chunk_id=chunk_id, 
                           entities_count=len(result.entities),
                           relations_count=len(result.relations))
                return result
            except Exception as inner_e:
                logger.error("Inner exception in CVE LLM processing", error=str(inner_e), error_type=type(inner_e).__name__, raw_sample=raw_output[:500])
                return ExtractionResult(error=f"Inner error: {str(inner_e)}", chunk_id=chunk_id)

        except Exception as e:
            logger.error("CVE LLM extraction failed", chunk_id=chunk_id, error=str(e), error_type=type(e).__name__)

    # ==================== General-purpose completion (Phase 11+) ====================

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=3, max=20))
    async def _raw_completion(self, prompt: str, temperature: float = 0.0) -> str:
        """Send a raw prompt to the LLM and return the response text.
        Used by KGCompletionService and GNNService for open-ended queries.
        """
        response = await self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": temperature},
        )
        return response.message.content or ""