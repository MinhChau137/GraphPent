import json
from pathlib import Path
from typing import List, Dict

GROUND_TRUTH = {
    "SQL injection": {
        "relevant_ids": ["cwe-1073", "cwe-405"],
        "relevant_cves": []
    },
    "XSS": {
        "relevant_ids": ["1000", "732"],
        "relevant_cves": []
    },
    "IDOR": {
        "relevant_ids": ["1057"],  # Data Access Operations Outside of Expected Data Manager
        "relevant_cves": []
    },
    "CSRF": {
        "relevant_ids": ["1275"],  # Sensitive Cookie with Improper SameSite Attribute
        "relevant_cves": []
    },
    "authentication bypass": {
        "relevant_ids": ["1390"],
        "relevant_cves": []
    },
    "SQL injection": {  # Duplicate for scenario 2
        "relevant_ids": ["cwe-1073", "cwe-405"],
        "relevant_cves": []
    },
    "CWE": {
        "relevant_ids": ["cwe-1073", "cwe-405", "cwe-1007"],  # Some CWE IDs
        "relevant_cves": []
    },
    "SQL injection": {  # For scenario 3
        "relevant_ids": ["cwe-1073", "cwe-405"],
        "relevant_cves": []
    },
    "XSS": {  # For scenario 3
        "relevant_ids": ["1000", "732"],
        "relevant_cves": []
    },
    "authentication": {
        "relevant_ids": ["1390"],
        "relevant_cves": []
    },
    "SQL injection": {  # For scenario 5
        "relevant_ids": ["cwe-1073", "cwe-405"],
        "relevant_cves": []
    }
}

def load_ground_truth() -> Dict:
    return GROUND_TRUTH