@echo off
REM ============================================================================
REM  LLM-Wiki Engine - 一键启动脚本 (Windows)
REM ----------------------------------------------------------------------------
REM  功能:
REM    1. 检查必备依赖(docker / python / node / npm)
REM    2. 缺失则提示安装链接
REM    3. 检查 .env 是否存在,缺则从 .env.template 复制
REM    4. 三种启动模式:
REM         start.bat docker  → docker-compose 全栈(默认)
REM         start.bat mock    → 纯前端 + Mock 后端
REM         start.bat dev     → 本地 Python + npm dev
REM
REM  用法:
REM    start.bat
REM    start.bat mock
REM ============================================================================

setlocal EnableDelayedExpansion

REM ---- 切换到脚本目录 ----
cd /d "%~dp0"

REM ---- 模式 ----
set "MODE=%~1"
if "%MODE%"=="" set "MODE=docker"

echo.
echo ===========================================================
echo    LLM-Wiki Engine - One-Click Start (Windows)
echo    Mode: %MODE%
echo ===========================================================
echo.

REM ---- 模式分发 ----
if /i "%MODE%"=="docker" goto :MODE_DOCKER
if /i "%MODE%"=="mock"   goto :MODE_MOCK
if /i "%MODE%"=="dev"    goto :MODE_DEV
if /i "%MODE%"=="help"   goto :HELP
if /i "%MODE%"=="-h"     goto :HELP
if /i "%MODE%"=="--help" goto :HELP

echo [ERROR] Unknown mode: %MODE%
echo Run "start.bat help" for usage.
exit /b 1


REM ===========================================================
REM  MODE 1: docker-compose
REM ===========================================================
:MODE_DOCKER
echo [INFO]  [1/4] Checking docker...
where docker >nul 2>&1
if errorlevel 1 (
    echo [ERROR] docker not found. Install: https://docs.docker.com/desktop/install/windows-install/
    exit /b 1
)
docker compose version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] "docker compose" subcommand unavailable. Need Docker Desktop 4.0+.
    exit /b 1
)
echo [OK]    docker compose available

echo [INFO]  [2/4] Checking .env...
call :ENSURE_ENV
if errorlevel 1 exit /b 1

echo [INFO]  [3/4] Starting docker-compose stack...
cd llmwiki
docker compose -f deploy\docker-compose.yml up -d --build
if errorlevel 1 (
    echo [ERROR] docker compose up failed
    exit /b 1
)

echo [INFO]  [4/4] Waiting for services...
timeout /t 5 /nobreak >nul
for %%p in (8000 8001 8002 8003 8004) do (
    curl -fsS "http://localhost:%%p/health" >nul 2>&1
    if !errorlevel! equ 0 (
        echo [OK]    Service :%%p healthy
    ) else (
        echo [WARN]  Service :%%p not yet reachable
    )
)

echo.
echo [OK]    Stack started. Logs: docker compose -f llmwiki\deploy\docker-compose.yml logs -f
echo [OK]    Frontend dev: cd llmwiki\frontend ^&^& npm run dev
goto :EOF


REM ===========================================================
REM  MODE 2: Mock backend
REM ===========================================================
:MODE_MOCK
echo [INFO]  [1/3] Checking node...
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] node not found. Install: https://nodejs.org/ (^>= 18)
    exit /b 1
)
where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found. Bundled with node.
    exit /b 1
)
echo [OK]    node + npm available

echo [INFO]  [2/3] Preparing Mock backend...
if not exist "mock-backend" (
    echo [ERROR] mock-backend\ directory not found
    exit /b 1
)
cd mock-backend
if not exist "node_modules" (
    echo [INFO]  First run, installing dependencies...
    call npm install --no-audit --no-fund
)

echo [INFO]  [3/3] Starting Mock backend on :8000...
echo [OK]    Mock backend - http://localhost:8000
echo [OK]    Endpoints: GET /api/health  POST /api/query/ask  ...
echo [OK]    Stop: Ctrl+C
echo.
node server.js
goto :EOF


REM ===========================================================
REM  MODE 3: dev (local Python + npm)
REM ===========================================================
:MODE_DEV
echo [INFO]  [1/5] Checking python/node...
where python >nul 2>&1
if errorlevel 1 (
    where python3 >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] python not found. Install: https://www.python.org/downloads/ (^>= 3.11)
        exit /b 1
    )
)
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] node not found. Install: https://nodejs.org/
    exit /b 1
)
echo [OK]    python + node available

echo [INFO]  [2/5] Checking .env...
call :ENSURE_ENV
if errorlevel 1 exit /b 1

echo [INFO]  [3/5] Installing Python deps...
cd llmwiki
pip install -q -r requirements.txt
echo [OK]    Python deps ready

echo [INFO]  [4/5] Installing frontend deps...
cd frontend
if not exist "node_modules" (
    call npm install --no-audit --no-fund
)
echo [OK]    Frontend deps ready

echo [INFO]  [5/5] Manual start hints:
echo.
echo [WARN]  Please start these services in separate terminals (assume PG/Redis already running):
echo   Terminal 1: cd llmwiki ^&^& uvicorn app.evidence.service:app --port 8001
echo   Terminal 2: cd llmwiki ^&^& uvicorn app.query.gateway:app    --port 8000
echo   Terminal 3: cd llmwiki ^&^& uvicorn app.admin.service:app    --port 8002
echo   Terminal 4: cd llmwiki ^&^& uvicorn app.ingest.service:app   --port 8003
echo   Terminal 5: cd llmwiki ^&^& uvicorn app.generation.service:app --port 8004
echo   Terminal 6: cd llmwiki ^&^& python -m app.compile.run_worker
echo   Terminal 7: cd llmwiki\frontend ^&^& npm run dev
goto :EOF


REM ===========================================================
REM  HELP
REM ===========================================================
:HELP
echo Usage: start.bat [MODE]
echo.
echo MODE:
echo   docker  (default)  Use docker-compose full stack
echo   mock              Mock backend only (zero external deps)
echo   dev               Local Python + npm dev
echo   help              Show this help
echo.
echo Examples:
echo   start.bat                 (docker)
echo   start.bat mock            (mock only)
echo   start.bat dev             (local dev)
goto :EOF


REM ===========================================================
REM  Helper: ensure .env exists
REM ===========================================================
:ENSURE_ENV
if exist ".env" (
    echo [OK]    .env ready
    exit /b 0
)
echo [WARN]  .env file not found
if exist ".env.template" (
    copy /Y .env.template .env >nul
    echo [OK]    Copied .env.template to .env
    echo [WARN]  Edit .env to fill real API credentials, then re-run:
    echo [WARN]    notepad .env
    echo [WARN]  Key fields: OPENAI_API_KEY / OPENAI_BASE_URL / EMBED_API_KEY / JWT_SECRET
    exit /b 1
)
echo [ERROR] .env.template also missing. Please pull latest template.
exit /b 1
