"""Chunking pipeline - recursive character text splitter."""

from langchain.text_splitter import RecursiveCharacterTextSplitter
from typing import List, Dict
import hashlib
from app.core.logger import logger

def generate_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

async def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> List[Dict]:
    """Chunk + metadata."""
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
            "metadata": {"chunk_size": len(chunk)}
        })

    logger.info("Text chunked", chunks_count=len(result))
    return result