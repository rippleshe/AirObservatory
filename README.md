# Air Observatory

一个持续运行的空气质量可视分析系统：OpenAQ 提供地面观测，Open-Meteo 提供 CAMS 模式分析与气象，
历史数据持续保留，用于城市对照、结构分析（PCA / 聚类）和短期预测与回测。
**Observation / Model Analysis / Forecast 三者在数据库、API 和界面上始终分开。**

前端 Vue 3 + TypeScript + Vite + ECharts + 手写 d3/SVG；后端 FastAPI + SQLite。
本仓库同时是课程作业：**四个人，四个页面，一人一个目录并行开发。**

---

## 1. 先跑起来

```powershell
uv sync --extra dev --extra analysis       # 后端依赖
cd frontend && pnpm install                # 前端依赖（回到仓库根目录继续）
start_all.bat                              # 造数据 → 起 API(8110) → 起前端(5173)
```

打开 <http://127.0.0.1:5173/overview>。

`start_all.bat` 会先调 `scripts/seed_demo.py`：**库里有数据就直接跳过**。
数据不在考核范围，所以每个人本地都是一份自己生成的演示库（181 城 × 最近 60 天，逐小时），
**不需要 OpenAQ 密钥，不需要跑采集，一人一份互不影响**。

- 看数据"旧了"（顶栏显示等待新数据、信号条空了）：`uv run python -m scripts.seed_demo --force` 按当前时间重造，两三分钟。
- 演示库不是造假报表：气象场、污染物场、观测缺测、预测快照都由同一套生成器产生，
  **里面的 PCA / 聚类 / 误差统计是真的算出来的**（`backend/analytics` 对这份输入真跑一遍）。
- 库里故意留了不健康的状态，因为四个页面都是围绕"来源、时效、覆盖率"设计的，只给健康数据等于没演示：
  121 城有地面站、60 城只有模式场；一个站中途停报（站点绑定显示 INACTIVE、观测在 40 小时前断掉）；
  3 个城市的气象档案尾部 6 小时是空的（模式场照常完整）；地面批次带着 2 个 429 限流错误（数据更新表显示 PARTIAL）。
- 城市目录是真实坐标（181 城 / 31 省），扩表用 `backend/city_geocoding.csv`，里面每行都是省份校验过的；
  再要扩表就跑 `uv run python -m scripts.expand_cities`（地理编码 + 省份交叉校验，校验不过的不会写进去）。

## 2. 谁负责哪一页

| 页面 | 路由 | 负责人 | 目录 | 分支 |
| --- | --- | --- | --- | --- |
| 全国时空 | `/overview` | 佘硕（组长） | `frontend/src/pages/overview/` | `page/overview` |
| 污染过程 | `/city/:locationId` | 侯嘉佩 | `frontend/src/pages/city/` | `page/city` |
| 多变量关联 | `/analysis` | 张江楠 | `frontend/src/pages/analysis/` | `page/analysis` |
| 预测评估 + 数据与方法 | `/forecast`、`/system` | 唐春柳 | `frontend/src/pages/forecast/`、`pages/system/` | `page/forecast` |

**归属规则只有一句：`frontend/src/pages/<你的页>/` 是你的，`frontend/src/` 下其它一切是共享区。**
自检也就一句话：

```bash
git diff --name-only origin/main        # 除了共享文件，只应该出现你自己那个目录
```

想换人？改上面这张表的一行，其他人不受影响。

## 3. 共享区（一个改动同时影响四个人）

```text
frontend/src/App.vue                 全站外壳：左侧导航 + 顶栏城市选择器 + 健康灯
frontend/src/main.ts                 入口
frontend/src/app/router.ts           路由表
frontend/src/api/                    client / request / schema.d.ts（生成物）
frontend/src/styles/                 base.css 设计 token + research.css 共享排版
frontend/src/lib/                    palette 颜色 / charts ECharts 注册 / motion 动效 / viz 绘图基元
frontend/src/composables/            跨页复用的组合式函数
frontend/src/stores/context.ts       全站唯一的跨页状态：顶栏选中的城市
frontend/src/shared/WindClearance.vue  唯一被两个页面共用的组件（高度由它自己拥有）
.agents/skills/                      给 AI 用的项目级 skill（含本项目开工规则，见第 9 节）
frontend/package.json、pnpm-lock.yaml、vite.config.ts、tsconfig*.json
backend/**、scripts/**、tests/**
```

