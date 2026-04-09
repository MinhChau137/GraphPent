"""Multi-format parsers - UPDATED để hỗ trợ CWE XML."""

import PyPDF2
import json
import csv
import asyncio
import xml.etree.ElementTree as ET
from io import StringIO, BytesIO
from bs4 import BeautifulSoup
from app.core.logger import logger

async def parse_document(file_bytes: bytes, content_type: str, filename: str) -> str:
    """Parse file thành text thuần - hỗ trợ CWE XML."""
    try:
        # === PDF ===
        if content_type.startswith("application/pdf") or filename.lower().endswith(".pdf"):
            reader = PyPDF2.PdfReader(BytesIO(file_bytes))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text or ""

        # === JSON ===
        elif content_type in ["application/json", "text/json"] or filename.lower().endswith(".json"):
            data = json.loads(file_bytes)
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

        # === Text formats (MD, TXT, HTML, XML thông thường) ===
        else:
            return file_bytes.decode("utf-8", errors="replace")

    except Exception as e:
        logger.error("Parse failed", filename=filename, error=str(e))
        # Fallback cuối cùng
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