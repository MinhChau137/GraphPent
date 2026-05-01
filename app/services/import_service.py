"""Import service (Phase 5.6)."""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from functools import lru_cache

from sqlalchemy import select

from app.adapters.postgres import AsyncSessionLocal, JobQueue
from app.domain.schemas.export_import import (
    ImportJob,
    ImportJobResponse,
    DataIntegrityReport,
    ValidationRule,
)

logger = logging.getLogger(__name__)


class ImportService:
    """Service for importing scan data from external sources."""

    def __init__(self):
        """Initialize import service."""
        self.import_jobs = {}  # In-memory cache for demo
        self.validation_rules = {}

    # ==================== Import Operations ====================

    async def create_import_job(
        self,
        import_config: ImportJob,
        user_id: str,
    ) -> ImportJobResponse:
        """Create and execute import job."""
        import_id = f"import-{datetime.utcnow().timestamp()}"

        try:
            # Load data from source
            import_data = await self._load_source_data(import_config.source)

            if not import_data:
                return ImportJobResponse(
                    import_id=import_id,
                    job_name=import_config.job_name,
                    status="failed",
                    error_summary="No data found in source",
                    created_at=datetime.utcnow(),
                )

            # Validate data
            if import_config.validate_data:
                validation_result = await self._validate_data(import_data, import_config.source.format)
                if not validation_result["valid"]:
                    return ImportJobResponse(
                        import_id=import_id,
                        job_name=import_config.job_name,
                        status="failed",
                        failed_records=validation_result["failed_count"],
                        error_summary=f"Data validation failed: {validation_result.get('error')}",
                        created_at=datetime.utcnow(),
                    )

            # Deduplicate if needed
            if import_config.deduplicate:
                import_data = await self._deduplicate_records(import_data)

            # Import data
            import_result = await self._import_data(
                import_data,
                import_config.merge_mode,
                user_id,
            )

            import_response = ImportJobResponse(
                import_id=import_id,
                job_name=import_config.job_name,
                status="completed",
                progress_percent=100,
                imported_records=import_result["imported"],
                failed_records=import_result["failed"],
                skipped_records=import_result["skipped"],
                created_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
            )

            self.import_jobs[import_id] = {
                "config": import_config,
                "result": import_response,
                "user_id": user_id,
            }

            logger.info(
                f"Import {import_id} completed: {import_result['imported']} imported, "
                f"{import_result['failed']} failed, {import_result['skipped']} skipped"
            )

            return import_response

        except Exception as e:
            logger.error(f"Import job {import_id} failed: {e}")
            return ImportJobResponse(
                import_id=import_id,
                job_name=import_config.job_name,
                status="failed",
                error_summary=str(e),
                created_at=datetime.utcnow(),
            )

    async def _load_source_data(self, source) -> Optional[List[Dict[str, Any]]]:
        """Load data from source."""
        if source.source_type == "file":
            return await self._load_from_file(source.source_location)
        elif source.source_type == "api":
            return await self._load_from_api(source.source_location)
        elif source.source_type == "database":
            return await self._load_from_database(source.source_location)

        return None

    async def _load_from_file(self, file_path: str) -> Optional[List[Dict[str, Any]]]:
        """Load data from file."""
        try:
            # TODO: Implement file loading (CSV, JSON, etc.)
            logger.info(f"Loading from file: {file_path}")
            return []
        except Exception as e:
            logger.error(f"Failed to load file {file_path}: {e}")
            return None

    async def _load_from_api(self, api_url: str) -> Optional[List[Dict[str, Any]]]:
        """Load data from API."""
        try:
            # TODO: Implement API loading (via aiohttp or requests)
            logger.info(f"Loading from API: {api_url}")
            return []
        except Exception as e:
            logger.error(f"Failed to load from API {api_url}: {e}")
            return None

    async def _load_from_database(self, connection_string: str) -> Optional[List[Dict[str, Any]]]:
        """Load data from external database."""
        try:
            # TODO: Implement database loading
            logger.info(f"Loading from database: {connection_string}")
            return []
        except Exception as e:
            logger.error(f"Failed to load from database: {e}")
            return None

    async def _validate_data(
        self,
        data: List[Dict[str, Any]],
        format_type: str,
    ) -> Dict[str, Any]:
        """Validate imported data."""
        valid = True
        failed_count = 0
        errors = []

        for record in data:
            try:
                # Basic validation
                if "target_url" not in record:
                    valid = False
                    failed_count += 1
                    errors.append("Missing required field: target_url")

                if "findings" not in record and "results" not in record:
                    valid = False
                    failed_count += 1
                    errors.append("Missing findings or results data")

            except Exception as e:
                valid = False
                failed_count += 1
                errors.append(str(e))

        return {
            "valid": valid,
            "failed_count": failed_count,
            "error": errors[0] if errors else None,
        }

    async def _deduplicate_records(
        self,
        records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Remove duplicate records."""
        seen = set()
        deduplicated = []

        for record in records:
            target = record.get("target_url")
            record_hash = hash(target)

            if record_hash not in seen:
                seen.add(record_hash)
                deduplicated.append(record)

        logger.info(f"Deduplicated {len(records) - len(deduplicated)} records")
        return deduplicated

    async def _import_data(
        self,
        data: List[Dict[str, Any]],
        merge_mode: str,
        user_id: str,
    ) -> Dict[str, int]:
        """Import data into database."""
        imported = 0
        failed = 0
        skipped = 0

        async with AsyncSessionLocal() as session:
            for record in data:
                try:
                    target_url = record.get("target_url")

                    # Check for existing record
                    existing_query = select(JobQueue).filter(JobQueue.target_url == target_url)
                    result = await session.execute(existing_query)
                    existing = result.scalars().first()

                    if existing and merge_mode == "replace":
                        # Replace existing record
                        existing.result = record.get("findings") or record.get("results")
                        existing.job_metadata = record.get("metadata", {})
                        await session.merge(existing)
                        imported += 1

                    elif existing and merge_mode == "merge":
                        # Merge data with existing record
                        if existing.result:
                            existing.result.update(record.get("findings", {}))
                        else:
                            existing.result = record.get("findings")
                        await session.merge(existing)
                        imported += 1

                    elif not existing or merge_mode == "append":
                        # Create new record
                        job = JobQueue(
                            job_id=f"import-{target_url}",
                            job_type="imported",
                            status="completed",
                            target_url=target_url,
                            result=record.get("findings") or record.get("results"),
                            job_metadata=record.get("metadata", {}),
                            created_at=datetime.utcnow(),
                            completed_at=datetime.utcnow(),
                        )
                        session.add(job)
                        imported += 1

                except Exception as e:
                    failed += 1
                    logger.error(f"Failed to import record for {target_url}: {e}")

            await session.commit()

        return {
            "imported": imported,
            "failed": failed,
            "skipped": skipped,
        }

    async def get_import_status(self, import_id: str) -> Optional[ImportJobResponse]:
        """Get import job status."""
        if import_id not in self.import_jobs:
            return None

        return self.import_jobs[import_id]["result"]

    async def list_imports(
        self,
        user_id: str,
        limit: int = 20,
    ) -> List[ImportJobResponse]:
        """List user's imports."""
        user_imports = [
            self.import_jobs[import_id]["result"]
            for import_id in self.import_jobs
            if self.import_jobs[import_id].get("user_id") == user_id
        ]

        return user_imports[-limit:]

    # ==================== Data Integrity ====================

    async def check_data_integrity(self, check_scope: str = "all") -> DataIntegrityReport:
        """Check data integrity."""
        check_id = f"check-{datetime.utcnow().timestamp()}"
        total_records = 0
        valid_records = 0
        invalid_records = 0
        issues = []

        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(JobQueue))
                jobs = result.scalars().all()
                total_records = len(jobs)

                for job in jobs:
                    # Check for required fields
                    if not job.target_url:
                        invalid_records += 1
                        issues.append({
                            "job_id": job.job_id,
                            "issue": "Missing target_url",
                        })
                    elif not job.result or not job.result.get("findings"):
                        issues.append({
                            "job_id": job.job_id,
                            "issue": "No findings data",
                        })
                        valid_records += 1
                    else:
                        valid_records += 1

            status = "passed" if invalid_records == 0 else "warnings" if valid_records > 0 else "failed"

            return DataIntegrityReport(
                check_id=check_id,
                checked_at=datetime.utcnow(),
                total_records=total_records,
                valid_records=valid_records,
                invalid_records=invalid_records,
                issues=issues,
                status=status,
            )

        except Exception as e:
            logger.error(f"Data integrity check failed: {e}")
            return DataIntegrityReport(
                check_id=check_id,
                checked_at=datetime.utcnow(),
                total_records=0,
                valid_records=0,
                invalid_records=0,
                issues=[{"error": str(e)}],
                status="failed",
            )

    async def add_validation_rule(
        self,
        rule: ValidationRule,
    ) -> bool:
        """Add custom validation rule."""
        rule_id = f"rule-{datetime.utcnow().timestamp()}"
        self.validation_rules[rule_id] = rule
        logger.info(f"Validation rule {rule_id} added")
        return True

    async def get_validation_rules(self) -> List[ValidationRule]:
        """Get all validation rules."""
        return list(self.validation_rules.values())


@lru_cache(maxsize=1)
async def get_import_service() -> ImportService:
    """Get or create import service singleton."""
    return ImportService()
