---
name: air-observatory
description: 在 Air Observatory 这个仓库里干活时先用它——Vue 3 + FastAPI 的空气质量可视分析课程作业，四个人一人一页并行开发。只要涉及 frontend/src/pages/ 下的任何文件、本地演示数据库（scripts/seed_demo.py）、跑 pnpm build / visual-check / pytest / ruff、截图看效果、或者准备提交开 PR，就适用；即使对方只说"改一下我那一页""这个图不对""页面打不开""帮我提交"。Use whenever working in the Air Observatory repository (air quality visualization course project, Vue 3 + FastAPI, one page per teammate).
---

# Air Observatory 开工规则

**权威口径在仓库根目录的 `README.md`**（启动、分工、每页验收标准、故障排查都在里面）。
这份 skill 只讲两件事：动手前必须守的边界，和改完必须跑的验证。

## 1. 动手前先确认边界

| 页面 | 路由 | 负责人 | 目录 |
| --- | --- | --- | --- |
| 全国时空 | `/overview` | 佘硕 | `frontend/src/pages/overview/` |
| 污染过程 | `/city/:locationId` | 侯嘉佩 | `frontend/src/pages/city/` |
| 多变量关联 | `/analysis` | 张江楠 | `frontend/src/pages/analysis/` |
| 预测评估 / 数据与方法 | `/forecast`、`/system` | 唐春柳 | `frontend/src/pages/forecast/`、`pages/system/` |

（换人了以 README 里的表为准。）

- **只能改负责的那个页面目录。** `frontend/src/` 下其它一切是共享区；`backend/`、`scripts/`、`tests/`、
  `package.json`、`pnpm-lock.yaml`、`vite.config.ts`、`tsconfig*.json`、`index.html` 同样冻结。
- 需要动共享区或后端接口时：**停下来向用户说明为什么非改不可，由他决定**，不要自己动手改。
- 不引入、不升级依赖。

## 2. 三个最容易误伤的点

1. `frontend/src/api/schema.d.ts` 是后端自动生成的（1803 行）。**不要跑 `pnpm run api:types`**；
   真要加接口，得由组长把 `backend/` 改动和重生成放在同一个 PR 里。
2. 路由路径与 route name 冻结（`/city/:locationId` 被顶栏选择器和全国页地图跳转引用）。加 query 参数没问题。
3. `frontend/src/shared/WindClearance.vue` 被两个页面共用，且高度由它自己拥有：
   不传 `height` 就填满父容器，传数字（px）就是固定高度。不要用父级 `:deep()` 去改它尺寸。

## 3. 跑起来（要真看数据/截图时才需要）

```bash
# 后端：本地演示库（181 城 × 60 天合成数据，不需要任何密钥）
uv run python -m scripts.seed_demo        # 已有数据会跳过；要按当前时间重造加 --force（约两三分钟）
uv run python -m uvicorn backend.main:app --host 127.0.0.1 --port 8110

# 前端
cd frontend && pnpm install && pnpm run dev     # http://127.0.0.1:5173/overview
```

数据是本地生成的演示库，看旧了（顶栏显示"等待新数据"）重跑 `seed_demo --force` 即可。
库里故意含不健康状态（一个站停报、三城气象档案尾部为空、地面批次 PARTIAL）——
改覆盖率 / 时效 / Trust 相关的东西时别把"缺数据"当成 bug 修掉。

## 4. 改完必须跑（顺序就是优先级）

```bash
cd frontend
pnpm run build                 # vue-tsc 类型检查 + 页面边界检查 + 打包，必过；红了会卡住所有人的 PR
node scripts/visual-check.mjs  # 五个路由黑盒验收：console error / 横向溢出 / 关键交互，必须 exit 0
node scripts/shot.mjs          # 截图到 frontend/.review/，然后真的看图，不要只看命令行

cd ..
uv run python -m pytest -q     # 后端 33 个测试
uv run ruff check backend scripts tests
git status                     # 确认没有数据库、schema.d.ts、pnpm-lock.yaml 被改动
```

`build` 里的**页面边界检查**会拒绝任何跨页引用（`pages/<a>/` 引 `pages/<b>/` 的文件）：
报这个错说明你想用的东西属于别人那一页，改成放进 `src/shared/` 或跟用户确认。

## 5. 提交

```bash
git fetch origin && git rebase origin/main      # 开工前先接主干
git add <明确路径>                               # 禁止 git add -A / git add .
git commit -m "feat(city): 小时热力改成时段选择"
git push -u origin page/city
```

推到自己的 `page/<页>` 分支并开 PR，**合并由组长点，不要自己 merge，不要推 main**。
PR 前自查：`git diff --name-only origin/main` 应该只出现自己那个目录（加共享文件的话要有理由）。

## 6. 改图表时不能破的四条设计约束

这几条是这个作业的评分点，改任何图之前都要确认没破坏：

1. **地面实测与模式分析是两套数据**（`data_kind: observation` / `model_analysis`），
   分开画、不合并成一条线，并标明来源（CAMS 模式换算 vs 地面观测）。
2. **缺数据就显示缺失**，不要插值、不要补零、不要为了图好看填值。缺测有专门的显示样式。
3. **中国 AQI 按 HJ 633-2026**，并说明是实测浓度换算还是模式浓度换算；单位（µg/m³、CO 的 mg/m³）不能混。
4. **统计图必须带样本量**：PCA 给解释方差与标准化方法，相关矩阵标样本数与时间窗，
   预测每个 horizon 给 MAE/RMSE/样本数；聚类只作探索线索，不推因果。

## 7. 常用参考

- 每页要做到什么、故障排查：`README.md`
- 选题正式表述：`docs/选题报告.md`
- 数据从哪来、为什么这样生成：`scripts/seed_demo.py` 顶部的说明
- 想采真实数据（可选，需要自己申请 OpenAQ 密钥）：README 第 8 节
