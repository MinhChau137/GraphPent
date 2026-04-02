#!/usr/bin/env python3
"""Phase 3: Weaviate collections bootstrap."""

import weaviate
from weaviate.classes.config import Configure, Property, DataType
import os

#!/usr/bin/env python3
"""Phase 3: Weaviate collections bootstrap."""

import weaviate
from weaviate.classes.config import Configure, Property, DataType
import os

# Load config from environment variables
WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://weaviate:8080")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY", "")

# Connect using the correct API for Weaviate 4.x with anonymous access
client = weaviate.Client(
    url=WEAVIATE_URL,
    # No auth for anonymous access
)

collections = ["docs_chunks", "tool_findings", "remediation_knowledge", "reports_history"]

for name in collections:
    if not client.schema.exists(name):
        class_obj = {
            "class": name,
            "description": f"{name} collection for GraphRAG",
            "properties": [
                {
                    "name": "content",
                    "dataType": ["text"],
                    "description": "Content of the document or finding"
                },
                {
                    "name": "metadata",
                    "dataType": ["object"],
                    "description": "Metadata information",
                    "nestedProperties": [
                        {
                            "name": "source",
                            "dataType": ["text"]
                        },
                        {
                            "name": "timestamp",
                            "dataType": ["date"]
                        },
                        {
                            "name": "confidence",
                            "dataType": ["number"]
                        },
                        {
                            "name": "tool_origin",
                            "dataType": ["text"]
                        }
                    ]
                },
                {
                    "name": "hash",
                    "dataType": ["text"],
                    "description": "Content hash for deduplication"
                }
            ],
            "vectorizer": "none",
            "vectorIndexConfig": {
                "distance": "cosine"
            }
        }
        client.schema.create_class(class_obj)
        print(f"✅ Created collection: {name}")
    else:
        print(f"✅ Collection already exists: {name}")

print("🎉 Weaviate bootstrap completed")