"""Multi-format parsers - Support CWE XML, NVD CVE JSON, CVE List v5 JSON."""

import PyPDF2
import json
import csv
import asyncio
import xml.etree.ElementTree as ET
from io import StringIO, BytesIO
from bs4 import BeautifulSoup
from app.core.logger import logger

async def parse_document(file_bytes: bytes, content_type: str, filename: str) -> str:
    """Parse file thành text thuần - hỗ trợ CWE XML, CVE JSON."""
    try:
        # === PDF ===
        if content_type.startswith("application/pdf") or filename.lower().endswith(".pdf"):
            reader = PyPDF2.PdfReader(BytesIO(file_bytes))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text or ""

        # === JSON - Detect type (NVD, CVE List v5, or generic) ===
        elif content_type in ["application/json", "text/json"] or filename.lower().endswith(".json"):
            data = json.loads(file_bytes)
            
            # Detect format
            if isinstance(data, dict):
                if "vulnerabilities" in data:  # NVD format
                    return await parse_nvd_cve_json(data, filename)
                elif "cveMetadata" in data and "containers" in data:  # CVE v5 format
                    return await parse_cve_v5_json(data, filename)
                elif "vulnerabilities" in data or "version" in data and data.get("version") == "2.0":  # NVD
                    return await parse_nvd_cve_json(data, filename)
                else:
                    # Generic JSON
                    return json.dumps(data, indent=2, ensure_ascii=False)
            else:
                return json.dumps(data, indent=2, ensure_ascii=False)

        # === CSV ===
        elif content_type in ["text/csv", "application/csv"] or filename.lower().endswith(".csv"):
            text = ""
            csv_reader = csv.reader(StringIO(file_bytes.decode("utf-8", errors="replace")))
            for row in csv_reader:
                text += " | ".join(str(cell) for cell in row) + "\n"
            return text

        # === XML - Đặc biệt hỗ trợ CWE XML ===
        elif content_type in ["application/xml", "text/xml"] or filename.lower().endswith(".xml"):
            return await parse_cwe_xml(file_bytes, filename)

        # === Text formats (MD, TXT, HTML) ===
        else:
            return file_bytes.decode("utf-8", errors="replace")

    except Exception as e:
        logger.error("Parse failed", filename=filename, error=str(e))
        return file_bytes.decode("utf-8", errors="replace")


