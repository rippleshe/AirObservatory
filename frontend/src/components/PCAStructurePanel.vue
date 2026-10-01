<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { init, type ECharts } from "../lib/charts";

type Structure = components["schemas"]["CityStructureResponse"];

const props = defineProps<{ structure: Structure }>();

const screeEl = ref<HTMLDivElement | null>(null);
const loadingEl = ref<HTMLDivElement | null>(null);
const scoreEl = ref<HTMLDivElement | null>(null);
const correlationEl = ref<HTMLDivElement | null>(null);

const charts: ECharts[] = [];
let observer: ResizeObserver | null = null;

const FEATURE_LABELS: Record<string, string> = {
  pm25: "PM2.5",
  pm10: "PM10",
  no2: "NO₂",
  o3: "O₃",
  so2: "SO₂",
  co: "CO",
  temperature_2m: "气温",
  relative_humidity_2m: "湿度",
  pressure_msl: "气压",
  precipitation: "降水",
  wind_speed_10m: "风速",
  wind_direction_sin: "风向 sin",
  wind_direction_cos: "风向 cos",
  boundary_layer_height: "边界层高度",
};

/* Diverging: cool pole / neutral midpoint / warm pole. Value is printed in
   the tooltip and both axes are labelled, so it never rides on hue alone. */
const DIVERGING = ["#366fa3", "#eef1ef", "#b44b45"];

function featureLabel(name: string) {
  return FEATURE_LABELS[name] ?? name;
}

/* Headings read the same numbers the charts draw, so the finding never needs
   a paragraph of instructions underneath it. */
const leadingComponent = computed(
  () => props.structure.explained_variance[0]?.component ?? "PC1",
);

const topPair = computed<{ a: string; b: string; value: number } | null>(() => {
  const features = props.structure.meta.features;
  let best: { a: string; b: string; value: number } | null = null;
  for (let y = 0; y < props.structure.correlation.length; y += 1) {
    const row = props.structure.correlation[y];
    for (let x = y + 1; x < features.length; x += 1) {
      const value = row.values[features[x]];
      if (value == null || !Number.isFinite(value)) continue;
      if (!best || Math.abs(value) > Math.abs(best.value)) {
        best = { a: features[y], b: features[x], value };
      }
    }
  }
  return best;
});

const topPairCopy = computed(() => {
  const pair = topPair.value;
  const city = props.structure.meta.city;
  if (!pair) {
    return `${city}：${props.structure.meta.sample_count} 小时样本的结构分解`;
  }
  return `${city}：${featureLabel(pair.a)} 与 ${featureLabel(pair.b)} ${
    pair.value > 0 ? "同向最强" : "反向最强"
  } r = ${pair.value.toFixed(2)}`;
});

const screeCopy = computed(() => {
  const explained = props.structure.explained_variance;
  if (!explained.length) return "解释比例尚未生成";
  const first = explained[0].variance_ratio;
  const rest = explained[explained.length - 1].cumulative_ratio - first;
  if (explained.length === 1) return `只有一个方向，解释 ${(first * 100).toFixed(1)}%`;
  return `第一个方向解释 ${(first * 100).toFixed(1)}%，其余 ${
    explained.length - 1
  } 个合计 ${(rest * 100).toFixed(1)}%`;
});

const loadingCopy = computed(() => {
  const component = leadingComponent.value;
  let high: { feature: string; value: number } | null = null;
  let low: { feature: string; value: number } | null = null;
  for (const row of props.structure.loadings) {
    const value = row.values[component];
    if (value == null || !Number.isFinite(value)) continue;
    if (!high || value > high.value) high = { feature: row.feature, value };
    if (!low || value < low.value) low = { feature: row.feature, value };
  }
  if (!high || !low) return "权重尚未生成";
  return `第一个方向上 ${featureLabel(high.feature)} 权重最高（${high.value.toFixed(
    2,
  )}），${featureLabel(low.feature)} 最低（${low.value.toFixed(2)}）`;
});