需要改共享区？**单独开一个小 PR，说明理由，由组长合并。**

三条硬规则：

1. **不要跑 `pnpm run api:types`**：它会覆盖 1803 行的 `src/api/schema.d.ts`，四个人一起改必冲突。
   真要加接口，`backend/` 的改动和重生成 `schema.d.ts` 必须在同一个 PR 里，由组长做。
2. **路由路径与 route name 冻结**（`/city/:locationId` 被顶栏和全国页地图跳转引用）。要加 query 参数没问题。
3. **不要 `git add -A` / `git add .`**：会把本地数据库、构建产物一起提交。

还有一条不是靠自觉的：**跨页引用会被构建直接拦下来**。`pnpm run build` 里跑了一道边界检查，
`pages/<a>/` 引 `pages/<b>/` 的文件、或者页面之外的代码引页面，都会报错退出。
需要两个页面共用东西时，放进 `src/shared/`（像 `WindClearance.vue` 那样），或者找组长开单独的 PR。

## 4. 开工流程

```bash
git clone https://github.com/rippleshe/AirObservatory.git
cd AirObservatory
git checkout -b page/city            # 换成你自己那一页

# 之后每轮开工前（组长合并完会在群里说一声）
git fetch origin && git rebase origin/main

# 提交：只 add 你自己改的文件
git add frontend/src/pages/city/CityPage.vue
git commit -m "feat(city): 小时热力改成时段选择"
git push -u origin page/city
```

然后去 GitHub 开 PR，**合并由组长点，不要自己点 Merge**。

数据库文件不入库是技术限制，不是规矩：单文件上百 MB 超过 GitHub 单文件 100 MiB 上限，
而且二进制没法手工合并。`.gitignore` 已经排除了它，不用你操心。

## 5. 每页要做到什么（唯一口径）

总口径：**受众是科研人员**。数据语义优先于视觉完整：缺数据就显示缺失，不补造值；
地面实测与模式换算必须分开显示，且标注清楚来源；中国 AQI 按 HJ 633-2026，必须说明是实测换算还是模式换算。

**全国时空** —— 地图是主导航面，点城市进详情；省代表（每省 AQI 最高的城市）是一种展示归约，
标题里的省数、色带格数、地图点数必须描述同一个集合；时间切片所有图联动、同一个数据 cohort。

**污染过程** —— Pulse / Structure / Forecast / Trust 四区；地面观测和模式分析分成两条独立系列，
不合并成一条线；Trust 区展示覆盖率、Provider 绑定和数据时效。

**多变量关联** —— PCA 要给解释方差、载荷、样本量和标准化方法；相关矩阵标注样本数与时间窗；
聚类只作探索线索，不下"环境类型"结论；风玫瑰说明风速分箱，**不推因果**。

**预测评估** —— 分清 CAMS 外部预测 / 本项目模型预测 / 地面真值三者；每个 horizon 给 MAE、RMSE、
基线对比和样本数；回测用后来真正到达的观测值。

**数据与方法** —— provider 健康、站点绑定、采集批次、存储状态。

## 6. 提交前自检

```powershell
# 前端（在 frontend/ 里跑）
cd frontend
pnpm run build                         # 含 vue-tsc 类型检查，必过（红了会把别人的 PR 一起卡住）
node scripts/visual-check.mjs          # 五个路由的黑盒验收：console error、横向溢出、关键交互
node scripts/shot.mjs                  # 截图到 frontend/.review/，自己打开看图，不要只看命令行

# 后端与仓库自查（在仓库根目录跑）
cd ..
uv run python -m pytest -q
uv run ruff check backend scripts tests
git status                             # 确认没有数据库、schema.d.ts、pnpm-lock.yaml 被改动
```

