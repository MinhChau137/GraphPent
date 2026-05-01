"""Export/Import schemas (Phase 5.6)."""

from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class ExportFormatEnum(str, Enum):
    """Export data format."""
    
    JSON = "json"
    CSV = "csv"
    PDF = "pdf"


class SavedSearchCreate(BaseModel):
    """Create saved search."""
    
    name: str = Field(..., min_length=1, max_length=100, description="Search name")
    description: Optional[str] = None
    query: str = Field(..., description="Search query")
    filters: Optional[Dict[str, Any]] = None
    is_public: bool = False


class SavedSearchUpdate(BaseModel):
    """Update saved search."""
    
    name: Optional[str] = None
    description: Optional[str] = None
    query: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    is_public: Optional[bool] = None


class SavedSearchResponse(BaseModel):
    """Saved search response."""
    
    search_id: str = Field(..., description="Unique search ID")
    name: str
    description: Optional[str]
    query: str
    filters: Dict[str, Any]
    is_public: bool
    created_by: str
    created_at: datetime
    updated_at: datetime
    last_executed_at: Optional[datetime] = None
    execution_count: int = 0
    
    class Config:
        from_attributes = True


class ExportJob(BaseModel):
    """Export job configuration."""
    
    export_id: Optional[str] = None
    name: str = Field(..., description="Export name")
    source: str = Field(..., pattern="^(batch|search|job|report)$", description="Data source type")
    source_id: str = Field(..., description="Source ID (batch_id, search_id, job_id, etc)")
    format: ExportFormatEnum = ExportFormatEnum.JSON
    include_metadata: bool = True
    include_findings: bool = True
    include_remediation: bool = False
    template: Optional[str] = None


class ExportJobResponse(BaseModel):
    """Export job response."""
    
    export_id: str
    name: str
    source: str
    source_id: str
    format: ExportFormatEnum
    status: str = Field(..., regex="^(pending|processing|completed|failed)$")
    progress_percent: int = Field(default=0, ge=0, le=100)
    download_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    class Config:
        from_attributes = True


class ReportTemplate(BaseModel):
    """Report template configuration."""
    
    template_id: str = Field(..., description="Template ID")
    template_name: str
    sections: List[str] = Field(default=["summary", "findings", "remediation"])
    include_charts: bool = True
    include_timeline: bool = False


class ReportGenerationRequest(BaseModel):
    """Generate report from scan results."""
    
    report_name: str = Field(..., min_length=1, max_length=200)
    source: str = Field(..., pattern="^(batch|job|search)$")
    source_id: str
    template: str = Field(default="standard")
    include_executive_summary: bool = True
    include_findings_detail: bool = True
    include_remediation: bool = True
    include_metrics: bool = True
    findings_filter: Optional[Dict[str, Any]] = None
    severity_threshold: Optional[str] = None


class ReportGenerationResponse(BaseModel):
    """Report generation response."""
    
    report_id: str
    report_name: str
    status: str = Field(..., pattern="^(pending|generating|completed|failed)$")
    progress_percent: int = Field(default=0, ge=0, le=100)
    download_url: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ImportDataSource(BaseModel):
    """Import data source configuration."""
    
    source_type: str = Field(..., pattern="^(file|api|database)$")
    source_location: str = Field(..., description="File path, API URL, or connection string")
    format: ExportFormatEnum = ExportFormatEnum.JSON
    mapping: Optional[Dict[str, str]] = None
    transform_rules: Optional[List[Dict[str, Any]]] = None


class ImportJob(BaseModel):
    """Import job configuration."""
    
    import_id: Optional[str] = None
    job_name: str = Field(..., description="Import job name")
    source: ImportDataSource
    merge_mode: str = Field(default="replace", pattern="^(replace|merge|append)$")
    deduplicate: bool = True
    validate_data: bool = True


class ImportJobResponse(BaseModel):
    """Import job response."""
    
    import_id: str
    job_name: str
    status: str = Field(..., regex="^(pending|processing|completed|failed)$")
    progress_percent: int = Field(default=0, ge=0, le=100)
    imported_records: int = 0
    failed_records: int = 0
    skipped_records: int = 0
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_summary: Optional[str] = None
    
    class Config:
        from_attributes = True


class ExportTemplate(BaseModel):
    """Export template for recurring exports."""
    
    template_id: Optional[str] = None
    template_name: str = Field(..., min_length=1, max_length=100)
    export_config: ExportJob
    schedule: Optional[str] = None  # cron format for recurring exports
    retain_days: int = Field(default=30, description="How long to keep exported files")


class ExportTemplateResponse(BaseModel):
    """Export template response."""
    
    template_id: str
    template_name: str
    export_config: ExportJob
    schedule: Optional[str]
    retain_days: int
    created_at: datetime
    updated_at: datetime
    last_execution_at: Optional[datetime] = None
    next_execution_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class DataMappingRule(BaseModel):
    """Data field mapping rule for imports."""
    
    source_field: str = Field(..., description="Source field name")
    target_field: str = Field(..., description="Target field name")
    transform: Optional[str] = None  # json_path, xpath, regex, etc
    default_value: Optional[Any] = None
    required: bool = False


class ValidationRule(BaseModel):
    """Validation rule for imported data."""
    
    field_name: str
    rule_type: str = Field(..., pattern="^(required|regex|range|enum)$")
    rule_config: Dict[str, Any]
    error_action: str = Field(default="skip", pattern="^(skip|fail|warn)$")


class ExportStatistics(BaseModel):
    """Export/Import statistics."""
    
    total_exports: int
    total_imports: int
    successful_exports: int
    failed_exports: int
    total_data_exported_mb: float
    total_data_imported_mb: float
    average_export_duration_seconds: float
    average_import_duration_seconds: float


class DataIntegrityReport(BaseModel):
    """Data integrity check report."""
    
    check_id: str
    checked_at: datetime
    total_records: int
    valid_records: int
    invalid_records: int
    issues: List[Dict[str, Any]] = []
    status: str = Field(..., pattern="^(passed|failed|warnings)$")
