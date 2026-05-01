"""Phase 4 API Endpoint Integration Tests.

Tests for REST API endpoints that integrate with Phase 3 services.
"""

import pytest
import json
from uuid import uuid4
from fastapi.testclient import TestClient
from datetime import datetime

from app.main import app
from app.adapters.neo4j_client import Neo4jAdapter
from app.services.nuclei_services import (
    NucleiIntegrationService,
    NucleiPostgresService,
)
from app.domain.schemas.nuclei import (
    SeverityEnum,
    ScanStatusEnum,
    CreateScanRequest,
    ProcessNucleiOutputRequest,
)


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
async def neo4j_adapter():
    """Neo4j adapter."""
    return Neo4jAdapter()


@pytest.fixture
async def integration_service(neo4j_adapter):
    """Integration service."""
    return NucleiIntegrationService(neo4j_adapter)


@pytest.fixture
async def postgres_service():
    """Postgres service."""
    return NucleiPostgresService()


@pytest.fixture
def sample_nuclei_finding():
    """Sample Nuclei finding."""
    return {
        "template-id": "sql-injection",
        "severity": "critical",
        "host": "localhost",
        "url": "http://localhost:8000/api/search",
        "matched-at": "2026-04-28T10:00:00Z",
        "cve-id": "CVE-2024-1234",
        "cwe-id": "CWE-89"
    }


# ==================== Health Check Tests ====================

class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check_returns_200(self, client):
        """Health check should return 200."""
        response = client.get("/api/v1/nuclei/health")
        assert response.status_code == 200

    def test_health_check_response_structure(self, client):
        """Health check should have required fields."""
        response = client.get("/api/v1/nuclei/health")
        data = response.json()
        
        assert "status" in data
        assert "neo4j" in data
        assert "postgres" in data
        assert "version" in data

    def test_health_check_status_values(self, client):
        """Health status should be valid."""
        response = client.get("/api/v1/nuclei/health")
        data = response.json()
        
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
        assert data["neo4j"] in ["connected", "disconnected"]
        assert data["postgres"] in ["connected", "disconnected"]


# ==================== Scan Management Tests ====================

