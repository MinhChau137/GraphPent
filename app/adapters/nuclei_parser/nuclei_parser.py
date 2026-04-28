"""
Nuclei Parser Implementation

Main parser for Nuclei vulnerability scanner outputs.
Converts Nuclei JSON to normalized Finding entities.
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from uuid import uuid4

from .base import AbstractParser
from .models import Finding, NucleiRawOutput, SeverityEnum, NormalizationResult


logger = logging.getLogger(__name__)


class NucleiParser(AbstractParser):
    """Parse Nuclei JSON output into Finding entities"""
    
    def __init__(self):
        """Initialize Nuclei parser"""
        self.severity_mapping = {
            "critical": SeverityEnum.CRITICAL,
            "high": SeverityEnum.HIGH,
            "medium": SeverityEnum.MEDIUM,
            "low": SeverityEnum.LOW,
            "info": SeverityEnum.INFO,
        }
    
    async def parse(self, nuclei_output: str | Dict | List) -> List[Finding]:
        """
        Parse Nuclei output. Supports:
        1. JSONL format (one JSON per line)
        2. Dict (single finding)
        3. List (multiple findings)
        
        Args:
            nuclei_output: Raw Nuclei output in various formats
            
        Returns:
            List of normalized Finding entities
            
        Raises:
            ValueError: If output format is invalid
        """
        findings = []
        
        if isinstance(nuclei_output, str):
            # JSONL format (one JSON per line)
            findings = self._parse_jsonl(nuclei_output)
        elif isinstance(nuclei_output, dict):
            # Single finding
            finding = self._convert_raw_to_finding(nuclei_output)
            if finding:
                findings.append(finding)
        elif isinstance(nuclei_output, list):
            # List of findings
            for raw in nuclei_output:
                try:
                    finding = self._convert_raw_to_finding(raw)
                    if finding:
                        findings.append(finding)
                except Exception as e:
                    logger.warning(f"Failed to parse finding: {e}")
                    continue
        else:
            raise ValueError(f"Unsupported nuclei_output type: {type(nuclei_output)}")
        
        logger.info(f"Parsed {len(findings)} findings from Nuclei output")
        return findings
    
    def _parse_jsonl(self, jsonl: str) -> List[Finding]:
        """Parse JSONL format (one JSON per line)"""
        findings = []
        for line_num, line in enumerate(jsonl.strip().split('\n'), 1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                finding = self._convert_raw_to_finding(raw)
                if finding:
                    findings.append(finding)
            except json.JSONDecodeError as e:
                logger.warning(f"Line {line_num}: Invalid JSON - {e}")
                continue
            except Exception as e:
                logger.warning(f"Line {line_num}: Failed to parse - {e}")
                continue
        return findings
    
    def _convert_raw_to_finding(self, raw: dict) -> Optional[Finding]:
        """Convert raw Nuclei output to Finding model"""
        try:
            # Validate minimum required fields
            if not all(k in raw for k in ['template-id', 'host', 'severity']):
                logger.warning("Missing required fields in Nuclei output")
                return None
            
            # Handle severity mapping
            severity_str = raw.get('severity', 'info').lower()
            severity = self.severity_mapping.get(severity_str, SeverityEnum.INFO)
            
            # Extract CVE/CWE IDs
            cve_ids = self._parse_ids(raw.get('cve-id', ''))
            cwe_ids = self._parse_ids(raw.get('cwe-id', ''))
            
            # Build URL
            host = raw.get('host', '')
            matched_at = raw.get('matched-at', host)
            
            # Extract description
            description = ""
            if 'info' in raw and isinstance(raw['info'], dict):
                description = raw['info'].get('description', '')
            
            # Create Finding
            finding = Finding(
                id=str(uuid4()),
                template_id=raw.get('template-id', 'unknown'),
                severity=severity,
                host=host,
                url=matched_at or host,
                cve_ids=cve_ids,
                cwe_ids=cwe_ids,
                matched_at=self._parse_timestamp(raw.get('timestamp', '')),
                description=description,
                metadata={
                    'type': raw.get('type'),
                    'template_url': raw.get('template-url'),
                    'matcher_name': raw.get('matcher-name'),
                    'extracted_results': raw.get('extracted-results', {}),
                    'raw_data': raw  # Store raw for debugging
                }
            )
            
            logger.debug(f"Converted finding: {finding.template_id} on {host}")
            return finding
            
        except Exception as e:
            logger.error(f"Failed to convert raw output: {e}")
            return None
    
    @staticmethod
    def _parse_ids(value: str | list) -> List[str]:
        """Parse ID string (may be comma/space separated or list)"""
        if not value:
            return []
        
        if isinstance(value, list):
            return [str(id).strip() for id in value if id]
        
        # Handle comma/space separated string
        ids = [id.strip() for id in str(value).replace(',', ' ').split()]
        return [id for id in ids if id]
    
    @staticmethod
    def _parse_timestamp(timestamp_str: str) -> datetime:
        """Parse Nuclei timestamp (ISO 8601 format)"""
        if not timestamp_str:
            return datetime.utcnow()
        
        try:
            # Handle ISO format with Z or +00:00
            if timestamp_str.endswith('Z'):
                timestamp_str = timestamp_str[:-1] + '+00:00'
            
            return datetime.fromisoformat(timestamp_str)
        except (ValueError, TypeError):
            logger.warning(f"Could not parse timestamp: {timestamp_str}")
            return datetime.utcnow()
    
    async def validate(self, output: Dict[str, Any]) -> bool:
        """Validate Nuclei output format"""
        try:
            required_fields = ['template-id', 'host', 'severity']
            has_required = all(field in output for field in required_fields)
            
            if not has_required:
                logger.warning("Missing required Nuclei fields")
                return False
            
            # Validate severity
            severity = output.get('severity', '').lower()
            valid_severities = ['critical', 'high', 'medium', 'low', 'info']
            if severity not in valid_severities:
                logger.warning(f"Invalid severity: {severity}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False
    
    async def normalize(self, nuclei_output: str | Dict | List) -> NormalizationResult:
        """
        Full normalization pipeline: parse + validate + prepare for storage.
        
        Args:
            nuclei_output: Raw Nuclei output
            
        Returns:
            NormalizationResult with findings and metadata
        """
        findings = []
        errors = []
        
        try:
            # Parse output
            findings = await self.parse(nuclei_output)
            
            # Validate each finding
            for finding in findings:
                if not finding.cve_ids and not finding.cwe_ids:
                    logger.debug(f"Finding {finding.id} has no CVE/CWE correlation")
            
            logger.info(f"Normalization complete: {len(findings)} findings")
            
            return NormalizationResult(
                findings=findings,
                normalized_count=len(findings),
                failed_count=0,
                errors=errors
            )
            
        except Exception as e:
            error_msg = f"Normalization failed: {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)
            
            return NormalizationResult(
                findings=findings,
                normalized_count=len(findings),
                failed_count=1,
                errors=errors
            )
