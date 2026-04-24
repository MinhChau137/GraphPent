@echo off
REM Windows Docker Build Script
REM Usage: docker-build.bat

echo.
echo ========================================
echo Docker Build - GraphRAG
echo ========================================
echo.

REM Enable BuildKit
set DOCKER_BUILDKIT=1
set COMPOSE_DOCKER_CLI_BUILD=1

echo [*] BuildKit enabled
echo [*] Starting build...
echo.

REM Check if docker is running
docker ps > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running!
    echo Please start Docker Desktop and try again.
    pause
    exit /b 1
)

echo [*] Docker is running - proceeding with build
echo.

REM Start build
docker compose up --build -d

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    echo.
    echo Try the following:
    echo 1. Check Docker Desktop is running
    echo 2. Ensure 8GB+ RAM allocated to Docker
    echo 3. Check disk space (need ~10GB)
    echo 4. Run: docker system prune -a --volumes
    echo 5. Try again
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo [SUCCESS] Build complete!
echo ========================================
echo.
echo Waiting for services to start...
timeout /t 3 /nobreak

echo.
echo Services status:
docker compose ps

echo.
echo [INFO] Access endpoints:
echo   Backend:  http://localhost:8000
echo   Ollama:   http://localhost:9443
echo   Neo4j:    http://localhost:7474
echo   Weaviate: http://localhost:8080
echo.
echo [INFO] View logs: docker compose logs -f backend
echo.

pause
