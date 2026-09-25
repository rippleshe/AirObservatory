<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { init, type ECharts } from "../lib/charts";

type SeriesResponse = components["schemas"]["SeriesResponse"];
const props = defineProps<{ series: SeriesResponse | undefined }>();

const el = ref<HTMLDivElement | null>(null);
let chart: ECharts | null = null;
let observer: ResizeObserver | null = null;

/* Buckets, axis and tooltip all read the browser's local hour, the same
   timezone every other timestamp on the site is formatted in. */
const dayKeyFormatter = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

function dayKey(time: string) {
  return dayKeyFormatter.format(new Date(time));
}

function hourRange(hour: number) {
  const next = (hour + 1) % 24;
  return `${String(hour).padStart(2, "0")}:00–${String(next).padStart(2, "0")}:00`;
}

const hourMeans = computed(() => {
  const buckets = Array.from({ length: 24 }, () => [] as number[]);
  (props.series?.points ?? []).forEach((point) => {
    if (point.value == null) return;
    buckets[new Date(point.time).getHours()].push(Number(point.value));
  });
  return buckets.map((values) =>
    values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null,
  );
});

const peakHour = computed(() => {
  const means = hourMeans.value;
  let best: number | null = null;
  for (let hour = 0; hour < means.length; hour += 1) {
    const mean = means[hour];
    if (mean == null) continue;
    if (best == null || mean > (means[best] ?? 0)) best = hour;
  }
  return best;
});

const windowCopy = computed(() => {
  const days = new Set((props.series?.points ?? []).map((point) => dayKey(point.time))).size;
  return days >= 30 ? "近 30 天" : `近 ${days} 天`;
});

const peakCopy = computed(() => {
  if (peakHour.value == null) return "近 30 天样本不足，暂无法判断高值时段";
  return `${windowCopy.value}，${hourRange(peakHour.value)} 平均浓度最高`;
});

const peakRangeCopy = computed(() => {
  const peak = peakHour.value;
  if (peak == null) return "日内分时均值待生成";
  const filled = hourMeans.value.filter((mean): mean is number => mean != null);
  return `${hourRange(peak)} 均值 ${(hourMeans.value[peak] ?? 0).toFixed(1)} µg/m³，最低时段 ${Math.min(...filled).toFixed(1)} µg/m³`;
});

defineExpose({ peakCopy });

function render() {
  if (!chart) return;
  const points = (props.series?.points ?? []).filter((point) => point.value != null);
  const dates = [...new Set(points.map((point) => dayKey(point.time)))];
  const dateIndex = new Map(dates.map((day, index) => [day, index]));
  const values = points.map((point) => {
    const date = new Date(point.time);
    return [date.getHours(), dateIndex.get(dayKey(point.time)) ?? 0, Number(point.value)];
  });
  const max = Math.max(1, ...values.map((item) => Number(item[2])));

  chart.setOption({
    animation: false,
    aria: { enabled: true, description: `${windowCopy.value} PM2.5 按小时与日期的分布热力图。` },
    grid: { left: 52, right: 76, top: 14, bottom: 32 },
    tooltip: {
      backgroundColor: "rgba(255,255,255,.985)",
      borderColor: "#8fa39b",
      borderWidth: 1,
      padding: [11, 13],
      textStyle: { color: "#0b1512", fontSize: 13, lineHeight: 21 },
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
        color: "#566a61",
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
        color: "#566a61",
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
      textStyle: { color: "#566a61", fontSize: 12 },
      inRange: { color: ["#eef2ee", "#9fc4b8", "#c9a521", "#c8702b", "#86251a"] },
    },
    series: [{
      type: "heatmap",
      data: values,
      itemStyle: { borderColor: "#fbfcfb", borderWidth: 2 },
      emphasis: { itemStyle: { borderColor: "#0b1512", borderWidth: 1 } },
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
      <h3 class="display-face">{{ peakRangeCopy }}</h3>
    </header>
    <div ref="el" class="hour-day-chart"></div>
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
.hour-day-chart {
  width: 100%;
  height: 370px;
}
</style>
