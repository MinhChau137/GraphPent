#!/usr/bin/env python3
"""Verify Docker build fixes are in place."""

import os
import sys
from pathlib import Path

def check_file_content(filepath, keyword, description):
    """Check if file contains expected keyword."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        if keyword in content:
            print(f"[OK] {description}")
            return True
        else:
            print(f"[XX] {description}")
            return False
    except FileNotFoundError:
        print(f"[XX] {description} - File not found")
        return False
    except Exception as e:
        print(f"[XX] {description}")
        return False

def main():
    """Run verification checks."""
    # Assume script is in project root
    project_root = Path(__file__).parent
    
    print("\n" + "="*60)
    print("🔍 Verifying Docker Build Fixes")
    print("="*60)
    print(f"Project root: {project_root}\n")
    
    checks = [
        (
            project_root / "Dockerfile.ollama",
            "FROM ollama/ollama:latest",
            "Dockerfile.ollama uses official image"
        ),
        (
            project_root / "Dockerfile",
            "COPY requirements.txt .",
            "Dockerfile has optimized layer caching"
        ),
        (
            project_root / "docker-compose.yml",
            "image: ollama/ollama:latest",
            "docker-compose uses direct Ollama image"
        ),
        (
            project_root / ".dockerignore",
            ".git",
            ".dockerignore exists"
        ),
        (
            project_root / "Makefile",
            "DOCKER_BUILDKIT=1",
            "Makefile enables BuildKit"
        ),
        (
            project_root / "docker-build.bat",
            "DOCKER_BUILDKIT",
            "docker-build.bat helper exists"
        ),
        (
            project_root / "scripts" / "docker-build.sh",
            "DOCKER_BUILDKIT",
            "docker-build.sh helper exists"
        ),
        (
            project_root / "DOCKER_BUILD_FIX.md",
            "context canceled",
            "DOCKER_BUILD_FIX.md documentation exists"
        ),
    ]
    
    results = []
    for filepath, keyword, description in checks:
        results.append(check_file_content(filepath, keyword, description))
    
    print("\n" + "="*60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n[SUCCESS] ALL FIXES VERIFIED - READY TO BUILD")
        print("\nBuild now with:")
        print("  make up")
        print("\nOr use helper scripts:")
        print("  docker-build.bat    (Windows)")
        print("  bash docker-build.sh (Mac/Linux)")
        return 0
    else:
        print(f"\n[WARNING] {total - passed} checks failed - see above")
        return 1

if __name__ == "__main__":
    sys.exit(main())
