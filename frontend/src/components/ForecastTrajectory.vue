<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { chartTheme, init, type ECharts } from "../lib/charts";
import { FORECAST_COLOR, MODEL_COLOR, MUTED_DATA_COLOR, OBSERVATION_COLOR } from "../lib/palette";

type Series = components["schemas"]["SeriesResponse"];
type Forecast = components["schemas"]["ForecastResponse"];
const props = defineProps<{
  history?: Series;
  observation?: Series;
  forecast?: Forecast;
  activeModels: string[];
}>();
const el = ref<HTMLDivElement | null>(null);
let chart: ECharts | null = null;
let observer: ResizeObserver | null = null;
const tones: Record<string, string> = {
  CAMS: MODEL_COLOR, LSTM: FORECAST_COLOR,
  Persistence: MUTED_DATA_COLOR, "Rolling Mean": OBSERVATION_COLOR,
};

const latestHistorical = computed(() => props.history?.points.at(-1)?.time ?? null);
const latestStamp = computed(() => latestHistorical.value ? +new Date(latestHistorical.value) : 0);
const historyPoints = computed(() => {
  const values: [string, number | null][] = [];
  let previous: number | null = null;
  for (const point of props.history?.points ?? []) {
    const at = +new Date(point.time);
    if (at < latestStamp.value - 7 * 24 * 3_600_000) continue;
    if (previous !== null && at - previous > 1.5 * 3_600_000) {
      values.push([new Date((at + previous) / 2).toISOString(), null]);
    }
    values.push([point.time, point.value]);
    previous = at;
  }
  return values;
});

const historyGapHours = computed(() => {
  const stamps = (props.history?.points ?? [])
    .map((point) => +new Date(point.time))
    .filter((time) => time >= latestStamp.value - 7 * 24 * 3_600_000);
  return stamps.reduce((max, time, index) =>
    index ? Math.max(max, Math.round((time - stamps[index - 1]!) / 3_600_000) - 1) : max, 0);
});

/* A gap in sparse observations is never connected into a fabricated trend. */
const observationPoints = computed(() => {
  const values: [string, number | null][] = [];
  let previous: number | null = null;
  for (const point of props.observation?.points ?? []) {
    if (point.value == null || +new Date(point.time) < latestStamp.value - 7 * 24 * 3_600_000) continue;
    const at = +new Date(point.time);
    if (previous !== null && at - previous > 3 * 3_600_000) {
      values.push([new Date((at + previous) / 2).toISOString(), null]);
    }
    values.push([point.time, point.value]);
    previous = at;
  }
  return values;
});

function render() {
  if (!chart) return;
  const theme = chartTheme();
  const series: any[] = [
    {
      name: "CAMS 历史分析", type: "line", data: historyPoints.value,
      symbol: "none", connectNulls: false, lineStyle: { width: 2.2, color: MODEL_COLOR },
      itemStyle: { color: MODEL_COLOR }, animationDuration: 400,
    },
    {
      name: "OpenAQ 地面观测", type: "line", data: observationPoints.value,
      symbol: "circle", symbolSize: 5, connectNulls: false,
      lineStyle: { width: 2, color: OBSERVATION_COLOR }, itemStyle: { color: OBSERVATION_COLOR },
    },
  ];
  for (const row of props.forecast?.series ?? []) {
    if (!props.activeModels.includes(row.model_name)) continue;
    const color = tones[row.model_name] ?? FORECAST_COLOR;
    series.push({
      name: row.model_name + " 预测",
      type: "line", data: row.points.map((point) => [point.target_at, point.value]),
      symbol: "circle", symbolSize: 4, showSymbol: false, connectNulls: false,
      itemStyle: { color }, lineStyle: { color, width: 2.1, type: row.model_name === "LSTM" ? "solid" : "dashed" },
      emphasis: { focus: "series" },
    });
  }
  const all = series.flatMap((row) => row.data)
    .filter((point: [string, number | null]) => point[1] != null);
  if (!all.length) { chart.clear(); return; }
  chart.setOption({
    animation: true,
    grid: { left: 57, top: 27, right: 25, bottom: 43 },
    tooltip: {
      trigger: "axis", confine: true, backgroundColor: theme.surface,
      borderColor: theme.tooltipBorder, textStyle: { color: theme.ink, fontSize: 12 },
      axisPointer: { type: "cross", crossStyle: { color: theme.faint } },
      valueFormatter: (value: unknown) => value == null ? "缺测" : Number(value).toFixed(1) + " µg/m³",
    },
    xAxis: {
      type: "time",
      axisLine: { lineStyle: { color: theme.axisLine } },
      axisTick: { show: false },
      axisLabel: { color: theme.axisInk, fontSize: 12, formatter: "{MM}/{dd} {HH}:00" },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value", name: "PM2.5 · µg/m³",
      nameTextStyle: { color: theme.axisInk, fontSize: 12, padding: [0, 0, 9, 0] },
      scale: true, min: 0,
      axisLabel: { color: theme.axisInk, fontSize: 12 },
      axisLine: { show: false }, splitLine: { lineStyle: { color: theme.splitLine } },
    },
    series,
  }, true);
}
onMounted(() => {
  if (!el.value) return;
  chart = init(el.value, undefined, { renderer: "svg" });
  observer = new ResizeObserver(() => chart?.resize());
  observer.observe(el.value);
  render();
});
watch(() => [props.history, props.observation, props.forecast, props.activeModels], render, { deep: true });
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose(); });
</script>

<template>
  <div class="forecast-trajectory">
    <div class="trajectory-legend" aria-label="预测图例">
      <span class="legend-model"><i></i>CAMS 分析</span>
      <span class="legend-observation"><i></i>地面观测</span>
    </div>
    <p v-if="historyGapHours > 0" class="trajectory-gap" role="status">
      模式历史最长缺测 {{ historyGapHours }} 小时 · 缺口已断开
    </p>
    <div ref="el" class="trajectory-chart" role="img" aria-label="CAMS 历史分析、地面观测与各模型 PM2.5 预测曲线"></div>
    <div v-if="!history?.points.length && !forecast?.series.length" class="research-empty">
      <strong>当前城市尚无有效预测记录</strong>
    </div>
  </div>
</template>

<style scoped>
.forecast-trajectory { min-width: 0; padding: 22px 24px 12px; }
.trajectory-chart { width: 100%; height: 405px; }
.trajectory-legend { display: flex; flex-wrap: wrap; gap: 9px 20px; align-items: center; color: var(--ink-secondary); font-size: 13px; }
.trajectory-legend span { display: inline-flex; gap: 7px; align-items: center; }
.trajectory-legend i { display: inline-block; width: 20px; height: 0; border-top: 2px solid var(--model); }
.legend-observation i { border-top-color: var(--observation); }
.trajectory-gap { margin: 12px 0 0; color: var(--ink-secondary); font-size: 13px; }
@media(max-width: 760px) {
  .forecast-trajectory { padding: 18px 12px 8px; }
  .trajectory-chart { height: 340px; }
}
</style>
