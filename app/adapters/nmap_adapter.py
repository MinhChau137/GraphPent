"""Nmap Adapter - Phase 10: Parse Nmap XML output into graph entities."""

import asyncio
import subprocess
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from app.core.logger import logger
from app.core.security import validate_target
from app.config.settings import settings
from app.domain.schemas.extraction import Entity, Provenance, Relation


_VENDOR_MAP = {
    "apache": "apache", "apache httpd": "apache", "apache http server": "apache",
    "apache tomcat": "apache", "tomcat": "apache", "struts": "apache",
    "nginx": "nginx",
    "iis": "microsoft", "microsoft iis": "microsoft",
    "openssh": "openbsd",
    "dropbear": "matt_johnston", "dropbear sshd": "matt_johnston",
    "mysql": "oracle", "mysql community server": "oracle",
    "mariadb": "mariadb",
    "postgresql": "postgresql",
    "redis": "redis",
    "mongodb": "mongodb",
    "proftpd": "proftpd",
    "vsftpd": "beasts",
    "pure-ftpd": "pureftpd",
    "samba": "samba",
    "exim": "exim", "exim smtpd": "exim",
    "postfix": "postfix",
    "sendmail": "sendmail",
    "dovecot": "dovecot", "dovecot imapd": "dovecot",
    "lighttpd": "lighttpd",
    "php": "php",
    "wordpress": "wordpress",
    "drupal": "drupal",
    "joomla": "joomla",
    "jenkins": "jenkins",
    "elasticsearch": "elastic",
    "kibana": "elastic",
    "grafana": "grafana",
    "influxdb": "influxdata",
    "rabbitmq": "vmware",
    "spring": "vmware",
    "log4j": "apache",
    # Products in sample nmap scan
    "activemq": "apache", "apache activemq": "apache",
    "confluence": "atlassian",
    "zookeeper": "apache", "apache zookeeper": "apache",
    "couchdb": "apache", "couchdb httpd": "apache",
    "bind": "isc", "bind9": "isc",
    "dnsmasq": "thekelleys",
    "dropbear sshd": "matt_johnston",
    "filezilla server": "filezilla-project",
    "jupyter": "jupyter", "jupyter notebook": "jupyter",
    "prometheus": "prometheus",
    "sonarqube": "sonarsource",
    "oracle weblogic": "oracle", "weblogic": "oracle",
    "oracle tns listener": "oracle",
    "microsoft iis httpd": "microsoft",
    "microsoft terminal services": "microsoft",
    "pure-ftpd": "pureftpd", "pure ftpd": "pureftpd",
    "cyrus imapd": "cmu", "dovecot pop3d": "dovecot",
    "postfix smtpd": "postfix",
}


