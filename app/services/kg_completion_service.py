"""KG Completion Service - Phase 11: LLM-based relation prediction & fact correction."""

import json
import re
from typing import Dict, List, Optional

from app.adapters.neo4j_client import Neo4jAdapter
from app.adapters.llm_client import LLMClient
from app.core.logger import logger
from app.core.security import audit_log

def _min_confidence() -> float:
    from app.config.settings import settings
    return getattr(settings, "KG_MIN_CONFIDENCE", 0.65)

# Known security relation types that the LLM can predict
_VALID_REL_TYPES = {
    "MITIGATED_BY", "HAS_CONSEQUENCE", "AFFECTS", "IMPACTS", "TARGETS",
    "RELATED_TO", "CHILD_OF", "PARENT_OF", "MAPPED_TO", "REFERENCES",
    "DETECTABLE_BY", "PRECEDES", "ENABLES", "REQUIRES",
    "HAS_PORT", "RUNS_SERVICE", "EXPOSES", "HOSTED_ON",
    "CORRELATES_TO", "CLASSIFIED_AS",
}

_PREDICTION_PROMPT = """You are a cybersecurity knowledge graph expert.
Given a source entity and a list of candidate target entities, predict plausible
security relationships between the source and the candidates.

Source entity:
  id: {source_id}
  type: {source_label}
  name: {source_name}

Candidate targets (id | type | name):
{candidates_text}

Valid relationship types:
{valid_types}

Return a JSON array of predictions. Each prediction:
{{
  "target_id": "<candidate id>",
  "rel_type": "<one of the valid types>",
  "confidence": <0.0-1.0>,
  "rationale": "<one sentence>"
}}

Rules:
- Only predict relations that make semantic sense in a security context.
- Only include confidence >= 0.65.
- Return an empty array [] if no plausible relations exist.
- Return ONLY the JSON array, no other text.
"""

_CONFLICT_PROMPT = """You are a cybersecurity knowledge graph auditor.
Review the following set of relations connected to a single entity and identify
any logical contradictions or suspicious facts.

Entity: {entity_id} ({entity_label}) — "{entity_name}"

Connected relations:
{relations_text}

Return a JSON array of conflicts found (empty array if none):
[
  {{
    "rel_type": "<relation type>",
    "target_id": "<target id>",
    "issue": "<one-sentence explanation of the contradiction>",
    "severity": "high" | "medium" | "low"
  }}
]

Return ONLY the JSON array.
"""


