<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { chartTheme, init, type ECharts } from "../lib/charts";
import { useInView } from "../composables/useInView";

/* Charts stay blank until the reader scrolls to them: the first paint is
   the animated entrance, never a show that already ended. */
const shell = ref<HTMLElement | null>(null);
const inView = useInView(shell);
import {
  AQI_LEVEL_COLORS,
  FORECAST_COLOR,
  OBSERVATION_COLOR,
  PM25_BANDS,
} from "../lib/palette";

type SeriesResponse = components["schemas"]["SeriesResponse"];
type ForecastResponse = components["schemas"]["ForecastResponse"];
type WindowHours = 24 | 168 | 720;

const props = defineProps<{
  history: SeriesResponse | undefined;
  observations: SeriesResponse | undefined;
  forecast: ForecastResponse | undefined;
}>();

const el = ref<HTMLDivElement | null>(null);
const windowHours = ref<WindowHours>(168);
let chart: ECharts | null = null;
let observer: ResizeObserver | null = null;

const activeForecast = computed(() => props.forecast?.series?.[0]);

function fmtTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

const windowEndMs = computed(() => {
  const lastTime = props.history?.points?.at(-1)?.time;
  return lastTime ? new Date(lastTime).getTime() : Date.now();
});
const windowStartMs = computed(() => windowEndMs.value - windowHours.value * 3600 * 1000);

const windowPeakCopy = computed(() => {
  const points = (props.history?.points ?? []).filter(
    (point) => point.value != null && new Date(point.time).getTime() >= windowStartMs.value,
  );
  if (!points.length) return "时序变化轨迹";
  const peak = points.reduce(
    (best, point) => (Number(point.value) > Number(best.value) ? point : best),
    points[0],
  );
  return `窗口峰值 ${Number(peak.value).toFixed(1)} µg/m³ · ${fmtTime(peak.time)}`;
});

const observationCopy = computed(() => {
  const points = (props.observations?.points ?? []).filter((point) => point.value != null);
  if (!points.length) return "模式历史与预测轨迹";
  const latest = points[points.length - 1];
  return `地面观测最新 ${Number(latest.value).toFixed(1)} µg/m³`;
});

function setWindow(value: WindowHours) {
  windowHours.value = value;
  render();
}

/* Sparse ground readings must not read as continuous coverage: a gap longer
   than the comparability window breaks the line — missing stays missing. */
const OBSERVATION_GAP_MS = 3 * 3_600_000;

function observationSeriesData(points: { time: string; value: number | null }[]) {
  const data: [string, number | null][] = [];
  let previousMs: number | null = null;
  for (const point of points) {
    if (point.value == null || !Number.isFinite(Number(point.value))) continue;
    const timeMs = new Date(point.time).getTime();
    if (previousMs != null && timeMs - previousMs > OBSERVATION_GAP_MS) {
      data.push([new Date((previousMs + timeMs) / 2).toISOString(), null]);
    }
    data.push([point.time, Number(point.value)]);
    previousMs = timeMs;
  }
  return data;
}

