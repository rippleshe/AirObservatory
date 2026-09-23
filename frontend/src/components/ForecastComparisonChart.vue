<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { init, type ECharts } from "../lib/charts";

type ForecastResponse = components["schemas"]["ForecastResponse"];
type SeriesResponse = components["schemas"]["SeriesResponse"];

const props = defineProps<{
  forecast: ForecastResponse | undefined;
  observations: SeriesResponse | undefined;
}>();

const el = ref<HTMLDivElement | null>(null);
let chart: ECharts | null = null;
let observer: ResizeObserver | null = null;

const linePalette = ["#3d7489", "#7a5c3d", "#7a5578", "#64704a"];

function render() {
  if (!chart) return;
  const observations = props.observations?.points ?? [];
  const forecastSeries = props.forecast?.series ?? [];
  const unit = props.forecast?.unit ?? props.observations?.unit ?? "";
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  chart.setOption(
    {
      aria: {
        enabled: true,
        description: "近期地面观测与多模型未来预测。",
      },
      animation: !reduceMotion,
      grid: { left: 58, right: 26, top: 34, bottom: 44 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#f9faf7",
        borderColor: "#c9d0cc",
        textStyle: { color: "#18201e", fontSize: 11 },
      },
      xAxis: {
        type: "time",
        axisLine: { lineStyle: { color: "#c7cfca" } },
        axisTick: { show: false },
        axisLabel: { color: "#707a76", fontSize: 10 },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        name: unit,
        nameTextStyle: { color: "#7b8581", fontSize: 10 },
        axisLabel: { color: "#707a76", fontSize: 10 },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: "#dde2df" } },
      },
      series: [
        {
          name: "OpenAQ 观测",
          type: "line",
          data: observations.map((point) => [point.time, point.value]),
          showSymbol: false,
          lineStyle: { color: "#2f725f", width: 2.2 },
          itemStyle: { color: "#2f725f" },
        },
        ...forecastSeries.map((series, index) => ({
          name: series.model_name,
          type: "line",
          data: series.points.map((point) => [point.target_at, point.value]),
          showSymbol: false,
          lineStyle: {
            color: linePalette[index % linePalette.length],
            width: series.model_name === "CAMS" ? 1.8 : 1.5,
            type: series.model_name === "CAMS" ? "solid" : "dashed",
          },
          itemStyle: { color: linePalette[index % linePalette.length] },
        })),
      ],
    },
    true,
  );
}

onMounted(() => {
  if (!el.value) return;
  chart = init(el.value);
  observer = new ResizeObserver(() => chart?.resize());
  observer.observe(el.value);
  render();
});

watch(() => [props.forecast, props.observations], render, { deep: true });

onBeforeUnmount(() => {
  observer?.disconnect();
  chart?.dispose();
});
</script>

<template>
  <div ref="el" class="forecast-comparison-chart"></div>
</template>

<style scoped>
.forecast-comparison-chart { width: 100%; height: 100%; min-height: 360px; }
</style>
