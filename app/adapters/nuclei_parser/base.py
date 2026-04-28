"""
Abstract Parser Base Class

Base class for implementing tool output parsers (for multi-tool support in Phase 2.0)
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
from .models import Finding


class AbstractParser(ABC):
    """
    Abstract base class for parsing tool outputs.
    
    Supports:
    - Nuclei (Phase 1.0)
    - Nmap, Nessus, Burp (Phase 2.0+)
    """
    
    @abstractmethod
    async def parse(self, output: str | Dict[str, Any] | List[Dict]) -> List[Finding]:
        """
        Parse raw tool output into Finding entities.
        
        Args:
            output: Raw tool output (JSON string, dict, or list)
            
        Returns:
            List of Finding entities
            
        Raises:
            ValueError: If output format is invalid
        """
        pass
    
    @abstractmethod
    async def validate(self, output: Dict[str, Any]) -> bool:
        """
        Validate tool output format.
        
        Args:
            output: Single output entry to validate
            
        Returns:
            True if valid format, False otherwise
        """
        pass
    
    async def parse_bulk(self, outputs: List[Dict[str, Any]]) -> List[Finding]:
        """
        Parse multiple outputs (default implementation).
        Override if tool has better bulk parsing.
        
        Args:
            outputs: List of raw output entries
            
        Returns:
            List of Finding entities
        """
        findings = []
        for output in outputs:
            try:
                result = await self.parse(output)
                if isinstance(result, list):
                    findings.extend(result)
                else:
                    findings.append(result)
            except Exception as e:
                # Log error but continue processing
                print(f"Error parsing output: {e}")
                continue
        return findings
