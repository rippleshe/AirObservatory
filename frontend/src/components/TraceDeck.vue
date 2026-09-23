<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { init, type ECharts } from "../lib/charts";

type SeriesResponse = components["schemas"]["SeriesResponse"];
type ForecastResponse = components["schemas"]["ForecastResponse"];

const props = defineProps<{
  history: SeriesResponse | undefined;
  observations: SeriesResponse | undefined;
  forecast: ForecastResponse | undefined;
}>();

const el = ref<HTMLDivElement | null>(null);
let chart: ECharts | null = null;
let observer: ResizeObserver | null = null;

function render() {
  if (!chart) return;
  const history = props.history?.points ?? [];
  const observations = props.observations?.points ?? [];
  const forecast = props.forecast?.series?.[0]?.points ?? [];
  const now = history.at(-1)?.time ?? observations.at(-1)?.time;
  const unit = props.history?.unit ?? props.forecast?.unit ?? "";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  chart.setOption({
    aria: {
      enabled: true,
      description: "选中城市的地面观测、CAMS 模式历史和未来预测时间序列。",
    },
    animation: !reduceMotion,
    animationDurationUpdate: reduceMotion ? 0 : 180,
    animationEasingUpdate: "cubicOut",
    grid: { left: 52, right: 24, top: 36, bottom: 38 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#f9faf7",
      borderColor: "#c9d0cc",
      textStyle: { color: "#18201e", fontSize: 11 },
      formatter(params: any) {
        const rows = Array.isArray(params) ? params : [params];
        const time = new Intl.DateTimeFormat("zh-CN", {
          month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
        }).format(new Date(rows[0]?.value?.[0] ?? rows[0]?.axisValue));
        const body = rows
          .filter((row: any) => row.value?.[1] != null)
          .map((row: any) => `${row.seriesName}&nbsp;&nbsp;<b>${Number(row.value[1]).toFixed(1)}</b> ${unit}`)
          .join("<br/>");
        return `<div style="font-family:var(--mono);font-size:10px;margin-bottom:6px">${time}</div>${body}`;
      },
    },
    xAxis: {
      type: "time",
      axisLine: { lineStyle: { color: "#c7cfca" } },
      axisTick: { show: false },
      axisLabel: {
        color: "#707a76",
        fontSize: 10,
        formatter(value: number) {
          return new Intl.DateTimeFormat("zh-CN", {
            hour: "2-digit", minute: "2-digit", hour12: false,
          }).format(new Date(value));
        },
      },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      name: unit,
      nameTextStyle: { color: "#7b8581", fontSize: 10, padding: [0, 0, 6, -16] },
      axisLabel: { color: "#707a76", fontSize: 10 },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: "#dde2df", width: 1 } },
    },
    series: [
      {
        name: "OpenAQ 地面观测",
        type: "line",
        data: observations.map((point) => [point.time, point.value]),
        showSymbol: false,
        connectNulls: false,
        lineStyle: { color: "#2f725f", width: 2.2 },
        itemStyle: { color: "#2f725f" },
        emphasis: { disabled: true },
      },
      {
        name: "CAMS 模式历史",
        type: "line",
        data: history.map((point) => [point.time, point.value]),
        showSymbol: false,
        connectNulls: false,
        lineStyle: { color: "#18201e", width: 1.8 },
        itemStyle: { color: "#18201e" },
        emphasis: { disabled: true },
        markLine: now
          ? {
              symbol: ["none", "none"],
              silent: true,
              lineStyle: { color: "#43656a", width: 1, type: "solid" },
              label: {
                show: true,
                formatter: "NOW",
                color: "#27464b",
                backgroundColor: "#eef1ee",
                padding: [2, 4],
                fontSize: 9,
                fontFamily: "Cascadia Code",
                position: "insideEndTop",
              },
              data: [{ xAxis: now }],
            }
          : undefined,
      },
      {
        name: "CAMS 模式预测",
        type: "line",
        data: forecast.map((point) => [point.target_at, point.value]),
        showSymbol: false,
        connectNulls: false,
        lineStyle: { color: "#597e8d", width: 1.5, type: "dashed" },
        itemStyle: { color: "#597e8d" },
        emphasis: { disabled: true },
      },
    ],
  }, true);
}

onMounted(() => {
  if (!el.value) return;
  chart = init(el.value);
  observer = new ResizeObserver(() => chart?.resize());
  observer.observe(el.value);
  render();
});

watch(() => [props.history, props.observations, props.forecast], render, { deep: true });
onBeforeUnmount(() => {
  observer?.disconnect();
  chart?.dispose();
});
</script>

<template>
  <section class="trace-deck">
    <header class="trace-header">
      <div>
        <h3>过去 → 现在 → 未来</h3>
        <p>同一时间轴上的模式历史与 CAMS 未来预测</p>
      </div>
      <div class="trace-legend" aria-label="图例">
        <span><i class="observation-line"></i>地面观测</span>
        <span><i class="history-line"></i>模式历史</span>
        <span><i class="forecast-line"></i>模式预测</span>
      </div>
    </header>
    <div ref="el" class="trace-chart"></div>
  </section>
</template>

<style scoped>
.trace-deck {
  min-height: 0;
  background: var(--sheet);
  border-top: 1px solid var(--hairline);
}
.trace-header {
  height: 54px;
  padding: 10px 18px 0;
  display: flex;
  justify-content: space-between;
  align-items: start;
}
.trace-header h3 { margin: 0; font-size: 12px; font-weight: 650; }
.trace-header p { margin: 4px 0 0; color: var(--muted); font-size: 10px; }
.trace-legend { display: flex; gap: 14px; color: var(--muted); font-size: 10px; padding-top: 3px; }
.trace-legend span { display: flex; align-items: center; gap: 6px; }
.trace-legend i { width: 18px; height: 0; border-top: 2px solid var(--ink); }
.trace-legend .observation-line { border-top-color: var(--ok); }
.trace-legend .forecast-line { border-top: 1.5px dashed var(--model); }
.trace-chart { width: 100%; height: calc(100% - 54px); min-height: 180px; }
</style>
