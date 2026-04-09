"""Dashboard API - Phase 10."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Dict, List, Any
from app.services.report_service import ReportService
from app.core.logger import logger

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

class DashboardResponse(BaseModel):
    system_status: str
    total_documents: int
    total_chunks: int
    total_entities_in_graph: int
    recent_reports: List[Dict]

@router.get("/")
async def get_dashboard() -> DashboardResponse:
    """Trang dashboard chính."""
    # TODO: Lấy dữ liệu thực từ DB/Neo4j ở phase sau
    return {
        "system_status": "healthy",
        "total_documents": 12,
        "total_chunks": 87,
        "total_entities_in_graph": 245,
        "recent_reports": [
            {"id": "report-20260405-001", "query": "SQL Injection DVWA", "generated_at": "2026-04-05T10:15:00Z"},
            {"id": "report-20260404-002", "query": "CVE-1999-0001 analysis", "generated_at": "2026-04-04T16:45:00Z"}
        ]
    }

@router.post("/generate-report")
async def generate_report(query: str, workflow_result: Dict):
    """Tạo báo cáo từ workflow result."""
    report_md = await ReportService.generate_markdown_report(workflow_result, query)
    report_json = await ReportService.generate_json_report(workflow_result, query)

    logger.info("Report generated", query=query)
    await audit_log("report_generated", {"query": query, "report_id": report_json["report_id"]})

    return {
        "report_id": report_json["report_id"],
        "markdown": report_md,
        "json": report_json
    }

@router.get("/tracing")
async def get_tracing_info():
    """Thông tin tracing (LangSmith / Prometheus stub)."""
    return {
        "status": "tracing enabled",
        "langsmith_project": "graphrag-pentest",
        "recent_traces": 42,
        "message": "Tracing được tích hợp qua structlog + LangSmith (có thể config sau)"
    }