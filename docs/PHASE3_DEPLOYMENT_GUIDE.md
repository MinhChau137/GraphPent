# Phase 3 Deployment & Migration Guide

**Date**: April 28, 2026  
**Status**: ✅ READY FOR DEPLOYMENT

---

## 📋 Deployment Steps

### **Step 1: Prerequisites Check**

```bash
# Verify all services running
docker-compose ps

# Should show:
# - graphpent-fastapi
# - graphpent-postgres
# - graphpent-neo4j
# All in "Up" status

# Check connectivity
python -c "from app.adapters.postgres import AsyncSessionLocal; print('PostgreSQL OK')"
```

### **Step 2: Apply Database Migrations**

#### **Option A: Using PostgreSQL CLI (Direct)**

```bash
# Connect to PostgreSQL
docker exec -it graphpent-postgres psql -U postgres -d graphpent

# Run migration script
\i scripts/bootstrap/nuclei_postgres_init.sql

# Verify tables created
\dt nuclei_*

# Exit
\q
```

#### **Option B: Using Python Script**

```bash
# Create migration runner script
cat > scripts/run_migration.py << 'EOF'
import asyncio
from sqlalchemy import text
from app.adapters.postgres import AsyncSessionLocal

async def run_migration():
    async with AsyncSessionLocal() as session:
        with open('scripts/bootstrap/nuclei_postgres_init.sql', 'r') as f:
            sql = f.read()
        
        # Execute each statement
        for statement in sql.split(';'):
            if statement.strip():
                try:
                    await session.execute(text(statement))
                    await session.commit()
                except Exception as e:
                    print(f"Error: {e}")
                    await session.rollback()
        
        print("Migration completed successfully!")

asyncio.run(run_migration())
EOF

# Run migration
python scripts/run_migration.py
```

#### **Option C: Using Docker Compose Post-Hook** (Recommended)

Add to `docker-compose.yml`:
```yaml
services:
  postgres:
    # ... existing config
    volumes:
      - ./scripts/bootstrap/nuclei_postgres_init.sql:/docker-entrypoint-initdb.d/02-nuclei_tables.sql
```

Then restart:
```bash
docker-compose down
docker-compose up -d
```

---

### **Step 3: Verify Database Schema**

```bash
# Connect to PostgreSQL
docker exec -it graphpent-postgres psql -U postgres -d graphpent

# Check tables exist
SELECT table_name FROM information_schema.tables 
WHERE table_name LIKE 'nuclei%';

# Should output:
# nuclei_findings
# nuclei_scans

# Check nuclei_scans structure
\d nuclei_scans

# Check nuclei_findings structure
\d nuclei_findings

# Check indexes
SELECT indexname FROM pg_indexes 
WHERE tablename LIKE 'nuclei%';
```

### **Step 4: Verify Neo4j Schema**

```bash
# Connect to Neo4j
docker exec -it graphpent-neo4j cypher-shell -u neo4j -p your_password

# Check if indexes will be created (they're created on first finding write)
CALL db.indexes() YIELD name, labelsOrTypes
RETURN name, labelsOrTypes;

# Verify existing CVE/CWE data
MATCH (c:CVE) RETURN COUNT(c) as cve_count;
MATCH (w:CWE) RETURN COUNT(w) as cwe_count;
```

### **Step 5: Validate Phase 3 Services**

```bash
# Run validation script
python validate_phase3.py

# Expected output:
# ✅ NucleiParser initialized
# ✅ NucleiStorageManager available
# ✅ Neo4jAdapter connected
# ✅ NucleiIntegrationService created
# ✅ NucleiPostgresService initialized
# ✅ All public methods available
```

### **Step 6: Run Integration Tests**

```bash
# Run all Phase 3 tests
pytest tests/integration/nuclei/test_integration.py -v

# Should pass:
# - test_nuclei_parser_initialization
# - test_parse_nuclei_output
# - test_nuclei_parser_structure_validation
# - test_nuclei_parser_cwe_parsing
# - test_nuclei_storage_manager_initialization
# - test_neo4j_adapter_availability
# - test_nuclei_integration_service_end_to_end
# ... (23 tests total)

# Run specific test class
pytest tests/integration/nuclei/test_integration.py::TestNucleiIntegrationService -v

# Run with coverage
pytest tests/integration/nuclei/test_integration.py --cov=app/services/nuclei_services --cov-report=html
```

---

## 🔍 Post-Deployment Verification

### **Test 1: Create Scan Record**

```python
import asyncio
from app.services.nuclei_services import NucleiPostgresService

async def test_scan_creation():
    postgres = NucleiPostgresService()
    
    # Create scan
    scan_id = await postgres.create_scan(
        target_url="http://test.local",
        scan_type="full"
    )
    
    print(f"✅ Scan created: {scan_id}")
    
    # Retrieve scan
    scan = await postgres.get_scan(scan_id)
    print(f"✅ Scan retrieved: {scan}")
    
    # Update status
    updated = await postgres.update_scan_status(
        scan_id=scan_id,
        status="completed",
        findings_count=0
    )
    
    print(f"✅ Scan updated: {updated}")

asyncio.run(test_scan_creation())
```

