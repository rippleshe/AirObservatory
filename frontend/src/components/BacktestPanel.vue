<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { init, type ECharts } from "../lib/charts";
import { MODEL_COLOR, MUTED_DATA_COLOR, OBSERVATION_COLOR, FORECAST_COLOR } from "../lib/palette";

type BacktestResponse = components["schemas"]["BacktestResponse"];
const props = defineProps<{ backtest: BacktestResponse | undefined }>();

const maeEl = ref<HTMLDivElement | null>(null);
const rmseEl = ref<HTMLDivElement | null>(null);
const scatterEl = ref<HTMLDivElement | null>(null);
const charts: ECharts[] = [];
let observer: ResizeObserver | null = null;

/* Drawing error-vs-horizon curves needs enough realised pairs at enough
   horizons. Below that a line invents a trend the records don't support —
   PRODUCT.md: claims beyond those records must not be fabricated. */
const MIN_SAMPLES = 30;
const MIN_HORIZONS = 3;

const seriesColors = [MODEL_COLOR, OBSERVATION_COLOR, FORECAST_COLOR, MUTED_DATA_COLOR];

const evidence = computed(() => {
  const samples = props.backtest?.samples ?? [];
  const horizons = [...new Set(samples.map((row) => row.horizon_hours))].sort(
    (a, b) => a - b,
  );
  const models = [...new Set(samples.map((row) => row.model_name))];
  return {
    samples,
    horizons,
    models,
    enough: samples.length >= MIN_SAMPLES && horizons.length >= MIN_HORIZONS,
  };
});

const horizonSpan = computed(() => {
  const h = evidence.value.horizons;
  return h.length ? `${h[0]}–${h[h.length - 1]} 小时` : "—";
});

/* Every heading below is built from the same rows the chart plots, so no
   reading instructions are needed under them. */
const overallError = computed(() => {
  const samples = evidence.value.samples;
  if (!samples.length) return null;
  return samples.reduce((sum, row) => sum + Math.abs(row.error), 0) / samples.length;
});

const backtestHeadline = computed(() => {
  const count = evidence.value.samples.length;
  const error = overallError.value;
  if (!count || error == null) return "还没有可与地面观测对齐的预测样本";
  return `已对齐 ${count} 组预测与实测，平均误差 ${error.toFixed(1)} µg/m³`;
});

const maeHeadline = computed(() => {
  const byHorizon = new Map<number, number[]>();
  (props.backtest?.metrics ?? []).forEach((row) => {
    const bucket = byHorizon.get(row.horizon_hours) ?? [];
    bucket.push(row.mae);
    byHorizon.set(row.horizon_hours, bucket);
  });
  const horizons = [...byHorizon.keys()].sort((a, b) => a - b);
  if (horizons.length < 2) return "只有一档预测时长，无法比较误差变化";
  const mean = (horizon: number) => {
    const values = byHorizon.get(horizon) ?? [];
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  };
  const first = horizons[0];
  const last = horizons[horizons.length - 1];
  return `MAE 误差：+${first}h ${mean(first).toFixed(1)} → +${last}h ${mean(last).toFixed(1)} µg/m³`;
});

const rmseHeadline = computed(() => {
  const samples = evidence.value.samples;
  if (!samples.length) return "RMSE 样本不足";
  const worst = samples.reduce(
    (best, row) => (Math.abs(row.error) > Math.abs(best.error) ? row : best),
    samples[0],
  );
  return `最大单次偏差 ${Math.abs(worst.error).toFixed(1)} µg/m³ (+${worst.horizon_hours}h)`;
});

const fitHeadline = computed(() => {
  const samples = evidence.value.samples;
  if (samples.length < 3) return `${samples.length} 组预测与实测对照`;
  const predicted = samples.map((row) => row.predicted_value);
  const observed = samples.map((row) => row.observed_value);
  const meanPredicted = predicted.reduce((sum, value) => sum + value, 0) / predicted.length;
  const meanObserved = observed.reduce((sum, value) => sum + value, 0) / observed.length;
  let covariance = 0;
  let variancePredicted = 0;
  let varianceObserved = 0;
  for (let index = 0; index < predicted.length; index += 1) {
    const dx = predicted[index] - meanPredicted;
    const dy = observed[index] - meanObserved;
    covariance += dx * dy;
    variancePredicted += dx * dx;
    varianceObserved += dy * dy;
  }
  if (!variancePredicted || !varianceObserved) return `${samples.length} 组预测与实测对照`;
  const r = covariance / Math.sqrt(variancePredicted * varianceObserved);
  return `相关性 r = ${r.toFixed(2)} · ${samples.length} 组对照`;
});

