#!/usr/bin/env python3
"""
generate_sample_nmap.py — Tạo file Nmap XML mẫu với ~100 hosts đa dạng.
Output: data/sample_nmap_scan.xml
"""

import random
import sys
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).parent.parent / "data" / "sample_nmap_scan.xml"

# ── Service templates ─────────────────────────────────────────────────────────
# (port, name, product, version, cpe, os_type)
WEB_SERVERS = [
    (80,  "http",  "Apache httpd", "2.4.49", "cpe:/a:apache:http_server:2.4.49", "Linux"),
    (80,  "http",  "Apache httpd", "2.4.51", "cpe:/a:apache:http_server:2.4.51", "Linux"),
    (80,  "http",  "Apache httpd", "2.4.54", "cpe:/a:apache:http_server:2.4.54", "Linux"),
    (80,  "http",  "Apache httpd", "2.4.57", "cpe:/a:apache:http_server:2.4.57", "Linux"),
    (80,  "http",  "nginx",        "1.18.0", "cpe:/a:nginx:nginx:1.18.0",        "Linux"),
    (80,  "http",  "nginx",        "1.20.2", "cpe:/a:nginx:nginx:1.20.2",        "Linux"),
    (80,  "http",  "nginx",        "1.24.0", "cpe:/a:nginx:nginx:1.24.0",        "Linux"),
    (80,  "http",  "Microsoft IIS httpd", "10.0", "cpe:/a:microsoft:iis:10.0",   "Windows"),
    (80,  "http",  "Microsoft IIS httpd", "8.5",  "cpe:/a:microsoft:iis:8.5",    "Windows"),
    (8080,"http",  "Apache Tomcat",       "9.0.65", "cpe:/a:apache:tomcat:9.0.65", "Linux"),
    (8080,"http",  "Apache Tomcat",       "8.5.78", "cpe:/a:apache:tomcat:8.5.78", "Linux"),
    (8080,"http",  "Jetty",               "9.4.48", "cpe:/a:eclipse:jetty:9.4.48", "Linux"),
    (8443,"https-alt","nginx",            "1.18.0", "cpe:/a:nginx:nginx:1.18.0",   "Linux"),
]

SSH_SERVERS = [
    (22, "ssh", "OpenSSH", "7.4p1",  "cpe:/a:openbsd:openssh:7.4",  "protocol 2.0"),
    (22, "ssh", "OpenSSH", "7.9p1",  "cpe:/a:openbsd:openssh:7.9",  "protocol 2.0"),
    (22, "ssh", "OpenSSH", "8.0p1",  "cpe:/a:openbsd:openssh:8.0",  "protocol 2.0"),
    (22, "ssh", "OpenSSH", "8.2p1",  "cpe:/a:openbsd:openssh:8.2",  "Ubuntu 20.04"),
    (22, "ssh", "OpenSSH", "8.9p1",  "cpe:/a:openbsd:openssh:8.9",  "Ubuntu 22.04"),
    (22, "ssh", "OpenSSH", "9.3p1",  "cpe:/a:openbsd:openssh:9.3",  "Ubuntu 23.04"),
    (22, "ssh", "Dropbear sshd", "2019.78", "cpe:/a:matt_johnston:dropbear_ssh:2019.78", ""),
    (2222,"ssh","OpenSSH", "8.4p1",  "cpe:/a:openbsd:openssh:8.4",  "protocol 2.0"),
]

DB_SERVERS = [
    (3306, "mysql",      "MySQL",          "5.7.36",  "cpe:/a:mysql:mysql:5.7.36",          ""),
    (3306, "mysql",      "MySQL",          "5.7.40",  "cpe:/a:mysql:mysql:5.7.40",          ""),
    (3306, "mysql",      "MySQL",          "8.0.28",  "cpe:/a:mysql:mysql:8.0.28",          ""),
    (3306, "mysql",      "MySQL",          "8.0.32",  "cpe:/a:mysql:mysql:8.0.32",          ""),
    (5432, "postgresql", "PostgreSQL DB",  "9.6.24",  "cpe:/a:postgresql:postgresql:9.6.24", ""),
    (5432, "postgresql", "PostgreSQL DB",  "12.9",    "cpe:/a:postgresql:postgresql:12.9",   ""),
    (5432, "postgresql", "PostgreSQL DB",  "14.5",    "cpe:/a:postgresql:postgresql:14.5",   ""),
    (27017,"mongodb",    "MongoDB",        "4.4.15",  "cpe:/a:mongodb:mongodb:4.4.15",       ""),
    (27017,"mongodb",    "MongoDB",        "5.0.9",   "cpe:/a:mongodb:mongodb:5.0.9",        ""),
    (6379, "redis",      "Redis",          "6.2.6",   "cpe:/a:redis:redis:6.2.6",            "64-bit"),
    (6379, "redis",      "Redis",          "7.0.5",   "cpe:/a:redis:redis:7.0.5",            "64-bit"),
    (1521, "oracle",     "Oracle TNS listener", "12.2", "cpe:/a:oracle:database_server:12.2", ""),
    (5984, "couchdb",    "CouchDB httpd",  "2.3.1",   "cpe:/a:apache:couchdb:2.3.1",         ""),
    (9200, "http",       "Elasticsearch",  "7.17.3",  "cpe:/a:elastic:elasticsearch:7.17.3", ""),
]

