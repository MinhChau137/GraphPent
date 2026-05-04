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
        "description": "So sánh Vector-only vs Graph-only vs Hybrid trên 5 loại lỗ hổng cơ bản"
    },
    {
        "id": 2,
        "name": "CVE Linking Accuracy",
        "queries": ["SQL injection", "CWE"],
        "description": "Kiểm tra khả năng link CVE/CWE — graph chứa đầy đủ CVE nodes từ NVD"
    },
    {
        "id": 3,
        "name": "Finding Correlation",
        "queries": ["SQL injection", "XSS"],
        "description": "Map finding → CVE/CWE — đánh giá correlation giữa finding và knowledge graph"
    },
    {
        "id": 4,
        "name": "Multi-hop Reasoning",
        "queries": ["authentication", "authentication bypass"],
        "description": "Graph traversal multi-hop qua CWE family — authentication có 15+ liên kết"
    },
    {
        "id": 5,
        "name": "Remediation Quality",
        "queries": ["SQL injection"],
        "description": "Đánh giá gợi ý remediation — ground truth gồm các CWE/CVE liên quan"
    }
]
