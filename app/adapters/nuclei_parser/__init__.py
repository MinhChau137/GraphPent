"""
Nuclei Parser Package

Parsers and models for Nuclei vulnerability scanner output processing.
"""

from .models import (
    SeverityEnum,
    Finding,
    NucleiRawOutput,
    NormalizationResult,
    ScanMetadata,
    ScanResult,
    CorrelationResult,
)
from .nuclei_parser import NucleiParser
from .base import AbstractParser

__all__ = [
    'SeverityEnum',
    'Finding',
    'NucleiRawOutput',
    'NormalizationResult',
    'ScanMetadata',
    'ScanResult',
    'CorrelationResult',
    'NucleiParser',
    'AbstractParser',
]