FTP_SERVERS = [
    (21, "ftp", "ProFTPD",     "1.3.5",   "cpe:/a:proftpd:proftpd:1.3.5",   ""),
    (21, "ftp", "ProFTPD",     "1.3.5e",  "cpe:/a:proftpd:proftpd:1.3.5e",  ""),
    (21, "ftp", "vsftpd",      "2.3.4",   "cpe:/a:beasts:vsftpd:2.3.4",     ""),
    (21, "ftp", "vsftpd",      "3.0.3",   "cpe:/a:beasts:vsftpd:3.0.3",     ""),
    (21, "ftp", "Pure-FTPd",   "1.0.49",  "cpe:/a:pureftpd:pure-ftpd:1.0.49",""),
    (21, "ftp", "FileZilla Server", "0.9.60", "cpe:/a:filezilla-project:filezilla_server:0.9.60", ""),
]

MAIL_SERVERS = [
    (25,  "smtp",  "Exim smtpd",    "4.92",  "cpe:/a:exim:exim:4.92",          ""),
    (25,  "smtp",  "Exim smtpd",    "4.94",  "cpe:/a:exim:exim:4.94",          ""),
    (25,  "smtp",  "Postfix smtpd", "3.4.13","cpe:/a:postfix:postfix:3.4.13",  ""),
    (25,  "smtp",  "Sendmail",      "8.15.2","cpe:/a:sendmail:sendmail:8.15.2", ""),
    (110, "pop3",  "Dovecot pop3d", "2.3.7", "cpe:/a:dovecot:dovecot:2.3.7",   ""),
    (143, "imap",  "Dovecot imapd", "2.3.7", "cpe:/a:dovecot:dovecot:2.3.7",   ""),
    (143, "imap",  "Cyrus imapd",   "2.5.14","cpe:/a:cmu:cyrus_imap:2.5.14",   ""),
    (465, "smtps", "Postfix smtpd", "3.5.6", "cpe:/a:postfix:postfix:3.5.6",   ""),
    (587, "submission","Exim smtpd","4.94",  "cpe:/a:exim:exim:4.94",          ""),
]

SMB_SERVERS = [
    (445, "microsoft-ds", "Samba",          "3.5.0", "cpe:/a:samba:samba:3.5.0",  "workgroup: WORKGROUP"),
    (445, "microsoft-ds", "Samba",          "4.6.2", "cpe:/a:samba:samba:4.6.2",  "workgroup: CORP"),
    (445, "microsoft-ds", "Samba",          "4.13.2","cpe:/a:samba:samba:4.13.2", "workgroup: CORP"),
    (445, "microsoft-ds", "Windows Server 2008 R2", "", "cpe:/o:microsoft:windows_server_2008:r2", ""),
    (445, "microsoft-ds", "Windows Server 2012",    "", "cpe:/o:microsoft:windows_server_2012:-",  ""),
    (445, "microsoft-ds", "Windows Server 2016",    "", "cpe:/o:microsoft:windows_server_2016:-",  ""),
    (139, "netbios-ssn",  "Samba",          "3.5.0", "cpe:/a:samba:samba:3.5.0",  ""),
    (139, "netbios-ssn",  "Samba",          "4.6.2", "cpe:/a:samba:samba:4.6.2",  ""),
    (3389,"ms-wbt-server","Microsoft Terminal Services", "", "cpe:/a:microsoft:remote_desktop_protocol:-", ""),
]

