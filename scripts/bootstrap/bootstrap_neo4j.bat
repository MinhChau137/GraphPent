@echo off
setlocal enabledelayedexpansion

REM Load environment variables from .env file
for /f "tokens=*" %%i in (.env) do (
    set "line=%%i"
    if not "!line:~0,1!"=="#" (
        for /f "tokens=1,2 delims==" %%a in ("!line!") do (
            if "%%a"=="NEO4J_USER" set NEO4J_USER=%%b
            if "%%a"=="NEO4J_PASSWORD" set NEO4J_PASSWORD=%%b
        )
    )
)

docker compose exec neo4j sh -c "cypher-shell -u %NEO4J_USER% -p %NEO4J_PASSWORD% -f /scripts/bootstrap/neo4j_bootstrap.cypher"