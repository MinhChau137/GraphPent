#!/usr/bin/env python3
"""
Integration test script for Phase 7-9 features.
Tests: Hybrid Retrieval, Multi-Agent Workflow, Pentest Tools
"""

import asyncio
import httpx
import json
from datetime import datetime

# Configuration
API_BASE_URL = "http://localhost:8000"

class TestRunner:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.results = {
            "phase_7": [],
            "phase_8": [],
            "phase_9": []
        }
    
    async def test_phase_7_retrieval(self):
        """Test Phase 7: Hybrid Retrieval with Analytics"""
        print("\n" + "="*60)
        print("🔍 PHASE 7: Hybrid Retrieval & Analytics")
        print("="*60)
        
        test_cases = [
            {
                "name": "Hybrid Search (Vector + Graph)",
                "endpoint": "/retrieve/query",
                "payload": {
                    "query": "SQL injection vulnerability detection",
                    "limit": 10,
                    "alpha": 0.7,
                    "mode": "hybrid"
                }
            },
            {
                "name": "Vector-Only Search",
                "endpoint": "/retrieve/vector-only",
                "payload": {
                    "query": "buffer overflow exploitation",
                    "limit": 5
                }
            },
            {
                "name": "Graph-Only Search",
                "endpoint": "/retrieve/graph-only",
                "payload": {
                    "query": "CVE-2023-44487",
                    "limit": 5
                }
            }
        ]
        
        for test in test_cases:
            try:
                print(f"\n📌 {test['name']}")
                resp = await self.client.post(
                    f"{API_BASE_URL}{test['endpoint']}",
                    json=test['payload']
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"   ✅ Success: {data.get('total', 0)} results returned")
                    print(f"   Mode: {data.get('mode')}, Alpha: {data.get('alpha')}")
                    self.results["phase_7"].append({
                        "test": test['name'],
                        "status": "PASS"
                    })
                else:
                    print(f"   ❌ Failed: {resp.status_code}")
                    self.results["phase_7"].append({
                        "test": test['name'],
                        "status": "FAIL",
                        "error": resp.text[:100]
                    })
            except Exception as e:
                print(f"   ⚠️  Error: {e}")
                self.results["phase_7"].append({
                    "test": test['name'],
                    "status": "ERROR",
                    "error": str(e)
                })
        
        # Test analytics endpoint
        try:
            print(f"\n📌 Retrieval Statistics")
            resp = await self.client.get(f"{API_BASE_URL}/retrieve/stats?hours=24")
            if resp.status_code == 200:
                stats = resp.json()
                print(f"   ✅ Total queries: {stats.get('total_queries', 0)}")
                print(f"   ✅ Avg latency: {stats.get('avg_latency_ms', 0):.1f}ms")
                print(f"   ✅ Cache enabled: {stats.get('cache_enabled')}")
                self.results["phase_7"].append({
                    "test": "Analytics Endpoint",
                    "status": "PASS"
                })
        except Exception as e:
            print(f"   ⚠️  Error: {e}")
    
    async def test_phase_8_workflow(self):
        """Test Phase 8: Multi-Agent Workflow"""
        print("\n" + "="*60)
        print("🤖 PHASE 8: Multi-Agent Workflow (LangGraph)")
        print("="*60)
        
        test_cases = [
            {
                "name": "Simple Query Analysis",
                "payload": {
                    "query": "Find SQL injection vulnerabilities",
                    "user_id": "test_analyst_1"
                }
            },
            {
                "name": "CVE Analysis Query",
                "payload": {
                    "query": "Analyze CVE-2023-44487 exploitability",
                    "user_id": "test_analyst_2"
                }
            }
        ]
        
        for test in test_cases:
            try:
                print(f"\n📌 {test['name']}")
                resp = await self.client.post(
                    f"{API_BASE_URL}/workflow/multi-agent",
                    json=test['payload']
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"   ✅ Success: Workflow completed")
                    print(f"   Workflow ID: {data.get('workflow_id')}")
                    print(f"   Status: {data.get('status')}")
                    print(f"   Latency: {data.get('latency_ms'):.1f}ms")
                    print(f"   Retrieval Results: {len(data.get('retrieval_results', []))}")
                    print(f"   Tool Results: {len(data.get('tool_results', []))}")
                    self.results["phase_8"].append({
                        "test": test['name'],
                        "status": "PASS"
                    })
                else:
                    print(f"   ❌ Failed: {resp.status_code}")
                    print(f"   Response: {resp.text[:200]}")
                    self.results["phase_8"].append({
                        "test": test['name'],
                        "status": "FAIL",
                        "error": resp.text[:100]
                    })
            except Exception as e:
                print(f"   ⚠️  Error: {e}")
                self.results["phase_8"].append({
                    "test": test['name'],
                    "status": "ERROR",
                    "error": str(e)
                })
    
    async def test_phase_9_tools(self):
        """Test Phase 9: Pentest Tools"""
        print("\n" + "="*60)
        print("🛠️  PHASE 9: Pentest Tools (CVE & Nuclei)")
        print("="*60)
        
        # Sample CVE JSON (minimal)
        sample_cve = {
            "cveMetadata": {
                "cveId": "CVE-2023-44487"
            },
            "containers": {
                "cna": {
                    "descriptions": [
                        {
                            "value": "HTTP/2 Rapid Reset attack allows remote denial of service"
                        }
                    ],
                    "affected": [
                        {
                            "vendor": "OpenSSL",
                            "product": "OpenSSL",
                            "versions": [
                                {"version": "3.0.0"},
                                {"version": "3.0.1"}
                            ]
                        }
                    ],
                    "references": [
                        {"url": "https://nvd.nist.gov/vuln/detail/CVE-2023-44487"}
                    ]
                }
            }
        }
        
        # Test CVE Analysis
        try:
            print(f"\n📌 CVE Exploitability Analysis")
            payload = {"cve_json": sample_cve}
            resp = await self.client.post(
                f"{API_BASE_URL}/tools/cve/analyze",
                json=payload
            )
            
            if resp.status_code == 200:
                data = resp.json()
                print(f"   ✅ Success: CVE {data.get('cve_id')} analyzed")
                print(f"   Exploitability Score: {data.get('exploitability_score', 0):.2f}")
                print(f"   Attack Vector: {data.get('attack_vector')}")
                print(f"   Severity: {data.get('severity')}")
                print(f"   Recommend Nuclei Scan: {data.get('recommend_nuclei_scan')}")
                self.results["phase_9"].append({
                    "test": "CVE Analysis",
                    "status": "PASS"
                })
            else:
                print(f"   ❌ Failed: {resp.status_code}")
                self.results["phase_9"].append({
                    "test": "CVE Analysis",
                    "status": "FAIL"
                })
        except Exception as e:
            print(f"   ⚠️  Error: {e}")
        
        # Test Nuclei Templates Endpoint
        try:
            print(f"\n📌 Nuclei Templates List")
            resp = await self.client.get(
                f"{API_BASE_URL}/tools/cve/templates"
            )
            
            if resp.status_code == 200:
                templates = resp.json()
                print(f"   ✅ Success: Templates retrieved")
                for severity, tmpl_list in templates.items():
                    print(f"   {severity}: {len(tmpl_list)} templates")
                self.results["phase_9"].append({
                    "test": "Templates List",
                    "status": "PASS"
                })
        except Exception as e:
            print(f"   ⚠️  Error: {e}")
        
        # Test Batch CVE Analysis
        try:
            print(f"\n📌 Batch CVE Analysis")
            payload = {"cve_jsons": [sample_cve] * 3}
            resp = await self.client.post(
                f"{API_BASE_URL}/tools/cve/batch-analyze",
                json=payload
            )
            
            if resp.status_code == 200:
                data = resp.json()
                print(f"   ✅ Success: {data.get('total', 0)} CVEs analyzed")
                self.results["phase_9"].append({
                    "test": "Batch Analysis",
                    "status": "PASS"
                })
        except Exception as e:
            print(f"   ⚠️  Error: {e}")
        
        # Test Tool Health Check
        try:
            print(f"\n📌 Tool Service Health")
            resp = await self.client.get(f"{API_BASE_URL}/tools/health")
            
            if resp.status_code == 200:
                health = resp.json()
                print(f"   ✅ Status: {health.get('status')}")
                print(f"   Services: {json.dumps(health.get('services'), indent=12)}")
                self.results["phase_9"].append({
                    "test": "Health Check",
                    "status": "PASS"
                })
        except Exception as e:
            print(f"   ⚠️  Error: {e}")
    
    async def run_all_tests(self):
        """Run all test suites"""
        print("\n" + "🚀 "*20)
        print("PHASE 7-9 INTEGRATION TEST SUITE")
        print(f"Started: {datetime.now().isoformat()}")
        print("🚀 "*20)
        
        try:
            await self.test_phase_7_retrieval()
            await self.test_phase_8_workflow()
            await self.test_phase_9_tools()
        finally:
            await self.client.aclose()
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print("📊 TEST SUMMARY")
        print("="*60)
        
        for phase, results in self.results.items():
            if not results:
                continue
            
            passed = sum(1 for r in results if r.get('status') == 'PASS')
            failed = sum(1 for r in results if r.get('status') == 'FAIL')
            errors = sum(1 for r in results if r.get('status') == 'ERROR')
            total = len(results)
            
            print(f"\n{phase.upper()}:")
            print(f"  ✅ Passed: {passed}/{total}")
            print(f"  ❌ Failed: {failed}")
            print(f"  ⚠️  Errors: {errors}")
            
            if failed > 0 or errors > 0:
                for r in results:
                    if r.get('status') in ['FAIL', 'ERROR']:
                        print(f"    - {r.get('test')}: {r.get('error', 'Unknown error')[:50]}")
        
        # Overall status
        all_results = [r for results in self.results.values() for r in results]
        overall_passed = sum(1 for r in all_results if r.get('status') == 'PASS')
        overall_total = len(all_results)
        
        print(f"\n{'='*60}")
        if overall_passed == overall_total:
            print(f"🟢 ALL TESTS PASSED ({overall_passed}/{overall_total})")
        else:
            print(f"🟡 PARTIAL SUCCESS ({overall_passed}/{overall_total})")
        print(f"{'='*60}\n")

async def main():
    runner = TestRunner()
    await runner.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