OTHER_SERVICES = [
    (53,   "domain",    "dnsmasq",   "2.85",  "cpe:/a:thekelleys:dnsmasq:2.85",    ""),
    (53,   "domain",    "BIND",      "9.11.3","cpe:/a:isc:bind:9.11.3",            ""),
    (161,  "snmp",      "SNMPv2",    "",      "",                                    ""),
    (443,  "https",     "Apache httpd","2.4.54","cpe:/a:apache:http_server:2.4.54", ""),
    (443,  "https",     "nginx",     "1.20.2","cpe:/a:nginx:nginx:1.20.2",          ""),
    (8888, "http",      "Jupyter",   "6.4.8", "cpe:/a:jupyter:notebook:6.4.8",      ""),
    (9090, "http",      "Prometheus","2.37.0","cpe:/a:prometheus:prometheus:2.37.0", ""),
    (3000, "http",      "Grafana",   "8.5.5", "cpe:/a:grafana:grafana:8.5.5",       ""),
    (8161, "http",      "ActiveMQ",  "5.15.9","cpe:/a:apache:activemq:5.15.9",      ""),
    (4848, "http",      "GlassFish", "4.1",   "cpe:/a:oracle:glassfish_server:4.1", ""),
    (7001, "http",      "Oracle WebLogic", "12.2.1","cpe:/a:oracle:weblogic_server:12.2.1",""),
    (4443, "https",     "Confluence","7.12.5","cpe:/a:atlassian:confluence:7.12.5", ""),
    (8090, "http",      "Confluence","7.13.0","cpe:/a:atlassian:confluence:7.13.0", ""),
    (8888, "http",      "Jupyter",   "5.7.8", "cpe:/a:jupyter:notebook:5.7.8",      ""),
    (9000, "http",      "SonarQube", "8.9.3", "cpe:/a:sonarsource:sonarqube:8.9.3", ""),
    (2181, "zookeeper", "Apache Zookeeper","3.4.14","cpe:/a:apache:zookeeper:3.4.14",""),
    (9092, "kafka",     "Apache Kafka","2.8.0","cpe:/a:apache:kafka:2.8.0",         ""),
]

OS_TEMPLATES = [
    ("Linux 4.15",   "Linux",     "Linux",   "4.X", "cpe:/o:linux:linux_kernel:4.15"),
    ("Linux 5.4",    "Linux",     "Linux",   "5.X", "cpe:/o:linux:linux_kernel:5.4"),
    ("Linux 5.15",   "Linux",     "Linux",   "5.X", "cpe:/o:linux:linux_kernel:5.15"),
    ("Linux 5.19",   "Linux",     "Linux",   "5.X", "cpe:/o:linux:linux_kernel:5.19"),
    ("Ubuntu 18.04", "Canonical", "Linux",   "4.X", "cpe:/o:canonical:ubuntu_linux:18.04"),
    ("Ubuntu 20.04", "Canonical", "Linux",   "5.X", "cpe:/o:canonical:ubuntu_linux:20.04"),
    ("Ubuntu 22.04", "Canonical", "Linux",   "5.X", "cpe:/o:canonical:ubuntu_linux:22.04"),
    ("CentOS 7",     "CentOS",    "Linux",   "3.X", "cpe:/o:centos:centos:7"),
    ("Debian 10",    "Debian",    "Linux",   "4.X", "cpe:/o:debian:debian_linux:10"),
    ("Debian 11",    "Debian",    "Linux",   "5.X", "cpe:/o:debian:debian_linux:11"),
    ("Windows Server 2012 R2", "Microsoft", "Windows", "-", "cpe:/o:microsoft:windows_server_2012:r2"),
    ("Windows Server 2016",    "Microsoft", "Windows", "-", "cpe:/o:microsoft:windows_server_2016:-"),
    ("Windows Server 2019",    "Microsoft", "Windows", "-", "cpe:/o:microsoft:windows_server_2019:-"),
    ("Windows 10",             "Microsoft", "Windows", "-", "cpe:/o:microsoft:windows_10:-"),
    ("FreeBSD 12.2",           "FreeBSD",   "BSD",    "12.X","cpe:/o:freebsd:freebsd:12.2"),
]

HOSTNAME_PREFIXES = [
    "web", "app", "api", "db", "sql", "mail", "smtp", "ftp", "file",
    "dev", "test", "prod", "staging", "backup", "log", "monitor",
    "proxy", "lb", "vpn", "gw", "router", "switch", "dc", "ad",
    "jenkins", "ci", "docker", "k8s", "registry", "repo", "git",
    "wiki", "confluence", "jira", "nexus", "sonar", "grafana",
    "kafka", "rabbit", "elastic", "kibana", "redis", "mongo",
]