## 7. 卡住了怎么办

| 症状 | 解决 |
| --- | --- |
| 页面打开是空白 | 后端起了吗？`http://127.0.0.1:8110/api/health` 有没有 `{"ok":true}` |
| 顶栏显示"等待新数据" | 演示数据的时间窗口旧了，`uv run python -m scripts.seed_demo --force` |
| `pnpm run build` 报类型错误 | 看错误里的文件是不是你的；不是你的说明主干上有问题，找组长 |
| `git rebase` 冲突 | 不要瞎 `--force`，在群里说一声让组长看 |
| `push` 被拒绝（文件太大） | 你八成提交了数据库，`git reset HEAD~1` 撤回，重新只 add 自己的文件 |
| 想改共享区的文件 | 单独开个小 PR 说明为什么非改不可 |

## 8. 可选：采真实数据（平时不需要）

数据不在考核范围，演示库够用。真要接真实数据：

```powershell
copy .env.example .env      # 然后在 .env 里填自己申请的 OPENAQ_API_KEY（OpenAQ 官网免费）
uv run python -m scripts.init_db
uv run python -m scripts.backfill_cams --all --start 2026-07-18 --end 2026-10-16 --batch-size 5
uv run python -m scripts.backfill_weather --all --start 2026-07-18 --end 2026-10-16 --batch-size 10
uv run python -m scripts.worker     # 常驻采集（API 与前端照常）
```

`.env` 不入库，密钥不会被提交。真实采集的库和演示库是两个文件：想两套都留着，
在 `.env` 里用 `AIR_OBSERVATORY_DATABASE_PATH` 指过去就行（默认路径是演示库）。

## 9. 用 AI 写代码

**AI 工具支持项目级 skill 时，直接开工就行**（ZCode / Claude Code 等会自动发现）：

- `.agents/skills/air-observatory/SKILL.md` —— 本项目自己的开工规则：归属表、共享冻结区、
  三个最容易误伤的点、验证命令顺序、改图表不能破的四条设计约束。**它会让 AI 自己守规矩，不用你每次交代。**
- 仓库里还带了几个通用 skill，队友没装过也能直接用：`frontend-design`、`impeccable`（视觉设计）、
  `ponytail`（精简代码）、`codebase-design`、`webapp-testing`。

**工具不支持的话**，把下面整段贴给它当第一条消息：

```text
你在帮我改一个可视化课程作业仓库（Air Observatory）。先读 .agents/skills/air-observatory/SKILL.md，
再读根目录 README.md，这两份是开工依据。

我是 <你的名字>，负责四个页面里的「<你的页面>」，分支 <page/xxx>。
我**只能改 frontend/src/pages/<我的页面目录>/ 里的文件**，frontend/src/ 下其它目录以及
backend/、scripts/、tests/、各种配置文件都是共享冻结区，改之前要先告诉我为什么非改不可。

铁律：
1. 提交只能 git add <明确路径>，禁止 git add -A。
2. 不要跑 pnpm run api:types（会覆盖生成文件，四个人都改必冲突）。
3. 不要提交数据库和构建产物。
4. 不要往 main 推，也不要自己 Merge；只推到我的分支并开 PR。
5. 不要引入或升级依赖。

动手前：git fetch origin && git rebase origin/main。
改完必须：cd frontend && pnpm run build（含类型检查，必过），然后 node scripts/visual-check.mjs。
需要看数据/跑后端：先 uv run python -m scripts.seed_demo（本地演示库，不需要密钥），
再 uv run python -m uvicorn backend.main:app --host 127.0.0.1 --port 8110。
如果构建报的错不在我负责的文件里，先告诉我，不要自己去改别人的文件。
```

选题的正式表述见 [`docs/选题报告.md`](docs/选题报告.md)。
下一步的数据骨架、地图留痕与文案收尾见 [`docs/规划.md`](docs/规划.md)（2026-10-16 定稿，事实已核实，按 A→E 执行）。
