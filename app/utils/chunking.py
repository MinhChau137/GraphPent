"""Chunking pipeline - recursive character text splitter with XML-aware chunking."""

from langchain.text_splitter import RecursiveCharacterTextSplitter
from typing import List, Dict
import hashlib
import re
from app.core.logger import logger

def generate_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def chunk_xml_by_weakness(text: str) -> List[str]:
    """Chunk XML by individual Weakness entries for CWE catalog."""
    # Pattern to match complete Weakness entries
    weakness_pattern = r'<Weakness[^>]*>.*?</Weakness>'

    # Find all Weakness entries
    weaknesses = re.findall(weakness_pattern, text, re.DOTALL)

    if weaknesses:
        logger.info(f"Found {len(weaknesses)} Weakness entries in XML")
        return weaknesses
    else:
        # Fallback to regular chunking if no Weakness entries found
        logger.warning("No Weakness entries found, falling back to regular chunking")
        return []

async def chunk_text(text: str, chunk_size: int = 8000, chunk_overlap: int = 500) -> List[Dict]:
    """Chunk + metadata với XML-aware strategy."""

    # Detect if this is CWE XML
    if '<Weakness_Catalog' in text and '<Weakness ID=' in text:
        logger.info("Detected CWE XML, using Weakness-based chunking")
        weakness_chunks = chunk_xml_by_weakness(text)

        if weakness_chunks:
            result = []
            for i, chunk in enumerate(weakness_chunks):
                chunk_hash = generate_hash(chunk)
                result.append({
                    "content": chunk,
                    "chunk_index": i,
                    "hash": chunk_hash,
                    "metadata": {
                        "chunk_size": len(chunk),
                        "chunk_type": "weakness_xml",
                        "weakness_count": 1
                    }
                })
            logger.info(f"XML chunked into {len(result)} Weakness entries")
            return result

    # Default chunking for other content types
    logger.info(f"Using default chunking with size {chunk_size}")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_text(text)

    result = []
    for i, chunk in enumerate(chunks):
        chunk_hash = generate_hash(chunk)
        result.append({
            "content": chunk,
            "chunk_index": i,
            "hash": chunk_hash,
            "metadata": {
                "chunk_size": len(chunk),
                "chunk_type": "text"
            }
        })

    logger.info("Text chunked", chunks_count=len(result), total_chars=sum(len(c["content"]) for c in result))
    return result