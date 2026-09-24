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
  return h.length ? `${h[0]}–${h[h.length - 1]} 小时` : "暂无";
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
      borderColor: "#c5d1cb",
      borderWidth: 1,
      textStyle: { color: "#17231e", fontSize: 13 },
      extraCssText: "box-shadow:0 12px 32px rgba(21,36,30,.12);border-radius:10px;",
    },
    xAxis: {
      type: "value",
      name: "预测时长（小时）",
      nameLocation: "middle",
      nameGap: 28,
      nameTextStyle: { color: "#5b6d64", fontSize: 12 },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#c9d3cd" } },
      axisLabel: { color: "#5b6d64", fontSize: 12 },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      name: metric === "mae" ? "平均误差 MAE" : "均方根误差 RMSE",
      nameTextStyle: { color: "#5b6d64", fontSize: 12, padding: [0, 0, 6, 0] },
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { color: "#5b6d64", fontSize: 12 },
      splitLine: { lineStyle: { color: "#dde4e0" } },
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
        borderColor: "#fff",
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
      description: "预测值与地面观测真值对照，含一比一参考线。",
    },
    grid: { left: 56, right: 24, top: 26, bottom: 48 },
    tooltip: {
      backgroundColor: "rgba(255,255,255,.985)",
      borderColor: "#c5d1cb",
      borderWidth: 1,
      textStyle: { color: "#17231e", fontSize: 13 },
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
      nameTextStyle: { color: "#5b6d64", fontSize: 12 },
      axisLabel: { color: "#5b6d64", fontSize: 12 },
      splitLine: { lineStyle: { color: "#dde4e0" } },
    },
    yAxis: {
      type: "value",
      name: "实测",
      nameLocation: "middle",
      nameGap: 40,
      min: 0,
      max,
      nameTextStyle: { color: "#5b6d64", fontSize: 12 },
      axisLabel: { color: "#5b6d64", fontSize: 12 },
      splitLine: { lineStyle: { color: "#dde4e0" } },
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
          borderColor: "#fff",
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
      <div>
        <h2>预测过去表现得怎么样？</h2>
        <p>只用已经到达的真实观测检验过去的预测，不用未来信息「作弊」。</p>
      </div>
      <span class="panel-meta data-mono">N={{ evidence.samples.length }}</span>
    </header>

    <div v-if="!evidence.enough" class="not-enough">
      <h3>样本还不够，暂时不给结论</h3>
      <p>
        目前只有 <b>{{ evidence.samples.length }}</b> 组「预测 ↔ 实测」成功对齐的样本，
        预测时长只覆盖 <b>{{ horizonSpan }}</b>
        <template v-if="evidence.horizons.length > 1">
          （{{ evidence.horizons.length }} 档）
        </template>
        ，还不足以判断预测得准不准。
      </p>
      <dl class="evidence-facts">
        <div>
          <dt>已对齐样本</dt>
          <dd class="data-mono">{{ evidence.samples.length }}</dd>
        </div>
        <div>
          <dt>预测时长覆盖</dt>
          <dd class="data-mono">{{ horizonSpan }}</dd>
        </div>
        <div>
          <dt>参与模型</dt>
          <dd>{{ evidence.models.length ? evidence.models.join(" / ") : "—" }}</dd>
        </div>
        <div>
          <dt>对齐口径</dt>
          <dd>预测时刻与地面实测小时精确对齐</dd>
        </div>
      </dl>
      <p class="why">
        为什么这里不画误差曲线：样本少、时长档位少时，连线会看起来像一个稳定的规律，
        但那只是几个点连起来的形状。等样本到 {{ MIN_SAMPLES }} 组以上、时长覆盖
        {{ MIN_HORIZONS }} 档以上，这里会自动换成误差随预测时长的对照图。
      </p>
    </div>

    <div v-else class="backtest-grid">
      <article>
        <h3>预测得越远，平均误差越大吗？</h3>
        <p class="chart-note">纵轴是平均误差（MAE），单位 µg/m³。</p>
        <div ref="maeEl" class="metric-chart"></div>
      </article>
      <article>
        <h3>极端偏差随预测时长怎么变？</h3>
        <p class="chart-note">纵轴是均方根误差（RMSE），对大偏差更敏感。</p>
        <div ref="rmseEl" class="metric-chart"></div>
      </article>
      <article class="scatter-article">
        <h3>预测和真实观测有多接近？</h3>
        <p class="chart-note">越贴近中间的虚线（1:1），说明预测与实测越一致。</p>
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
  box-shadow: 0 10px 30px rgba(24, 41, 34, .045);
}
.panel-header {
  min-height: 78px;
  padding: 18px 20px 12px;
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 20px;
  border-bottom: 1px solid var(--hairline-soft);
}
.panel-header h2 {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-sub);
  font-weight: var(--fw-display);
  letter-spacing: var(--track-title);
}
.panel-header p {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: var(--fs-label);
  line-height: 1.55;
}
.panel-meta {
  color: var(--muted);
  font-size: var(--fs-label);
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
.evidence-facts {
  margin: 18px 0 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: var(--hairline);
}
.evidence-facts > div {
  padding: 13px 15px;
  display: grid;
  gap: 5px;
  background: var(--sheet-soft);
}
.evidence-facts dt {
  color: var(--muted);
  font-size: var(--fs-label);
}
.evidence-facts dd {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-body);
  font-weight: var(--fw-strong);
  line-height: 1.4;
}
.why {
  margin-top: 18px;
  padding: 13px 15px;
  border-left: 3px solid var(--hairline-strong);
  background: var(--sheet-sunken);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  color: var(--muted);
  font-size: var(--fs-label);
  line-height: 1.7;
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
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-body);
  font-weight: var(--fw-strong);
  letter-spacing: var(--track-title);
}
.chart-note {
  margin: 4px 0 10px;
  color: var(--muted);
  font-size: var(--fs-label);
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
  .evidence-facts { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 520px) {
  .evidence-facts { grid-template-columns: 1fr; }
}
</style>
