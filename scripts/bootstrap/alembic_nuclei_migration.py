"""Alembic migration: Add Nuclei tables for Phase 3.

This migration creates:
- nuclei_scans table
- nuclei_findings table
- Indexes and constraints
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '003_nuclei_tables'
down_revision = '002_initial_schema'
branch_labels = None
depends_on = None


def upgrade():
    """Create Nuclei tables and indexes."""
    
    # Create nuclei_scans table
    op.create_table(
        'nuclei_scans',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('target_url', sa.String(1024), nullable=False),
        sa.Column('status', sa.String(50), server_default='pending', nullable=True),
        sa.Column('findings_count', sa.Integer(), server_default='0', nullable=True),
        sa.Column('scan_type', sa.String(50), server_default='full', nullable=True),
        sa.Column('raw_output_path', sa.String(1024), nullable=True),
        sa.Column('neo4j_status', sa.String(50), server_default='pending', nullable=True),
        sa.Column('neo4j_error', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name='check_scan_status'
        ),
        sa.CheckConstraint(
            "neo4j_status IN ('pending', 'upserted', 'failed')",
            name='check_neo4j_status'
        )
    )
    
    # Create nuclei_findings table
    op.create_table(
        'nuclei_findings',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('scan_id', sa.String(36), nullable=False),
        sa.Column('finding_id', sa.String(36), nullable=False),
        sa.Column('template_id', sa.String(256), nullable=False),
        sa.Column('severity', sa.String(50), nullable=False),
        sa.Column('host', sa.String(256), nullable=False),
        sa.Column('url', sa.String(2048), nullable=False),
        sa.Column('matched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source', sa.String(50), server_default='nuclei', nullable=True),
        sa.Column('cve_ids', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=True),
        sa.Column('cwe_ids', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=True),
        sa.Column('neo4j_id', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['scan_id'], ['nuclei_scans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO')",
            name='check_severity'
        )
    )
    
    # Create indexes for nuclei_scans
    op.create_index('idx_nuclei_scans_target_url', 'nuclei_scans', ['target_url'])
    op.create_index('idx_nuclei_scans_status', 'nuclei_scans', ['status'])
    op.create_index('idx_nuclei_scans_created_at', 'nuclei_scans', ['created_at'], postgresql_using='DESC')
    op.create_index('idx_nuclei_scans_neo4j_status', 'nuclei_scans', ['neo4j_status'])
    
    # Create indexes for nuclei_findings
    op.create_index('idx_nuclei_findings_scan_id', 'nuclei_findings', ['scan_id'])
    op.create_index('idx_nuclei_findings_template_id', 'nuclei_findings', ['template_id'])
    op.create_index('idx_nuclei_findings_severity', 'nuclei_findings', ['severity'])
    op.create_index('idx_nuclei_findings_host', 'nuclei_findings', ['host'])
    op.create_index('idx_nuclei_findings_matched_at', 'nuclei_findings', ['matched_at'], postgresql_using='DESC')
    op.create_index('idx_nuclei_findings_neo4j_id', 'nuclei_findings', ['neo4j_id'])
    
    # Composite indexes
    op.create_index('idx_nuclei_findings_scan_severity', 'nuclei_findings', ['scan_id', 'severity'])
    op.create_index('idx_nuclei_findings_host_severity', 'nuclei_findings', ['host', 'severity'])


def downgrade():
    """Drop Nuclei tables and indexes."""
    
    # Drop indexes
    op.drop_index('idx_nuclei_findings_host_severity', table_name='nuclei_findings')
    op.drop_index('idx_nuclei_findings_scan_severity', table_name='nuclei_findings')
    op.drop_index('idx_nuclei_findings_neo4j_id', table_name='nuclei_findings')
    op.drop_index('idx_nuclei_findings_matched_at', table_name='nuclei_findings')
    op.drop_index('idx_nuclei_findings_host', table_name='nuclei_findings')
    op.drop_index('idx_nuclei_findings_severity', table_name='nuclei_findings')
    op.drop_index('idx_nuclei_findings_template_id', table_name='nuclei_findings')
    op.drop_index('idx_nuclei_findings_scan_id', table_name='nuclei_findings')
    
    op.drop_index('idx_nuclei_scans_neo4j_status', table_name='nuclei_scans')
    op.drop_index('idx_nuclei_scans_created_at', table_name='nuclei_scans')
    op.drop_index('idx_nuclei_scans_status', table_name='nuclei_scans')
    op.drop_index('idx_nuclei_scans_target_url', table_name='nuclei_scans')
    
    # Drop tables
    op.drop_table('nuclei_findings')
    op.drop_table('nuclei_scans')
