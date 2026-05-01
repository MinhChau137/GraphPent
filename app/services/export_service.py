"""Export service (Phase 5.6)."""

import logging
import json
import csv
import io
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from functools import lru_cache

from sqlalchemy import select

from app.adapters.postgres import AsyncSessionLocal, JobQueue, BatchJob
from app.domain.schemas.export_import import (
    ExportJob,
    ExportJobResponse,
    SavedSearchCreate,
    SavedSearchResponse,
    ExportTemplate,
    ExportTemplateResponse,
)

logger = logging.getLogger(__name__)


class ExportService:
    """Service for exporting scan results and managing saved searches."""

    def __init__(self):
        """Initialize export service."""
        self.export_jobs = {}  # In-memory cache for demo
        self.saved_searches = {}  # In-memory cache for demo
        self.export_templates = {}  # In-memory cache for demo

    # ==================== Export Operations ====================

    async def create_export(
        self,
        export_config: ExportJob,
        user_id: str,
    ) -> ExportJobResponse:
        """Create and schedule export job."""
        export_id = f"export-{datetime.utcnow().timestamp()}"

        # Fetch data based on source type
        data = await self._fetch_source_data(export_config.source, export_config.source_id)

        if not data:
            return ExportJobResponse(
                export_id=export_id,
                name=export_config.name,
                source=export_config.source,
                source_id=export_config.source_id,
                format=export_config.format,
                status="failed",
                error_message=f"No data found for {export_config.source} {export_config.source_id}",
                created_at=datetime.utcnow(),
            )

        # Generate export file
        try:
            file_content, file_size = await self._generate_export_file(data, export_config)

            # Store export metadata
            export_response = ExportJobResponse(
                export_id=export_id,
                name=export_config.name,
                source=export_config.source,
                source_id=export_config.source_id,
                format=export_config.format,
                status="completed",
                progress_percent=100,
                download_url=f"/api/v1/exports/{export_id}/download",
                file_size_bytes=file_size,
                created_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
            )

            self.export_jobs[export_id] = {
                "config": export_config,
                "content": file_content,
                "response": export_response,
                "user_id": user_id,
            }

            logger.info(f"Export {export_id} created successfully ({file_size} bytes)")
            return export_response

        except Exception as e:
            logger.error(f"Failed to create export {export_id}: {e}")
            return ExportJobResponse(
                export_id=export_id,
                name=export_config.name,
                source=export_config.source,
                source_id=export_config.source_id,
                format=export_config.format,
                status="failed",
                error_message=str(e),
                created_at=datetime.utcnow(),
            )

    async def _fetch_source_data(self, source_type: str, source_id: str) -> Optional[List[Dict[str, Any]]]:
        """Fetch data from various sources."""
        async with AsyncSessionLocal() as session:
            if source_type == "batch":
                result = await session.execute(
                    select(BatchJob).filter(BatchJob.id == source_id)
                )
                batch = result.scalars().first()

                if not batch:
                    return None

                # Fetch all jobs in batch
                jobs_query = select(JobQueue).filter(JobQueue.job_id.in_(batch.job_ids))
                jobs_result = await session.execute(jobs_query)
                jobs = jobs_result.scalars().all()

                return [
                    {
                        "job_id": job.job_id,
                        "target_url": job.target_url,
                        "status": job.status,
                        "findings": job.result.get("findings", []) if job.result else [],
                    }
                    for job in jobs
                ]

            elif source_type == "job":
                result = await session.execute(
                    select(JobQueue).filter(JobQueue.job_id == source_id)
                )
                job = result.scalars().first()

                if not job:
                    return None

                return [
                    {
                        "job_id": job.job_id,
                        "target_url": job.target_url,
                        "status": job.status,
                        "findings": job.result.get("findings", []) if job.result else [],
                    }
                ]

        return None

    async def _generate_export_file(
        self,
        data: List[Dict[str, Any]],
        export_config: ExportJob,
    ) -> tuple[bytes, int]:
        """Generate export file in specified format."""
        if export_config.format == "json":
            return self._export_json(data, export_config)
        elif export_config.format == "csv":
            return self._export_csv(data, export_config)
        elif export_config.format == "pdf":
            return await self._export_pdf(data, export_config)

        raise ValueError(f"Unsupported export format: {export_config.format}")

    def _export_json(
        self,
        data: List[Dict[str, Any]],
        export_config: ExportJob,
    ) -> tuple[bytes, int]:
        """Export data as JSON."""
        export_data = {
            "export_metadata": {
                "created_at": datetime.utcnow().isoformat(),
                "source": export_config.source,
                "format": "json",
                "record_count": len(data),
            },
            "data": data,
        }

        json_bytes = json.dumps(export_data, indent=2, default=str).encode("utf-8")
        return json_bytes, len(json_bytes)

    def _export_csv(
        self,
        data: List[Dict[str, Any]],
        export_config: ExportJob,
    ) -> tuple[bytes, int]:
        """Export data as CSV."""
        if not data:
            return b"", 0

        # Flatten findings for CSV
        flattened_data = []
        for record in data:
            base_row = {
                "job_id": record.get("job_id"),
                "target_url": record.get("target_url"),
                "status": record.get("status"),
            }

            findings = record.get("findings", [])
            if findings:
                for finding in findings:
                    row = base_row.copy()
                    row.update({
                        "template_id": finding.get("template_id"),
                        "severity": finding.get("severity"),
                        "description": finding.get("description"),
                        "cve_ids": ",".join(finding.get("cve_ids", [])),
                    })
                    flattened_data.append(row)
            else:
                flattened_data.append(base_row)

        # Generate CSV
        output = io.StringIO()
        if flattened_data:
            writer = csv.DictWriter(output, fieldnames=flattened_data[0].keys())
            writer.writeheader()
            writer.writerows(flattened_data)

        csv_bytes = output.getvalue().encode("utf-8")
        return csv_bytes, len(csv_bytes)

    async def _export_pdf(
        self,
        data: List[Dict[str, Any]],
        export_config: ExportJob,
    ) -> tuple[bytes, int]:
        """Export data as PDF (placeholder - would require reportlab/weasyprint)."""
        # TODO: Implement PDF generation with reportlab or weasyprint
        logger.info("PDF export requested - not yet implemented")
        raise NotImplementedError("PDF export coming in future release")

    async def get_export_status(self, export_id: str) -> Optional[ExportJobResponse]:
        """Get export job status."""
        if export_id not in self.export_jobs:
            return None

        return self.export_jobs[export_id]["response"]

    async def download_export(self, export_id: str) -> Optional[bytes]:
        """Download exported file."""
        if export_id not in self.export_jobs:
            return None

        return self.export_jobs[export_id]["content"]

    async def list_exports(
        self,
        user_id: str,
        limit: int = 20,
    ) -> List[ExportJobResponse]:
        """List user's exports."""
        user_exports = [
            self.export_jobs[export_id]["response"]
            for export_id in self.export_jobs
            if self.export_jobs[export_id].get("user_id") == user_id
        ]

        return user_exports[-limit:]

    # ==================== Saved Searches ====================

    async def create_saved_search(
        self,
        search_data: SavedSearchCreate,
        created_by: str,
    ) -> SavedSearchResponse:
        """Create and save search."""
        search_id = f"search-{datetime.utcnow().timestamp()}"

        search_response = SavedSearchResponse(
            search_id=search_id,
            name=search_data.name,
            description=search_data.description,
            query=search_data.query,
            filters=search_data.filters or {},
            is_public=search_data.is_public,
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        self.saved_searches[search_id] = {
            "data": search_response,
            "created_by": created_by,
        }

        logger.info(f"Saved search {search_id} created by {created_by}")
        return search_response

    async def get_saved_search(self, search_id: str) -> Optional[SavedSearchResponse]:
        """Get saved search."""
        if search_id not in self.saved_searches:
            return None

        return self.saved_searches[search_id]["data"]

    async def list_saved_searches(
        self,
        user_id: Optional[str] = None,
        include_public: bool = True,
    ) -> List[SavedSearchResponse]:
        """List saved searches."""
        searches = []

        for search_id, search_data in self.saved_searches.items():
            search = search_data["data"]

            if user_id and search.created_by != user_id and not include_public:
                continue

            if not include_public and search.is_public and search.created_by != user_id:
                continue

            searches.append(search)

        return searches

    async def update_saved_search(
        self,
        search_id: str,
        update_data: Dict[str, Any],
    ) -> Optional[SavedSearchResponse]:
        """Update saved search."""
        if search_id not in self.saved_searches:
            return None

        search = self.saved_searches[search_id]["data"]

        # Update fields
        for field, value in update_data.items():
            if hasattr(search, field) and value is not None:
                setattr(search, field, value)

        search.updated_at = datetime.utcnow()
        return search

    async def delete_saved_search(self, search_id: str) -> bool:
        """Delete saved search."""
        if search_id not in self.saved_searches:
            return False

        del self.saved_searches[search_id]
        logger.info(f"Saved search {search_id} deleted")
        return True

    # ==================== Export Templates ====================

    async def create_export_template(
        self,
        template_data: ExportTemplate,
    ) -> ExportTemplateResponse:
        """Create export template."""
        template_id = f"template-{datetime.utcnow().timestamp()}"

        template_response = ExportTemplateResponse(
            template_id=template_id,
            template_name=template_data.template_name,
            export_config=template_data.export_config,
            schedule=template_data.schedule,
            retain_days=template_data.retain_days,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        self.export_templates[template_id] = template_response

        logger.info(f"Export template {template_id} created")
        return template_response

    async def get_export_template(self, template_id: str) -> Optional[ExportTemplateResponse]:
        """Get export template."""
        return self.export_templates.get(template_id)

    async def list_export_templates(self) -> List[ExportTemplateResponse]:
        """List export templates."""
        return list(self.export_templates.values())

    async def delete_export_template(self, template_id: str) -> bool:
        """Delete export template."""
        if template_id not in self.export_templates:
            return False

        del self.export_templates[template_id]
        logger.info(f"Export template {template_id} deleted")
        return True

    async def cleanup_old_exports(self, older_than_days: int = 30) -> int:
        """Clean up old export files."""
        cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
        deleted_count = 0

        export_ids_to_delete = []
        for export_id, export_data in self.export_jobs.items():
            if export_data["response"].created_at < cutoff_date:
                export_ids_to_delete.append(export_id)

        for export_id in export_ids_to_delete:
            del self.export_jobs[export_id]
            deleted_count += 1

        logger.info(f"Cleaned up {deleted_count} old exports")
        return deleted_count


@lru_cache(maxsize=1)
async def get_export_service() -> ExportService:
    """Get or create export service singleton."""
    return ExportService()