class KGCompletionService:
    """
    Phase 11 — Knowledge Graph Completion.

    Two capabilities:
    1. predict_and_store(): For low-degree entities, use the LLM to predict
       missing relations and write them to Neo4j with inferred=True flag.
    2. detect_conflicts(): Audit entities for contradictory/suspicious relations.
    """

    def __init__(self):
        self.neo4j = Neo4jAdapter()
        self.llm = LLMClient()

    # ---------------------------------------------------------------- public

    async def complete_graph(
        self,
        max_entities: int = 10,
        max_degree: int = 2,
    ) -> Dict:
        """
        Full KG-completion pass.
        Returns stats: entities_processed, relations_predicted, relations_stored.
        """
        logger.info("KG Completion: starting", max_entities=max_entities, max_degree=max_degree)

        low_degree = await self.neo4j.get_low_degree_entities(max_degree=max_degree, limit=max_entities)
        if not low_degree:
            return {"entities_processed": 0, "relations_predicted": 0, "relations_stored": 0}

        candidate_pool = await self.neo4j.get_entity_sample_for_completion(limit=60)

        total_predicted = 0
        total_stored = 0

        for entity_row in low_degree:
            entity_id = entity_row.get("id") or ""
            if not entity_id:
                continue

            predictions = await self._predict_relations(entity_row, candidate_pool)
            total_predicted += len(predictions)

            for pred in predictions:
                result = await self.neo4j.upsert_inferred_relation(
                    source_id=entity_id,
                    target_id=pred["target_id"],
                    rel_type=pred["rel_type"],
                    confidence=pred["confidence"],
                )
                if result.get("success"):
                    total_stored += 1

        logger.info(
            "KG Completion: done",
            entities=len(low_degree),
            predicted=total_predicted,
            stored=total_stored,
        )
        await audit_log("kg_completion", {
            "entities_processed": len(low_degree),
            "relations_predicted": total_predicted,
            "relations_stored": total_stored,
        })

        return {
            "entities_processed": len(low_degree),
            "relations_predicted": total_predicted,
            "relations_stored": total_stored,
        }

    async def detect_conflicts(self, entity_ids: Optional[List[str]] = None, limit: int = 20) -> List[Dict]:
        """
        Audit entities for contradictory or suspicious relations.
        Returns a list of conflict dicts (empty if none found).
        """
        if entity_ids is None:
            sample = await self.neo4j.get_entity_sample_for_completion(limit=limit)
            entity_ids = [e["id"] for e in sample if e.get("id")]

        all_conflicts: List[Dict] = []
        for eid in entity_ids[:limit]:
            neighbors = await self.neo4j.get_entity_neighbors(eid, hops=1)
            if len(neighbors) < 2:
                continue

            conflicts = await self._audit_entity_relations(eid, neighbors)
            all_conflicts.extend(conflicts)

        logger.info("KG conflict detection done", conflicts_found=len(all_conflicts))
        await audit_log("kg_conflict_detection", {"conflicts": len(all_conflicts)})
        return all_conflicts

    # ---------------------------------------------------------------- private

    async def _predict_relations(
        self,
        entity_row: Dict,
        candidate_pool: List[Dict],
    ) -> List[Dict]:
        entity_id = entity_row.get("id", "?")
        labels = entity_row.get("labels") or []
        label = labels[0] if labels else "Unknown"
        props = entity_row.get("props") or {}
        name = props.get("name", entity_id)

        # Exclude self from candidates
        candidates = [c for c in candidate_pool if c.get("id") != entity_id][:30]
        if not candidates:
            return []

        candidates_text = "\n".join(
            f"  {c.get('id','?')} | {c.get('label','?')} | {c.get('name','?')}"
            for c in candidates
        )
        valid_types_text = ", ".join(sorted(_VALID_REL_TYPES))

        prompt = _PREDICTION_PROMPT.format(
            source_id=entity_id,
            source_label=label,
            source_name=name,
            candidates_text=candidates_text,
            valid_types=valid_types_text,
        )

        try:
            raw = await self.llm._raw_completion(prompt)
            predictions = self._parse_predictions(raw, entity_id)
            logger.debug("KG predictions", entity=entity_id, count=len(predictions))
            return predictions
        except Exception as exc:
            logger.warning("KG prediction failed", entity=entity_id, error=str(exc))
            return []

    async def _audit_entity_relations(self, entity_id: str, neighbors: List[Dict]) -> List[Dict]:
        sample = await self.neo4j.get_entity_sample_for_completion(limit=1)
        entity_info = next((e for e in sample if e.get("id") == entity_id), {})

        relations_text = "\n".join(
            f"  -[{n.get('last_rel_type','?')}]-> {n.get('id','?')} ({n.get('labels',['?'])[0] if n.get('labels') else '?'}): {(n.get('props') or {}).get('name','?')}"
            for n in neighbors[:15]
        )

        prompt = _CONFLICT_PROMPT.format(
            entity_id=entity_id,
            entity_label=(entity_info.get("label") or "Unknown"),
            entity_name=(entity_info.get("name") or entity_id),
            relations_text=relations_text,
        )

        try:
            raw = await self.llm._raw_completion(prompt)
            conflicts = self._parse_json_array(raw)
            for c in conflicts:
                c["entity_id"] = entity_id
            return conflicts
        except Exception as exc:
            logger.warning("Conflict audit failed", entity=entity_id, error=str(exc))
            return []

    # --------------------------------------------------------------- parsers

    def _parse_predictions(self, raw: str, source_id: str) -> List[Dict]:
        items = self._parse_json_array(raw)
        valid = []
        for item in items:
            tid = str(item.get("target_id", "")).strip()
            rtype = str(item.get("rel_type", "")).strip().upper()
            conf = float(item.get("confidence", 0.0))

            if not tid or not rtype:
                continue
            if rtype not in _VALID_REL_TYPES:
                continue
            if conf < _min_confidence():
                continue
            if tid == source_id:
                continue

            valid.append({"target_id": tid, "rel_type": rtype, "confidence": conf})
        return valid

    @staticmethod
    def _parse_json_array(raw: str) -> List[Dict]:
        """Extract first JSON array from raw LLM output."""
        raw = raw.strip()
        # Strip markdown fences
        raw = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
        # Find first '[' ... ']'
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1:
            return []
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return []
