# SESSION BRIEF — 新会话必读

> 给下一个 ZCode 会话的交接文档。用户习惯 + 项目铁律 + 当前状态 + 运行方式。读这页就能接手，不需要翻旧会话。

## 用户是谁、怎么合作

- **课程期末作业**，评分看可视化的震撼度与完成度。目标：获奖级、经济学人/FT 编辑图型水准、**绝对不要科研绘图味**。
- **合作方式**：授权大刀阔斧改革（"不要小修小改"）；动手前先想清楚、可写计划文档；每轮改完用 Playwright 截图**亲读验收**（visual-judge 子代理在本环境不可用，直接自己 Read PNG）；**推送 GitHub 需用户确认后执行**，平时只改不推。
- **反馈风格**：直接、会骂"小学生级别/很脏/很丑"。逐条消化，不要辩解。

## 视觉铁律（违反=返工）

1. **瑞士极简浅色**（Apple/Linear/Vercel 基调），永不做深色主题。色感脏是第一禁区——现行为清亮系：AQI 六级 `#10b981/#eab308/#f97316/#ef4444/#8b5cf6/#9f1239`（palette.ts，改色必须过 CVD 邻接 ΔE≥10/正常≥15 的自写校验）。
2. **文字越少越好**：页面可见静态散文=0；兜底句 ≤6 字；灰字堆、图例说明、方法注能删则删。
3. **标题=功能词，不是数据结论**：区块标题只写 2–4 字（构成/排名×风场/联动/趋势…），11.5px 宽字距 muted；面板组件内部禁止第二层标题；大黑数据句（"某某 领跑…""XX 比 YY 高 N"）已全站废除，别再发明。
4. **不要"收纳"**（折叠/卡片格子），全出血 section + hairline 分隔。
5. **不要图表库默认质感**：核心图手写 SVG/canvas；ECharts 仅复杂坐标系且深度定制；不偷懒。

## 已知坑（踩过的）

- ECharts6 `graph-circular` 在 SVG 渲染器下节点不渲染 → 弦图已手写，别回去。
- 手写 SVG 图容器必须**定高**（svg attr=clientHeight 会反馈爆炸）；尺寸一律走 `lib/viz.ts` 的 `useElementSize`。
- ECharts 更新用 `mergeOption + universalTransition`，禁 `notMerge` 瞬跳。
- `start_all.bat` 的 cmd /k 窗口从 Git Bash spawn 会静默失败 → 用 PowerShell `Start-Process` + 重定向（服务已这样常驻）。
- 气象数据天然滞后 5 天；OpenAQ 只有京沪等少数城市有真数据（"stale"是现实不是故障）。
- shot.mjs 已双次滚动行走（晚挂载 section 的入场触发需要第二遍）。

## 架构速览

- 后端 FastAPI+SQLite（uv，8110）：`backend/`。新增过 `GET /api/overview/national/weather?hours=&location_id=`（60 城逐小时风速/风向/温度对齐矩阵）。
- 前端 Vue3+Vite+TS+pnpm（5173）：手写图在 `frontend/src/components/`——ChinaFieldMap（d3 地图+canvas 粒子风场+时间机器插值）、StreamGraph（河流+波浪扫入）、BarChartRace（排名赛跑）、WindRose（24 方位玫瑰）、ChordDiagram（丝带弦图）、WaterfallChart、HorizonChart、HourRing、PhasePath。动效统一走 `lib/motion.ts`（GSAP，ScrollTrigger，reduced-motion 单点）。颜色唯一出口 `lib/palette.ts`。
- 视图 3 个：NationalOverviewView / CityDetailView / SystemView（纯状态表）。

## 运行

- 常驻三件套已以独立 Windows 进程跑着（不依赖 ZCode）：重启用 `start_all.bat`，停止用 `stop_all.bat`。Worker 日志 `data/_worker_err.log`。
- 验收：`pnpm exec vue-tsc -b` → `pnpm run build` → `node scripts/shot.mjs all`（动画帧加 `APP_MOTION=1`）→ Read `frontend/.review/*.png` 亲读。

## 当前状态 & Backlog

- 六轮改革已完成（详见 git log 与 `docs/REDESIGN.md`）。数据从 2026-09-03 起逐小时积累，worker 常驻采集，跨度越长图越有料。
- Backlog：TraceDeck / PollutionWeave / Backtest 三张 ECharts 老图手写重绘；ridgeline、Nightingale 玫瑰、barcode plot；季节对比 slope（数据 >6 个月后）。
