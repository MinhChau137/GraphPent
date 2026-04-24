# 📊 CVE JSON Support Implementation Guide

## Overview

The GraphRAG project now supports comprehensive processing of both **CWE XML** and **CVE JSON** data formats:

| Format | Source | Status | Usage |
|--------|--------|--------|-------|
| **CWE XML** | MITRE | ✅ Existing | `cwec_v4.19.1.xml` |
| **NVD CVE JSON** | NIST | ✅ New | `nvdcve-2.0-modified.json` |
| **CVE v5 JSON** | CVE Program | ✅ New | `data/cvelistV5-main/cves/YYYY/xxxx/*.json` |

---

## Architecture Changes

### 1. **Enhanced Parsers** (`app/utils/parsers.py`)

#### New Parser Functions:
- `parse_nvd_cve_json()` - Extracts CVE info from NVD format
- `parse_cve_v5_json()` - Extracts CVE info from CVE List v5 format
- `parse_cwe_xml()` - Existing CWE parser (preserved)

#### Data Extraction:
```
INPUT: Raw file bytes (XML/JSON)
  ↓
FORMAT DETECTION: Detect CWE, NVD-CVE, or CV5
  ↓
SPECIALIZED PARSING: Extract key fields
  ↓
OUTPUT: Normalized text representation
```

**Extracted Fields by Format:**

| Field | CWE XML | NVD CVE | CVE v5 |
|-------|---------|---------|--------|
| ID | CWE-XXXX | CVE-YYYY-XXXXX | CVE-YYYY-XXXXX |
| Description | ✅ | ✅ | ✅ |
| Weaknesses/CWE | ✅ | ✅ | ✅ |
| CVSS Score | - | ✅ | - |
| Affected Products | - | ✅ (CPE) | ✅ |
| References | ✅ | ✅ | ✅ |

### 2. **LLM Client Enhancement** (`app/adapters/llm_client.py`)

#### New Features:
- **Auto-detection**: `_detect_data_type()` - Identifies CWE vs CVE data
- **Dual extraction methods**:
  - `extract_entities_and_relations()` - CWE-optimized
  - `extract_entities_and_relations_from_cve()` - CVE-optimized

#### CVE Entity Types:
```
Vulnerability      - CVE vulnerabilities
AffectedProduct   - Vendor/Product affected
CWE              - Related CWE weaknesses
CVSS_Score       - CVSS metrics
Reference        - External references
Mitigation       - Fixes/patches
Vendor           - Software vendors
Consequence      - Impact/outcome
CVE_ID           - CVE identifier
```

#### CVE Relation Types:
```
AFFECTS          - CVE affects product
RELATED_TO       - General relation
HAS_CWE         - CVE has CWE weakness
HAS_CVSS        - CVE has CVSS score
REFERENCES      - CVE references URL
MITIGATED_BY    - CVE mitigated by patch
```

**Prompts:**
- **CWE Prompt**: Specialized for Weakness analysis
- **CVE Prompt**: Specialized for Vulnerability analysis

### 3. **Extraction Service Update** (`app/services/extraction_service.py`)

```python
# Auto-select extraction method based on data type
if data_type == "cve":
    extraction_result = await llm.extract_entities_and_relations_from_cve(...)
else:
    extraction_result = await llm.extract_entities_and_relations(...)
```

### 4. **Batch Data Loader** (`app/utils/batch_loader.py`)

Utility class for bulk data operations:

```python
loader = BatchDataLoader()

# Load single files
cwe_data = await loader.load_cwe_xml()
nvd_data = await loader.load_nvd_cve_json()

# Stream CVE v5 files
async for cve_file in loader.load_cve_v5_files():
    process(cve_file)

# Get statistics
stats = await get_data_statistics()
```

