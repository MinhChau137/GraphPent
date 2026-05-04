"""Elasticsearch client adapter for advanced search functionality."""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

from elasticsearch import Elasticsearch

from app.config.settings import settings

logger = logging.getLogger(__name__)


class ElasticsearchClient:
    """Elasticsearch client for indexing and searching job data."""

    # Index names
    INDEX_JOBS = "graphpent-jobs"
    INDEX_RESULTS = "graphpent-results"
    INDEX_FINDINGS = "graphpent-findings"

    # Aliases for easier management
    ALIAS_JOBS = "jobs-alias"
    ALIAS_RESULTS = "results-alias"
    ALIAS_FINDINGS = "findings-alias"

    def __init__(self, hosts: Optional[List[str]] = None):
        """
        Initialize Elasticsearch client.

        Args:
            hosts: Elasticsearch hosts (default from settings)
        """
        if hosts is None:
            hosts = settings.ELASTICSEARCH_HOSTS or ["localhost:9200"]

        self.hosts = hosts
        self.client = Elasticsearch(hosts=hosts)
        self._ensure_indexes_exist()

    def _ensure_indexes_exist(self):
        """Create indexes if they don't exist."""
        try:
            # Jobs index
            if not self.client.indices.exists(index=self.INDEX_JOBS):
                self.client.indices.create(
                    index=self.INDEX_JOBS,
                    mappings=self._get_jobs_mapping(),
                    settings=self._get_index_settings(),
                )
                logger.info(f"Created index: {self.INDEX_JOBS}")

            # Results index
            if not self.client.indices.exists(index=self.INDEX_RESULTS):
                self.client.indices.create(
                    index=self.INDEX_RESULTS,
                    mappings=self._get_results_mapping(),
                    settings=self._get_index_settings(),
                )
                logger.info(f"Created index: {self.INDEX_RESULTS}")

            # Findings index
            if not self.client.indices.exists(index=self.INDEX_FINDINGS):
                self.client.indices.create(
                    index=self.INDEX_FINDINGS,
                    mappings=self._get_findings_mapping(),
                    settings=self._get_index_settings(),
                )
                logger.info(f"Created index: {self.INDEX_FINDINGS}")

        except Exception as e:
            logger.error(f"Error ensuring indexes exist: {str(e)}")
            # Continue even if index creation fails - they might already exist

    @staticmethod
    def _get_index_settings() -> Dict[str, Any]:
        """Get common index settings."""
        return {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    "default": {
                        "type": "standard",
                        "stopwords": "_english_",
                    },
                    "text_analyzer": {
                        "type": "standard",
                        "stopwords": "_english_",
                    },
                }
            },
        }

    @staticmethod
    def _get_jobs_mapping() -> Dict[str, Any]:
        """Get mapping for jobs index."""
        return {
            "properties": {
                "job_id": {"type": "keyword"},
                "job_type": {"type": "keyword"},
                "status": {"type": "keyword"},
                "priority": {"type": "integer"},
                "target_url": {"type": "text", "analyzer": "text_analyzer"},
                "created_at": {"type": "date"},
                "started_at": {"type": "date"},
                "completed_at": {"type": "date"},
                "error_message": {"type": "text", "analyzer": "text_analyzer"},
                "findings_count": {"type": "integer"},
                "duration_seconds": {"type": "float"},
            }
        }

    @staticmethod
    def _get_results_mapping() -> Dict[str, Any]:
        """Get mapping for results index."""
        return {
            "properties": {
                "job_id": {"type": "keyword"},
                "target_url": {"type": "text", "analyzer": "text_analyzer"},
                "findings_count": {"type": "integer"},
                "severity_critical": {"type": "integer"},
                "severity_high": {"type": "integer"},
                "severity_medium": {"type": "integer"},
                "severity_low": {"type": "integer"},
                "severity_info": {"type": "integer"},
                "neo4j_status": {"type": "keyword"},
                "neo4j_count": {"type": "integer"},
                "created_at": {"type": "date"},
            }
        }

    @staticmethod
    def _get_findings_mapping() -> Dict[str, Any]:
        """Get mapping for findings index."""
        return {
            "properties": {
                "job_id": {"type": "keyword"},
                "finding_id": {"type": "keyword"},
                "template_id": {"type": "keyword"},
                "target_url": {"type": "text", "analyzer": "text_analyzer"},
                "severity": {"type": "keyword"},
                "host": {"type": "keyword"},
                "url": {"type": "text", "analyzer": "text_analyzer"},
                "matched_at": {"type": "date"},
                "cve_ids": {"type": "keyword"},
                "cwe_ids": {"type": "keyword"},
                "description": {"type": "text", "analyzer": "text_analyzer"},
                "created_at": {"type": "date"},
            }
        }

    def index_job(self, job_id: str, job_data: Dict[str, Any]) -> bool:
        """
        Index a job document.

        Args:
            job_id: Unique job ID
            job_data: Job data dictionary

        Returns:
            True if successful
        """
        try:
            self.client.index(index=self.INDEX_JOBS, id=job_id, document=job_data)
            return True
        except Exception as e:
            logger.error(f"Error indexing job {job_id}: {str(e)}")
            return False

    def index_result(self, job_id: str, result_data: Dict[str, Any]) -> bool:
        """
        Index a job result document.

        Args:
            job_id: Unique job ID
            result_data: Result data dictionary

        Returns:
            True if successful
        """
        try:
            self.client.index(index=self.INDEX_RESULTS, id=job_id, document=result_data)
            return True
        except Exception as e:
            logger.error(f"Error indexing result {job_id}: {str(e)}")
            return False

    def index_finding(
        self, finding_id: str, finding_data: Dict[str, Any]
    ) -> bool:
        """
        Index a finding document.

        Args:
            finding_id: Unique finding ID
            finding_data: Finding data dictionary

        Returns:
            True if successful
        """
        try:
            self.client.index(
                index=self.INDEX_FINDINGS, id=finding_id, document=finding_data
            )
            return True
        except Exception as e:
            logger.error(f"Error indexing finding {finding_id}: {str(e)}")
            return False

    def search_jobs(
        self,
        query: Optional[str] = None,
        status: Optional[str] = None,
        target_url: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        priority_min: Optional[int] = None,
        priority_max: Optional[int] = None,
        page: int = 1,
        size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Search jobs with advanced filtering.

        Args:
            query: Full-text search query
            status: Filter by status
            target_url: Filter by target URL
            date_from: Filter jobs created after this date
            date_to: Filter jobs created before this date
            priority_min: Minimum priority (1-10)
            priority_max: Maximum priority (1-10)
            page: Page number (1-based)
            size: Results per page

        Returns:
            Tuple of (results list, total count)
        """
        try:
            must_queries = []
            filter_queries = []

            # Full-text search
            if query:
                must_queries.append(
                    {
                        "multi_match": {
                            "query": query,
                            "fields": ["target_url", "error_message"],
                        }
                    }
                )

            # Exact filters
            if status:
                filter_queries.append({"term": {"status": status}})

            if target_url:
                filter_queries.append({"match": {"target_url": target_url}})

            # Range filters
            date_range = {}
            if date_from:
                date_range["gte"] = int(date_from.timestamp() * 1000)
            if date_to:
                date_range["lte"] = int(date_to.timestamp() * 1000)

            if date_range:
                filter_queries.append({"range": {"created_at": date_range}})

            priority_range = {}
            if priority_min is not None:
                priority_range["gte"] = priority_min
            if priority_max is not None:
                priority_range["lte"] = priority_max

            if priority_range:
                filter_queries.append({"range": {"priority": priority_range}})

            # Build query
            bool_query = {}
            if must_queries:
                bool_query["must"] = must_queries
            if filter_queries:
                bool_query["filter"] = filter_queries

            query_body = {
                "query": {"bool": bool_query} if bool_query else {"match_all": {}},
                "from": (page - 1) * size,
                "size": size,
                "sort": [{"created_at": {"order": "desc"}}],
            }

            response = self.client.search(index=self.INDEX_JOBS, body=query_body)

            results = [hit["_source"] for hit in response["hits"]["hits"]]
            total = response["hits"]["total"]["value"]

            return results, total

        except Exception as e:
            logger.error(f"Error searching jobs: {str(e)}")
            return [], 0

    def search_findings(
        self,
        query: Optional[str] = None,
        severity: Optional[str] = None,
        job_id: Optional[str] = None,
        target_url: Optional[str] = None,
        cve_id: Optional[str] = None,
        cwe_id: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        page: int = 1,
        size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Search findings with advanced filtering.

        Args:
            query: Full-text search query
            severity: Filter by severity (CRITICAL, HIGH, MEDIUM, LOW, INFO)
            job_id: Filter by job ID
            target_url: Filter by target URL
            cve_id: Filter by CVE ID
            cwe_id: Filter by CWE ID
            date_from: Filter findings created after this date
            date_to: Filter findings created before this date
            page: Page number (1-based)
            size: Results per page

        Returns:
            Tuple of (results list, total count)
        """
        try:
            must_queries = []
            filter_queries = []

            # Full-text search
            if query:
                must_queries.append(
                    {"multi_match": {"query": query, "fields": ["url", "description"]}}
                )

            # Exact filters
            if severity:
                filter_queries.append({"term": {"severity": severity}})

            if job_id:
                filter_queries.append({"term": {"job_id": job_id}})

            if target_url:
                filter_queries.append({"match": {"target_url": target_url}})

            if cve_id:
                filter_queries.append({"term": {"cve_ids": cve_id}})

            if cwe_id:
                filter_queries.append({"term": {"cwe_ids": cwe_id}})

            # Date range
            date_range = {}
            if date_from:
                date_range["gte"] = int(date_from.timestamp() * 1000)
            if date_to:
                date_range["lte"] = int(date_to.timestamp() * 1000)

            if date_range:
                filter_queries.append({"range": {"created_at": date_range}})

            # Build query
            bool_query = {}
            if must_queries:
                bool_query["must"] = must_queries
            if filter_queries:
                bool_query["filter"] = filter_queries

            query_body = {
                "query": {"bool": bool_query} if bool_query else {"match_all": {}},
                "from": (page - 1) * size,
                "size": size,
                "sort": [{"created_at": {"order": "desc"}}],
            }

            response = self.client.search(index=self.INDEX_FINDINGS, body=query_body)

            results = [hit["_source"] for hit in response["hits"]["hits"]]
            total = response["hits"]["total"]["value"]

            return results, total

        except Exception as e:
            logger.error(f"Error searching findings: {str(e)}")
            return [], 0

    def get_statistics(
        self,
        job_id: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get aggregated statistics from search indexes.

        Args:
            job_id: Filter to specific job
            date_from: Date range start
            date_to: Date range end

        Returns:
            Statistics dictionary
        """
        try:
            # Build filters
            filter_queries = []
            if job_id:
                filter_queries.append({"term": {"job_id": job_id}})

            date_range = {}
            if date_from:
                date_range["gte"] = int(date_from.timestamp() * 1000)
            if date_to:
                date_range["lte"] = int(date_to.timestamp() * 1000)

            if date_range:
                filter_queries.append({"range": {"created_at": date_range}})

            bool_query = {}
            if filter_queries:
                bool_query["filter"] = filter_queries

            query_body = {
                "query": {"bool": bool_query} if bool_query else {"match_all": {}},
                "aggs": {
                    "severity_distribution": {
                        "terms": {"field": "severity", "size": 10}
                    },
                    "total_findings": {"sum": {"field": "findings_count"}},
                    "average_findings": {"avg": {"field": "findings_count"}},
                },
            }

            response = self.client.search(index=self.INDEX_FINDINGS, body=query_body)
            aggs = response.get("aggregations", {})

            return {
                "severity_distribution": aggs.get("severity_distribution", {}).get(
                    "buckets", []
                ),
                "total_findings": int(
                    aggs.get("total_findings", {}).get("value", 0)
                ),
                "average_findings": aggs.get("average_findings", {}).get("value", 0),
                "documents_count": response["hits"]["total"]["value"],
            }

        except Exception as e:
            logger.error(f"Error getting statistics: {str(e)}")
            return {}

    def delete_job_data(self, job_id: str) -> bool:
        """
        Delete all documents related to a job.

        Args:
            job_id: Job ID to delete

        Returns:
            True if successful
        """
        try:
            # Delete from jobs index
            self.client.delete_by_query(
                index=self.INDEX_JOBS, body={"query": {"term": {"job_id": job_id}}}
            )

            # Delete from results index
            self.client.delete_by_query(
                index=self.INDEX_RESULTS, body={"query": {"term": {"job_id": job_id}}}
            )

            # Delete from findings index
            self.client.delete_by_query(
                index=self.INDEX_FINDINGS, body={"query": {"term": {"job_id": job_id}}}
            )

            return True

        except Exception as e:
            logger.error(f"Error deleting job data {job_id}: {str(e)}")
            return False

    def health_check(self) -> bool:
        """
        Check Elasticsearch connection health.

        Returns:
            True if healthy
        """
        try:
            response = self.client.cluster.health()
            return response.get("status") in ["green", "yellow"]
        except Exception as e:
            logger.error(f"Elasticsearch health check failed: {str(e)}")
            return False


# Singleton instance
_es_client_instance: Optional[ElasticsearchClient] = None


async def get_elasticsearch_client() -> ElasticsearchClient:
    """Get or create Elasticsearch client singleton."""
    global _es_client_instance
    if _es_client_instance is None:
        _es_client_instance = ElasticsearchClient()
    return _es_client_instance
