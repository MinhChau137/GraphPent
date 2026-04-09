TEST_SCENARIOS = [
    {
        "id": 1,
        "name": "Retrieval Accuracy",
        "queries": [
            "SQL injection",
            "XSS",
            "IDOR",
            "CSRF",
            "authentication"
        ],
        "description": "So sánh Vector-only vs Graph-only vs Hybrid"
    },
    {
        "id": 2,
        "name": "CVE Linking Accuracy",
        "queries": ["SQL injection", "CWE"],
        "description": "Kiểm tra khả năng link CVE/CWE"
    },
    {
        "id": 3,
        "name": "Finding Correlation",
        "queries": ["SQL injection", "XSS"],
        "description": "Map finding → CVE/CWE"
    },
    {
        "id": 4,
        "name": "Multi-hop Reasoning",
        "queries": ["authentication"],
        "description": "Graph traversal multi-hop"
    },
    {
        "id": 5,
        "name": "Remediation Quality",
        "queries": ["SQL injection"],
        "description": "Đánh giá gợi ý remediation"
    }
]