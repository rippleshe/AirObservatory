# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary users are students, instructors, and reviewers evaluating a data-visualization course project. The interface must also remain understandable to a non-specialist reader who wants to inspect current air-quality conditions, while retaining enough provenance and analytical depth for a technically literate reviewer.

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

The visual language is a public-facing environmental information product: map-first, calm, direct, and evidence-led. The first reading must work for a non-specialist without requiring them to decode axes, acronyms, model names, or statistical terminology. Technical provenance and analytical depth remain available as a secondary layer rather than dominating the primary story. It should not resemble a generic neon command center, a research plotting notebook, or a grid of interchangeable KPI cards.

National interaction commitments:
- The China map is the primary national navigation surface; city entry happens from map markers, not a parallel text ranking.
- Primary views lead with a plain-language conclusion, then use graphics as evidence; chart-type names and methodology labels are secondary.
- Direct labels, semantic color, and annotations are preferred over requiring users to read dense axes or legends.
- Technical terms such as PCA, RMSE, provider bindings, model readiness, and backtest diagnostics belong in deep-analysis or data/method sections.
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