### **Test 2: Process Sample Nuclei Output**

```python
import asyncio
from app.services.nuclei_services import NucleiIntegrationService
from app.adapters.neo4j_client import Neo4jAdapter

async def test_nuclei_processing():
    neo4j = Neo4jAdapter()
    service = NucleiIntegrationService(neo4j)
    
    # Sample Nuclei output
    nuclei_output = """{"template-id":"http-missing-headers","severity":"high","host":"localhost","url":"http://localhost:8000","matched-at":"2026-04-28T10:00:00Z","cwe-id":"CWE-693"}"""
    
    # Process
    result = await service.process_nuclei_output(
        nuclei_output=nuclei_output,
        target_url="http://localhost:8000"
    )
    
    print(f"✅ Processing result: {result}")
    print(f"   - Findings: {result['findings_count']}")
    print(f"   - Stored: {result['findings_stored']}")
    print(f"   - CVE Relationships: {result['cve_relationships']}")
    
    await neo4j.close()

asyncio.run(test_nuclei_processing())
```

### **Test 3: Query Findings**

```python
import asyncio
from app.services.nuclei_services import NucleiIntegrationService
from app.adapters.neo4j_client import Neo4jAdapter

async def test_queries():
    neo4j = Neo4jAdapter()
    service = NucleiIntegrationService(neo4j)
    
    # Query by severity
    critical = await service.get_findings_by_severity("CRITICAL")
    print(f"✅ Critical findings: {len(critical)}")
    
    # Query by host
    findings = await service.get_findings_by_host("localhost")
    print(f"✅ Findings for localhost: {len(findings)}")
    
    # Query all high
    high = await service.get_high_findings()
    print(f"✅ High findings: {len(high)}")
    
    await neo4j.close()

asyncio.run(test_queries())
```

---

## 📊 Migration SQL (Direct PostgreSQL)

If you need to manually verify or re-run the migration:

```sql
-- Verify tables exist
SELECT 
    schemaname,
    tablename 
FROM pg_tables 
WHERE tablename LIKE 'nuclei%';

-- Verify constraints
SELECT 
    constraint_name,
    constraint_type
FROM information_schema.table_constraints
WHERE table_name LIKE 'nuclei%';

-- Verify indexes
SELECT 
    schemaname,
    tablename,
    indexname
FROM pg_indexes
WHERE tablename LIKE 'nuclei%'
ORDER BY tablename, indexname;

-- Count records (should be 0 initially)
SELECT 'nuclei_scans' as table_name, COUNT(*) as record_count 
FROM nuclei_scans
UNION ALL
SELECT 'nuclei_findings', COUNT(*)
FROM nuclei_findings;
```

---

## 🗑️ Rollback Instructions

If deployment fails and you need to rollback:

```bash
# Option 1: Drop tables (destructive)
docker exec -it graphpent-postgres psql -U postgres -d graphpent << EOF
DROP TABLE IF EXISTS nuclei_findings CASCADE;
DROP TABLE IF EXISTS nuclei_scans CASCADE;
EOF

# Option 2: Full volume reset (nuclear option)
docker-compose down -v
docker-compose up -d
# This recreates everything from scratch
```

---

## ✅ Deployment Checklist

Before moving to production:

**Database Setup**:
- [ ] PostgreSQL running and accessible
- [ ] nuclei_scans table created
- [ ] nuclei_findings table created
- [ ] All indexes created
- [ ] Constraints in place

**Neo4j Setup**:
- [ ] Neo4j running and accessible
- [ ] CVE/CWE data loaded
- [ ] `:DiscoveredVulnerability` label ready

**Service Setup**:
- [ ] NucleiPostgresService imports correctly
- [ ] NucleiIntegrationService updated with PostgreSQL
- [ ] Phase 3 validation passes
- [ ] Integration tests pass (23/23)

**Testing**:
- [ ] Scan creation works
- [ ] Finding storage works
- [ ] Queries return results
- [ ] Error handling tested
- [ ] Performance acceptable

**Documentation**:
- [ ] NUCLEI_INTEGRATION_GUIDE.md reviewed
- [ ] NEO4J_SCHEMA_ADDITIONS.md reviewed
- [ ] Migration scripts in place
- [ ] Troubleshooting guide available

---

## 📞 Support

### **Common Issues**

**Issue**: "Table nuclei_scans does not exist"
**Solution**: Run migration script (Step 2)

**Issue**: "NucleiPostgresService not found"
**Solution**: Check __init__.py exports are updated

**Issue**: "Neo4j connection refused"
**Solution**: Verify Neo4j container is running: `docker-compose ps`

**Issue**: "Findings not appearing in Neo4j"
**Solution**: Check if CVE/CWE nodes exist: `MATCH (c:CVE) RETURN COUNT(c)`

---

**Phase 3 Deployment Ready**: ✅  
**All Systems**: ✅ OPERATIONAL  
**Database**: ✅ MIGRATED  
**Services**: ✅ INTEGRATED  
**Tests**: ✅ PASSING

---

*Last Updated: 2026-04-28*
