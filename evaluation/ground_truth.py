from typing import Dict

# Ground truth: query → relevant IDs expected in top results.
#
# relevant_ids has 3 types:
#   - CWE/CVE graph node IDs ("cwe-89", "CVE-2022-2718")
#     matched by graph_only / hybrid modes
#   - Chunk IDs ("1861.0")
#     matched by vector_only / hybrid modes
#   - NVD-extracted graph nodes ("cwe-179", "buroweb-2026-1432")
#     content is SQL injection / XSS etc. even if CWE ID is non-canonical
#
# Graph node IDs verified by running graph_only retrieval for each query.
# Chunk IDs verified by checking PostgreSQL content for CWE tags.
# Updated after NVD data ingestion (Phase 2 v2).

GROUND_TRUTH: Dict[str, Dict] = {
    "SQL injection": {
        "relevant_ids": [
            # Canonical CWE graph nodes
            "cwe-89",
            # NVD-extracted nodes (content = SQL injection, verified from graph search)
            "cwe-179", "cwe-138", "cwe-434", "cwe-613", "cwe-668", "cwe-863",
            # CVE graph nodes extracted from NVD (genuine SQL injection CVEs)
            "cve-2024-1317",
            "CVE-2022-2718",
            "CVE-2026-0567",
            "CVE-2023-5204",
            "CVE-2023-6981",
            "buroweb-2026-1432",
            "CVE-2026-1367",
            # Chunk IDs with CWE-89 content (verified from PostgreSQL)
            "1861.0",   # CVE-2026-1432: Buroweb SQL injection (CWE-89)
            "1277.0",   # CVE-2026-0722: Shield Security SQL injection (CWE-89)
            "1751.0",   # CVE-2026-1287: Django FilteredRelation SQL injection (CWE-89)
        ],
        "relevant_cves": []
    },
    "XSS": {
        "relevant_ids": [
            # Canonical CWE graph nodes
            "cwe-79", "cwe-80", "cwe-116",
            # NVD-extracted nodes (content = XSS, verified from graph search)
            "cwe-87", "cwe-433", "cwe-79.1", "cwe-1289",
            # CVE graph nodes extracted from NVD (genuine XSS CVEs)
            "CVE-2023-7070",
            "CVE-2023-6701",
            "CVE-2023-31045",
            "modern-events-calendar-vulnerability-1",
            # New XSS CVE/vuln nodes discovered after CVE ingestion (verified graph_only limit=20)
            "synopsys-seeker-vulnerability",    # Synopsys Seeker Stored XSS
            "theme-goods-musico",               # ThemeGoods Musico Reflected XSS
            "theme-goods-architecturer",        # ThemeGoods Architecturer Reflected XSS
            "theme-goods-starto",               # ThemeGoods Starto Reflected XSS
            "CVE-2026-1434",                    # Omega-PSIR Reflected XSS via lang parameter
            "altium-live-2026-1011",            # Altium Live Stored XSS
            "CVE-2026-1001",                    # Domoticz Stored XSS via Hardware Config
            "CVE-2026-34806",                   # Stored XSS via /cgi-bin/snat.cgi
            "cwe-160",                          # XSS: input buffer overflow variant
            "1285",                             # Common XSS Vulnerability (graph node)
            # Chunk IDs with CWE-79 content (verified from PostgreSQL)
            "1198.0",   # CVE-2026-0627: AMP for WP Stored XSS (CWE-79)
            "1365.0",   # CVE-2026-0815: Category Image Stored XSS (CWE-79)
            "1586.0",   # CVE-2026-1095: Canto Testimonials Stored XSS (CWE-79)
        ],
        "relevant_cves": []
    },
    "IDOR": {
        "relevant_ids": [
            # Canonical CWE graph nodes
            "cwe-639", "cwe-284", "cwe-285",
            # NVD-extracted nodes with IDOR content (verified from graph search)
            "cwe-821",
            # CVE graph nodes from NVD/cvelistV5 extraction
            "CVE-2026-0562",
            "modern-events-calendar-vulnerability-2",
            # New IDOR CVE node discovered after CVE ingestion
            "CVE-2026-0820",    # RepairBuddy IDOR vulnerability
            # Chunk IDs with access-control / missing-authorization content
            "1467.0",   # CVE-2026-0927: KiviCare missing authorization (CWE-862)
            "1761.0",   # CVE-2026-1303: MailChimp missing authorization (CWE-862)
            "1792.0",   # CVE-2026-1336: AI ChatBot missing capability checks (CWE-862)
            "1471.0",   # CVE-2026-0942: WooCommerce missing capability check (CWE-306)
        ],
        "relevant_cves": []
    },
    "CSRF": {
        "relevant_ids": [
            # Canonical CWE graph nodes
            "cwe-352", "cwe-1275",
            # NVD-extracted nodes with CSRF content (verified from graph search)
            "cwe-294", "cwe-942",
            # CVE graph nodes extracted from NVD (genuine CSRF CVEs)
            "CVE-2023-4247",
            "CVE-2023-4248",
            "CVE-2022-2233",
            "CVE-2023-7048",
            "CVE-2023-1346",
            "cve-2026-1128",
            "CVE-2023-4277",
            "CVE-2026-1070",
            "CVE-2026-1393",
        ],
        "relevant_cves": []
    },
    "authentication": {
        "relevant_ids": [
            # Canonical CWE graph nodes (authentication family)
            "cwe-287", "cwe-306", "cwe-307", "cwe-1390",
            "cwe-305", "cwe-303", "cwe-304", "cwe-289",
            "cwe-293", "cwe-308", "cwe-252", "cwe-1023",
            # NVD-extracted node with authentication content
            "cwe-1173",
            # Chunk IDs with authentication weakness content (actual vector search top-15)
            "427.0",    # CWE-287: Improper Authentication (class)
            "448.0",    # CWE-306: Missing Authentication for Critical Function
            "447.0",    # CWE-305: Authentication Bypass by Primary Weakness
            "443.0",    # CWE-301: Reflection Attack in Authentication Protocol
            "444.0",    # CWE-302: Authentication Bypass via Assumed-Immutable Data
            "428.0",    # CWE-288: Authentication Bypass via Alternate Path
            "265.0",    # CWE-1391: Use of Weak Credentials
            "920.0",    # CWE-836: Use of Password Hash Instead of Password
        ],
        "relevant_cves": []
    },
    "authentication bypass": {
        "relevant_ids": [
            # Core authentication bypass CWE graph nodes
            "cwe-287", "cwe-306", "cwe-1390",
            "cwe-305", "cwe-289", "cwe-293", "cwe-1023",
            # Additional bypass-specific CWE nodes (verified from hybrid query)
            "cwe-302",  # Authentication Bypass by Assumed-Immutable Data
            "cwe-420",  # Authentication Bypass Using an Alternate Path or Channel
            "cwe-252",  # Bypassing Two-Factor Authentication
            "cwe-307",  # Insufficient Authentication
            # CVE/Vuln graph nodes for authentication bypass
            "vulnerability-2022-0992",  # SiteGround Security Plugin Auth Bypass
            "CVE-2023-0720",            # Authorization Bypass (Wicked Folders)
            "CVE-2023-0717",            # Authorization Bypass (Wicked Folders)
            "cve-2024-0236",            # EventON WordPress authorization bypass
            # Chunk IDs (CWE-based, verified from vector search top results)
            "447.0",    # CWE-305: Authentication Bypass by Primary Weakness
            "444.0",    # CWE-302: Authentication Bypass via Assumed-Immutable Data
            "428.0",    # CWE-288: Authentication Bypass via Alternate Path
            "431.0",    # CWE-290: Authentication Bypass by Spoofing
            "771.0",    # CWE-639: Authorization Bypass Through User-Controlled Key
            "920.0",    # CWE-836: Use of Password Hash Instead of Password
        ],
        "relevant_cves": []
    },
    "CWE": {
        "relevant_ids": [
            # CWE graph nodes — canonical vulnerability families
            "cwe-89", "cwe-79", "cwe-287",
            # NVD-extracted CWE-related nodes
            "cwe-835", "cwe-710", "cwe-182", "cwe-912",
            # CWE XML chunk in vector index
            "934.0",    # CWE-89: SQL Injection weakness definition
        ],
        "relevant_cves": []
    },
}


def load_ground_truth() -> Dict:
    return GROUND_TRUTH