**Methods:**
- `load_cwe_xml()` - Load CWE XML
- `load_nvd_cve_json()` - Load NVD CVE JSON
- `load_cve_v5_files()` - Stream individual CVE files
- `load_all_cve_v5_files()` - Load all CVE files into memory
- `count_cve_v5_files()` - Count available files
- `load_delta_changes()` - Load incremental updates
- `get_data_statistics()` - Get data summary

---

## Usage Guide

### 1. **View Available Data**

```bash
python scripts/batch_ingest_all.py --mode stats
```

Output:
```
============================================================
📊 DATA STATISTICS
============================================================

✅ CWE XML:
   - File: cwec_v4.19.1.xml
   - Size: 28.45 MB

✅ NVD CVE JSON:
   - File: nvdcve-2.0-modified.json
   - Size: 542.31 MB

✅ CVE v5 JSON Files:
   - Count: 235,847

✅ CVE Delta Changes:
   - New: 16
   - Updated: 0

============================================================
```

### 2. **Ingest CWE Data**

```bash
python scripts/batch_ingest_all.py --mode cwe
```

Output:
```
✅ CWE XML ingestion completed
   - document_id: 1
   - filename: cwec_v4.19.1.xml
   - chunks_count: 1,245
   - status: success
```

### 3. **Ingest NVD CVE Data**

```bash
python scripts/batch_ingest_all.py --mode nvd
```

Output:
```
✅ NVD CVE JSON ingestion completed
   - document_id: 2
   - filename: nvdcve-2.0-modified.json
   - chunks_count: 8,432
   - status: success
```

### 4. **Ingest CVE v5 Files**

```bash
# Ingest first 100 CVE files
python scripts/batch_ingest_all.py --mode cv5 --limit 100

# Ingest all CVE files
python scripts/batch_ingest_all.py --mode cv5

# Custom CVE directory
python scripts/batch_ingest_all.py --mode cv5 --cve-dir /path/to/cves
```

Output:
```
✅ CVE v5 ingestion completed
   - total_files: 100
   - successful: 98
   - failed: 2
   - errors: [...]
```

### 5. **Ingest All Data**

```bash
python scripts/batch_ingest_all.py --mode all
```

---

## Processing Pipeline

### Example: CVE Data Processing

```
Input: CVE-2023-12345.json
  ↓
parse_cve_v5_json()
  ↓
Extracted:
  - CVE ID: CVE-2023-12345
  - Description: SQL Injection in Product X v1.0
  - CWE: CWE-89
  - Affected: Vendor - Product
  - References: [URL1, URL2]
  ↓
Chunked: 3 chunks (if large)
  ↓
LLM Extraction (with CVE prompt)
  ↓
Entities:
  - Vulnerability (CVE-2023-12345)
  - AffectedProduct (Vendor-Product-1.0)
  - CWE (CWE-89: SQL Injection)
  - CVSS_Score (7.5)
  ↓
Relations:
  - AFFECTS: CVE → Product
  - HAS_CWE: CVE → CWE
  - HAS_CVSS: CVE → Score
  ↓
Graph Storage (Neo4j)
```

---

## Data Format Reference

### CWE XML Structure
```xml
<Weakness ID="79">
  <Name>Cross-site Scripting</Name>
  <Description>...</Description>
  <Related_Weaknesses>
    <Related_Weakness CWE_ID="93" Nature="Parent" />
  </Related_Weaknesses>
  <Common_Consequences>
    <Consequence>
      <Scope>Integrity</Scope>
      <Impact>Modify Data</Impact>
    </Consequence>
  </Common_Consequences>
</Weakness>
```

### NVD CVE JSON Structure
```json
{
  "vulnerabilities": [
    {
      "cve": {
        "id": "CVE-2001-0631",
        "descriptions": [{
          "lang": "en",
          "value": "..."
        }],
        "metrics": {
          "cvssMetricV31": [{
            "cvssData": {
              "baseScore": 7.5,
              "baseSeverity": "HIGH"
            }
          }]
        },
        "weaknesses": [{
          "description": [{"value": "CWE-89"}]
        }]
      }
    }
  ]
}
```

