# Product

> **本文档是 Air Observatory 唯一的权威产品与视觉口径**（受众：科研人员）。
> 配套文档：[docs/科研可视化重构.md](docs/科研可视化重构.md) 是实施路线，[docs/选题报告.md](docs/选题报告.md) 是选题正式表述，[docs/协作指南.md](docs/协作指南.md) 是四人分工与流程规范，[ARCHITECTURE.md](ARCHITECTURE.md) 是数据闭环与工程边界。
> 历史上面向普通用户、主张“文字越少越好”的 `DESIGN.md`、`docs/SESSION_BRIEF.md`、`docs/REDESIGN.md` 与本文冲突，已从仓库删除（需要时从 git 历史取回）。**四个页面的分支不得再引用这三份文件的规则。**

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary users are environmental science, atmospheric science and data science researchers who investigate air-quality variation, pollutant–meteorology relationships, model–observation differences and forecast skill. The university course is the evaluation context, not the product's intended audience. Research questions, comparable time windows, provenance, uncertainty and reproducible evidence take precedence over a non-specialist news-style narrative.

## Product Purpose

Air Observatory continuously combines ground/sensor observations from OpenAQ with CAMS atmospheric-model data, stores historical state, exposes current conditions, supports historical and structural analysis, produces forecasts, and evaluates those forecasts when later observations arrive.

Success means a reviewer can answer four questions from one coherent product: where conditions are notable now, what has happened over time, what structure or drivers are visible in the data, and how credible the forecasts and source data are.

## Positioning

The product is not a static dashboard and not an API demo. Its differentiating mechanism is the closed data loop: ingestion → persistent history → analysis → forecast snapshot → later truth → backtest, while keeping Observation, Model Analysis, and Forecast semantically separate.

## Operating Context

The primary flow is national overview → city drill-down → structural analysis / forecast / trust evidence. Data updates come from external providers and are persisted locally rather than replacing prior history.

## Capabilities and Constraints

- Vue + TypeScript + ECharts frontend; FastAPI + SQLite backend.
- OpenAPI remains the source of frontend API types.
- OpenAQ ground/sensor observations and CAMS model fields must never be silently merged.
- Missing data must remain missing; no example values or interpolation may be used merely to make charts look complete.
- National-scale comparison may use the wider CAMS city field; analyses that require ground truth must visibly limit themselves to cities with sufficient observations.
- Statistical and ML methods must answer a real analytical question rather than exist as decorative sophistication.
- LSTM remains a candidate model for research cities once the required observation history and features are available; it is not assumed to be the best model.

## Brand Commitments

Product name: Air Observatory.

The visual language is a research-oriented visual analytics workbench: map-first, calm, precise and evidence-led. Experienced readers should be able to inspect periods, cohorts, statistical relationships, forecast error and missingness without drilling through decorative explanation layers. Statistical terminology is allowed when defined and measurable, and methods must remain attached to their evidence. The interface must not become a neon command center, an uncoordinated notebook of plots, or a grid of interchangeable KPI cards.

National interaction commitments:
- The China map is the primary national navigation surface; city entry happens from map markers, not a parallel text ranking.
- Primary views lead with a research question, analytical controls and evidence; quantitative conclusions must follow from visible data, with methods accessible alongside the relevant analysis.
- Direct labels, semantic color, and annotations are preferred over requiring users to read dense axes or legends.
- PCA, RMSE, sample size, time range, provider bindings and model readiness are first-class analytical metadata wherever needed to interpret a figure.
- Geographic boundaries and labels should remain vector-crisp at normal zoom; core charts should render at deliberate high DPI.
- Supporting copy and chart annotation must stay legible at presentation distance; tiny technical text is not a substitute for density.
- National analysis should prefer real charts and spatial relationships over rows of decorative cards or text-only rankings.

## Evidence on Hand

The repository contains real persisted CAMS data, OpenAQ observations for a limited subset of cities, forecast snapshots, provider health, ingestion history, and typed API contracts. Claims beyond those records must not be fabricated.

## Product Principles

1. Data semantics before visual completeness.
2. National context first, city explanation second.
3. Visualization is the analytical interface, not decoration around API calls.
4. Every model is compared against baselines and later truth where possible.
5. Provenance, freshness, sample size, and missingness remain visible.