function render() {
  if (!inView.value) return;
  if (!chart) return;

  const fullHistory = props.history?.points ?? [];
  const startMs = windowStartMs.value;
  const history = fullHistory.filter((point) => new Date(point.time).getTime() >= startMs);
  const observations = (props.observations?.points ?? []).filter(
    (point) => new Date(point.time).getTime() >= startMs,
  );
  const forecast = activeForecast.value?.points ?? [];
  const now = history.at(-1)?.time ?? observations.at(-1)?.time;
  const unit = props.history?.unit ?? props.forecast?.unit ?? "";
  const latestHistory = history.at(-1)?.value;

  const forecastLine =
    now && latestHistory != null
      ? [[now, latestHistory], ...forecast.map((point) => [point.target_at, point.value])]
      : forecast.map((point) => [point.target_at, point.value]);

  const lower = forecast.filter(
    (point) => point.lower_bound != null && point.upper_bound != null,
  );
  const hasBand = lower.length > 0;
  /* Index of the model-history series inside the option below: the forecast
     band prepends two invisible stacked lines when it exists. */
  const historyIndex = hasBand ? 2 : 0;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  chart.setOption(
    {
      aria: {
        enabled: true,
        description:
          "PM2.5 综合时间图，同时展示模式历史、地面观测、未来预测、预测区间和空气质量浓度等级背景。",
      },
      animation: !reduceMotion,
      animationDurationUpdate: reduceMotion ? 0 : 220,
      animationEasingUpdate: "cubicOut",
      /* The band scale is rendered as chips in the header, right beside the
         line legend: ECharts' own visualMap block parked over the y-axis. */
      visualMap: {
        type: "piecewise",
        show: false,
        seriesIndex: historyIndex,
        dimension: 1,
        pieces: [
          { max: 35, color: PM25_BANDS[0][1] },
          { min: 35, max: 75, color: PM25_BANDS[1][1] },
          { min: 75, max: 115, color: PM25_BANDS[2][1] },
          { min: 115, max: 150, color: PM25_BANDS[3][1] },
          { min: 150, color: PM25_BANDS[4][1] },
        ],
      },
      grid: { left: 58, right: 34, top: 28, bottom: 46 },
      tooltip: {
        trigger: "axis",
        confine: true,
        backgroundColor: "rgba(255,255,255,.985)",
        borderColor: chartTheme().tooltipBorder,
        borderWidth: 1,
        padding: [12, 14],
        textStyle: { color: chartTheme().ink, fontSize: 13, lineHeight: 22 },
        extraCssText:
          "box-shadow:0 14px 36px rgba(21,37,30,.12);border-radius:10px;",
        formatter(params: any) {
          const rows = (Array.isArray(params) ? params : [params]).filter(
            (row: any) => !String(row.seriesName).startsWith("__"),
          );
          const rawTime = rows[0]?.value?.[0] ?? rows[0]?.axisValue;
          const time = new Intl.DateTimeFormat("zh-CN", {
            month: "numeric",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
          }).format(new Date(rawTime));
          const body = rows
            .filter((row: any) => row.value?.[1] != null)
            .map(
              (row: any) =>
                `${row.marker}${row.seriesName} <b>${Number(row.value[1]).toFixed(1)}</b> ${unit}`,
            )
            .join("<br/>");
          return `<b>${time}</b><br/>${body}`;
        },
      },
      xAxis: {
        type: "time",
        axisLine: { lineStyle: { color: chartTheme().axisLine } },
        axisTick: { show: false },
        axisLabel: {
          color: chartTheme().axisInk,
          fontSize: 12,
          hideOverlap: true,
          formatter(value: number) {
            const options =
              windowHours.value === 24
                ? { hour: "2-digit" as const, minute: "2-digit" as const, hour12: false }
                : { month: "numeric" as const, day: "numeric" as const };
            return new Intl.DateTimeFormat("zh-CN", options).format(new Date(value));
          },
        },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        min: 0,
        axisLabel: {
          color: chartTheme().axisInk,
          fontSize: 12,
          formatter: (value: number) => String(Math.round(value)),
        },
        axisLine: { show: false },
        axisTick: { show: false },
        splitNumber: 5,
        splitLine: { lineStyle: { color: chartTheme().splitLine, width: 1 } },
        name: "PM2.5 µg/m³",
        nameTextStyle: { color: chartTheme().axisInk, fontSize: 12, padding: [0, 0, 6, 0] },
      },
      series: [
        ...(lower.length
          ? [
              {
                name: "__lower",
                type: "line",
                stack: "confidence",
                data: lower.map((point) => [point.target_at, point.lower_bound]),
                showSymbol: false,
                lineStyle: { opacity: 0 },
                areaStyle: { opacity: 0 },
                silent: true,
                tooltip: { show: false },
                z: 1,
              },
              {
                name: "__range",
                type: "line",
                stack: "confidence",
                data: lower.map((point) => [
                  point.target_at,
                  Number(point.upper_bound) - Number(point.lower_bound),
                ]),
                showSymbol: false,
                lineStyle: { opacity: 0 },
                areaStyle: { color: "rgba(160,106,52,.18)" },
                silent: true,
                tooltip: { show: false },
                z: 1,
              },
            ]
          : []),
        {
          name: "模式历史",
          type: "line",
          data: history.map((point) => [point.time, point.value]),
          showSymbol: false,
          connectNulls: false,
          smooth: 0.1,
          // No fixed line colour: visualMap paints each segment by its PM2.5
          // band, so peaks actually turn orange/red the way the scale says.
          lineStyle: { width: 2.4 },
          areaStyle: { opacity: 0.12 },
          z: 3,
          markLine: now
            ? {
                symbol: ["none", "none"],
                silent: true,
                lineStyle: { color: chartTheme().inkSoft, width: 1.2, type: "dashed" },
                label: {
                  show: true,
                  formatter: "现在",
                  color: chartTheme().ink,
                  backgroundColor: chartTheme().surfaceSubtle,
                  borderRadius: 5,
                  padding: [4, 6],
                  fontSize: 12,
                  fontWeight: 700,
                  position: "insideEndTop",
                },
                data: [{ xAxis: now }],
              }
            : undefined,
          markPoint: {
            symbol: "circle",
            symbolSize: 9,
            data: [
              {
                type: "max",
                name: "窗口峰值",
                itemStyle: { color: AQI_LEVEL_COLORS["中度污染"], borderColor: chartTheme().surface, borderWidth: 2 },
                label: {
                  show: true,
                  formatter(params: any) {
                    return `峰值 ${Number(params.value).toFixed(0)}`;
                  },
                  position: "top",
                  distance: 7,
                  color: chartTheme().inkSoft,
                  fontSize: 12,
                  fontWeight: 700,
                  backgroundColor: "rgba(255,255,255,.94)",
                  borderRadius: 5,
                  padding: [3, 6],
                },
              },
            ],
          },
        },
        {
          name: "地面观测",
          type: "line",
          data: observationSeriesData(observations),
          showSymbol: true,
          symbol: "circle",
          symbolSize: 5,
          connectNulls: false,
          lineStyle: { color: OBSERVATION_COLOR, width: 2.8 },
          itemStyle: { color: OBSERVATION_COLOR },
          z: 5,
        },
        {
          name: "未来预测",
          type: "line",
          data: forecastLine,
          showSymbol: false,
          connectNulls: false,
          smooth: 0.12,
          lineStyle: { color: FORECAST_COLOR, width: 2, type: "dashed" },
          itemStyle: { color: FORECAST_COLOR },
          z: 6,
        },
      ],
    },
    true,
  );
}

