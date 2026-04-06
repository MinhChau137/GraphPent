-- Phase 3: PostgreSQL schema – idempotent
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. documents
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    filename TEXT NOT NULL,
    content_type TEXT,
    minio_path TEXT UNIQUE NOT NULL,
    doc_metadata JSONB DEFAULT '{}',
    hash TEXT UNIQUE,
    chunks_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE documents ADD COLUMN IF NOT EXISTS chunks_count INTEGER DEFAULT 0;

-- 2. chunks
CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    chunk_metadata JSONB DEFAULT '{}',
    weaviate_uuid UUID,
    hash TEXT UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. ingestion_jobs
CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id INTEGER REFERENCES documents(id),
    status TEXT DEFAULT 'pending',
    error TEXT,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    finished_at TIMESTAMP WITH TIME ZONE
);

-- 4. extraction_jobs
CREATE TABLE IF NOT EXISTS extraction_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chunk_id INTEGER REFERENCES chunks(id),
    status TEXT DEFAULT 'pending',
    entities_json JSONB,
    error TEXT,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    finished_at TIMESTAMP WITH TIME ZONE
);

-- 5. findings
CREATE TABLE IF NOT EXISTS findings (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    severity TEXT CHECK (severity IN ('critical','high','medium','low','info')),
    cve_id TEXT,
    description TEXT,
    evidence JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. reports
CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    markdown TEXT,
    json_data JSONB,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 7. audit_logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    action TEXT NOT NULL,
    details JSONB DEFAULT '{}',
    request_id TEXT,
    user_id TEXT DEFAULT 'system',
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 8. tool_runs
CREATE TABLE IF NOT EXISTS tool_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tool_name TEXT NOT NULL,
    target TEXT NOT NULL,
    command TEXT,
    output_summary TEXT,
    status TEXT,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    finished_at TIMESTAMP WITH TIME ZONE
);

-- 9. analyst_feedback
CREATE TABLE IF NOT EXISTS analyst_feedback (
    id SERIAL PRIMARY KEY,
    entity_id TEXT,
    feedback_type TEXT,
    comment TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 10. entity_links
CREATE TABLE IF NOT EXISTS entity_links (
    id SERIAL PRIMARY KEY,
    neo4j_node_id TEXT NOT NULL,
    postgres_table TEXT,
    postgres_id INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_findings_severity ON findings(severity);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_tool_runs_target ON tool_runs(target);

-- Triggers update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_documents_updated_at BEFORE UPDATE
ON documents FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();