"""Collection Service - Phase 10: Nmap scan → normalize → store in Knowledge Graph."""

from typing import Dict, List, Optional

from app.adapters.nmap_adapter import NmapAdapter
from app.adapters.neo4j_client import Neo4jAdapter
from app.core.logger import logger
from app.core.security import audit_log
from app.domain.schemas.extraction import Entity, Relation


class CollectionService:
    """Orchestrate: run Nmap → parse output → upsert entities/relations to Neo4j."""

    @property
    def DEFAULT_OPTIONS(self) -> list:
        """Nmap options from settings (comma-separated string → list)."""
        from app.config.settings import settings
        raw = getattr(settings, "NMAP_OPTIONS", "-sV,--top-ports,1000")
        return [o.strip() for o in raw.split(",") if o.strip()]

    def __init__(self):
        self.nmap = NmapAdapter()
        self.neo4j = Neo4jAdapter()

    # ---------------------------------------------------------------- public API

    async def collect_and_store(
        self,
        target: str,
        nmap_options: Optional[List[str]] = None,
    ) -> Dict:
        """Full pipeline: scan target → parse → upsert to graph.

        Returns a summary dict with counts of what was discovered and stored.
        Raises PermissionError if target is not whitelisted.
        """
        options = nmap_options if nmap_options is not None else self.DEFAULT_OPTIONS
        logger.info("CollectionService: start", target=target, options=options)

        entities, relations = await self.nmap.scan_and_parse(target, options)

        if not entities:
            logger.warning("No hosts found (all down or filtered)", target=target)
            await audit_log("collection_empty", {"target": target})
            return self._empty_result(target)

        store_result = await self.neo4j.upsert_entities_and_relations(entities, relations)

        summary = NmapAdapter.summarise(entities, relations)
        summary.update(
            {
                "target": target,
                "entities_upserted": store_result.get("entities_upserted", 0),
                "relations_created": store_result.get("relations_created", 0),
                "new_findings_count": len(entities),
            }
        )

        logger.info("CollectionService: done", **{k: v for k, v in summary.items() if k != "host_ips"})
        await audit_log("collection_complete", {"target": target, "entities": len(entities)})

        return summary

    async def collect_from_file(self, xml_path: str) -> Dict:
        """Parse an existing Nmap XML file and store results (no live scan)."""
        logger.info("CollectionService: parsing file", path=xml_path)

        entities, relations = await self.nmap.parse_file(xml_path)

        if not entities:
            return self._empty_result(xml_path)

        store_result = await self.neo4j.upsert_entities_and_relations(entities, relations)

        summary = NmapAdapter.summarise(entities, relations)
        summary.update(
            {
                "target": xml_path,
                "entities_upserted": store_result.get("entities_upserted", 0),
                "relations_created": store_result.get("relations_created", 0),
                "new_findings_count": len(entities),
            }
        )

        await audit_log("collection_from_file", {"path": xml_path, "entities": len(entities)})
        return summary

    async def collect_from_xml_string(self, xml_data: str, label: str = "raw-xml") -> Dict:
        """Parse raw Nmap XML string and store results."""
        entities, relations = self.nmap.parse_xml(xml_data)

        if not entities:
            return self._empty_result(label)

        store_result = await self.neo4j.upsert_entities_and_relations(entities, relations)

        summary = NmapAdapter.summarise(entities, relations)
        summary.update(
            {
                "target": label,
                "entities_upserted": store_result.get("entities_upserted", 0),
                "relations_created": store_result.get("relations_created", 0),
                "new_findings_count": len(entities),
            }
        )

        await audit_log("collection_from_xml", {"label": label, "entities": len(entities)})
        return summary

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _empty_result(target: str) -> Dict:
        return {
            "target": target,
            "hosts": 0,
            "open_ports": 0,
            "services": 0,
            "relations": 0,
            "entities_upserted": 0,
            "relations_created": 0,
            "new_findings_count": 0,
            "host_ips": [],
            "service_names": [],
        }
