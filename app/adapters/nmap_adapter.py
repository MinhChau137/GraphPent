"""Nmap Adapter - Phase 10: Parse Nmap XML output into graph entities."""

import asyncio
import subprocess
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from app.core.logger import logger
from app.core.security import validate_target
from app.config.settings import settings
from app.domain.schemas.extraction import Entity, Provenance, Relation


_NMAP_PROVENANCE = Provenance(
    confidence=0.95,
    tool_origin="nmap-scanner",
    sensitivity="lab-internal",
)


class NmapAdapter:
    """Run Nmap scans and convert XML output to Entity/Relation objects."""

    # ------------------------------------------------------------------ scan

    async def run_scan(
        self,
        target: str,
        options: Optional[List[str]] = None,
    ) -> str:
        """Execute nmap and return raw XML as a string.

        Raises:
            PermissionError: if target is not in ALLOWED_TARGETS.
            FileNotFoundError: if nmap binary is not on PATH.
            RuntimeError: if nmap exits with non-zero status.
        """
        await validate_target(target)

        cmd = ["nmap", "-oX", "-", "--open"]
        if options:
            cmd.extend(options)
        cmd.append(target)

        logger.info("Running Nmap", target=target, cmd=" ".join(cmd))

        loop = asyncio.get_event_loop()
        try:
            proc = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=settings.MAX_TOOL_TIMEOUT,
                ),
            )
        except FileNotFoundError:
            raise FileNotFoundError("nmap binary not found — install nmap on this host")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Nmap timed out after {settings.MAX_TOOL_TIMEOUT}s")

        if proc.returncode != 0:
            raise RuntimeError(f"Nmap error (exit {proc.returncode}): {proc.stderr[:300]}")

        logger.info("Nmap scan finished", target=target, output_bytes=len(proc.stdout))
        return proc.stdout

    # --------------------------------------------------------------- parsing

    def parse_xml(self, xml_data: str) -> Tuple[List[Entity], List[Relation]]:
        """Parse Nmap XML string into (entities, relations).

        Produces Host → Port → Service graph facts.
        Only 'up' hosts and 'open' ports are included.
        """
        entities: List[Entity] = []
        relations: List[Relation] = []

        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as exc:
            logger.error("Nmap XML parse error", error=str(exc))
            return [], []

        for host_elem in root.findall("host"):
            status = host_elem.find("status")
            if status is None or status.get("state") != "up":
                continue

            ip = self._get_ip(host_elem)
            if not ip:
                continue

            hostname = self._get_hostname(host_elem)
            os_name = self._get_os(host_elem)

            host_entity = Entity(
                id=f"host-{ip}",
                type="Host",
                name=ip,
                properties={
                    "ip": ip,
                    "hostname": hostname,
                    "os": os_name,
                    "status": "up",
                },
                provenance=_NMAP_PROVENANCE,
            )
            entities.append(host_entity)

            ports_elem = host_elem.find("ports")
            if ports_elem is None:
                continue

            for port_elem in ports_elem.findall("port"):
                state_elem = port_elem.find("state")
                if state_elem is None or state_elem.get("state") != "open":
                    continue

                portid = port_elem.get("portid", "0")
                protocol = port_elem.get("protocol", "tcp")
                port_key = f"port-{ip}-{protocol}-{portid}"

                port_entity = Entity(
                    id=port_key,
                    type="Port",
                    name=f"{portid}/{protocol}",
                    properties={
                        "port": int(portid),
                        "protocol": protocol,
                        "state": "open",
                        "host": ip,
                    },
                    provenance=_NMAP_PROVENANCE,
                )
                entities.append(port_entity)

                # Host -[HAS_PORT]-> Port
                relations.append(
                    Relation(
                        type="HAS_PORT",
                        source_id=f"host-{ip}",
                        target_id=port_key,
                        provenance=_NMAP_PROVENANCE,
                    )
                )

                service_elem = port_elem.find("service")
                if service_elem is None:
                    continue

                svc_name = service_elem.get("name", "unknown")
                svc_product = service_elem.get("product", "")
                svc_version = service_elem.get("version", "")
                svc_key = f"service-{ip}-{portid}"

                service_entity = Entity(
                    id=svc_key,
                    type="Service",
                    name=svc_name,
                    properties={
                        "product": svc_product,
                        "version": svc_version,
                        "port": int(portid),
                        "protocol": protocol,
                        "host": ip,
                        "full_name": f"{svc_product} {svc_version}".strip() or svc_name,
                    },
                    provenance=_NMAP_PROVENANCE,
                )
                entities.append(service_entity)

                # Port -[RUNS_SERVICE]-> Service
                relations.append(
                    Relation(
                        type="RUNS_SERVICE",
                        source_id=port_key,
                        target_id=svc_key,
                        provenance=_NMAP_PROVENANCE,
                    )
                )

                # Host -[EXPOSES]-> Service (shortcut edge for graph queries)
                relations.append(
                    Relation(
                        type="EXPOSES",
                        source_id=f"host-{ip}",
                        target_id=svc_key,
                        provenance=_NMAP_PROVENANCE,
                    )
                )

        logger.info(
            "Nmap XML parsed",
            entities=len(entities),
            relations=len(relations),
        )
        return entities, relations

    async def parse_file(self, xml_path: str) -> Tuple[List[Entity], List[Relation]]:
        """Parse an existing Nmap XML file (no scan needed)."""
        with open(xml_path, "r", encoding="utf-8") as fh:
            xml_data = fh.read()
        return self.parse_xml(xml_data)

    # ------------------------------------------------------------ full pipeline

    async def scan_and_parse(
        self,
        target: str,
        options: Optional[List[str]] = None,
    ) -> Tuple[List[Entity], List[Relation]]:
        """Run scan then parse — returns (entities, relations)."""
        xml_data = await self.run_scan(target, options)
        return self.parse_xml(xml_data)

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _get_ip(host_elem: ET.Element) -> Optional[str]:
        for addr in host_elem.findall("address"):
            if addr.get("addrtype") == "ipv4":
                return addr.get("addr")
        return None

    @staticmethod
    def _get_hostname(host_elem: ET.Element) -> Optional[str]:
        hostnames = host_elem.find("hostnames")
        if hostnames is not None:
            hn = hostnames.find("hostname")
            if hn is not None:
                return hn.get("name")
        return None

    @staticmethod
    def _get_os(host_elem: ET.Element) -> Optional[str]:
        os_elem = host_elem.find("os")
        if os_elem is not None:
            match = os_elem.find("osmatch")
            if match is not None:
                return match.get("name")
        return None

    # ----------------------------------------- summary helper (used by service)

    @staticmethod
    def summarise(
        entities: List[Entity],
        relations: List[Relation],
    ) -> Dict:
        hosts = [e for e in entities if e.type == "Host"]
        ports = [e for e in entities if e.type == "Port"]
        services = [e for e in entities if e.type == "Service"]
        return {
            "hosts": len(hosts),
            "open_ports": len(ports),
            "services": len(services),
            "relations": len(relations),
            "host_ips": [e.name for e in hosts],
            "service_names": list({e.name for e in services}),
        }
