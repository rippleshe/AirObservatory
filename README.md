# Air Observatory

Air Observatory 是一个持续运行的空气质量动态可视分析系统：OpenAQ 提供地面/传感器观测，Open-Meteo 提供 CAMS 模式分析与预测；历史数据持续保留，用于城市对照、预测和后续 PCA / 气象结构分析。Observation、Model Analysis、Forecast 在数据库、API 和界面中始终分开。

## 当前产品面

- **National Overview**：CAMS 覆盖 60 城的空气场，全国层按 **31 个省代表**（每省取该省当前 AQI 最高的城市）阅读——HJ 633-2026 AQI 模式换算、区域剖面、等级结构、24h 变化、地面真值覆盖，以及 31 省统一特征 PCA / 探索性聚类结构指纹。地图直接标注每一个省代表；完整 60 城名册由矩阵的表格孪生承载，不因显示层收敛而丢失。
- **City**：单城四区一体化详情——Pulse、Structure、Forecast、Trust；包含六污染物历史、小时时段热力、污染物×气象 PCA、预测回测与覆盖率。
- **System**：provider health、站点绑定、采集运行、数据库状态。
- **Pipeline**：CAMS 60 城批量刷新；OpenAQ 独立采集；worker 与 Web API 分进程运行。
- **Contract**：FastAPI OpenAPI 自动生成 TypeScript 类型。

产品只有一条叙事：**全国哪里值得关注 → 这个城市发生了什么 → 结构与关联 → 接下来怎样、是否可信**。预测、结构、可信度都在城市页内，不再单开页面。

## 启动

后端：

```powershell
uv sync --extra dev --extra analysis
uv run python -m uvicorn backend.main:app --host 127.0.0.1 --port 8110
```

后台采集：

```powershell
uv run python -m scripts.worker
```

前端：

```powershell
cd frontend
pnpm install
pnpm run api:types
pnpm run dev
```

打开：`http://127.0.0.1:5173/overview`

## 配置

复制 `.env.example` 为 `.env` 并配置 `OPENAQ_API_KEY`。`.env` 已被 Git 忽略，且已从版本库中移除；密钥不得进入源码、README 或前端环境变量。

## 数据准备

运行时数据库 `data/air_observatory.db` **不入库**：单文件已超 GitHub 100 MiB 上限，且每次采集都会写入，入库必然产生无法手工合并的二进制冲突。首次 clone 后任选其一：

```powershell
uv run python -m scripts.init_db
uv run python -m scripts.backfill_cams --all --start 2026-06-25 --end 2026-09-23 --batch-size 5
uv run python -m scripts.backfill_openaq --city 北京 --start 2026-06-25 --end 2026-09-23 --parameter pm25
uv run python -m scripts.backfill_weather --all --start 2026-06-25 --end 2026-09-23 --batch-size 10
```

或直接使用课程组共享的数据库文件（网盘 / Release 附件）放到 `data/air_observatory.db`。离线分析产物用 `scripts.run_analysis` 与 `scripts.run_fingerprint` 重新物化。单元测试使用临时库，不依赖该文件。

## 文档

| 文档 | 作用 |
| --- | --- |
| `PRODUCT.md` | **唯一权威**的产品与视觉口径（科研受众） |
| `docs/选题报告.md` | 选题正式表述 |
| `docs/科研可视化重构.md` | 科研定位、逐图重构方向与验收条件 |
| `ARCHITECTURE.md` | 数据闭环、产品层级与工程边界 |
| `docs/协作指南.md` | 四人分工、文件归属、分支与 PR 流程 |

历史上面向普通用户的 `DESIGN.md`、`docs/SESSION_BRIEF.md`、`docs/REDESIGN.md` 与上述口径冲突，已删除（需要时从 git 历史取回），四个页面的分支不得再引用。

## 常用命令

```powershell
uv run python -m scripts.refresh
uv run python -m scripts.backfill_openaq --city 北京 --start 2026-06-25 --end 2026-09-23 --parameter pm25
uv run python -m scripts.backfill_cams --all --start 2026-06-25 --end 2026-09-23 --batch-size 5
uv run python -m scripts.backfill_weather --all --start 2026-06-25 --end 2026-09-23 --batch-size 10
uv run python -m scripts.run_analysis --all --hours 2160 --components 5
uv run python -m scripts.run_fingerprint --hours 2160 --components 5 --max-clusters 6
uv run python -m scripts.check_model_readiness --location-id 1
```

验证：

```powershell
uv run ruff check backend scripts tests
uv run python -m pytest -q
cd frontend
pnpm run build
node scripts/visual-check.mjs
```

原则：缺数据就显示缺失；provider 失败不伪造替代值；中国 AQI 必须标明是地面实测换算还是 CAMS 模式浓度换算。
