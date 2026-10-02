@echo off
REM Air Observatory one-click launcher: API + worker + web dev server.
REM Close the spawned windows to stop each process.
cd /d "%~dp0"

start "AirObservatory API (8110)" cmd /k "uv run python -m uvicorn backend.main:app --host 127.0.0.1 --port 8110"
timeout /t 2 /nobreak >nul
start "AirObservatory Worker" cmd /k "uv run python -m scripts.worker"
start "AirObservatory Web (5173)" cmd /k "cd frontend && pnpm run dev"

echo.
echo  API    : http://127.0.0.1:8110/api/health
echo  Web    : http://127.0.0.1:5173/overview
echo  Worker : separate window, logs ingestion cycles
echo  Close the three windows to stop everything.
