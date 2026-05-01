#!/usr/bin/env python3
"""Quick validation script for Phase 3."""

import asyncio
from app.services.nuclei_services import NucleiIntegrationService
from app.adapters.neo4j_client import Neo4jAdapter


async def validate_phase3():
    """Validate Phase 3 implementation."""
    try:
        # Initialize
        adapter = Neo4jAdapter()
        service = NucleiIntegrationService(adapter)
        
        print("✅ Phase 3 initialized successfully")
        print(f"✅ Parser: {type(service.parser).__name__}")
        print(f"✅ Storage: {type(service.storage).__name__}")
        print(f"✅ Neo4j: {type(service.neo4j).__name__}")
        
        # Check methods
        methods = [m for m in dir(service) if not m.startswith("_") and callable(getattr(service, m))]
        print(f"✅ Public methods: {len(methods)}")
        
        # List key methods
        key_methods = [
            "process_nuclei_output",
            "get_findings_by_severity",
            "get_findings_by_host",
            "get_findings_by_template",
            "get_critical_findings",
            "get_high_findings"
        ]
        
        for method in key_methods:
            if hasattr(service, method):
                print(f"  ✅ {method}")
            else:
                print(f"  ❌ {method}")
        
        await adapter.close()
        print("\n✅ Phase 3 validation complete!")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(validate_phase3())
    exit(0 if success else 1)
