<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { init, type ECharts } from "../lib/charts";

type SeriesResponse = components["schemas"]["SeriesResponse"];
const props = defineProps<{ series: SeriesResponse | undefined }>();

const el = ref<HTMLDivElement | null>(null);
let chart: ECharts | null = null;
let observer: ResizeObserver | null = null;

const peakHour = computed(() => {
  const buckets = Array.from({ length: 24 }, () => [] as number[]);
  (props.series?.points ?? []).forEach((point) => {
    if (point.value == null) return;
    buckets[new Date(point.time).getUTCHours()].push(Number(point.value));
  });
  const means = buckets.map((values) =>
    values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : -1,
  );
  const max = Math.max(...means);
  if (max < 0) return null;
  return means.indexOf(max);
});

const peakCopy = computed(() => {
  if (peakHour.value == null) return "数据不足，暂时无法判断高值时段";
  const next = (peakHour.value + 1) % 24;
  return `最近 30 天，${String(peakHour.value).padStart(2, "0")}:00–${String(next).padStart(2, "0")}:00 平均浓度最高`;
});

function render() {
  if (!chart) return;
  const points = (props.series?.points ?? []).filter((point) => point.value != null);
  const dates = [...new Set(points.map((point) => String(point.time).slice(0, 10)))];
  const dateIndex = new Map(dates.map((day, index) => [day, index]));
  const values = points.map((point) => {
    const date = new Date(point.time);
    return [date.getUTCHours(), dateIndex.get(String(point.time).slice(0, 10)) ?? 0, Number(point.value)];
  });
  const max = Math.max(1, ...values.map((item) => Number(item[2])));

  chart.setOption({
    animation: false,
    aria: { enabled: true, description: "近 30 天 PM2.5 在一天不同小时的变化热力图。" },
    grid: { left: 52, right: 76, top: 14, bottom: 32 },
    tooltip: {
      backgroundColor: "rgba(255,255,255,.985)",
      borderColor: "#c5d1cb",
      borderWidth: 1,
      padding: [11, 13],
      textStyle: { color: "#17231e", fontSize: 13, lineHeight: 21 },
      extraCssText: "box-shadow:0 12px 32px rgba(21,36,30,.12);border-radius:10px;",
      formatter(params: any) {
        const [hour, dayIndex, value] = params.data;
        return `${dates[dayIndex]} · ${String(hour).padStart(2, "0")}:00<br/><b>${Number(value).toFixed(1)}</b> µg/m³`;
      },
    },
    xAxis: {
      type: "category",
      data: Array.from({ length: 24 }, (_, hour) => String(hour)),
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: {
        color: "#5b6d64",
        fontSize: 12,
        // Keep the round-the-clock landmarks readable at projector distance.
        interval: (index: number) => index % 6 === 0 || index === 23,
        formatter: (value: string) => value + "时",
      },
    },
    yAxis: {
      type: "category",
      data: dates,
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: {
        color: "#5b6d64",
        fontSize: 12,
        interval: Math.max(0, Math.floor(dates.length / 6) - 1),
        formatter: (value: string) => value.slice(5),
      },
    },
    // Semantic-heat ramp is allowed to run across hues, but it must ship a
    // scale legend — otherwise the wash is unreadable colour.
    visualMap: {
      min: 0,
      max,
      calculable: false,
      orient: "vertical",
      right: 6,
      top: "center",
      itemWidth: 10,
      itemHeight: 110,
      text: ["高", "低"],
      textStyle: { color: "#5b6d64", fontSize: 12 },
      inRange: { color: ["#eef2ee", "#9fc4b8", "#c9a521", "#c8702b", "#86251a"] },
    },
    series: [{
      type: "heatmap",
      data: values,
      itemStyle: { borderColor: "#ffffff", borderWidth: 2 },
      emphasis: { itemStyle: { borderColor: "#10221a", borderWidth: 1 } },
    }],
  }, true);
}

onMounted(() => {
  if (!el.value) return;
  chart = init(el.value, undefined, { renderer: "svg" });
  observer = new ResizeObserver(() => chart?.resize());
  observer.observe(el.value);
  render();
});

watch(() => props.series, render, { deep: true });

onBeforeUnmount(() => {
  observer?.disconnect();
  chart?.dispose();
});
</script>

<template>
  <section class="hour-day-panel">
    <header>
      <div>
        <h3>一天中，什么时候更容易出现高值？</h3>
        <p>{{ peakCopy }}</p>
      </div>
    </header>
    <div ref="el" class="hour-day-chart"></div>
    <footer>横向看一天 24 小时，纵向看最近 30 天；颜色越暖，PM2.5 越高。</footer>
  </section>
</template>

<style scoped>
.hour-day-panel {
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
  box-shadow: 0 8px 24px rgba(24, 41, 34, .035);
}
.hour-day-panel header {
  min-height: 72px;
  padding: 16px 20px 12px;
  border-bottom: 1px solid var(--hairline-soft);
}
.hour-day-panel h3 {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-sub);
  font-weight: var(--fw-display);
  letter-spacing: var(--track-title);
}
.hour-day-panel p {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: var(--fs-body);
}
.hour-day-chart {
  width: 100%;
  height: 370px;
}
.hour-day-panel footer {
  padding: 11px 20px 13px;
  border-top: 1px solid var(--hairline-soft);
  color: var(--muted);
  font-size: var(--fs-label);
  line-height: 1.5;
}
</style>
