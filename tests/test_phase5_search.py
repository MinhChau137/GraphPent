"""Integration tests for advanced search and filtering (Phase 5.3)."""

import pytest
from typing import Dict, List, Any
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from app.domain.schemas.search import (
    SearchJobsRequest,
    SearchFindingsRequest,
    SeverityEnum,
    JobStatusFilterEnum,
)
from app.services.search_service import get_search_service, SearchService
from app.adapters.elasticsearch_client import ElasticsearchClient


# Test fixtures
@pytest.fixture
def mock_es_client():
    """Create a mock Elasticsearch client."""
    return MagicMock(spec=ElasticsearchClient)


@pytest.fixture
async def search_service():
    """Get search service."""
    return await get_search_service()


# Test Classes
class TestElasticsearchClient:
    """Tests for Elasticsearch client."""

    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test Elasticsearch client initializes."""
        client = ElasticsearchClient(hosts=["localhost:9200"])
        assert client is not None
        assert client.hosts == ["localhost:9200"]

    @pytest.mark.asyncio
    async def test_index_names_defined(self):
        """Test index names are correctly defined."""
        assert ElasticsearchClient.INDEX_JOBS == "graphpent-jobs"
        assert ElasticsearchClient.INDEX_RESULTS == "graphpent-results"
        assert ElasticsearchClient.INDEX_FINDINGS == "graphpent-findings"

    @pytest.mark.asyncio
    async def test_get_jobs_mapping(self):
        """Test jobs index mapping."""
        mapping = ElasticsearchClient._get_jobs_mapping()
        
        assert "properties" in mapping
        assert "job_id" in mapping["properties"]
        assert "status" in mapping["properties"]
        assert "priority" in mapping["properties"]
        assert "target_url" in mapping["properties"]
        
        # Verify field types
        assert mapping["properties"]["job_id"]["type"] == "keyword"
        assert mapping["properties"]["status"]["type"] == "keyword"
        assert mapping["properties"]["priority"]["type"] == "integer"
        assert mapping["properties"]["target_url"]["type"] == "text"

    @pytest.mark.asyncio
    async def test_get_findings_mapping(self):
        """Test findings index mapping."""
        mapping = ElasticsearchClient._get_findings_mapping()
        
        assert "properties" in mapping
        assert "finding_id" in mapping["properties"]
        assert "severity" in mapping["properties"]
        assert "cve_ids" in mapping["properties"]
        assert "cwe_ids" in mapping["properties"]
        
        # Verify field types
        assert mapping["properties"]["finding_id"]["type"] == "keyword"
        assert mapping["properties"]["severity"]["type"] == "keyword"
        assert mapping["properties"]["cve_ids"]["type"] == "keyword"


class TestJobSearch:
    """Tests for job search functionality."""

    @pytest.mark.asyncio
    async def test_search_jobs_request_creation(self):
        """Test creating a search jobs request."""
        request = SearchJobsRequest(
            query="SQL injection",
            status=JobStatusFilterEnum.COMPLETED,
            target_url="https://example.com",
            priority_min=5,
            priority_max=10,
            page=1,
            size=20,
        )
        
        assert request.query == "SQL injection"
        assert request.status == JobStatusFilterEnum.COMPLETED
        assert request.target_url == "https://example.com"
        assert request.priority_min == 5
        assert request.priority_max == 10
        assert request.page == 1
        assert request.size == 20

    @pytest.mark.asyncio
    async def test_search_jobs_with_defaults(self):
        """Test search jobs request with default values."""
        request = SearchJobsRequest()
        
        assert request.query is None
        assert request.status is None
        assert request.page == 1
        assert request.size == 20

    @pytest.mark.asyncio
    async def test_search_jobs_date_filtering(self):
        """Test date filtering in job search."""
        date_from = datetime(2026, 4, 1)
        date_to = datetime(2026, 4, 30)
        
        request = SearchJobsRequest(
            date_from=date_from,
            date_to=date_to,
        )
        
        assert request.date_from == date_from
        assert request.date_to == date_to

    @pytest.mark.asyncio
    async def test_search_jobs_priority_validation(self):
        """Test priority validation."""
        # Valid priorities
        request = SearchJobsRequest(priority_min=1, priority_max=10)
        assert request.priority_min == 1
        assert request.priority_max == 10


class TestFindingsSearch:
    """Tests for findings search functionality."""

    @pytest.mark.asyncio
    async def test_search_findings_request_creation(self):
        """Test creating a search findings request."""
        request = SearchFindingsRequest(
            query="XSS vulnerability",
            severity=SeverityEnum.CRITICAL,
            cve_id="CVE-2024-1234",
            cwe_id="CWE-79",
            page=1,
            size=20,
        )
        
        assert request.query == "XSS vulnerability"
        assert request.severity == SeverityEnum.CRITICAL
        assert request.cve_id == "CVE-2024-1234"
        assert request.cwe_id == "CWE-79"
        assert request.page == 1
        assert request.size == 20

    @pytest.mark.asyncio
    async def test_search_findings_severity_enum(self):
        """Test severity enum values."""
        assert SeverityEnum.CRITICAL.value == "CRITICAL"
        assert SeverityEnum.HIGH.value == "HIGH"
        assert SeverityEnum.MEDIUM.value == "MEDIUM"
        assert SeverityEnum.LOW.value == "LOW"
        assert SeverityEnum.INFO.value == "INFO"

    @pytest.mark.asyncio
    async def test_search_findings_with_job_filter(self):
        """Test filtering findings by job ID."""
        request = SearchFindingsRequest(
            job_id="test-job-001",
        )
        
        assert request.job_id == "test-job-001"

    @pytest.mark.asyncio
    async def test_search_findings_pagination(self):
        """Test findings pagination."""
        request = SearchFindingsRequest(
            page=5,
            size=50,
        )
        
        assert request.page == 5
        assert request.size == 50


class TestSearchService:
    """Tests for search service."""

    @pytest.mark.asyncio
    async def test_search_service_singleton(self):
        """Test search service singleton pattern."""
        service1 = await get_search_service()
        service2 = await get_search_service()
        
        # Both should be same instance (after initialization)
        assert service1 is service2

    @pytest.mark.asyncio
    async def test_search_service_initialization(self, search_service):
        """Test search service initializes."""
        assert search_service is not None
        assert isinstance(search_service, SearchService)

    @pytest.mark.asyncio
    async def test_index_job_from_queue(self, search_service):
        """Test indexing a job from queue."""
        with patch.object(search_service, '_get_es_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.index_job.return_value = True
            mock_get_client.return_value = mock_client
            
            search_service.es_client = mock_client
            
            result = await search_service.index_job_from_queue(
                job_id="test-job-001",
                job_type="scan",
                status="completed",
                priority=8,
                target_url="https://example.com",
                findings_count=42,
            )
            
            # Verify method was called (mock verification)
            mock_client.index_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_index_finding(self, search_service):
        """Test indexing a finding."""
        with patch.object(search_service, '_get_es_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.index_finding.return_value = True
            mock_get_client.return_value = mock_client
            
            search_service.es_client = mock_client
            
            result = await search_service.index_finding(
                finding_id="finding-001",
                job_id="job-001",
                template_id="xss-reflection",
                target_url="https://example.com",
                severity="CRITICAL",
                host="example.com",
                url="https://example.com/search?q=test",
                cve_ids=["CVE-2024-1234"],
                cwe_ids=["CWE-79"],
            )
            
            mock_client.index_finding.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_job_all_data(self, search_service):
        """Test deleting all data for a job."""
        with patch.object(search_service, '_get_es_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.delete_job_data.return_value = True
            mock_get_client.return_value = mock_client
            
            search_service.es_client = mock_client
            
            result = await search_service.delete_job_all_data("job-001")
            
            mock_client.delete_job_data.assert_called_once_with("job-001")


class TestSearchFiltering:
    """Tests for search filtering options."""

    @pytest.mark.asyncio
    async def test_job_status_filter_enum(self):
        """Test job status filter enum."""
        assert JobStatusFilterEnum.PENDING.value == "pending"
        assert JobStatusFilterEnum.RUNNING.value == "running"
        assert JobStatusFilterEnum.COMPLETED.value == "completed"
        assert JobStatusFilterEnum.FAILED.value == "failed"
        assert JobStatusFilterEnum.CANCELLED.value == "cancelled"

    @pytest.mark.asyncio
    async def test_search_with_multiple_filters(self):
        """Test search with multiple filters applied."""
        request = SearchJobsRequest(
            query="SQL injection",
            status=JobStatusFilterEnum.COMPLETED,
            target_url="https://example.com",
            priority_min=5,
            priority_max=10,
            date_from=datetime(2026, 4, 1),
            date_to=datetime(2026, 4, 30),
            page=1,
            size=20,
        )
        
        # All filters should be set
        assert request.query is not None
        assert request.status is not None
        assert request.target_url is not None
        assert request.priority_min is not None
        assert request.priority_max is not None
        assert request.date_from is not None
        assert request.date_to is not None

    @pytest.mark.asyncio
    async def test_search_findings_with_cve_filter(self):
        """Test findings search with CVE filter."""
        request = SearchFindingsRequest(
            cve_id="CVE-2024-1234",
        )
        
        assert request.cve_id == "CVE-2024-1234"
        assert request.cwe_id is None

    @pytest.mark.asyncio
    async def test_search_findings_with_cwe_filter(self):
        """Test findings search with CWE filter."""
        request = SearchFindingsRequest(
            cwe_id="CWE-79",
        )
        
        assert request.cwe_id == "CWE-79"
        assert request.cve_id is None


class TestSearchPagination:
    """Tests for pagination in search results."""

    @pytest.mark.asyncio
    async def test_pagination_defaults(self):
        """Test pagination defaults."""
        request = SearchJobsRequest()
        
        assert request.page == 1
        assert request.size == 20

    @pytest.mark.asyncio
    async def test_pagination_custom_values(self):
        """Test custom pagination values."""
        request = SearchJobsRequest(page=5, size=50)
        
        assert request.page == 5
        assert request.size == 50

    @pytest.mark.asyncio
    async def test_pagination_max_size(self):
        """Test pagination size limit."""
        # Size should be validated (max 100)
        request = SearchJobsRequest(size=100)
        assert request.size == 100


class TestHealthCheck:
    """Tests for health check functionality."""

    @pytest.mark.asyncio
    async def test_search_service_health_check(self, search_service):
        """Test search service health check."""
        with patch.object(search_service, '_get_es_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.health_check.return_value = True
            mock_get_client.return_value = mock_client
            
            search_service.es_client = mock_client
            
            result = await search_service.health_check()
            
            mock_client.health_check.assert_called_once()


class TestErrorHandling:
    """Tests for error handling in search service."""

    @pytest.mark.asyncio
    async def test_search_jobs_error_handling(self, search_service):
        """Test error handling in job search."""
        request = SearchJobsRequest(query="test")
        
        with patch.object(search_service, '_get_es_client') as mock_get_client:
            mock_get_client.side_effect = Exception("Connection failed")
            
            # Should handle error gracefully and return empty results
            result = await search_service.search_jobs(request)
            
            assert result.results == []
            assert result.total == 0

    @pytest.mark.asyncio
    async def test_search_findings_error_handling(self, search_service):
        """Test error handling in findings search."""
        request = SearchFindingsRequest(query="test")
        
        with patch.object(search_service, '_get_es_client') as mock_get_client:
            mock_get_client.side_effect = Exception("Connection failed")
            
            result = await search_service.search_findings(request)
            
            assert result.results == []
            assert result.total == 0