const scoreCopy = computed(() => {
  const values = props.structure.scores
    .map((row) => row.values[leadingComponent.value])
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b);
  if (!values.length) return "主成分取值尚未生成";
  const at = (q: number) => values[Math.min(values.length - 1, Math.round((values.length - 1) * q))];
  return `主成分 1 有 90% 的时刻落在 ${at(0.05).toFixed(2)}～${at(0.95).toFixed(
    2,
  )} 之间，中位 ${at(0.5).toFixed(2)}`;
});

const correlationCopy = computed(() => {
  const features = props.structure.meta.features;
  let strong = 0;
  let inverse = 0;
  props.structure.correlation.forEach((row, y) => {
    features.forEach((feature, x) => {
      if (x <= y) return;
      const value = row.values[feature];
      if (value == null || !Number.isFinite(value) || Math.abs(value) < 0.6) return;
      strong += 1;
      if (value < 0) inverse += 1;
    });
  });
  if (!strong) return `${features.length} 个变量里没有一对相关超过 |r| = 0.6`;
  return `${features.length} 个变量里有 ${strong} 对相关超过 |r| = 0.6，其中 ${inverse} 对反向`;
});

function makeChart(el: HTMLDivElement | null) {
  if (!el) return null;
  const chart = init(el, undefined, { renderer: "svg" });
  charts.push(chart);
  return chart;
}

function tooltipBase() {
  return {
    backgroundColor: "rgba(255,255,255,.985)",
    borderColor: "#8fa39b",
    borderWidth: 1,
    padding: [11, 13],
    textStyle: { color: "#0b1512", fontSize: 13, lineHeight: 21 },
    extraCssText: "box-shadow:0 12px 32px rgba(21,36,30,.12);border-radius:10px;",
  };
}

