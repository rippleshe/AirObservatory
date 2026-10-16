@echo off
REM Air Observatory one-click launcher: demo library + API + web dev server.
REM Close the two spawned windows to stop everything.
cd /d "%~dp0"

REM 库里已经有数据就什么都不做；要按当前时间重造窗口，手动跑一次：
REM   uv run python -m scripts.seed_demo --force
echo [1/3] 准备本地演示数据...
uv run python -m scripts.seed_demo

echo [2/3] 启动 API (8110)...
start "AirObservatory API (8110)" cmd /k "uv run python -m uvicorn backend.main:app --host 127.0.0.1 --port 8110"
timeout /t 2 /nobreak >nul

echo [3/3] 启动 Web (5173)...
start "AirObservatory Web (5173)" cmd /k "cd frontend && pnpm run dev"

echo.
echo  API : http://127.0.0.1:8110/api/health
echo  Web : http://127.0.0.1:5173/overview
echo  Close the two windows to stop everything.
echo  要采真实数据（需要 OpenAQ 密钥）再单独跑 uv run python -m scripts.worker
