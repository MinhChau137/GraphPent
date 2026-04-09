import pytest
from app.services.extraction_service import ExtractionService

@pytest.mark.asyncio
async def test_extract_cve(sample_cve_json):
    service = ExtractionService()
    # Giả sử chunk_id = 1 đã tồn tại
    result = await service.extract_from_chunk(1)
    assert result.error is None
    assert len(result.entities) >= 1