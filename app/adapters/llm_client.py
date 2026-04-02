"""LLM Adapter cho Ollama - sử dụng AsyncClient chính thức (fix TypeError)."""

import ollama
from ollama import AsyncClient
import json
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config.settings import settings
from app.core.logger import logger
from app.domain.schemas.extraction import ExtractionResult

class LLMClient:
    def __init__(self):
        self.client = AsyncClient(host=settings.OLLAMA_BASE_URL.rstrip("/"))
        self.model = settings.OLLAMA_MODEL

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=30))
    async def extract_entities_and_relations(self, chunk_text: str, chunk_id: int) -> ExtractionResult:
        """Gọi Ollama async với JSON mode + structured output."""
        system_prompt = """
Bạn là chuyên gia bảo mật và penetration testing. 
Hãy trích xuất entities và relations từ text sau theo ontology GraphRAG Pentest.
Entities: Asset, Host, IP, Domain, URL, Service, Application, APIEndpoint, Vulnerability, CVE, CWE, TTP, Credential, Finding, Evidence, Remediation, Tool, Report.
Relations: AFFECTS, HOSTED_ON, EXPOSES, HAS_VULN, LINKED_TO_CVE, CONFIRMED_BY, OBSERVED_IN, REMEDIATED_BY, REACHABLE_VIA, DEPENDS_ON, EXPLOITS, POST_EXPLOIT, GENERATED_BY, DESCRIBED_IN.

Trả về JSON sạch theo format sau, không thêm bất kỳ text nào ngoài JSON:
{
  "entities": [
    {"id": "...", "type": "Host", "name": "...", "properties": {...}}
  ],
  "relations": [
    {"id": "...", "type": "HAS_VULN", "source_id": "...", "target_id": "...", "properties": {...}}
  ]
}
"""

        user_content = f"Text cần phân tích (chunk {chunk_id}):\n\n{chunk_text[:3500]}"

        try:
            response = await self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                format="json",           # Bắt buộc JSON mode
                options={"temperature": 0.0, "num_ctx": 8192, "num_predict": 2048}
            )

            raw_output = response['message']['content'].strip()

            # Parse JSON
            parsed = json.loads(raw_output)

            result = ExtractionResult(
                entities=[ExtractionResult.model_fields['entities'].annotation.__args__[0](**e) for e in parsed.get("entities", [])],
                relations=[ExtractionResult.model_fields['relations'].annotation.__args__[0](**r) for r in parsed.get("relations", [])],
                raw_llm_output=raw_output,
                chunk_id=chunk_id
            )

            logger.info("LLM extraction successful", 
                       chunk_id=chunk_id, 
                       entities_count=len(result.entities),
                       relations_count=len(result.relations))
            return result

        except json.JSONDecodeError as je:
            logger.error("LLM returned invalid JSON", chunk_id=chunk_id, raw=raw_output[:500] if 'raw_output' in locals() else None)
            return ExtractionResult(error=f"Invalid JSON from LLM: {str(je)}", chunk_id=chunk_id, raw_llm_output=raw_output if 'raw_output' in locals() else None)

        except Exception as e:
            logger.error("LLM extraction failed", chunk_id=chunk_id, error_type=type(e).__name__, error=str(e))
            raise  # Để retry mechanism hoạt động