random.seed(42)


def _port_xml(port: int, protocol: str, name: str, product: str,
              version: str, cpe: str, extrainfo: str = "") -> str:
    extra = f' extrainfo="{escape(extrainfo)}"' if extrainfo else ""
    cpe_attr = f' cpe="{escape(cpe)}"' if cpe else ""
    return f"""      <port protocol="{protocol}" portid="{port}">
        <state state="open" reason="syn-ack"/>
        <service name="{escape(name)}" product="{escape(product)}" version="{escape(version)}"{extra}{cpe_attr}/>
      </port>"""


def _os_xml(os_info: tuple) -> str:
    name, vendor, family, gen, cpe = os_info
    acc = random.randint(85, 98)
    return f"""    <os>
      <osmatch name="{escape(name)}" accuracy="{acc}">
        <osclass type="general purpose" vendor="{escape(vendor)}" osfamily="{escape(family)}" osgen="{escape(gen)}" accuracy="{acc}">
          <cpe>{escape(cpe)}</cpe>
        </osclass>
      </osmatch>
    </os>"""


def _host_xml(ip: str, hostname: str, ports: list, os_info: tuple, ts: int) -> str:
    ports_xml = "\n".join(ports)
    return f"""
  <host starttime="{ts}" endtime="{ts + random.randint(5,30)}">
    <status state="up" reason="echo-reply" reason_ttl="64"/>
    <address addr="{ip}" addrtype="ipv4"/>
    <hostnames>
      <hostname name="{hostname}" type="PTR"/>
    </hostnames>
    <ports>
{ports_xml}
    </ports>
{_os_xml(os_info)}
  </host>"""


def _pick_ssh() -> tuple:
    s = random.choice(SSH_SERVERS)
    return _port_xml(s[0], "tcp", s[1], s[2], s[3], s[4], s[5])


def _pick_https(web: tuple) -> str:
    return _port_xml(443, "tcp", "https", web[2], web[3], web[4], "ssl")


def build_hosts() -> list[str]:
    hosts = []
    ts_base = 1747008200
    ts = ts_base

    # ── Subnet 192.168.1.x ── (50 - 99, thêm vào file gốc có 1,10,20,30,40)
    subnets = [
        ("192.168.1", range(50, 100)),
        ("192.168.2", range(1,  51)),
    ]

    host_idx = 0

    for subnet, ip_range in subnets:
        for octet in ip_range:
            ip       = f"{subnet}.{octet}"
            prefix   = HOSTNAME_PREFIXES[host_idx % len(HOSTNAME_PREFIXES)]
            hostname = f"{prefix}-{octet:02d}.local"
            os_info  = random.choice(OS_TEMPLATES)
            host_idx += 1

            ports = []

            # Mỗi host đều có SSH
            ports.append(_pick_ssh())

            # Phân loại host theo octet/index
            role = host_idx % 10

            if role in (0, 1):
                # Web server
                web = random.choice(WEB_SERVERS)
                ports.append(_port_xml(web[0], "tcp", web[1], web[2], web[3], web[4], web[5]))
                ports.append(_pick_https(web))

            elif role in (2, 3):
                # DB server
                db = random.choice(DB_SERVERS)
                ports.append(_port_xml(db[0], "tcp", db[1], db[2], db[3], db[4], db[5]))
                # Thêm 1 DB phụ
                db2 = random.choice(DB_SERVERS)
                if db2[0] != db[0]:
                    ports.append(_port_xml(db2[0], "tcp", db2[1], db2[2], db2[3], db2[4], db2[5]))

            elif role == 4:
                # Mail server
                for svc in random.sample(MAIL_SERVERS, min(3, len(MAIL_SERVERS))):
                    ports.append(_port_xml(svc[0], "tcp", svc[1], svc[2], svc[3], svc[4], svc[5]))

            elif role == 5:
                # FTP / file server
                ftp = random.choice(FTP_SERVERS)
                ports.append(_port_xml(ftp[0], "tcp", ftp[1], ftp[2], ftp[3], ftp[4], ftp[5]))
                smb = random.choice(SMB_SERVERS[:3])
                ports.append(_port_xml(smb[0], "tcp", smb[1], smb[2], smb[3], smb[4], smb[5]))

            elif role == 6:
                # Windows / SMB
                for svc in random.sample(SMB_SERVERS, min(3, len(SMB_SERVERS))):
                    ports.append(_port_xml(svc[0], "tcp", svc[1], svc[2], svc[3], svc[4], svc[5]))

            elif role == 7:
                # App / middleware
                svc = random.choice(OTHER_SERVICES)
                ports.append(_port_xml(svc[0], "tcp", svc[1], svc[2], svc[3], svc[4], svc[5]))
                web = random.choice(WEB_SERVERS)
                ports.append(_port_xml(web[0], "tcp", web[1], web[2], web[3], web[4], web[5]))

            elif role == 8:
                # Mixed web + db
                web = random.choice(WEB_SERVERS)
                db  = random.choice(DB_SERVERS)
                ports.append(_port_xml(web[0], "tcp", web[1], web[2], web[3], web[4], web[5]))
                ports.append(_port_xml(db[0],  "tcp", db[1],  db[2],  db[3],  db[4],  db[5]))

            else:
                # Dev/misc — random services
                for svc in random.sample(OTHER_SERVICES, min(2, len(OTHER_SERVICES))):
                    ports.append(_port_xml(svc[0], "tcp", svc[1], svc[2], svc[3], svc[4], svc[5]))

            hosts.append(_host_xml(ip, hostname, ports, os_info, ts))
            ts += random.randint(10, 40)

    return hosts


