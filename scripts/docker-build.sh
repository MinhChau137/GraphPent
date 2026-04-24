#!/bin/bash
# Build optimization script for Docker

echo "🔧 Docker Build Optimization Script"
echo "===================================="

# Enable BuildKit for faster builds
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

echo "✅ BuildKit enabled for faster builds"
echo "Building with: docker compose up --build -d"
echo ""

# Clean old images if needed (optional)
# docker system prune -f

# Build with verbose output
docker compose up --build -d

echo ""
echo "Build complete! Check status:"
echo "  docker compose ps"
echo "  docker compose logs -f backend"