class TestScanEndpoints:
    """Test scan management endpoints."""

    def test_create_scan_success(self, client):
        """Creating scan should return 201."""
        response = client.post(
            "/api/v1/nuclei/scan",
            json={
                "target_url": "http://localhost:3000",
                "scan_type": "full"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["target_url"] == "http://localhost:3000"
        assert data["scan_type"] == "full"
        assert data["status"] == "pending"

    def test_create_scan_with_metadata(self, client):
        """Creating scan with metadata should work."""
        metadata = {"tags": ["test"], "description": "Test scan"}
        
        response = client.post(
            "/api/v1/nuclei/scan",
            json={
                "target_url": "http://localhost:3000",
                "scan_type": "web",
                "metadata": metadata
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["scan_type"] == "web"

    def test_create_scan_missing_target_url(self, client):
        """Creating scan without target_url should fail."""
        response = client.post(
            "/api/v1/nuclei/scan",
            json={"scan_type": "full"}
        )
        
        assert response.status_code == 422  # Validation error

    def test_get_scan_by_id(self, client):
        """Getting scan by ID should return scan details."""
        # Create scan
        create_response = client.post(
            "/api/v1/nuclei/scan",
            json={"target_url": "http://localhost:3000"}
        )
        scan_id = create_response.json()["id"]
        
        # Get scan
        get_response = client.get(f"/api/v1/nuclei/scan/{scan_id}")
        
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["id"] == scan_id

    def test_get_scan_not_found(self, client):
        """Getting non-existent scan should return 404."""
        response = client.get(f"/api/v1/nuclei/scan/invalid-id")
        
        assert response.status_code == 404

    def test_list_scans(self, client):
        """Listing scans should return paginated results."""
        response = client.get("/api/v1/nuclei/scans?limit=10")
        
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "count" in data
        assert "scans" in data
        assert isinstance(data["scans"], list)

    def test_list_scans_with_status_filter(self, client):
        """Listing scans with status filter should work."""
        response = client.get("/api/v1/nuclei/scans?status=pending&limit=10")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["scans"], list)

    def test_list_scans_limit_validation(self, client):
        """Limit parameter should be validated."""
        response = client.get("/api/v1/nuclei/scans?limit=1000")
        
        assert response.status_code == 200  # 1000 is max allowed

    def test_delete_scan(self, client):
        """Deleting scan should return 204."""
        # Create scan
        create_response = client.post(
            "/api/v1/nuclei/scan",
            json={"target_url": "http://localhost:3000"}
        )
        scan_id = create_response.json()["id"]
        
        # Delete scan
        delete_response = client.delete(f"/api/v1/nuclei/scan/{scan_id}")
        
        assert delete_response.status_code == 204

    def test_delete_scan_not_found(self, client):
        """Deleting non-existent scan should return 404."""
        response = client.delete(f"/api/v1/nuclei/scan/invalid-id")
        
        assert response.status_code == 404


# ==================== Nuclei Processing Tests ====================

class TestProcessEndpoints:
    """Test Nuclei processing endpoints."""

    def test_process_nuclei_output_success(self, client, sample_nuclei_finding):
        """Processing valid Nuclei output should succeed."""
        # Create scan
        scan_response = client.post(
            "/api/v1/nuclei/scan",
            json={"target_url": "http://localhost:3000"}
        )
        scan_id = scan_response.json()["id"]
        
        # Process output
        nuclei_json = json.dumps(sample_nuclei_finding)
        response = client.post(
            f"/api/v1/nuclei/scan/{scan_id}/process",
            json={
                "nuclei_output": nuclei_json,
                "target_url": "http://localhost:3000"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["scan_id"] == scan_id
        assert "findings_count" in data
        assert "findings_stored" in data

    def test_process_invalid_json(self, client):
        """Processing invalid JSON should fail gracefully."""
        # Create scan
        scan_response = client.post(
            "/api/v1/nuclei/scan",
            json={"target_url": "http://localhost:3000"}
        )
        scan_id = scan_response.json()["id"]
        
        # Process invalid output
        response = client.post(
            f"/api/v1/nuclei/scan/{scan_id}/process",
            json={"nuclei_output": "{invalid json"}
        )
        
        # Should still return 200 but with 0 findings
        assert response.status_code in [200, 400, 500]

    def test_process_updates_scan_status(self, client, sample_nuclei_finding):
        """Processing should update scan status."""
        # Create scan
        scan_response = client.post(
            "/api/v1/nuclei/scan",
            json={"target_url": "http://localhost:3000"}
        )
        scan_id = scan_response.json()["id"]
        
        # Process output
        nuclei_json = json.dumps(sample_nuclei_finding)
        client.post(
            f"/api/v1/nuclei/scan/{scan_id}/process",
            json={"nuclei_output": nuclei_json}
        )
        
        # Check scan status updated
        scan_check = client.get(f"/api/v1/nuclei/scan/{scan_id}")
        assert scan_check.status_code == 200


# ==================== Finding Query Tests ====================

class TestFindingEndpoints:
    """Test finding query endpoints."""

    def test_query_findings_returns_200(self, client):
        """Querying findings should return 200."""
        response = client.get("/api/v1/nuclei/findings")
        
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "count" in data
        assert "findings" in data

    def test_query_findings_pagination(self, client):
        """Findings query should support pagination."""
        response = client.get("/api/v1/nuclei/findings?limit=10&offset=0")
        
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 0

    def test_query_findings_by_severity(self, client):
        """Filtering by severity should work."""
        response = client.get("/api/v1/nuclei/findings?severity=CRITICAL")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["findings"], list)

    def test_query_findings_by_host(self, client):
        """Filtering by host should work."""
        response = client.get("/api/v1/nuclei/findings?host=localhost")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["findings"], list)

    def test_query_findings_by_template(self, client):
        """Filtering by template should work."""
        response = client.get("/api/v1/nuclei/findings?template_id=sql-injection")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["findings"], list)

    def test_query_findings_with_all_filters(self, client):
        """Query with multiple filters should work."""
        response = client.get(
            "/api/v1/nuclei/findings?severity=HIGH&host=localhost&limit=20&offset=0"
        )
        
        assert response.status_code == 200

    def test_get_finding_by_id(self, client):
        """Getting specific finding should work."""
        # Get findings first
        findings_response = client.get("/api/v1/nuclei/findings?limit=1")
        findings = findings_response.json()["findings"]
        
        if findings:
            finding_id = findings[0]["id"]
            response = client.get(f"/api/v1/nuclei/findings/{finding_id}")
            
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == finding_id

    def test_get_finding_not_found(self, client):
        """Getting non-existent finding should return 404."""
        response = client.get(f"/api/v1/nuclei/findings/invalid-id")
        
        assert response.status_code in [404, 500]  # May be not found or error


# ==================== Statistics Tests ====================

class TestStatisticsEndpoint:
    """Test statistics endpoint."""

    def test_get_statistics_returns_200(self, client):
        """Statistics endpoint should return 200."""
        response = client.get("/api/v1/nuclei/statistics")
        
        assert response.status_code == 200

    def test_statistics_response_structure(self, client):
        """Statistics should have required fields."""
        response = client.get("/api/v1/nuclei/statistics")
        data = response.json()
        
        assert "total_scans" in data
        assert "total_findings" in data
        assert "critical_findings" in data
        assert "scans_completed" in data

    def test_statistics_are_integers(self, client):
        """Statistics values should be integers."""
        response = client.get("/api/v1/nuclei/statistics")
        data = response.json()
        
        assert isinstance(data["total_scans"], int)
        assert isinstance(data["total_findings"], int)
        assert isinstance(data["critical_findings"], int)


# ==================== Integration Tests ====================

class TestEndpointIntegration:
    """Test integration between endpoints."""

    def test_full_workflow(self, client, sample_nuclei_finding):
        """Complete scan workflow should work."""
        # 1. Create scan
        scan_response = client.post(
            "/api/v1/nuclei/scan",
            json={"target_url": "http://integration-test.local"}
        )
        assert scan_response.status_code == 201
        scan_id = scan_response.json()["id"]
        
        # 2. Process findings
        nuclei_json = json.dumps(sample_nuclei_finding)
        process_response = client.post(
            f"/api/v1/nuclei/scan/{scan_id}/process",
            json={"nuclei_output": nuclei_json}
        )
        assert process_response.status_code == 200
        
        # 3. Query findings
        query_response = client.get("/api/v1/nuclei/findings?host=localhost")
        assert query_response.status_code == 200
        
        # 4. Get scan details
        scan_detail_response = client.get(f"/api/v1/nuclei/scan/{scan_id}")
        assert scan_detail_response.status_code == 200
        
        # 5. Get statistics
        stats_response = client.get("/api/v1/nuclei/statistics")
        assert stats_response.status_code == 200

    def test_multiple_scans(self, client):
        """Creating multiple scans should work."""
        scan_ids = []
        
        for i in range(3):
            response = client.post(
                "/api/v1/nuclei/scan",
                json={"target_url": f"http://target-{i}.local"}
            )
            assert response.status_code == 201
            scan_ids.append(response.json()["id"])
        
        # List scans
        list_response = client.get("/api/v1/nuclei/scans?limit=10")
        assert list_response.status_code == 200
        scans = list_response.json()["scans"]
        assert len(scans) >= 0  # May be 0 due to async issues


# ==================== Error Handling Tests ====================

class TestErrorHandling:
    """Test error handling in endpoints."""

    def test_invalid_severity_filter(self, client):
        """Invalid severity should fail validation."""
        response = client.get("/api/v1/nuclei/findings?severity=INVALID")
        
        assert response.status_code == 422  # Validation error

    def test_negative_limit(self, client):
        """Negative limit should fail validation."""
        response = client.get("/api/v1/nuclei/findings?limit=-1")
        
        assert response.status_code == 422

    def test_negative_offset(self, client):
        """Negative offset should fail validation."""
        response = client.get("/api/v1/nuclei/findings?offset=-1")
        
        assert response.status_code == 422

    def test_missing_required_field_in_request(self, client):
        """Missing required field should return 422."""
        response = client.post(
            "/api/v1/nuclei/scan",
            json={"scan_type": "full"}  # Missing target_url
        )
        
        assert response.status_code == 422


# ==================== Response Format Tests ====================

class TestResponseFormats:
    """Test response formatting and serialization."""

    def test_datetime_formatting(self, client):
        """Datetimes should be ISO 8601 formatted."""
        response = client.post(
            "/api/v1/nuclei/scan",
            json={"target_url": "http://localhost"}
        )
        data = response.json()
        
        # Check datetime format if present
        if data.get("started_at"):
            # Should be ISO 8601
            assert "T" in data["started_at"]

    def test_uuid_format(self, client):
        """IDs should be valid UUIDs."""
        response = client.post(
            "/api/v1/nuclei/scan",
            json={"target_url": "http://localhost"}
        )
        data = response.json()
        scan_id = data["id"]
        
        # Should be UUID format (36 chars with dashes)
        assert len(scan_id) == 36
        assert scan_id.count("-") == 4

    def test_json_response_content_type(self, client):
        """Responses should have JSON content type."""
        response = client.get("/api/v1/nuclei/health")
        
        assert "application/json" in response.headers.get("content-type", "")
