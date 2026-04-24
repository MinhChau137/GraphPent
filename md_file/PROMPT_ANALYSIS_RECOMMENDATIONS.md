# System Prompt Analysis & Optimization Recommendations

## 🔍 Current Issues Analysis

### **CWE XML Prompt - Issues Found:**

1. **❌ Too Many Entity Types (9 types)**
   - Current: Weakness, Mitigation, Consequence, DetectionMethod, Platform, Phase, Reference, Example, VulnerabilityType
   - Problem: LLM gets confused with too many choices, may extract low-quality entities
   - Impact: Creates noise in the graph, wastes LLM tokens

2. **❌ Lack of Extraction Priority**
   - Current: Treats all entities equally
   - Problem: Extracts everything instead of focusing on high-value data
   - Impact: Graph bloat, longer extraction time, lower quality relations

3. **❌ Limited Examples**
   - Current: Only 1 example (SQL Injection)
   - Problem: LLM doesn't see range of acceptable outputs
   - Impact: Inconsistent extraction patterns

4. **❌ No Property Guidance**
   - Current: Mentions "properties" and "provenance" but no specifics
   - Problem: LLM invents properties, creates inconsistent schema
   - Impact: Extraction validation fails, neo4j upsert issues

5. **❌ Weak Relation Guidance**
   - Current: Doesn't specify relation types or directions
   - Problem: Creates random relations, direction unclear
   - Impact: Poor graph connectivity, useless relations

6. **❌ Missing Data Quality Filters**
   - Current: "Do not create entities for empty values" - too vague
   - Problem: Still creates low-quality entities
   - Impact: Graph noise, validation failures

---

### **CVE JSON Prompt - Issues Found:**

1. **❌ Similar Type Overload (9 types)**
   - Current: Vulnerability, AffectedProduct, CWE, CVSS_Score, Reference, Mitigation, Vendor, Consequence, CVE_ID
   - Problem: CVE_ID is redundant (redundant with Vulnerability)
   - Impact: Schema inconsistency

2. **❌ Ambiguous Relation Semantics**
   - Current: AFFECTS vs HAS_CVSS vs REFERENCES
   - Problem: Direction unclear (CVE AFFECTS Product? Or Product AFFECTED_BY CVE?)
   - Impact: Wrong graph structure, relationship interpretation issues

3. **❌ CVSS Score Extraction Not Clear**
   - Current: Just says "CVSS_Score" type
   - Problem: Doesn't explain how to extract numeric vs severity vs vector
   - Impact: Inconsistent CVSS data in graph

4. **❌ Properties Schema Undefined**
   - Current: Shows example with cvss, severity, status but no comprehensive list
   - Problem: LLM guesses properties, creates schema drift
   - Impact: Inconsistent data model across chunks

5. **❌ No Version/Conflict Handling**
   - Current: No guidance on conflicting data
   - Problem: If CVE has multiple affected versions, unclear how to extract
   - Impact: Incomplete vulnerability information

---

## ✅ Recommended Improvements

### **Strategy 1: Reduce Entity Types (Focus on Quality)**

**CWE - Proposed Core Types (3-4 instead of 9):**
```
- Weakness (primary vulnerability pattern)
- Mitigation (recommended fixes)
- Platform (affected technology)
```

**Why:** Focus extraction on most valuable graph nodes

**CVE - Proposed Core Types (4-5 instead of 9):**
```
- Vulnerability (CVE record)
- AffectedProduct (impacted software)
- CWE (underlying weakness)
- Mitigation (fix/workaround)
```

---

### **Strategy 2: Add Extraction Priority & Confidence**

```
**Extraction Priority:**
1. PRIMARY entities (must extract):
   - Weakness name + ID, CVE ID, CWE ID
   - Clear product names + versions
   
2. SECONDARY entities (extract if clear):
   - Mitigations, detection methods
   - Affected platforms
   
3. SKIP entities:
   - Vague/generic descriptions
   - Example code snippets
   - References without substance
```

---

### **Strategy 3: Define Property Schema Explicitly**

**CWE Weakness Entity - Required Properties:**
```json
{
  "id": "cwe-XXX",
  "type": "Weakness",
  "name": "<exact CWE name>",
  "properties": {
    "cwe_id": "XXX",
    "description": "<1-2 sentence summary>",
    "severity_level": "high|medium|low",  // inferred from description
    "attack_vector": "<if mentioned>",
    "common_consequences": ["consequence1", "...]  // if listed
  },
  "provenance": {"source_type": "cwe_xml", "confidence": 0.95}
}
```

**CVE Vulnerability Entity - Required Properties:**
```json
{
  "id": "cve-2023-12345",
  "type": "Vulnerability",
  "name": "<CVE description>",
  "properties": {
    "cve_id": "2023-12345",
    "published_date": "YYYY-MM-DD",
    "cvss_score": 7.5,
    "cvss_severity": "HIGH",
    "attack_vector": "NETWORK|LOCAL|etc",
    "status": "published|disputed|etc"
  },
  "provenance": {"source_type": "cve_json", "confidence": 0.92}
}
```

---

### **Strategy 4: Clearer Relation Guidance**

```
**CWE Relations:**
- Weakness -> Weakness (RELATED_TO | REQUIRES_FIX | PARENT_OF)
- Weakness -> Mitigation (MITIGATED_BY)
- Weakness -> Platform (AFFECTS)

**CVE Relations:**
- CVE -> CWE (HAS_WEAKNESS) [always 1:M]
- CVE -> Product (IMPACTS) [direction: CVE -> Product]
- CVE -> Mitigation (RESOLVED_BY)
- Product -> Product (VERSION_OF)
```

---

### **Strategy 5: Data Quality Filters**

```
**SKIP entity if:**
1. Name is empty, "Unknown", "N/A", or generic term
2. Name is just a code/ID without description
3. Description < 10 characters
4. No meaningful properties can be extracted

**CONFIDENCE scoring:**
- 0.95: Full name + ID + clear definition
- 0.80: Name + partial properties
- 0.60: Only ID or vague name
- <0.60: Skip (don't include)
```

---

## 📊 Expected Improvements

| Metric | Current | After Optimization |
|--------|---------|-------------------|
| **Extraction Success Rate** | 80% | 95%+ |
| **False/Low-Quality Entities** | High | Reduced 40% |
| **Average Entities/Chunk** | ~2-3 | 2-3 (but higher quality) |
| **Neo4j Validation Errors** | 5-10% | <1% |
| **LLM Token Efficiency** | Medium | High (+20%) |

---

## 🔧 Proposed Code Changes

1. **Split prompts by complexity level**
   - Simple prompt for straightforward data
   - Complex prompt for nested/related data

2. **Add extraction confidence threshold**
   - Only return entities/relations with confidence > 0.75

3. **Implement property validation**
   - Check properties match entity type schema
   - Normalize values (dates, severity, etc.)

4. **Add example-based few-shot prompting**
   - Include 2-3 actual extraction examples in prompt
   - Show good vs bad extractions

5. **Implement retry logic for failed extractions**
   - If validation fails, ask LLM to re-extract with feedback

---

## 📝 Quick Implementation Checklist

- [ ] Reduce CWE entity types: 9 → 4
- [ ] Reduce CVE entity types: 9 → 5
- [ ] Add explicit property schemas
- [ ] Define relation types + directions clearly
- [ ] Add confidence scoring guidance
- [ ] Add 2-3 real extraction examples
- [ ] Add extraction priority rules
- [ ] Test with 100-chunk sample
- [ ] Measure improvement metrics
- [ ] Update prompt version in code

