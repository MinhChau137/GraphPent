"""
Unit tests for Nuclei Parser

Tests for parsing, validation, and normalization of Nuclei output.
"""

import pytest
import json
from datetime import datetime
from pathlib import Path

from app.adapters.nuclei_parser.nuclei_parser import NucleiParser
from app.adapters.nuclei_parser.models import SeverityEnum, Finding


@pytest.fixture
def parser():
    """Create a NucleiParser instance for testing"""
    return NucleiParser()


@pytest.fixture
def sample_nuclei_output():
    """Sample single Nuclei JSON output"""
    return {
        "template-id": "http-missing-headers",
        "type": "http",
        "host": "https://example.com",
        "matched-at": "https://example.com/",
        "severity": "high",
        "cve-id": "CVE-2021-12345",
        "cwe-id": "CWE-693",
        "timestamp": "2026-04-28T12:00:00.000000Z",
        "info": {
            "description": "Detects missing security headers"
        }
    }


@pytest.fixture
def sample_critical_finding():
    """Sample CRITICAL severity finding"""
    return {
        "template-id": "cve-2024-9999-rce",
        "type": "http",
        "host": "https://internal-service.local:8080",
        "matched-at": "https://internal-service.local:8080/api/execute",
        "severity": "critical",
        "cve-id": "CVE-2024-9999",
        "cwe-id": "CWE-78,CWE-94",
        "timestamp": "2026-04-28T12:02:00.000000Z"
    }


@pytest.fixture
def sample_jsonl():
    """Sample JSONL format with multiple findings"""
    return (
        '{"template-id": "http-missing-headers", "type": "http", "host": "https://example.com", '
        '"matched-at": "https://example.com/", "severity": "high", "cve-id": "CVE-2021-12345", "cwe-id": "CWE-693"}\n'
        '{"template-id": "sql-injection", "type": "http", "host": "https://vulnerable-app.local", '
        '"matched-at": "https://vulnerable-app.local/search.php?id=1", "severity": "critical", '
        '"cve-id": "CVE-2024-1234", "cwe-id": "CWE-89"}'
    )


class TestNucleiParserModels:
    """Test data models"""
    
    def test_severity_enum_values(self):
        """Test SeverityEnum contains all values"""
        assert SeverityEnum.CRITICAL.value == "critical"
        assert SeverityEnum.HIGH.value == "high"
        assert SeverityEnum.MEDIUM.value == "medium"
        assert SeverityEnum.LOW.value == "low"
        assert SeverityEnum.INFO.value == "info"
    
    def test_finding_creation(self):
        """Test Finding model creation"""
        finding = Finding(
            template_id="test-template",
            severity=SeverityEnum.HIGH,
            host="example.com",
            url="https://example.com",
            matched_at=datetime.utcnow()
        )
        
        assert finding.template_id == "test-template"
        assert finding.severity == SeverityEnum.HIGH
        assert finding.host == "example.com"
        assert finding.url == "https://example.com"
        assert finding.source == "nuclei"


class TestNucleiParserBasic:
    """Basic parser functionality tests"""
    
    @pytest.mark.asyncio
    async def test_parse_single_dict(self, parser, sample_nuclei_output):
        """Test parsing single dictionary"""
        findings = await parser.parse(sample_nuclei_output)
        
        assert len(findings) == 1
        assert findings[0].template_id == "http-missing-headers"
        assert findings[0].severity == SeverityEnum.HIGH
        assert "CVE-2021-12345" in findings[0].cve_ids
        assert "CWE-693" in findings[0].cwe_ids
    
    @pytest.mark.asyncio
    async def test_parse_list(self, parser):
        """Test parsing list of dictionaries"""
        outputs = [
            {
                "template-id": "test1",
                "host": "example.com",
                "severity": "high"
            },
            {
                "template-id": "test2",
                "host": "example.com",
                "severity": "low"
            }
        ]
        
        findings = await parser.parse(outputs)
        
        assert len(findings) == 2
        assert findings[0].template_id == "test1"
        assert findings[1].template_id == "test2"
    
    @pytest.mark.asyncio
    async def test_parse_jsonl(self, parser, sample_jsonl):
        """Test parsing JSONL format"""
        findings = await parser.parse(sample_jsonl)
        
        assert len(findings) == 2
        assert findings[0].template_id == "http-missing-headers"
        assert findings[1].template_id == "sql-injection"
        assert findings[1].severity == SeverityEnum.CRITICAL


