<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
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

function makeChart(el: HTMLDivElement | null) {
  if (!el) return null;
  const chart = init(el, undefined, { renderer: "svg" });
  charts.push(chart);
  return chart;
}

function tooltipBase() {
  return {
    backgroundColor: "rgba(255,255,255,.985)",
    borderColor: "#c5d1cb",
    borderWidth: 1,
    padding: [11, 13],
    textStyle: { color: "#17231e", fontSize: 13, lineHeight: 21 },
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
  const axisInk = "#5b6d64";
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
        axisLine: { lineStyle: { color: "#c9d3cd" } },
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
        splitLine: { lineStyle: { color: "#dde4e0" } },
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
          itemStyle: { color: "#a06a34", borderColor: "#fff", borderWidth: 2 },
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
        axisLine: { lineStyle: { color: "#c9d3cd" } },
        axisLabel: { color: axisInk, fontSize: axisSize },
      },
      yAxis: {
        type: "category",
        data: features.map(featureLabel),
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: { color: "#2a3d34", fontSize: axisSize },
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
          itemStyle: { borderWidth: 2, borderColor: "#ffffff" },
          emphasis: { itemStyle: { borderColor: "#10221a", borderWidth: 1 } },
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
            `变化方向 1 <b>${Number(params.value[0]).toFixed(2)}</b>`,
            `变化方向 2 <b>${Number(params.value[1]).toFixed(2)}</b>`,
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "value",
        name: "变化方向 1 →",
        nameLocation: "middle",
        nameGap: 30,
        nameTextStyle: { color: axisInk, fontSize: axisSize },
        axisLabel: { color: axisInk, fontSize: axisSize },
        axisLine: { lineStyle: { color: "#c9d3cd" } },
        splitLine: { lineStyle: { color: "#dde4e0" } },
      },
      yAxis: {
        type: "value",
        name: "变化方向 2 ↑",
        nameTextStyle: { color: axisInk, fontSize: axisSize, padding: [0, 0, 8, 0] },
        axisLabel: { color: axisInk, fontSize: axisSize },
        axisLine: { lineStyle: { color: "#c9d3cd" } },
        splitLine: { lineStyle: { color: "#dde4e0" } },
      },
      series: [
        {
          type: "scatter",
          data: scoreValues,
          symbolSize: 6,
          itemStyle: {
            color: "#356f87",
            opacity: 0.5,
            borderColor: "#fff",
            borderWidth: 1,
          },
          emphasis: { itemStyle: { color: "#10221a", opacity: 1 } },
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
        axisLabel: { color: "#2a3d34", fontSize: axisSize, rotate: 48 },
      },
      yAxis: {
        type: "category",
        data: features.map(featureLabel),
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: { color: "#2a3d34", fontSize: axisSize },
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
          itemStyle: { borderWidth: 2, borderColor: "#ffffff" },
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
      <div>
        <h2>{{ structure.meta.city }}：哪些因素经常一起变化？</h2>
        <p>把污染物和气象变量压缩成几个主要变化方向，再看它们怎么协同。</p>
      </div>
      <span class="panel-meta data-mono">{{ structure.meta.sample_count }} 小时样本</span>
    </header>

    <div class="structure-grid">
      <article>
        <div class="chart-heading">
          <h3>压缩之后，还保留了多少信息？</h3>
          <p>柱子是每个方向单独解释的变化，折线是累计解释。前两个方向合计就是散点图保留的信息量。</p>
        </div>
        <div ref="screeEl" class="structure-chart"></div>
      </article>

      <article>
        <div class="chart-heading">
          <h3>哪些变量总是一起变？</h3>
          <p>颜色越偏暖，该变量在这个方向上抬得越高；越偏冷则压得越低。</p>
        </div>
        <div ref="loadingEl" class="structure-chart tall"></div>
      </article>

      <article>
        <div class="chart-heading">
          <h3>这座城市的空气状态落在哪些区间？</h3>
          <p>每个点是一个小时。点靠得近，说明当时的污染与气象组合更相似。</p>
        </div>
        <div ref="scoreEl" class="structure-chart"></div>
      </article>

      <article>
        <div class="chart-heading">
          <h3>谁和谁同向，谁和谁反向？</h3>
          <p>暖色同向、冷色反向、近白几乎不同步。这只说明它们一起动，不说明谁导致了谁。</p>
        </div>
        <div ref="correlationEl" class="structure-chart tall"></div>
      </article>
    </div>

    <footer class="panel-footer">
      <span class="data-mono">
        {{ structure.meta.window_start.slice(0, 10) }} → {{ structure.meta.window_end.slice(0, 10) }}
      </span>
      <span>污染用模式历史，气象用网格历史数据</span>
      <span>缺失小时不补值</span>
      <span>相关不等于因果</span>
    </footer>
  </section>
</template>

<style scoped>
.structure-panel {
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
  box-shadow: 0 10px 30px rgba(24, 41, 34, .045);
}
.panel-header {
  min-height: 82px;
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
  max-width: 72ch;
  color: var(--muted);
  font-size: var(--fs-label);
  line-height: 1.55;
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
.chart-heading p {
  max-width: 60ch;
  margin: 5px 0 0;
  color: var(--muted);
  font-size: var(--fs-label);
  line-height: 1.55;
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
