"""Multi-format parsers - Phase 4."""

import PyPDF2
import json
import csv
from io import StringIO, BytesIO
from bs4 import BeautifulSoup
from langchain_community.document_loaders import TextLoader
from app.core.logger import logger

async def parse_document(file_bytes: bytes, content_type: str, filename: str) -> str:
    """Parse file thành text thuần."""
    try:
        logger.info("Starting document parsing", filename=filename, content_type=content_type, file_bytes_type=type(file_bytes), is_bytes=isinstance(file_bytes, bytes))
        
        if not isinstance(file_bytes, bytes):
            raise ValueError(f"file_bytes must be bytes, got {type(file_bytes)}")
        
        if content_type.startswith("application/pdf") or filename.endswith(".pdf"):
            logger.info("Parsing as PDF", filename=filename)
            reader = PyPDF2.PdfReader(BytesIO(file_bytes))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text

        elif content_type in ["application/json", "text/json"] or filename.endswith(".json"):
            logger.info("Parsing as JSON", filename=filename)
            data = json.loads(file_bytes)
            return json.dumps(data, indent=2, ensure_ascii=False)

        elif content_type in ["text/csv", "application/csv"] or filename.endswith(".csv"):
            logger.info("Parsing as CSV", filename=filename)
            text = ""
            csv_reader = csv.reader(StringIO(file_bytes.decode("utf-8")))
            for row in csv_reader:
                text += " | ".join(row) + "\n"
            return text

        elif content_type.startswith("text/") or filename.endswith((".md", ".txt", ".xml", ".html")):
            logger.info("Parsing as text", filename=filename)
            return file_bytes.decode("utf-8", errors="replace")

        else:
            logger.warning("Unsupported format, fallback to text", filename=filename)
            return file_bytes.decode("utf-8", errors="replace")

    except Exception as e:
        logger.error("Parse failed", filename=filename, error=str(e), error_type=type(e).__name__)
        import traceback
        logger.error("Parse traceback", traceback=traceback.format_exc())
        raise ValueError(f"Cannot parse {filename}: {str(e)}")