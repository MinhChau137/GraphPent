"""Report Service - Phase 10+ (complete): fetch real data from Neo4j, rank findings."""

from typing import Any, Dict, List, Optional
from datetime import datetime

from app.adapters.neo4j_client import Neo4jAdapter
from app.core.logger import logger
from app.core.security import audit_log

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "unknown": 5}


class ReportService:
    def __init__(self):
        self.neo4j = Neo4jAdapter()

    # ----------------------------------------------------------------- public

    async def generate_markdown_report(self, workflow_result: Dict, query: str) -> str:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        # Fetch live data from graph
        findings = await self._fetch_discovered_vulnerabilities()
        hosts = await self._fetch_hosts()
        cve_stats = await self._fetch_cve_stats()
        graph_stats = await self.neo4j.get_graph_statistics()

        collection = workflow_result.get("collection", {}).get("summary", {})
        retrieval_results = workflow_result.get("retrieval", {}).get("top_results", [])
        tool_results = workflow_result.get("tools", {}).get("findings", [])
        loop_iter = workflow_result.get("loop_iteration", 0)

        findings_sorted = sorted(
            findings,
            key=lambda f: _SEVERITY_ORDER.get(str(f.get("severity", "")).lower(), 5),
        )

        md = f"""# GraphRAG PenTest Report

**Generated**: {now}
**Query**: {query}
**Workflow iterations**: {loop_iter}

---

## 1. Executive Summary

| Metric | Value |
|--------|-------|
| Total graph nodes | {graph_stats.get("total_nodes", 0)} |
| Total relationships | {graph_stats.get("total_relationships", 0)} |
| Hosts discovered | {collection.get("hosts", len(hosts))} |
| Open ports | {collection.get("open_ports", "—")} |
| Services detected | {collection.get("services", "—")} |
| Vulnerabilities found | {len(findings)} |
| CVEs in graph | {cve_stats.get("cve_count", graph_stats.get("cve_count", 0))} |
| CWEs in graph | {cve_stats.get("cwe_count", graph_stats.get("cwe_count", 0))} |

"""

        # Hosts section
        if hosts:
            md += "## 2. Discovered Hosts\n\n"
            md += "| IP | Hostname | OS | Open Ports |\n"
            md += "|----|----------|----|------------|\n"
            for h in hosts[:20]:
                props = h.get("properties", {})
                md += (
                    f"| {props.get('ip', h.get('id', '?'))} "
                    f"| {props.get('hostname', '—')} "
                    f"| {props.get('os', '—')} "
                    f"| {props.get('open_ports', '—')} |\n"
                )
            md += "\n"

        # Findings by severity
        md += "## 3. Vulnerability Findings\n\n"
        if findings_sorted:
            sev_groups: Dict[str, List] = {}
            for f in findings_sorted:
                sev = str(f.get("severity", "unknown")).lower()
                sev_groups.setdefault(sev, []).append(f)

            for sev in ["critical", "high", "medium", "low", "info", "unknown"]:
                group = sev_groups.get(sev, [])
                if not group:
                    continue
                label = sev.upper()
                md += f"### {label} ({len(group)} findings)\n\n"
                for finding in group[:10]:
                    tid = finding.get("template_id", "?")
                    host = finding.get("host", "?")
                    url = finding.get("url", "")
                    cves = ", ".join(finding.get("cve_ids", []) or [])
                    md += f"- **{tid}** on `{host}`"
                    if url:
                        md += f" — `{url}`"
                    if cves:
                        md += f" — CVEs: {cves}"
                    md += "\n"
                md += "\n"
        else:
            md += "_No vulnerability findings recorded in graph._\n\n"

        # Knowledge retrieval summary
        if retrieval_results:
            md += "## 4. Knowledge Context (Top Retrieval)\n\n"
            for res in retrieval_results[:5]:
                res_id = res.get("id", "?")
                score = res.get("final_score", res.get("vector_score", 0))
                md += f"- `{res_id}` (score: {score:.3f})\n"
            md += "\n"

        # Tool results
        nuclei_tool = [t for t in tool_results if t.get("source") == "nuclei"]
        cve_tool = [t for t in tool_results if t.get("cve_id")]
        if cve_tool:
            md += "## 5. CVE Exploitability Analysis\n\n"
            for item in cve_tool[:10]:
                cve_id = item.get("cve_id", "?")
                rec = item.get("recommended_action", "—")
                md += f"- **{cve_id}**: {rec}\n"
            md += "\n"

        # Recommendations
        md += "## 6. Recommendations\n\n"
        recs = self._generate_recommendations(findings_sorted, hosts, cve_stats)
        for rec in recs:
            md += f"- {rec}\n"

        md += f"\n---\n*Generated by GraphRAG Pentest Platform · {now}*"
        await audit_log("report_generated", {"findings": len(findings), "hosts": len(hosts)})
        return md

    @staticmethod
    async def generate_markdown_report_static(workflow_result: Dict, query: str) -> str:
        """Static convenience wrapper — creates a temporary service instance."""
        svc = ReportService()
        return await svc.generate_markdown_report(workflow_result, query)

    async def generate_json_report(self, workflow_result: Dict, query: str) -> Dict:
        findings = await self._fetch_discovered_vulnerabilities()
        hosts = await self._fetch_hosts()
        cve_stats = await self._fetch_cve_stats()
        graph_stats = await self.neo4j.get_graph_statistics()
        markdown = await self.generate_markdown_report(workflow_result, query)

        return {
            "report_id": f"report-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "generated_at": datetime.utcnow().isoformat(),
            "query": query,
            "summary": {
                "hosts_discovered": len(hosts),
                "vulnerabilities_found": len(findings),
                "cves_in_graph": cve_stats.get("cve_count", 0),
                "cwes_in_graph": cve_stats.get("cwe_count", 0),
                "total_graph_nodes": graph_stats.get("total_nodes", 0),
            },
            "findings": findings,
            "hosts": hosts,
            "workflow_state": workflow_result,
            "recommendations": self._generate_recommendations(findings, hosts, cve_stats),
            "markdown": markdown,
            "version": "2.0",
        }

    # -------------------------------------------------------------- Neo4j fetch

    async def _fetch_discovered_vulnerabilities(self) -> List[Dict]:
        try:
            async with self.neo4j.driver.session() as session:
                result = await session.execute_read(self._query_all_findings_tx)
                return result
        except Exception as exc:
            logger.warning("Could not fetch findings from Neo4j", error=str(exc))
            return []

    async def _query_all_findings_tx(self, tx) -> List[Dict]:
        cypher = """
        MATCH (f:DiscoveredVulnerability)
        OPTIONAL MATCH (f)-[:CORRELATES_TO]->(c:CVE)
        OPTIONAL MATCH (f)-[:CLASSIFIED_AS]->(w:CWE)
        RETURN f.id AS id, f.template_id AS template_id,
               f.severity AS severity, f.host AS host,
               f.url AS url, f.matched_at AS matched_at,
               collect(DISTINCT c.id) AS cve_ids,
               collect(DISTINCT w.id) AS cwe_ids
        ORDER BY
          CASE f.severity
            WHEN 'critical' THEN 0 WHEN 'high' THEN 1
            WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4
          END
        LIMIT 200
        """
        result = await tx.run(cypher)
        records = await result.fetch(200)
        return [dict(r) for r in records]

    async def _fetch_hosts(self) -> List[Dict]:
        try:
            async with self.neo4j.driver.session() as session:
                result = await session.execute_read(self._query_hosts_tx)
                return result
        except Exception as exc:
            logger.warning("Could not fetch hosts from Neo4j", error=str(exc))
            return []

    async def _query_hosts_tx(self, tx) -> List[Dict]:
        cypher = """
        MATCH (h:Host)
        OPTIONAL MATCH (h)-[:HAS_PORT]->(p:Port)
        WITH h, count(p) AS open_ports
        RETURN h.id AS id, properties(h) AS properties,
               open_ports
        ORDER BY open_ports DESC
        LIMIT 100
        """
        result = await tx.run(cypher)
        records = await result.fetch(100)
        rows = []
        for r in records:
            d = dict(r)
            if isinstance(d.get("properties"), dict):
                d["properties"]["open_ports"] = d.get("open_ports", 0)
            rows.append(d)
        return rows

    async def _fetch_cve_stats(self) -> Dict:
        try:
            async with self.neo4j.driver.session() as session:
                result = await session.execute_read(self._query_cve_stats_tx)
                return result
        except Exception as exc:
            logger.warning("Could not fetch CVE stats", error=str(exc))
            return {}

    async def _query_cve_stats_tx(self, tx) -> Dict:
        cypher = """
        MATCH (c:CVE) WITH count(c) AS cve_count
        MATCH (w:CWE) WITH cve_count, count(w) AS cwe_count
        RETURN cve_count, cwe_count
        """
        result = await tx.run(cypher)
        record = await result.single()
        if record:
            return {"cve_count": record["cve_count"], "cwe_count": record["cwe_count"]}
        return {"cve_count": 0, "cwe_count": 0}

    # -------------------------------------------------------------- helpers

    @staticmethod
    def _generate_recommendations(findings: List, hosts: List, cve_stats: Dict) -> List[str]:
        recs = []
        critical_count = sum(1 for f in findings if str(f.get("severity", "")).lower() == "critical")
        high_count = sum(1 for f in findings if str(f.get("severity", "")).lower() == "high")

        if critical_count > 0:
            recs.append(f"Patch {critical_count} CRITICAL finding(s) immediately — highest priority.")
        if high_count > 0:
            recs.append(f"Address {high_count} HIGH severity finding(s) within 24 hours.")
        if hosts:
            recs.append(f"Review {len(hosts)} discovered host(s) — reduce attack surface by disabling unused services.")
        if cve_stats.get("cve_count", 0) > 0:
            recs.append(
                f"Cross-reference {cve_stats['cve_count']} CVE(s) in graph against NVD for latest CVSS scores."
            )
        if not findings:
            recs.append("No active findings — run a Nuclei scan against discovered hosts to populate findings.")
        recs.append("Schedule periodic scans via POST /collect/nmap/scan-and-analyze to track new exposure.")
        return recs
