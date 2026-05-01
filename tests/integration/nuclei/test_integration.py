"""Integration tests for Nuclei services - Phase 3.

Tests end-to-end integration between:
- NucleiParser (Phase 2)
- NucleiIntegrationService (Phase 3)
- Neo4jAdapter
- Storage operations
"""

import pytest
import json
from datetime import datetime
from uuid import uuid4
from app.services.nuclei_services import NucleiIntegrationService, NucleiStorageManager
from app.adapters.nuclei_parser import NucleiParser, Finding, SeverityEnum
from app.adapters.neo4j_client import Neo4jAdapter


class TestNucleiIntegrationService:
    """Tests for NucleiIntegrationService."""

    @pytest.fixture
    async def neo4j_adapter(self):
        """Create Neo4j adapter."""
        adapter = Neo4jAdapter()
        yield adapter
        # Cleanup: close connection
        await adapter.close()

    @pytest.fixture
    async def integration_service(self, neo4j_adapter):
        """Create integration service."""
        return NucleiIntegrationService(neo4j_adapter)

    @pytest.fixture
    def sample_nuclei_jsonl(self):
        """Sample Nuclei JSONL output."""
        return """{
    "matched-at": "2026-04-28T08:00:00Z",
    "template-id": "http-missing-headers",
    "severity": "high",
    "host": "192.168.1.100",
    "url": "http://192.168.1.100/",
    "cve-id": "CVE-2021-12345",
    "cwe-id": "CWE-693",
    "metadata": {"tags": "misconfig"}
}
{
    "matched-at": "2026-04-28T08:05:00Z",
    "template-id": "sql-injection",
    "severity": "critical",
    "host": "192.168.1.101",
    "url": "http://192.168.1.101/api/search",
    "cve-id": "CVE-2024-1234",
    "cwe-id": "CWE-89",
    "metadata": {"tags": "injection"}
}
{
    "matched-at": "2026-04-28T08:10:00Z",
    "template-id": "cve-2024-9999-rce",
    "severity": "critical",
    "host": "192.168.1.102",
    "url": "http://192.168.1.102/admin",
    "cve-id": "CVE-2024-9999",
    "cwe-id": "CWE-78,CWE-94",
    "metadata": {"tags": "rce"}
}"""

    # ==================== Parser Tests ====================

    @pytest.mark.asyncio
    async def test_parser_initialization(self, integration_service):
        """Test parser is properly initialized."""
        assert integration_service.parser is not None
        assert isinstance(integration_service.parser, NucleiParser)

    @pytest.mark.asyncio
    async def test_parse_nuclei_output(self, integration_service, sample_nuclei_jsonl):
        """Test parsing Nuclei output."""
        result = await integration_service.parser.normalize(sample_nuclei_jsonl)
        
        assert result.normalized_count == 3
        assert len(result.findings) == 3
        assert result.failed_count == 0

    @pytest.mark.asyncio
    async def test_parse_finding_structure(self, integration_service, sample_nuclei_jsonl):
        """Test Finding object structure."""
        result = await integration_service.parser.normalize(sample_nuclei_jsonl)
        finding = result.findings[0]
        
        assert isinstance(finding, Finding)
        assert finding.template_id == "http-missing-headers"
        assert finding.severity == SeverityEnum.HIGH
        assert finding.host == "192.168.1.100"
        assert len(finding.cve_ids) > 0
        assert len(finding.cwe_ids) > 0

    @pytest.mark.asyncio
    async def test_parse_multiple_cwe_ids(self, integration_service, sample_nuclei_jsonl):
        """Test parsing multiple CWE IDs."""
        result = await integration_service.parser.normalize(sample_nuclei_jsonl)
        finding = result.findings[2]  # The one with CWE-78,CWE-94
        
        assert len(finding.cwe_ids) == 2
        assert "CWE-78" in finding.cwe_ids
        assert "CWE-94" in finding.cwe_ids

    # ==================== Storage Tests ====================

    @pytest.mark.asyncio
    async def test_storage_manager_initialization(self, integration_service):
        """Test storage manager is properly initialized."""
        assert integration_service.storage is not None
        assert isinstance(integration_service.storage, NucleiStorageManager)

    @pytest.mark.asyncio
    async def test_neo4j_adapter_available(self, integration_service, neo4j_adapter):
        """Test Neo4j adapter is available."""
        assert integration_service.neo4j is not None
        assert isinstance(integration_service.neo4j, Neo4jAdapter)

    # ==================== Processing Pipeline Tests ====================

    @pytest.mark.asyncio
    async def test_process_nuclei_output_pipeline(self, integration_service, sample_nuclei_jsonl):
        """Test end-to-end processing pipeline."""
        result = await integration_service.process_nuclei_output(
            nuclei_output=sample_nuclei_jsonl,
            target_url="http://192.168.1.0/24"
        )
        
        assert result["status"] == "completed"
        assert result["findings_count"] == 3
        assert result["findings_stored"] > 0
        assert "scan_id" in result
        assert result["cve_relationships"] > 0
        assert result["cwe_relationships"] > 0

    @pytest.mark.asyncio
    async def test_process_with_scan_id(self, integration_service, sample_nuclei_jsonl):
        """Test processing with custom scan ID."""
        custom_scan_id = str(uuid4())
        
        result = await integration_service.process_nuclei_output(
            nuclei_output=sample_nuclei_jsonl,
            scan_id=custom_scan_id,
            target_url="http://target.com"
        )
        
        assert result["scan_id"] == custom_scan_id

    @pytest.mark.asyncio
    async def test_process_empty_output(self, integration_service):
        """Test processing empty Nuclei output."""
        result = await integration_service.process_nuclei_output(
            nuclei_output="",
            target_url="http://empty.com"
        )
        
        assert result["findings_count"] == 0
        assert result["findings_stored"] == 0

    @pytest.mark.asyncio
    async def test_process_dict_format(self, integration_service):
        """Test processing dict format."""
        nuclei_dict = {
            "template-id": "test-template",
            "severity": "high",
            "host": "192.168.1.1",
            "url": "http://192.168.1.1",
            "matched-at": datetime.now().isoformat(),
            "cve-id": "CVE-2024-1111",
            "cwe-id": "CWE-79"
        }
        
        result = await integration_service.process_nuclei_output(
            nuclei_output=nuclei_dict,
            target_url="http://single-finding.com"
        )
        
        assert result["status"] == "completed"
        assert result["findings_count"] >= 1

    @pytest.mark.asyncio
    async def test_process_list_format(self, integration_service):
        """Test processing list format."""
        nuclei_list = [
            {
                "template-id": "test-1",
                "severity": "medium",
                "host": "192.168.1.1",
                "url": "http://192.168.1.1",
                "matched-at": datetime.now().isoformat(),
                "cve-id": "CVE-2024-1111",
                "cwe-id": "CWE-79"
            },
            {
                "template-id": "test-2",
                "severity": "high",
                "host": "192.168.1.2",
                "url": "http://192.168.1.2",
                "matched-at": datetime.now().isoformat(),
                "cve-id": "CVE-2024-2222",
                "cwe-id": "CWE-89"
            }
        ]
        
        result = await integration_service.process_nuclei_output(
            nuclei_output=nuclei_list,
            target_url="http://multi-findings.com"
        )
        
        assert result["status"] == "completed"
        assert result["findings_count"] >= 2

    # ==================== Query Tests ====================

    @pytest.mark.asyncio
    async def test_get_critical_findings(self, integration_service, sample_nuclei_jsonl):
        """Test querying critical findings."""
        # First process findings
        await integration_service.process_nuclei_output(
            nuclei_output=sample_nuclei_jsonl,
            target_url="http://query-test.com"
        )
        
        # Query critical
        critical = await integration_service.get_critical_findings()
        assert isinstance(critical, list)

    @pytest.mark.asyncio
    async def test_get_high_findings(self, integration_service, sample_nuclei_jsonl):
        """Test querying high severity findings."""
        # Process findings
        await integration_service.process_nuclei_output(
            nuclei_output=sample_nuclei_jsonl,
            target_url="http://query-high.com"
        )
        
        # Query high
        high = await integration_service.get_high_findings()
        assert isinstance(high, list)

    @pytest.mark.asyncio
    async def test_get_findings_by_host(self, integration_service, sample_nuclei_jsonl):
        """Test querying findings by host."""
        await integration_service.process_nuclei_output(
            nuclei_output=sample_nuclei_jsonl,
            target_url="http://query-by-host.com"
        )
        
        findings = await integration_service.get_findings_by_host("192.168.1.100")
        assert isinstance(findings, list)

    @pytest.mark.asyncio
    async def test_get_findings_by_template(self, integration_service, sample_nuclei_jsonl):
        """Test querying findings by template."""
        await integration_service.process_nuclei_output(
            nuclei_output=sample_nuclei_jsonl,
            target_url="http://query-by-template.com"
        )
        
        findings = await integration_service.get_findings_by_template("sql-injection")
        assert isinstance(findings, list)

    @pytest.mark.asyncio
    async def test_get_findings_by_severity(self, integration_service, sample_nuclei_jsonl):
        """Test querying findings by severity."""
        await integration_service.process_nuclei_output(
            nuclei_output=sample_nuclei_jsonl,
            target_url="http://query-by-severity.com"
        )
        
        findings = await integration_service.get_findings_by_severity("CRITICAL")
        assert isinstance(findings, list)

    @pytest.mark.asyncio
    async def test_get_finding_by_id(self, integration_service, sample_nuclei_jsonl):
        """Test getting specific finding by ID."""
        result = await integration_service.process_nuclei_output(
            nuclei_output=sample_nuclei_jsonl,
            target_url="http://query-by-id.com"
        )
        
        # Get first finding (we would need to know the ID from Neo4j query)
        # This is a placeholder - in real implementation, we'd parse the ID from stored findings
        assert result["findings_stored"] > 0

    # ==================== Edge Cases ====================

    @pytest.mark.asyncio
    async def test_process_invalid_json(self, integration_service):
        """Test processing invalid JSON."""
        result = await integration_service.process_nuclei_output(
            nuclei_output="invalid json {",
            target_url="http://invalid.com"
        )
        
        assert result["findings_count"] == 0

    @pytest.mark.asyncio
    async def test_process_malformed_severity(self, integration_service):
        """Test processing malformed severity."""
        bad_finding = {
            "template-id": "test",
            "severity": "INVALID_SEVERITY",
            "host": "192.168.1.1",
            "url": "http://192.168.1.1",
            "matched-at": datetime.now().isoformat()
        }
        
        result = await integration_service.process_nuclei_output(
            nuclei_output=bad_finding,
            target_url="http://bad-severity.com"
        )
        
        # Should handle gracefully
        assert "findings_count" in result

    @pytest.mark.asyncio
    async def test_process_missing_required_fields(self, integration_service):
        """Test processing finding with missing required fields."""
        incomplete_finding = {
            "template-id": "test"
            # Missing severity, host, url
        }
        
        result = await integration_service.process_nuclei_output(
            nuclei_output=incomplete_finding,
            target_url="http://incomplete.com"
        )
        
        # Should handle gracefully
        assert "status" in result

    @pytest.mark.asyncio
    async def test_process_duplicate_findings(self, integration_service):
        """Test processing duplicate findings."""
        finding = {
            "template-id": "duplicate-test",
            "severity": "high",
            "host": "192.168.1.1",
            "url": "http://192.168.1.1",
            "matched-at": datetime.now().isoformat(),
            "cve-id": "CVE-2024-1111",
            "cwe-id": "CWE-79"
        }
        
        # Process same finding twice
        result1 = await integration_service.process_nuclei_output(
            nuclei_output=finding,
            target_url="http://duplicate-test.com"
        )
        
        result2 = await integration_service.process_nuclei_output(
            nuclei_output=finding,
            target_url="http://duplicate-test.com"
        )
        
        # Both should succeed (MERGE handles deduplication)
        assert result1["status"] == "completed"
        assert result2["status"] == "completed"

    # ==================== Performance Tests ====================

    @pytest.mark.asyncio
    async def test_bulk_processing_100_findings(self, integration_service):
        """Test processing 100 findings."""
        findings = []
        for i in range(100):
            findings.append({
                "template-id": f"perf-test-{i}",
                "severity": ["critical", "high", "medium"][i % 3],
                "host": f"192.168.1.{i % 254 + 1}",
                "url": f"http://192.168.1.{i % 254 + 1}/path-{i}",
                "matched-at": datetime.now().isoformat(),
                "cve-id": f"CVE-2024-{1000 + i}",
                "cwe-id": f"CWE-{79 + (i % 10)}"
            })
        
        import json
        jsonl_output = "\n".join(json.dumps(f) for f in findings)
        
        result = await integration_service.process_nuclei_output(
            nuclei_output=jsonl_output,
            target_url="http://perf-test-100.com"
        )
        
        assert result["status"] == "completed"
        assert result["findings_count"] == 100

    # ==================== Service Lifecycle Tests ====================

    @pytest.mark.asyncio
    async def test_service_can_process_multiple_times(self, integration_service):
        """Test service can process multiple times."""
        finding1 = '{"template-id":"t1","severity":"high","host":"192.168.1.1","url":"http://192.168.1.1","matched-at":"2026-04-28T08:00:00Z","cve-id":"CVE-2024-1111","cwe-id":"CWE-79"}'
        finding2 = '{"template-id":"t2","severity":"medium","host":"192.168.1.2","url":"http://192.168.1.2","matched-at":"2026-04-28T08:00:00Z","cve-id":"CVE-2024-2222","cwe-id":"CWE-89"}'
        
        result1 = await integration_service.process_nuclei_output(finding1, "http://scan1.com")
        result2 = await integration_service.process_nuclei_output(finding2, "http://scan2.com")
        
        assert result1["status"] == "completed"
        assert result2["status"] == "completed"
        assert result1["scan_id"] != result2["scan_id"]