def main():
    print(f"[GEN] Generating sample Nmap XML...")
    hosts = build_hosts()

    header = '''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE nmaprun>
<!--
  Sample Nmap scan data — 100+ hosts, 2 subnets
  192.168.1.50-99, 192.168.2.1-50
  Combined with original 5 hosts in this file.
  Generated by scripts/generate_sample_nmap.py
-->
<nmaprun scanner="nmap" args="nmap -sV -O --top-ports 1000 192.168.0.0/16"
         start="1747008200" version="7.94" xmloutputversion="1.05">

  <!-- ── Original 5 hosts (kept from manual data) ─────────────────────────── -->

  <host starttime="1747008001" endtime="1747008030">
    <status state="up" reason="echo-reply" reason_ttl="64"/>
    <address addr="192.168.1.10" addrtype="ipv4"/>
    <hostnames><hostname name="webserver.local" type="PTR"/></hostnames>
    <ports>
      <port protocol="tcp" portid="22"><state state="open" reason="syn-ack"/><service name="ssh" product="OpenSSH" version="8.9p1" extrainfo="Ubuntu 22.04" cpe="cpe:/a:openbsd:openssh:8.9"/></port>
      <port protocol="tcp" portid="80"><state state="open" reason="syn-ack"/><service name="http" product="Apache httpd" version="2.4.49" ostype="Linux" cpe="cpe:/a:apache:http_server:2.4.49"/></port>
      <port protocol="tcp" portid="443"><state state="open" reason="syn-ack"/><service name="https" product="Apache httpd" version="2.4.49" tunnel="ssl" cpe="cpe:/a:apache:http_server:2.4.49"/></port>
      <port protocol="tcp" portid="8080"><state state="open" reason="syn-ack"/><service name="http-proxy" product="Apache Tomcat" version="9.0.65" cpe="cpe:/a:apache:tomcat:9.0.65"/></port>
    </ports>
    <os><osmatch name="Linux 5.15" accuracy="96"><osclass type="general purpose" vendor="Linux" osfamily="Linux" osgen="5.X" accuracy="96"><cpe>cpe:/o:linux:linux_kernel:5.15</cpe></osclass></osmatch></os>
  </host>

  <host starttime="1747008031" endtime="1747008060">
    <status state="up" reason="echo-reply" reason_ttl="64"/>
    <address addr="192.168.1.20" addrtype="ipv4"/>
    <hostnames><hostname name="fileserver.local" type="PTR"/></hostnames>
    <ports>
      <port protocol="tcp" portid="21"><state state="open" reason="syn-ack"/><service name="ftp" product="ProFTPD" version="1.3.5" cpe="cpe:/a:proftpd:proftpd:1.3.5"/></port>
      <port protocol="tcp" portid="22"><state state="open" reason="syn-ack"/><service name="ssh" product="OpenSSH" version="7.4p1" extrainfo="protocol 2.0" cpe="cpe:/a:openbsd:openssh:7.4"/></port>
      <port protocol="tcp" portid="445"><state state="open" reason="syn-ack"/><service name="microsoft-ds" product="Samba" version="3.5.0" extrainfo="workgroup: WORKGROUP" cpe="cpe:/a:samba:samba:3.5.0"/></port>
    </ports>
    <os><osmatch name="Linux 3.10" accuracy="92"><osclass type="general purpose" vendor="Linux" osfamily="Linux" osgen="3.X" accuracy="92"><cpe>cpe:/o:linux:linux_kernel:3.10</cpe></osclass></osmatch></os>
  </host>

  <host starttime="1747008061" endtime="1747008090">
    <status state="up" reason="echo-reply" reason_ttl="64"/>
    <address addr="192.168.1.30" addrtype="ipv4"/>
    <hostnames><hostname name="dbserver.local" type="PTR"/></hostnames>
    <ports>
      <port protocol="tcp" portid="22"><state state="open" reason="syn-ack"/><service name="ssh" product="OpenSSH" version="7.9p1" cpe="cpe:/a:openbsd:openssh:7.9"/></port>
      <port protocol="tcp" portid="3306"><state state="open" reason="syn-ack"/><service name="mysql" product="MySQL" version="5.7.36" extrainfo="5.7.36-log" cpe="cpe:/a:mysql:mysql:5.7.36"/></port>
      <port protocol="tcp" portid="6379"><state state="open" reason="syn-ack"/><service name="redis" product="Redis" version="6.2.6" cpe="cpe:/a:redis:redis:6.2.6"/></port>
    </ports>
    <os><osmatch name="Linux 4.19" accuracy="94"><osclass type="general purpose" vendor="Linux" osfamily="Linux" osgen="4.X" accuracy="94"><cpe>cpe:/o:linux:linux_kernel:4.19</cpe></osclass></osmatch></os>
  </host>

  <host starttime="1747008091" endtime="1747008120">
    <status state="up" reason="echo-reply" reason_ttl="64"/>
    <address addr="192.168.1.40" addrtype="ipv4"/>
    <hostnames><hostname name="mailserver.local" type="PTR"/></hostnames>
    <ports>
      <port protocol="tcp" portid="22"><state state="open" reason="syn-ack"/><service name="ssh" product="OpenSSH" version="8.2p1" cpe="cpe:/a:openbsd:openssh:8.2"/></port>
      <port protocol="tcp" portid="25"><state state="open" reason="syn-ack"/><service name="smtp" product="Exim smtpd" version="4.92" cpe="cpe:/a:exim:exim:4.92"/></port>
      <port protocol="tcp" portid="143"><state state="open" reason="syn-ack"/><service name="imap" product="Dovecot imapd" version="2.3.7" cpe="cpe:/a:dovecot:dovecot:2.3.7"/></port>
    </ports>
    <os><osmatch name="Ubuntu 20.04" accuracy="95"><osclass type="general purpose" vendor="Canonical" osfamily="Linux" osgen="5.X" accuracy="95"><cpe>cpe:/o:canonical:ubuntu_linux:20.04</cpe></osclass></osmatch></os>
  </host>

  <host starttime="1747008121" endtime="1747008150">
    <status state="up" reason="echo-reply" reason_ttl="64"/>
    <address addr="192.168.1.1" addrtype="ipv4"/>
    <hostnames><hostname name="gateway.local" type="PTR"/></hostnames>
    <ports>
      <port protocol="tcp" portid="22"><state state="open" reason="syn-ack"/><service name="ssh" product="Dropbear sshd" version="2019.78" cpe="cpe:/a:matt_johnston:dropbear_ssh:2019.78"/></port>
      <port protocol="tcp" portid="80"><state state="open" reason="syn-ack"/><service name="http" product="lighttpd" version="1.4.55" cpe="cpe:/a:lighttpd:lighttpd:1.4.55"/></port>
    </ports>
    <os><osmatch name="Linux 4.9 (OpenWrt)" accuracy="88"><osclass type="WAP" vendor="Linux" osfamily="Linux" osgen="4.X" accuracy="88"><cpe>cpe:/o:linux:linux_kernel:4.9</cpe></osclass></osmatch></os>
  </host>
'''

    footer = "\n</nmaprun>\n"

    content = header + "\n".join(hosts) + footer

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(content, encoding="utf-8")

    print(f"[OK]  Written: {OUT}")
    print(f"      Total hosts: {5 + len(hosts)}")
    print(f"      File size: {OUT.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