### CVE v5 JSON Structure
```json
{
  "cveMetadata": {
    "cveId": "CVE-2023-27351",
    "state": "PUBLISHED",
    "datePublished": "2023-01-01T00:00:00.000Z"
  },
  "containers": {
    "cna": {
      "descriptions": [{
        "lang": "en",
        "value": "..."
      }],
      "affected": [{
        "vendor": "vendor-name",
        "product": "product-name",
        "versions": [{"version": "1.0", "status": "affected"}]
      }],
      "problemTypes": [{
        "descriptions": [{
          "cweId": "CWE-89",
          "description": "SQL Injection"
        }]
      }]
    }
  }
}
```

---

## Implementation Files Modified

| File | Changes |
|------|---------|
| `app/utils/parsers.py` | Added CVE JSON parsers |
| `app/adapters/llm_client.py` | Added CVE extraction method + data detection |
| `app/services/extraction_service.py` | Added auto-selection of extraction method |
| `app/utils/batch_loader.py` | **NEW** - Batch data loading utility |
| `scripts/batch_ingest_all.py` | **NEW** - Batch ingestion script |

---

## Testing

### Test Data
- **CWE XML**: `data/cwec_v4.19.1.xml`
- **NVD CVE**: `data/nvdcve-2.0-modified.json`
- **CVE v5**: `data/cvelistV5-main/cves/1999/0xxx/CVE-1999-0001.json`

### Quick Test
```bash
# Show data stats
python scripts/batch_ingest_all.py --mode stats

# Ingest 5 CVE files for testing
python scripts/batch_ingest_all.py --mode cv5 --limit 5
```

---

## Error Handling

| Scenario | Handling |
|----------|----------|
| Missing file | Logged as warning, skipped |
| Invalid JSON | Logged, fallback to raw text |
| Parse error | Logged, continue to next file |
| LLM timeout | Retry 4 times with exponential backoff |
| Database error | Logged, transaction rolled back |

---

## Performance Metrics

| Operation | Time | Notes |
|-----------|------|-------|
| Load CWE XML | ~2s | Single file, 28 MB |
| Load NVD CVE JSON | ~5s | Single file, 542 MB |
| Load 1 CVE v5 file | ~0.1s | Single file, ~2-5 KB |
| Stream 10K CVE files | ~30s | Async iteration |
| Ingest + Extract | ~5-10s | Per document (with LLM) |

---

## Future Enhancements

1. **Incremental Delta Loading** - Load only updated CVEs via delta.json
2. **Batch LLM Processing** - Process multiple chunks in parallel
3. **Advanced Filtering** - Filter by severity, date range, CWE type
4. **Caching** - Cache parsed documents to skip re-processing
5. **API Endpoints** - REST endpoints for batch operations

---

## Troubleshooting

### CVE Files Not Found
```bash
# Check if CVE directory exists
ls data/cvelistV5-main/cvelistV5-main/cves/

# Count files
find data/cvelistV5-main/cvelistV5-main/cves -name "CVE-*.json" | wc -l
```

### Memory Issues with Large Batches
```bash
# Use limit to process files in batches
python scripts/batch_ingest_all.py --mode cv5 --limit 100
# Process next batch
python scripts/batch_ingest_all.py --mode cv5 --limit 100
```

### LLM Timeout
- Increase `num_predict` in settings
- Reduce chunk size
- Check Ollama service status

---

## References

- **CWE XML**: [MITRE CWE](https://cwe.mitre.org/)
- **NVD CVE**: [NIST NVD](https://nvd.nist.gov/)
- **CVE List v5**: [CVE Program](https://www.cve.org/)
- **CVSS**: [CVSS Calculator](https://www.first.org/cvss/)

---

**Last Updated**: April 21, 2026
**Version**: 2.0