async def parse_cwe_xml(file_bytes: bytes, filename: str) -> str:
    """Parser chuyên biệt cho file XML CWE của MITRE."""
    try:
        tree = ET.fromstring(file_bytes)
        texts = []

        # Tìm tất cả các Weakness
        for weakness in tree.findall(".//Weakness"):
            cwe_id = weakness.get("ID")
            name = weakness.find("Name").text if weakness.find("Name") is not None else "Unknown"
            description = weakness.find("Description").text if weakness.find("Description") is not None else ""
            abstraction = weakness.get("Abstraction", "")
            status = weakness.get("Status", "")

            texts.append(f"CWE-{cwe_id}: {name}")
            texts.append(f"Abstraction: {abstraction} | Status: {status}")
            if description:
                texts.append(f"Description: {description.strip()}")

            # Related Weaknesses
            for rel in weakness.findall(".//Related_Weaknesses/Related_Weakness"):
                rel_id = rel.get("CWE_ID")
                nature = rel.get("Nature")
                if rel_id and nature:
                    texts.append(f"Related to CWE-{rel_id} ({nature})")

            # Consequences
            for cons in weakness.findall(".//Common_Consequences/Consequence"):
                scope = cons.find("Scope").text if cons.find("Scope") is not None else ""
                impact = cons.find("Impact").text if cons.find("Impact") is not None else ""
                if scope or impact:
                    texts.append(f"Consequence: {scope} - {impact}")

            texts.append("---")  # Phân cách các Weakness

        if texts:
            result = "\n".join(texts)
            logger.info("Parsed CWE XML successfully", filename=filename, weaknesses_count=len(texts)//3)
            return result
        else:
            logger.warning("No Weakness found in XML, fallback to raw text", filename=filename)
            return file_bytes.decode("utf-8", errors="replace")

    except ET.ParseError as e:
        logger.error("Invalid XML format", filename=filename, error=str(e))
        return file_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        logger.error("CWE XML parse failed", filename=filename, error=str(e))
        return file_bytes.decode("utf-8", errors="replace")


async def parse_nvd_cve_json(data: dict, filename: str) -> str:
    """Parser cho NVD CVE JSON format (v2.0)."""
    try:
        texts = []
        vulnerabilities = data.get("vulnerabilities", [])
        
        for vuln in vulnerabilities:
            cve = vuln.get("cve", {})
            cve_id = cve.get("id", "Unknown")
            
            texts.append(f"=== {cve_id} ===")
            
            # Description
            descriptions = cve.get("descriptions", [])
            if descriptions:
                for desc in descriptions:
                    value = desc.get("value", "")
                    if value:
                        texts.append(f"Description: {value}")
            
            # Weaknesses (CWE)
            weaknesses = cve.get("weaknesses", [])
            if weaknesses:
                cwe_ids = []
                for weakness in weaknesses:
                    descriptions = weakness.get("description", [])
                    for desc in descriptions:
                        cwe_value = desc.get("value", "")
                        if cwe_value and cwe_value not in cwe_ids:
                            cwe_ids.append(cwe_value)
                if cwe_ids:
                    texts.append(f"CWE: {', '.join(cwe_ids)}")
            
            # CVSS Scores
            metrics = cve.get("metrics", {})
            cvss_v3 = metrics.get("cvssMetricV31", [])
            cvss_v2 = metrics.get("cvssMetricV2", [])
            
            if cvss_v3:
                for metric in cvss_v3:
                    score = metric.get("cvssData", {}).get("baseScore", "N/A")
                    vector = metric.get("cvssData", {}).get("vectorString", "N/A")
                    severity = metric.get("cvssData", {}).get("baseSeverity", "N/A")
                    texts.append(f"CVSS v3.1: {score} ({severity}) - {vector}")
            
            if cvss_v2:
                for metric in cvss_v2:
                    score = metric.get("cvssData", {}).get("baseScore", "N/A")
                    severity = metric.get("baseSeverity", "N/A")
                    texts.append(f"CVSS v2.0: {score} ({severity})")
            
            # References
            references = cve.get("references", [])
            if references:
                refs = [ref.get("url", "") for ref in references[:3] if ref.get("url")]
                if refs:
                    texts.append(f"References: {'; '.join(refs)}")
            
            texts.append("---")
        
        result = "\n".join(texts)
        logger.info("Parsed NVD CVE JSON successfully", filename=filename, cves_count=len(vulnerabilities))
        return result
        
    except Exception as e:
        logger.error("NVD CVE JSON parse failed", filename=filename, error=str(e))
        return json.dumps(data, indent=2, ensure_ascii=False)[:2000]


async def parse_cve_v5_json(data: dict, filename: str) -> str:
    """Parser cho CVE List v5 JSON format."""
    try:
        texts = []
        
        # CVE Metadata
        cve_metadata = data.get("cveMetadata", {})
        cve_id = cve_metadata.get("cveId", "Unknown")
        
        texts.append(f"=== {cve_id} ===")
        texts.append(f"State: {cve_metadata.get('state', 'N/A')}")
        texts.append(f"Published: {cve_metadata.get('datePublished', 'N/A')}")
        texts.append(f"Updated: {cve_metadata.get('dateUpdated', 'N/A')}")
        
        # Container data (CNA - CVE Numbering Authority)
        containers = data.get("containers", {})
        cna = containers.get("cna", {})
        
        # Descriptions
        descriptions = cna.get("descriptions", [])
        if descriptions:
            for desc in descriptions:
                value = desc.get("value", "")
                if value:
                    texts.append(f"Description: {value}")
        
        # Affected products
        affected = cna.get("affected", [])
        if affected:
            for item in affected[:5]:  # Limit to first 5
                vendor = item.get("vendor", "N/A")
                product = item.get("product", "N/A")
                versions = item.get("versions", [])
                texts.append(f"Affected: {vendor} - {product}")
                if versions and len(versions) <= 3:
                    texts.append(f"  Versions: {', '.join([v.get('version', 'N/A') for v in versions])}")
        
        # Problem Types (CWE)
        problem_types = cna.get("problemTypes", [])
        if problem_types:
            cwes = []
            for pt in problem_types:
                descriptions = pt.get("descriptions", [])
                for desc in descriptions:
                    cwe_id = desc.get("cweId", "")
                    if cwe_id and cwe_id not in cwes:
                        cwes.append(cwe_id)
            if cwes:
                texts.append(f"CWE: {', '.join(cwes)}")
        
        # References
        references = cna.get("references", [])
        if references:
            refs = [ref.get("url", "") for ref in references[:3] if ref.get("url")]
            if refs:
                texts.append(f"References: {'; '.join(refs)}")
        
        texts.append("---")
        
        result = "\n".join(texts)
        logger.info("Parsed CVE v5 JSON successfully", filename=filename, cve_id=cve_id)
        return result
        
    except Exception as e:
        logger.error("CVE v5 JSON parse failed", filename=filename, error=str(e))
        return json.dumps(data, indent=2, ensure_ascii=False)[:2000]