def _vendor_from_product(product: str) -> str:
    key = product.strip().lower()
    if key in _VENDOR_MAP:
        return _VENDOR_MAP[key]
    for k, v in _VENDOR_MAP.items():
        if k in key or key in k:
            return v
    return ""


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

        seen_zones: Dict[str, bool] = {}
        seen_apps:  Dict[str, bool] = {}

        for host_elem in root.findall("host"):
            status = host_elem.find("status")
            if status is None or status.get("state") != "up":
                continue

            ip = self._get_ip(host_elem)
            if not ip:
                continue

            hostname = self._get_hostname(host_elem)
            os_name  = self._get_os(host_elem)
            mac      = self._get_mac(host_elem)

            # ── NetworkZone (subnet /24) ────────────────────────────────────
            subnet   = ".".join(ip.split(".")[:3]) + ".0/24"
            zone_id  = f"zone-{subnet.replace('/', '_')}"
            if zone_id not in seen_zones:
                seen_zones[zone_id] = True
                entities.append(Entity(
                    id=zone_id, type="NetworkZone", name=subnet,
                    properties={"subnet": subnet, "cidr": "/24",
                                "network": ".".join(ip.split(".")[:3]) + ".0"},
                    provenance=_NMAP_PROVENANCE,
                ))

            # ── IP ──────────────────────────────────────────────────────────
            entities.append(Entity(
                id=f"ip-{ip}", type="IP", name=ip,
                properties={"address": ip, "version": "ipv4", "subnet": subnet},
                provenance=_NMAP_PROVENANCE,
            ))

            # ── Host ────────────────────────────────────────────────────────
            entities.append(Entity(
                id=f"host-{ip}", type="Host", name=hostname or ip,
                properties={
                    "ip": ip, "hostname": hostname, "os": os_name,
                    "mac": mac, "status": "up", "subnet": subnet,
                },
                provenance=_NMAP_PROVENANCE,
            ))

            # Host -[HAS_IP]-> IP
            relations.append(Relation(type="HAS_IP",
                source_id=f"host-{ip}", target_id=f"ip-{ip}",
                provenance=_NMAP_PROVENANCE))

            # Host -[LOCATED_IN]-> NetworkZone
            relations.append(Relation(type="LOCATED_IN",
                source_id=f"host-{ip}", target_id=zone_id,
                provenance=_NMAP_PROVENANCE))

            # IP -[LOCATED_IN]-> NetworkZone
            relations.append(Relation(type="LOCATED_IN",
                source_id=f"ip-{ip}", target_id=zone_id,
                provenance=_NMAP_PROVENANCE))

            # ── Domain (hostname) ───────────────────────────────────────────
            if hostname:
                domain_id = f"domain-{hostname.lower()}"
                entities.append(Entity(
                    id=domain_id, type="Domain", name=hostname,
                    properties={"fqdn": hostname, "host_ip": ip},
                    provenance=_NMAP_PROVENANCE,
                ))
                relations.append(Relation(type="HAS_HOSTNAME",
                    source_id=f"host-{ip}", target_id=domain_id,
                    provenance=_NMAP_PROVENANCE))

            # ── Ports & Services ────────────────────────────────────────────
            ports_elem = host_elem.find("ports")
            if ports_elem is None:
                continue

            for port_elem in ports_elem.findall("port"):
                state_elem = port_elem.find("state")
                if state_elem is None or state_elem.get("state") != "open":
                    continue

                portid   = port_elem.get("portid", "0")
                protocol = port_elem.get("protocol", "tcp")
                port_key = f"port-{ip}-{protocol}-{portid}"

                entities.append(Entity(
                    id=port_key, type="Port", name=f"{portid}/{protocol}",
                    properties={"port": int(portid), "protocol": protocol,
                                "state": "open", "host": ip},
                    provenance=_NMAP_PROVENANCE,
                ))
                relations.append(Relation(type="HAS_PORT",
                    source_id=f"host-{ip}", target_id=port_key,
                    provenance=_NMAP_PROVENANCE))

                service_elem = port_elem.find("service")
                if service_elem is None:
                    continue

                svc_name    = service_elem.get("name", "unknown")
                svc_product = service_elem.get("product", "")
                svc_version = service_elem.get("version", "")
                svc_extra   = service_elem.get("extrainfo", "")
                svc_tunnel  = service_elem.get("tunnel", "")
                svc_cpe     = service_elem.get("cpe", "")
                if not svc_cpe:
                    cpe_elem = service_elem.find("cpe")
                    if cpe_elem is not None and cpe_elem.text:
                        svc_cpe = cpe_elem.text.strip()
                svc_key = f"service-{ip}-{portid}"

                entities.append(Entity(
                    id=svc_key, type="Service", name=svc_name,
                    properties={
                        "product": svc_product, "version": svc_version,
                        "port": int(portid), "protocol": protocol,
                        "host": ip, "extrainfo": svc_extra,
                        "tunnel": svc_tunnel,
                        "full_name": f"{svc_product} {svc_version}".strip() or svc_name,
                        "cpe": svc_cpe,
                    },
                    provenance=_NMAP_PROVENANCE,
                ))

                relations.append(Relation(type="RUNS_SERVICE",
                    source_id=port_key, target_id=svc_key,
                    provenance=_NMAP_PROVENANCE))

                relations.append(Relation(type="EXPOSES",
                    source_id=f"host-{ip}", target_id=svc_key,
                    provenance=_NMAP_PROVENANCE))

                # ── Application (deduplicated per product+version) ──────────
                if svc_product:
                    import re as _re
                    app_slug = _re.sub(r"[^a-z0-9]+", "-",
                                       f"{svc_product}-{svc_version}".lower()).strip("-")
                    app_id   = f"app-{app_slug}"
                    if app_id not in seen_apps:
                        seen_apps[app_id] = True
                        entities.append(Entity(
                            id=app_id, type="Application",
                            name=f"{svc_product} {svc_version}".strip(),
                            properties={
                                "product": svc_product, "version": svc_version,
                                "vendor": _vendor_from_product(svc_product),
                                "cpe": svc_cpe,
                            },
                            provenance=_NMAP_PROVENANCE,
                        ))
                    # Service -[RUNS]-> Application
                    relations.append(Relation(type="RUNS",
                        source_id=svc_key, target_id=app_id,
                        provenance=_NMAP_PROVENANCE))
                    # Host -[RUNS]-> Application
                    relations.append(Relation(type="RUNS",
                        source_id=f"host-{ip}", target_id=app_id,
                        properties={"port": int(portid)},
                        provenance=_NMAP_PROVENANCE))

                # ── URL (web services) ──────────────────────────────────────
                _WEB_PORTS = {
                    80, 443, 8080, 8443, 8888, 9000, 9090, 3000, 4443,
                    8161, 4848, 7001, 8090, 8000, 8008, 9200, 5601,
                }
                if int(portid) in _WEB_PORTS:
                    is_ssl = (svc_tunnel == "ssl" or
                              portid in ("443", "8443", "4443") or
                              "https" in svc_name)
                    scheme  = "https" if is_ssl else "http"
                    url_str = f"{scheme}://{ip}:{portid}"
                    url_id  = f"url-{ip}-{portid}"
                    entities.append(Entity(
                        id=url_id, type="URL", name=url_str,
                        properties={
                            "url": url_str, "scheme": scheme,
                            "host": ip, "port": int(portid),
                            "path": "/",
                        },
                        provenance=_NMAP_PROVENANCE,
                    ))
                    # Service -[EXPOSES_URL]-> URL
                    relations.append(Relation(type="EXPOSES",
                        source_id=svc_key, target_id=url_id,
                        provenance=_NMAP_PROVENANCE))
                    # URL -[HOSTED_ON]-> Host
                    relations.append(Relation(type="HOSTED_ON",
                        source_id=url_id, target_id=f"host-{ip}",
                        provenance=_NMAP_PROVENANCE))

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

    @staticmethod
    def _get_mac(host_elem: ET.Element) -> Optional[str]:
        for addr in host_elem.findall("address"):
            if addr.get("addrtype") == "mac":
                return addr.get("addr")
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