function render() {
  if (charts.length !== 4) return;
  const [scree, loadings, scores, correlation] = charts;
  const explained = props.structure.explained_variance;
  const components = explained.map((item) => item.component);
  const features = props.structure.meta.features;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const axisInk = "#566a61";
  const axisSize = 12;

  scree.setOption(
    {
      animation: !reducedMotion,
      aria: { enabled: true, description: "各变化方向解释的整体变化比例与累计比例。" },
      grid: { left: 48, right: 18, top: 24, bottom: 38 },
      tooltip: {
        ...tooltipBase(),
        trigger: "axis",
        formatter(params: any) {
          const row = Array.isArray(params) ? params[0] : params;
          const item = explained[row.dataIndex];
          return [
            `<b>${item.component}</b>`,
            `单独解释 <b>${(item.variance_ratio * 100).toFixed(1)}%</b>`,
            `累计解释 <b>${(item.cumulative_ratio * 100).toFixed(1)}%</b>`,
          ].join("<br/>");
        },
      },
      legend: {
        top: 0,
        right: 0,
        itemWidth: 12,
        itemHeight: 8,
        textStyle: { color: axisInk, fontSize: axisSize },
      },
      xAxis: {
        type: "category",
        data: components,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "#a7b8b0" } },
        axisLabel: { color: axisInk, fontSize: axisSize },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 1,
        axisLabel: {
          color: axisInk,
          fontSize: axisSize,
          formatter: (value: number) => Math.round(value * 100) + "%",
        },
        splitLine: { lineStyle: { color: "#c3d1cb" } },
      },
      series: [
        {
          name: "单独解释",
          type: "bar",
          data: explained.map((item) => item.variance_ratio),
          barMaxWidth: 26,
          itemStyle: { color: "#356f87", borderRadius: [4, 4, 0, 0] },
        },
        {
          name: "累计解释",
          type: "line",
          data: explained.map((item) => item.cumulative_ratio),
          showSymbol: true,
          symbolSize: 6,
          lineStyle: { color: "#a06a34", width: 2 },
          itemStyle: { color: "#a06a34", borderColor: "#fbfcfb", borderWidth: 2 },
        },
      ],
    },
    true,
  );

  const loadingValues = props.structure.loadings.flatMap((row, y) =>
    components.map((component, x) => [x, y, row.values[component] ?? 0]),
  );
  const loadingMax = Math.max(
    0.2,
    ...loadingValues.map((item) => Math.abs(Number(item[2]))),
  );
  loadings.setOption(
    {
      animation: !reducedMotion,
      aria: { enabled: true, description: "各变量在主要变化方向上的权重热力图。" },
      grid: { left: 96, right: 58, top: 18, bottom: 48 },
      tooltip: {
        ...tooltipBase(),
        formatter(params: any) {
          const [x, y, value] = params.data;
          return [
            `<b>${featureLabel(features[y])}</b>`,
            `${components[x]} 权重 <b>${Number(value).toFixed(3)}</b>`,
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "category",
        data: components,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "#a7b8b0" } },
        axisLabel: { color: axisInk, fontSize: axisSize },
      },
      yAxis: {
        type: "category",
        data: features.map(featureLabel),
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: { color: "#243530", fontSize: axisSize },
      },
      visualMap: {
        min: -loadingMax,
        max: loadingMax,
        calculable: false,
        orient: "vertical",
        right: 4,
        top: "center",
        itemWidth: 8,
        itemHeight: 92,
        textStyle: { color: axisInk, fontSize: axisSize },
        inRange: { color: DIVERGING },
      },
      series: [
        {
          type: "heatmap",
          data: loadingValues,
          itemStyle: { borderWidth: 2, borderColor: "#fbfcfb" },
          emphasis: { itemStyle: { borderColor: "#0b1512", borderWidth: 1 } },
        },
      ],
    },
    true,
  );

  const rawScores = props.structure.scores;
  const stride = Math.max(1, Math.floor(rawScores.length / 900));
  const scoreValues = rawScores
    .filter((_, index) => index % stride === 0)
    .map((row) => ({
      value: [row.values.PC1 ?? 0, row.values.PC2 ?? 0],
      time: row.time,
    }));
  scores.setOption(
    {
      animation: !reducedMotion,
      aria: { enabled: true, description: "空气状态在两个主要变化方向上的分布。" },
      grid: { left: 54, right: 20, top: 22, bottom: 46 },
      tooltip: {
        ...tooltipBase(),
        formatter(params: any) {
          const time = new Intl.DateTimeFormat("zh-CN", {
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
          }).format(new Date(params.data.time));
          return [
            `<b>${time}</b>`,
            `主成分 1 <b>${Number(params.value[0]).toFixed(2)}</b>`,
            `主成分 2 <b>${Number(params.value[1]).toFixed(2)}</b>`,
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "value",
        name: `主成分 1 · ${Math.round((explained[0]?.variance_ratio ?? 0) * 100)}%`,
        nameLocation: "middle",
        nameGap: 30,
        nameTextStyle: { color: axisInk, fontSize: axisSize },
        axisLabel: { color: axisInk, fontSize: axisSize },
        axisLine: { lineStyle: { color: "#a7b8b0" } },
        splitLine: { lineStyle: { color: "#c3d1cb" } },
      },
      yAxis: {
        type: "value",
        name: `主成分 2 · ${Math.round((explained[1]?.variance_ratio ?? 0) * 100)}%`,
        nameTextStyle: { color: axisInk, fontSize: axisSize, padding: [0, 0, 8, 0] },
        axisLabel: { color: axisInk, fontSize: axisSize },
        axisLine: { lineStyle: { color: "#a7b8b0" } },
        splitLine: { lineStyle: { color: "#c3d1cb" } },
      },
      series: [
        {
          type: "scatter",
          data: scoreValues,
          symbolSize: 6,
          itemStyle: {
            color: "#356f87",
            opacity: 0.5,
            borderColor: "#fbfcfb",
            borderWidth: 1,
          },
          emphasis: { itemStyle: { color: "#0b1512", opacity: 1 } },
        },
      ],
    },
    true,
  );

  const correlationValues = props.structure.correlation.flatMap((row, y) =>
    features.map((feature, x) => [x, y, row.values[feature] ?? 0]),
  );
  correlation.setOption(
    {
      animation: !reducedMotion,
      aria: { enabled: true, description: "污染物与气象变量的相关矩阵。" },
      grid: { left: 92, right: 50, top: 18, bottom: 86 },
      tooltip: {
        ...tooltipBase(),
        formatter(params: any) {
          const [x, y, value] = params.data;
          const v = Number(value);
          const dir = Math.abs(v) < 0.15 ? "几乎不同步" : v > 0 ? "同向变化" : "反向变化";
          return [
            `<b>${featureLabel(features[y])} × ${featureLabel(features[x])}</b>`,
            `相关系数 r = <b>${v.toFixed(3)}</b>`,
            dir,
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "category",
        data: features.map(featureLabel),
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: { color: "#243530", fontSize: axisSize, rotate: 48 },
      },
      yAxis: {
        type: "category",
        data: features.map(featureLabel),
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: { color: "#243530", fontSize: axisSize },
      },
      visualMap: {
        min: -1,
        max: 1,
        calculable: false,
        orient: "vertical",
        right: 2,
        top: "center",
        itemWidth: 8,
        itemHeight: 96,
        textStyle: { color: axisInk, fontSize: axisSize },
        inRange: { color: DIVERGING },
      },
      series: [
        {
          type: "heatmap",
          data: correlationValues,
          itemStyle: { borderWidth: 2, borderColor: "#fbfcfb" },
        },
      ],
    },
    true,
  );
}

onMounted(() => {
  makeChart(screeEl.value);
  makeChart(loadingEl.value);
  makeChart(scoreEl.value);
  makeChart(correlationEl.value);
  observer = new ResizeObserver(() => charts.forEach((chart) => chart.resize()));
  [screeEl, loadingEl, scoreEl, correlationEl].forEach((target) => {
    if (target.value) observer?.observe(target.value);
  });
  render();
});

watch(() => props.structure, render, { deep: true });

onBeforeUnmount(() => {
  observer?.disconnect();
  charts.forEach((chart) => chart.dispose());
});
</script>

<template>
  <section class="structure-panel">
    <header class="panel-header">
      <h2 class="display-face">{{ topPairCopy }}</h2>
      <span class="panel-meta data-mono">{{ structure.meta.sample_count }} 小时样本</span>
    </header>

    <div class="structure-grid">
      <article>
        <div class="chart-heading">
          <h3 class="display-face">{{ screeCopy }}</h3>
        </div>
        <div ref="screeEl" class="structure-chart"></div>
      </article>

      <article>
        <div class="chart-heading">
          <h3 class="display-face">{{ loadingCopy }}</h3>
        </div>
        <div ref="loadingEl" class="structure-chart tall"></div>
      </article>

      <article>
        <div class="chart-heading">
          <h3 class="display-face">{{ scoreCopy }}</h3>
        </div>
        <div ref="scoreEl" class="structure-chart"></div>
      </article>

      <article>
        <div class="chart-heading">
          <h3 class="display-face">{{ correlationCopy }}</h3>
        </div>
        <div ref="correlationEl" class="structure-chart tall"></div>
      </article>
    </div>

    <footer class="panel-footer data-mono">
      {{ structure.meta.window_start.slice(0, 10) }} → {{ structure.meta.window_end.slice(0, 10) }}
    </footer>
  </section>
</template>

<style scoped>
.structure-panel {
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-xl);
  background: var(--sheet);
  box-shadow: var(--shadow-sm);
  transition: all var(--duration-normal) var(--ease-out);
}
.structure-panel:hover {
  border-color: var(--hairline-strong);
  box-shadow: var(--shadow-md);
}
.panel-header {
  min-height: 84px;
  padding: 20px 24px 14px;
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
.panel-meta {
  color: var(--muted);
  font-size: var(--fs-label);
  white-space: nowrap;
}

.structure-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
}
.structure-grid article {
  min-width: 0;
  padding: 18px 20px;
  border-bottom: 1px solid var(--hairline-soft);
}
.structure-grid article:nth-child(odd) {
  border-right: 1px solid var(--hairline-soft);
}
.chart-heading {
  margin-bottom: 10px;
}
.chart-heading h3 {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-body);
  font-weight: var(--fw-strong);
  letter-spacing: var(--track-title);
}
.structure-chart {
  width: 100%;
  height: 290px;
}
.structure-chart.tall {
  height: 370px;
}
.panel-footer {
  min-height: 48px;
  padding: 12px 20px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 18px;
  color: var(--muted);
  font-size: var(--fs-label);
  line-height: 1.4;
}

@media (max-width: 980px) {
  .structure-grid { grid-template-columns: 1fr; }
  .structure-grid article:nth-child(odd) { border-right: 0; }
}
@media (max-width: 680px) {
  .panel-header { display: grid; }
}
</style>