onMounted(() => {
  if (!el.value) return;
  chart = init(el.value, undefined, { renderer: "svg" });
  observer = new ResizeObserver(() => chart?.resize());
  observer.observe(el.value);
  render();
});

watch(() => [props.history, props.observations, props.forecast], render, { deep: true });
watch(inView, () => render());

onBeforeUnmount(() => {
  observer?.disconnect();
  chart?.dispose();
});
</script>

<template>
  <section ref="shell" class="trace-deck">
    <header class="trace-header">
      <div>
        <h3>{{ windowPeakCopy }}</h3>
        <p>{{ observationCopy }}</p>
      </div>
      <div class="header-tools">
        <div class="window-switch" aria-label="时间范围">
          <button :class="{ active: windowHours === 24 }" @click="setWindow(24)">24 小时</button>
          <button :class="{ active: windowHours === 168 }" @click="setWindow(168)">7 天</button>
          <button :class="{ active: windowHours === 720 }" @click="setWindow(720)">30 天</button>
        </div>
        <div class="trace-legend" aria-label="图例">
          <span><i class="observation-line"></i>地面观测</span>
          <span><i class="history-line"></i>模式历史</span>
          <span><i class="forecast-line"></i>未来预测</span>
          <span v-if="activeForecast?.points?.some((point) => point.lower_bound != null)">
            <i class="forecast-band"></i>预测区间
          </span>
          <span class="band-chips" aria-label="浓度带">
            <i
              v-for="([label, color]) in PM25_BANDS"
              :key="label"
              :style="{ background: color }"
            >{{ label }}</i>
          </span>
        </div>
      </div>
    </header>
    <div ref="el" class="trace-chart"></div>
  </section>
</template>

<style scoped>
.trace-deck {
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
  box-shadow: var(--shadow-sm);
}
.trace-header {
  min-height: 72px;
  padding: 16px 20px 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  border-bottom: 1px solid var(--hairline);
}
.trace-header h3 {
  margin: 0;
  color: var(--ink);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: var(--track-title);
}
.trace-header p {
  margin: 3px 0 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.4;
}
.header-tools {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 16px;
}
.window-switch {
  padding: 2px;
  display: flex;
  gap: 2px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: var(--sheet-soft);
}
.window-switch button {
  min-height: 28px;
  padding: 0 10px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-fast) ease;
}
.window-switch button.active {
  background: var(--sheet);
  color: var(--ink);
  font-weight: 600;
  box-shadow: var(--shadow-sm);
}
.trace-legend {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--muted);
  font-size: 12px;
}
.trace-legend span { display: flex; align-items: center; gap: 6px; }
.trace-legend i { width: 19px; height: 0; border-top: 2px solid var(--model); }
/* 模式历史线按浓度带变色，图例条同色阶，不冒充单色线。 */
.trace-legend .history-line {
  height: 4px;
  border-top: 0;
  border-radius: 2px;
  background: linear-gradient(
    90deg,
    #45a274 0%,
    #45a274 22%,
    #c9a521 34%,
    #c8702b 56%,
    #86251a 78%,
    #703d88 100%
  );
}
.trace-legend .observation-line {
  border-top-color: var(--observation);
  border-top-width: 3px;
}
.trace-legend .forecast-line { border-top: 2px dashed var(--forecast); }
.trace-legend .forecast-band {
  height: 10px;
  border-top: 0;
  border-radius: 2px;
  background: rgba(160, 106, 52, .22);
}
.band-chips {
  display: flex;
  gap: 2px;
}
.band-chips i {
  width: auto;
  min-width: 38px;
  height: 15px;
  border-top: 0;
  border-radius: 2px;
  color: #fbfcfb;
  font-size: var(--fs-label);
  font-style: normal;
  font-weight: 600;
  text-align: center;
  line-height: 15px;
  text-shadow: 0 1px 2px rgba(0, 0, 0, .35);
}
.trace-chart {
  width: 100%;
  height: 390px;
}

@media (max-width: 760px) {
  .trace-header { display: grid; }
  .header-tools { justify-items: start; }
  .trace-legend { justify-content: start; }
  .trace-chart { height: 330px; }
}
</style>