function lineOption(metric: "mae" | "rmse") {
  const rows = props.backtest?.metrics ?? [];
  const models = [...new Set(rows.map((row) => row.model_name))];
  return {
    animation: false,
    aria: {
      enabled: true,
      description: metric.toUpperCase() + " 按预测时效变化。",
    },
    grid: { left: 52, right: 20, top: 26, bottom: 42 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(255,255,255,.985)",
      borderColor: "#8fa39b",
      borderWidth: 1,
      textStyle: { color: "#0b1512", fontSize: 13 },
      extraCssText: "box-shadow:0 12px 32px rgba(21,36,30,.12);border-radius:10px;",
    },
    xAxis: {
      type: "value",
      name: "预测时长（小时）",
      nameLocation: "middle",
      nameGap: 28,
      nameTextStyle: { color: "#566a61", fontSize: 12 },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#a7b8b0" } },
      axisLabel: { color: "#566a61", fontSize: 12 },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      name: metric === "mae" ? "平均误差 MAE" : "均方根误差 RMSE",
      nameTextStyle: { color: "#566a61", fontSize: 12, padding: [0, 0, 6, 0] },
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { color: "#566a61", fontSize: 12 },
      splitLine: { lineStyle: { color: "#c3d1cb" } },
    },
    series: models.map((model, index) => ({
      name: model,
      type: "line",
      showSymbol: true,
      symbolSize: 7,
      data: rows
        .filter((row) => row.model_name === model)
        .sort((a, b) => a.horizon_hours - b.horizon_hours)
        .map((row) => [row.horizon_hours, row[metric]]),
      lineStyle: { width: 2, color: seriesColors[index % seriesColors.length] },
      itemStyle: {
        color: seriesColors[index % seriesColors.length],
        borderColor: "#fbfcfb",
        borderWidth: 2,
      },
    })),
  };
}

function scatterOption() {
  const samples = evidence.value.samples;
  const models = evidence.value.models;
  const values = samples.flatMap((row) => [row.predicted_value, row.observed_value]);
  const max = Math.max(10, ...values);
  return {
    animation: false,
    aria: {
      enabled: true,
      description: "预测值与地面观测真值对照，含 1:1 参考线。",
    },
    grid: { left: 56, right: 24, top: 26, bottom: 48 },
    tooltip: {
      backgroundColor: "rgba(255,255,255,.985)",
      borderColor: "#8fa39b",
      borderWidth: 1,
      textStyle: { color: "#0b1512", fontSize: 13 },
      extraCssText: "box-shadow:0 12px 32px rgba(21,36,30,.12);border-radius:10px;",
      formatter(params: any) {
        const raw = params.data;
        return [
          `<b>${params.seriesName}</b>`,
          `预测 <b>${Number(raw.value[0]).toFixed(1)}</b> µg/m³`,
          `实测 <b>${Number(raw.value[1]).toFixed(1)}</b> µg/m³`,
          `提前 ${raw.horizon} 小时做出`,
        ].join("<br/>");
      },
    },
    xAxis: {
      type: "value",
      name: "预测",
      nameLocation: "middle",
      nameGap: 28,
      min: 0,
      max,
      nameTextStyle: { color: "#566a61", fontSize: 12 },
      axisLabel: { color: "#566a61", fontSize: 12 },
      splitLine: { lineStyle: { color: "#c3d1cb" } },
    },
    yAxis: {
      type: "value",
      name: "实测",
      nameLocation: "middle",
      nameGap: 40,
      min: 0,
      max,
      nameTextStyle: { color: "#566a61", fontSize: 12 },
      axisLabel: { color: "#566a61", fontSize: 12 },
      splitLine: { lineStyle: { color: "#c3d1cb" } },
    },
    series: [
      ...models.map((model, index) => ({
        name: model,
        type: "scatter",
        symbolSize: 8,
        data: samples
          .filter((row) => row.model_name === model)
          .map((row) => ({
            value: [row.predicted_value, row.observed_value],
            horizon: row.horizon_hours,
          })),
        itemStyle: {
          color: seriesColors[index % seriesColors.length],
          opacity: 0.72,
          borderColor: "#fbfcfb",
          borderWidth: 2,
        },
      })),
      {
        name: "1:1",
        type: "line",
        data: [
          [0, 0],
          [max, max],
        ],
        showSymbol: false,
        silent: true,
        lineStyle: { color: "#8f9d96", width: 1, type: "dashed" },
      },
    ],
  };
}

