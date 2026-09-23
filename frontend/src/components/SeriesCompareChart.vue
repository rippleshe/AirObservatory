<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { init, type ECharts } from "../lib/charts";

type SeriesResponse = components["schemas"]["SeriesResponse"];

const props = defineProps<{
  model: SeriesResponse | undefined;
  observation: SeriesResponse | undefined;
}>();

const el = ref<HTMLDivElement | null>(null);
let chart: ECharts | null = null;
let observer: ResizeObserver | null = null;

function render() {
  if (!chart) return;
  const model = props.model?.points ?? [];
  const observation = props.observation?.points ?? [];
  const unit = props.model?.unit ?? props.observation?.unit ?? "";
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  chart.setOption(
    {
      aria: {
        enabled: true,
        description: "地面观测与 CAMS 模式序列对比。",
      },
      animation: !reduceMotion,
      grid: { left: 58, right: 24, top: 28, bottom: 42 },
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
          data: observation.map((point) => [point.time, point.value]),
          showSymbol: false,
          connectNulls: false,
          lineStyle: { color: "#2f725f", width: 2.2 },
          itemStyle: { color: "#2f725f" },
        },
        {
          name: "CAMS 模式",
          type: "line",
          data: model.map((point) => [point.time, point.value]),
          showSymbol: false,
          connectNulls: false,
          lineStyle: { color: "#3d7489", width: 1.7 },
          itemStyle: { color: "#3d7489" },
        },
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

watch(() => [props.model, props.observation], render, { deep: true });

onBeforeUnmount(() => {
  observer?.disconnect();
  chart?.dispose();
});
</script>

<template>
  <div ref="el" class="series-compare-chart"></div>
</template>

<style scoped>
.series-compare-chart { width: 100%; height: 100%; min-height: 320px; }
</style>
