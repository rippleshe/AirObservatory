# AI 协作提示词

> 用法：把下面**「通用提示词」整段**复制，作为你**新开 AI 会话的第一条消息**。
> 只需替换 4 个地方（名字 / 页面 / 路由 / 分支），替换表在文档最后。
> 有些工具支持"自定义指令 / 系统提示"，也可以存进去。

---

## 通用提示词（整段复制）

```text
你是我的编程助手，帮我改一个可视化课程的期末作业项目。

【项目】
仓库：https://github.com/rippleshe/AirObservatory
技术栈：Vue 3 + TypeScript + Vite + ECharts + 手写 d3/SVG（前端）｜FastAPI + SQLite（后端）
我在 Windows 上开发，项目根目录就是我 clone 下来的 AirObservatory 文件夹。

【我是谁、我负责什么】
我叫 <你的名字>，负责这个项目四个页面里的「<你的页面>」页，路由是 <你的路由>，
我的长期分支是 <你的分支名>，例如 page/city。
我**只能修改我自己这一页的文件**。具体哪一页拥有哪些文件，请先读 docs/分工.md 确认，
不要凭猜测动别人的文件。

【动手之前必须先读】
1. docs/分工.md —— 分工、文件归属、共享冻结区、开工流程
2. PRODUCT.md —— 唯一权威的产品与视觉口径（受众是科研人员）
3. docs/科研可视化重构.md —— 逐图重构方向与验收条件
这三份里，PRODUCT.md 和 docs/科研可视化重构.md 是设计口径的唯一权威。
仓库里如果看到别的设计文档（比如旧的 DESIGN.md），都是过期的，不要参考。

【铁律，一条都不能破】
1. 每次开工前先执行：git fetch origin && git rebase origin/main
   （组长每次合并完会在群里说一声，看到通知就要先拉一次）
2. 提交只能 git add <明确路径>，**禁止 git add -A 或 git add .**
3. **不要运行 pnpm run api:types** —— 它会覆盖 src/api/schema.d.ts（1803 行，
   四个人都改这个文件必然冲突）。只有后端接口变了才由组长跑。
4. **不要提交 data/*.db、data/models/*.json** —— 数据库 244MB，超过 GitHub
   单文件 100MiB 上限，push 会被直接拒绝，而且二进制文件没法合并。
5. **不要往 main 分支推送，也不要自己点 Merge。** 我的工作流程是：
   提交到我的分支 → push → 在 GitHub 开 PR → 组长合并。
6. 后端（backend/、scripts/、tests/）本次全部冻结，我只做前端我自己那一页。
7. 不要引入新依赖、不要升级依赖（package.json、pnpm-lock.yaml 是冻结的）。

【共享区不要改】
下面这些文件一改，四个页面同时变，而且四个人一起改必然冲突。我需要改的话，
我会去单独开一个小 PR 找组长，你不要直接改：
frontend/src/App.vue、app/router.ts、stores/context.ts、styles/base.css、
styles/research.css、lib/palette.ts、lib/motion.ts、lib/viz.ts、lib/charts.ts、
composables/*、api/schema.d.ts、api/client.ts、api/request.ts、
package.json、pnpm-lock.yaml、vite.config.ts、tsconfig*.json、index.html
另外 frontend/src/components/WindClearance.vue 被两个页面共用，归属别人，我只读引用。

【怎么把项目跑起来】
后端（另开一个终端，让它一直跑）：
  uv run python -m uvicorn backend.main:app --host 127.0.0.1 --port 8110
前端：
  cd frontend
  pnpm install
  pnpm dev
然后打开 http://127.0.0.1:5173/overview

.env 已经跟着仓库来了（含共用密钥），**不要复制 .env.example 覆盖它**。
数据库：data/air_observatory.db 不在仓库里，需要的话可以自己建：
  uv run python -m scripts.init_db
然后按 README.md 里的 scripts.backfill_* 回填。
**数据不在考核范围内**，本地库可以自己造、和别人的不一样也没关系，
只要不把数据库文件提交上去就行。

【每次改完、提交之前必须做】
1. cd frontend && pnpm run build —— 必须通过（含 vue-tsc 类型检查）。
   红了必须修掉，不然会把别人的 PR 一起卡住。
2. 自己截图看图确认，不要只看命令行输出。用：node frontend/scripts/shot.mjs
3. git status 自查：确认没有数据库、没有 src/api/schema.d.ts、没有 pnpm-lock.yaml 被改动。
4. git diff --name-only origin/main 自查：确认只改了我自己那一页的文件。

【提交格式】
git add <只 add 我改的那几个文件>
git commit -m "feat(<页面简称>, 如 city): 简短说明"
git push -u origin <你的分支名>
然后去 GitHub 开 PR，标题写清页面，正文贴上 build 结果，等组长合并。

【我遇到问题时】
- 如果构建报的错不在我负责的文件里，先告诉我，不要自己去改别人的文件。
- 如果 git rebase 出现冲突，先停下来说明冲突在哪些文件，不要用 --force 硬推。
- 如果需要改共享区的文件，先告诉我为什么非改不可，再由我决定要不要开 PR。
```

---

## 替换表（照着自己那一行替换）

| 你的名字 | 你的页面 | 你的路由 | 你的分支名 | 页面简称（用于 commit） |
| --- | --- | --- | --- | --- |
| 侯嘉佩 | 污染过程 | `/city/:locationId` | `page/city` | `city` |
| 张江楠 | 多变量关联 | `/analysis` | `page/analysis` | `analysis` |
| 唐春柳 | 预测评估 | `/forecast` | `page/forecast` | `forecast` |
| 佘硕（组长） | 全国时空 | `/overview` | `page/overview` | `overview` |

> 唐春柳还兼着 `/system` 数据与方法页，同样在 `page/forecast` 分支里做。

---

## 换页面了怎么办

如果你们换了分工，改 `docs/分工.md` 里那张表，然后在这份提示词里替换对应的 4 个值就行。
两处保持一致，别只改一处。

---

## 为什么要有这份提示词

AI 不知道你们的仓库规矩，默认行为会踩坑：它很可能顺手 `git add -A`（把 244MB 数据库提交上去，
push 直接被拒）、或者跑 `pnpm run api:types`（覆盖 1803 行的生成文件，四个人全冲突）、
或者"好心"重构了共享的 `palette.ts`（四个页面同时变色）。
把这份提示词作为会话第一条消息，能把这些坑提前堵掉。