class TestSeverityHandling:
    """Test severity mapping"""
    
    @pytest.mark.asyncio
    async def test_severity_mapping(self, parser):
        """Test all severity levels map correctly"""
        severities = [
            ("critical", SeverityEnum.CRITICAL),
            ("high", SeverityEnum.HIGH),
            ("medium", SeverityEnum.MEDIUM),
            ("low", SeverityEnum.LOW),
            ("info", SeverityEnum.INFO),
        ]
        
        for sev_str, expected_enum in severities:
            output = {
                "template-id": "test",
                "host": "example.com",
                "severity": sev_str
            }
            findings = await parser.parse(output)
            assert findings[0].severity == expected_enum
    
    @pytest.mark.asyncio
    async def test_invalid_severity_defaults_to_info(self, parser):
        """Test invalid severity defaults to INFO"""
        output = {
            "template-id": "test",
            "host": "example.com",
            "severity": "unknown"
        }
        
        findings = await parser.parse(output)
        assert findings[0].severity == SeverityEnum.INFO


class TestCVECWEParsing:
    """Test CVE/CWE ID parsing"""
    
    @pytest.mark.asyncio
    async def test_single_cve_cwe(self, parser, sample_nuclei_output):
        """Test single CVE and CWE"""
        findings = await parser.parse(sample_nuclei_output)
        
        assert findings[0].cve_ids == ["CVE-2021-12345"]
        assert findings[0].cwe_ids == ["CWE-693"]
    
    @pytest.mark.asyncio
    async def test_multiple_cwe_comma_separated(self, parser, sample_critical_finding):
        """Test multiple CWE IDs (comma-separated)"""
        findings = await parser.parse(sample_critical_finding)
        
        assert len(findings[0].cwe_ids) == 2
        assert "CWE-78" in findings[0].cwe_ids
        assert "CWE-94" in findings[0].cwe_ids
    
    @pytest.mark.asyncio
    async def test_missing_cve_cwe(self, parser):
        """Test handling missing CVE/CWE"""
        output = {
            "template-id": "test",
            "host": "example.com",
            "severity": "low"
        }
        
        findings = await parser.parse(output)
        assert findings[0].cve_ids == []
        assert findings[0].cwe_ids == []


class TestValidation:
    """Test validation logic"""
    
    @pytest.mark.asyncio
    async def test_validate_valid_output(self, parser, sample_nuclei_output):
        """Test validation of valid output"""
        result = await parser.validate(sample_nuclei_output)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_validate_missing_template_id(self, parser):
        """Test validation fails with missing template-id"""
        output = {
            "host": "example.com",
            "severity": "high"
        }
        
        result = await parser.validate(output)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_validate_invalid_severity(self, parser):
        """Test validation fails with invalid severity"""
        output = {
            "template-id": "test",
            "host": "example.com",
            "severity": "ultra-critical"
        }
        
        result = await parser.validate(output)
        assert result is False


class TestTimestampParsing:
    """Test timestamp parsing"""
    
    def test_parse_iso_timestamp_with_z(self, parser):
        """Test parsing ISO timestamp with Z"""
        timestamp_str = "2026-04-28T12:00:00.000000Z"
        result = parser._parse_timestamp(timestamp_str)
        
        assert isinstance(result, datetime)
        assert result.year == 2026
        assert result.month == 4
        assert result.day == 28
    
    def test_parse_empty_timestamp(self, parser):
        """Test empty timestamp defaults to now"""
        result = parser._parse_timestamp("")
        assert isinstance(result, datetime)
    
    def test_parse_invalid_timestamp(self, parser):
        """Test invalid timestamp defaults to now"""
        result = parser._parse_timestamp("invalid-date")
        assert isinstance(result, datetime)


class TestNormalization:
    """Test normalization pipeline"""
    
    @pytest.mark.asyncio
    async def test_normalize_success(self, parser, sample_jsonl):
        """Test successful normalization"""
        result = await parser.normalize(sample_jsonl)
        
        assert result.normalized_count == 2
        assert result.failed_count == 0
        assert len(result.errors) == 0
        assert len(result.findings) == 2
    
    @pytest.mark.asyncio
    async def test_normalize_with_errors(self, parser):
        """Test normalization with malformed data"""
        jsonl_with_errors = (
            '{"template-id": "valid", "host": "example.com", "severity": "high"}\n'
            '{"invalid json"}\n'
            '{"template-id": "valid2", "host": "example.com", "severity": "low"}'
        )
        
        result = await parser.normalize(jsonl_with_errors)
        
        # Should still get 2 valid findings
        assert result.normalized_count == 2
        assert len(result.findings) == 2


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    @pytest.mark.asyncio
    async def test_parse_empty_string(self, parser):
        """Test parsing empty string"""
        findings = await parser.parse("")
        assert findings == []
    
    @pytest.mark.asyncio
    async def test_parse_empty_list(self, parser):
        """Test parsing empty list"""
        findings = await parser.parse([])
        assert findings == []
    
    @pytest.mark.asyncio
    async def test_parse_invalid_type(self, parser):
        """Test parsing invalid type raises error"""
        with pytest.raises(ValueError):
            await parser.parse(12345)
    
    @pytest.mark.asyncio
    async def test_parse_whitespace_jsonl(self, parser):
        """Test parsing JSONL with only whitespace"""
        jsonl = "\n\n\n"
        findings = await parser.parse(jsonl)
        assert findings == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