function render() {
  if (charts.length !== 3 || !evidence.value.enough) return;
  charts[0].setOption(lineOption("mae"), true);
  charts[1].setOption(lineOption("rmse"), true);
  charts[2].setOption(scatterOption(), true);
}

onMounted(() => {
  if (evidence.value.enough) {
    [maeEl.value, rmseEl.value, scatterEl.value].forEach((el) => {
      if (el) charts.push(init(el, undefined, { renderer: "svg" }));
    });
    observer = new ResizeObserver(() => charts.forEach((chart) => chart.resize()));
    [maeEl.value, rmseEl.value, scatterEl.value].forEach((el) => {
      if (el) observer?.observe(el);
    });
    render();
  }
});

watch(() => props.backtest, render, { deep: true });

onBeforeUnmount(() => {
  observer?.disconnect();
  charts.forEach((chart) => chart.dispose());
});
</script>

<template>
  <section class="backtest-panel">
    <header class="panel-header">
      <h2 class="display-face">{{ backtestHeadline }}</h2>
      <span class="panel-meta data-mono">N={{ evidence.samples.length }}</span>
    </header>

    <div v-if="!evidence.enough" class="not-enough">
      <h3>样本还不够，暂时不给结论</h3>
      <p class="evidence-line">
        <b class="data-mono">已对齐样本 {{ evidence.samples.length }}</b>
        <span>时长 {{ horizonSpan }}</span>
        <span>{{ evidence.models.length ? evidence.models.join(" / ") : "暂无" }}</span>
      </p>
    </div>

    <div v-else class="backtest-grid">
      <article>
        <h3>{{ maeHeadline }}</h3>
        <div ref="maeEl" class="metric-chart"></div>
      </article>
      <article>
        <h3>{{ rmseHeadline }}</h3>
        <div ref="rmseEl" class="metric-chart"></div>
      </article>
      <article class="scatter-article">
        <h3>{{ fitHeadline }}</h3>
        <div ref="scatterEl" class="scatter-chart"></div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.backtest-panel {
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
  box-shadow: var(--shadow-sm);
}
.panel-header {
  min-height: 60px;
  padding: 14px 20px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  border-bottom: 1px solid var(--hairline);
}
.panel-header h2 {
  margin: 0;
  color: var(--ink);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: var(--track-title);
}
.panel-meta {
  color: var(--muted);
  font-size: 12px;
  white-space: nowrap;
}

.not-enough {
  padding: 22px 20px 24px;
}
.not-enough h3 {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-body);
  font-weight: var(--fw-strong);
}
.not-enough > p {
  max-width: 74ch;
  margin: 8px 0 0;
  color: var(--muted);
  font-size: var(--fs-body);
  line-height: 1.7;
}
.not-enough > p b {
  color: var(--ink);
  font-weight: var(--fw-strong);
}
.evidence-line {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
  align-items: baseline;
  font-size: var(--fs-data);
}
.evidence-line span {
  color: var(--muted);
}

.backtest-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
}
.backtest-grid article {
  min-width: 0;
  padding: 18px;
  border-bottom: 1px solid var(--hairline-soft);
}
.backtest-grid article:nth-child(odd) {
  border-right: 1px solid var(--hairline-soft);
}
.backtest-grid h3 {
  margin: 0 0 10px;
  color: var(--ink);
  font-size: var(--fs-body);
  font-weight: var(--fw-strong);
  letter-spacing: var(--track-title);
}
.metric-chart {
  width: 100%;
  height: 250px;
}
.scatter-article {
  grid-column: 1 / -1;
  border-right: 0;
}
.scatter-chart {
  width: 100%;
  height: 340px;
}

@media (max-width: 860px) {
  .backtest-grid { grid-template-columns: 1fr; }
  .backtest-grid article:nth-child(odd) { border-right: 0; }
  .scatter-article { grid-column: auto; }
}
</style>
