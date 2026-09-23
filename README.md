# Air Observatory

Air Observatory 是一个面向空气质量观测、模式场对照和预测评估的全栈工作台。当前数据链路只使用真实 provider 数据：OpenAQ 提供地面/传感器观测，Open-Meteo 提供 CAMS 模式分析与预测。两类数据在数据库、API 和 UI 中始终分开标识。

## 当前能力

- **Live**：中国重点城市 CAMS 空间场，城市详情叠加 OpenAQ 最新观测。
- **Explore**：按小时对齐 OpenAQ 与 CAMS，计算 bias、MAE、RMSE 和观测覆盖率。
- **Forecast**：展示 CAMS 外部预测与 Persistence / Rolling Mean 基线，并显示训练数据就绪状态。
- **System**：查看 provider 健康状态、采集运行记录、站点绑定和数据库规模。
- **Data pipeline**：OpenAQ 自动发现并固定城市附近 PM2.5 站点；CAMS 与 OpenAQ 独立采集；后台 worker 与 API 进程分离。
- **Contracts**：FastAPI OpenAPI 生成前端 TypeScript 类型，前端不手写重复 API 类型。

## 快速启动

后端：

```powershell
uv sync --extra dev
uv run python -m uvicorn backend.main:app --host 127.0.0.1 --port 8110
```

后台采集：

```powershell
uv run python -m scripts.worker
```

前端：

```powershell
cd frontend
npm install
npm run api:types
npm run dev
```

访问：`http://127.0.0.1:5173`

## 配置

复制 `.env.example` 为 `.env`，至少配置：

```text
OPENAQ_API_KEY=...
```

`.env` 已被 Git 忽略。API key 不应写入源码、README 或前端环境变量。

## 常用运维命令

立即刷新全部数据：

```powershell
uv run python -m scripts.refresh
```

OpenAQ 历史回填：

```powershell
uv run python -m scripts.backfill_openaq --city 北京 --start 2026-06-25 --end 2026-09-23 --parameter pm25
```

CAMS 历史回填：

```powershell
uv run python -m scripts.backfill_cams --city 北京 --start 2026-09-01 --end 2026-09-23
```

检查 PM2.5 训练数据是否达到门槛：

```powershell
uv run python -m scripts.check_model_readiness --location-id 1
```

## 验证

```powershell
uv run ruff check backend scripts tests
uv run python -m pytest -q
cd frontend
npm run build
```

当前实现原则：缺数据就明确显示缺失；provider 失败保留最后成功状态；不使用示例值伪装成实时数据。
