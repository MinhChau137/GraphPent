-- Phase 5.1: Job Queue Table Schema
-- SQL migration for Celery job queue persistence

-- Create job_queue table
CREATE TABLE IF NOT EXISTS job_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id VARCHAR UNIQUE NOT NULL,
    job_type VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'pending',
    priority INTEGER DEFAULT 5,
    target_url VARCHAR,
    payload JSONB,
    result JSONB,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0 CHECK (retry_count >= 0),
    max_retries INTEGER DEFAULT 3 CHECK (max_retries >= 0),
    callback_url VARCHAR,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CHECK (priority BETWEEN 1 AND 10),
    CHECK (retry_count <= max_retries),
    CHECK (status IN (
        'pending', 'running', 'completed', 'failed', 
        'cancelled', 'retrying'
    )),
    CHECK (job_type IN (
        'nuclei_scan', 'batch_scan', 'neo4j_upsert',
        'report_generation', 'result_import'
    ))
);

-- Create indexes for performance
CREATE INDEX idx_job_queue_status ON job_queue(status);
CREATE INDEX idx_job_queue_created_at ON job_queue(created_at DESC);
CREATE INDEX idx_job_queue_priority_status ON job_queue(priority DESC, status);
CREATE INDEX idx_job_queue_target_url ON job_queue(target_url);
CREATE INDEX idx_job_queue_job_id ON job_queue(job_id);
CREATE INDEX idx_job_queue_completed_at ON job_queue(completed_at DESC) 
    WHERE completed_at IS NOT NULL;

-- Composite index for common queries
CREATE INDEX idx_job_queue_status_updated ON job_queue(status, updated_at DESC);

-- Update redis volume mount in docker-compose if needed
-- - redis_data:/data

-- Create function to update updated_at automatically
CREATE OR REPLACE FUNCTION update_job_queue_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for updated_at
DROP TRIGGER IF EXISTS trigger_job_queue_updated_at ON job_queue;
CREATE TRIGGER trigger_job_queue_updated_at
BEFORE UPDATE ON job_queue
FOR EACH ROW
EXECUTE FUNCTION update_job_queue_updated_at();

-- Optional: Create view for job statistics
CREATE OR REPLACE VIEW v_job_queue_stats AS
SELECT
    COUNT(*) as total_jobs,
    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
    SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
    SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled,
    ROUND(AVG(EXTRACT(EPOCH FROM (completed_at - created_at)))::numeric, 2) as avg_completion_seconds,
    ROUND(
        (
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END)::numeric /
            NULLIF(
                SUM(CASE WHEN status IN ('completed', 'failed') THEN 1 ELSE 0 END),
                0
            )
        ) * 100,
        2
    ) as success_rate_percent
FROM job_queue;
