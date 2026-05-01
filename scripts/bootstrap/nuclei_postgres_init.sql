-- Phase 3.3: Nuclei PostgreSQL Schema Migrations
-- Scan History & Finding Metadata Tables
-- Date: 2026-04-28

-- ==================== Table: nuclei_scans ====================
-- Tracks Nuclei scan execution and status

CREATE TABLE IF NOT EXISTS nuclei_scans (
    id VARCHAR(36) PRIMARY KEY,
    target_url VARCHAR(1024) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',  -- pending, running, completed, failed
    findings_count INTEGER DEFAULT 0,
    scan_type VARCHAR(50) DEFAULT 'full',  -- full, web, api
    raw_output_path VARCHAR(1024),
    neo4j_status VARCHAR(50) DEFAULT 'pending',  -- pending, upserted, failed
    neo4j_error TEXT,
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ==================== Table: nuclei_findings ====================
-- Stores individual findings from Nuclei scans

CREATE TABLE IF NOT EXISTS nuclei_findings (
    id VARCHAR(36) PRIMARY KEY,
    scan_id VARCHAR(36) NOT NULL REFERENCES nuclei_scans(id) ON DELETE CASCADE,
    finding_id VARCHAR(36) NOT NULL,
    template_id VARCHAR(256) NOT NULL,
    severity VARCHAR(50) NOT NULL,  -- CRITICAL, HIGH, MEDIUM, LOW, INFO
    host VARCHAR(256) NOT NULL,
    url VARCHAR(2048) NOT NULL,
    matched_at TIMESTAMP WITH TIME ZONE,
    source VARCHAR(50) DEFAULT 'nuclei',
    cve_ids JSONB DEFAULT '[]',
    cwe_ids JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    neo4j_id VARCHAR(36),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ==================== Indexes ====================

-- nuclei_scans indexes
CREATE INDEX IF NOT EXISTS idx_nuclei_scans_target_url 
    ON nuclei_scans(target_url);

CREATE INDEX IF NOT EXISTS idx_nuclei_scans_status 
    ON nuclei_scans(status);

CREATE INDEX IF NOT EXISTS idx_nuclei_scans_created_at 
    ON nuclei_scans(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_nuclei_scans_neo4j_status 
    ON nuclei_scans(neo4j_status);

-- nuclei_findings indexes
CREATE INDEX IF NOT EXISTS idx_nuclei_findings_scan_id 
    ON nuclei_findings(scan_id);

CREATE INDEX IF NOT EXISTS idx_nuclei_findings_template_id 
    ON nuclei_findings(template_id);

CREATE INDEX IF NOT EXISTS idx_nuclei_findings_severity 
    ON nuclei_findings(severity);

CREATE INDEX IF NOT EXISTS idx_nuclei_findings_host 
    ON nuclei_findings(host);

CREATE INDEX IF NOT EXISTS idx_nuclei_findings_matched_at 
    ON nuclei_findings(matched_at DESC);

CREATE INDEX IF NOT EXISTS idx_nuclei_findings_neo4j_id 
    ON nuclei_findings(neo4j_id);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_nuclei_findings_scan_severity 
    ON nuclei_findings(scan_id, severity);

CREATE INDEX IF NOT EXISTS idx_nuclei_findings_host_severity 
    ON nuclei_findings(host, severity);

-- ==================== Constraints ====================

-- Ensure severity values are valid (PostgreSQL CHECK constraint)
ALTER TABLE nuclei_findings 
ADD CONSTRAINT check_severity 
CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'));

-- Ensure status values are valid
ALTER TABLE nuclei_scans 
ADD CONSTRAINT check_scan_status 
CHECK (status IN ('pending', 'running', 'completed', 'failed'));

-- Ensure neo4j_status values are valid
ALTER TABLE nuclei_scans 
ADD CONSTRAINT check_neo4j_status 
CHECK (neo4j_status IN ('pending', 'upserted', 'failed'));
