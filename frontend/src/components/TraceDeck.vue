<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { init, type ECharts } from "../lib/charts";
import {
  FORECAST_COLOR,
  MODEL_COLOR,
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
const windowLabel = computed(() =>
  windowHours.value === 24 ? "24 小时" : windowHours.value === 168 ? "7 天" : "30 天",
);

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
  if (!points.length) return "当前窗口没有可用的模式历史";
  const peak = points.reduce(
    (best, point) => (Number(point.value) > Number(best.value) ? point : best),
    points[0],
  );
  return `当前窗口峰值 ${Number(peak.value).toFixed(1)} µg/m³，出现在 ${fmtTime(peak.time)}`;
});

const observationCopy = computed(() => {
  const points = (props.observations?.points ?? []).filter((point) => point.value != null);
  if (!points.length) return "当前窗口没有地面观测，图上只有模式历史与未来预测";
  const latest = points[points.length - 1];
  return `当前窗口有 ${points.length} 小时地面观测，最新一次 ${Number(latest.value).toFixed(1)} µg/m³`;
});

function setWindow(value: WindowHours) {
  windowHours.value = value;
  render();
}

function render() {
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
      grid: { left: 58, right: 34, top: 28, bottom: 46 },      tooltip: {
        trigger: "axis",
        confine: true,
        backgroundColor: "rgba(255,255,255,.985)",
        borderColor: "#b5c1bb",
        borderWidth: 1,
        padding: [12, 14],
        textStyle: { color: "#0b1512", fontSize: 13, lineHeight: 22 },
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
        axisLine: { lineStyle: { color: "#7f968c" } },
        axisTick: { show: false },
        axisLabel: {
          color: "#566a61",
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
          color: "#566a61",
          fontSize: 12,
          formatter: (value: number) => String(Math.round(value)),
        },
        axisLine: { show: false },
        axisTick: { show: false },
        splitNumber: 5,
        splitLine: { lineStyle: { color: "#c3d1cb", width: 1 } },
        name: "PM2.5 µg/m³",
        nameTextStyle: { color: "#566a61", fontSize: 12, padding: [0, 0, 6, 0] },
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
          lineStyle: { color: MODEL_COLOR, width: 2 },
          areaStyle: { color: "rgba(53,111,135,.055)" },
          itemStyle: { color: MODEL_COLOR },
          z: 3,
          // Concentration bands as a faint wash, tinted by the same AQI
          // severity ramp the map uses.
          markArea: {
            silent: true,
            label: { show: false },
            data: [
              [{ yAxis: 0, itemStyle: { color: "rgba(69,162,116,.055)" } }, { yAxis: 35 }],
              [{ yAxis: 35, itemStyle: { color: "rgba(201,165,33,.055)" } }, { yAxis: 75 }],
              [{ yAxis: 75, itemStyle: { color: "rgba(200,112,43,.050)" } }, { yAxis: 115 }],
              [{ yAxis: 115, itemStyle: { color: "rgba(134,37,26,.045)" } }, { yAxis: 150 }],
              [{ yAxis: 150, itemStyle: { color: "rgba(112,61,136,.045)" } }, { yAxis: 250 }],
            ],
          },
          markLine: now
            ? {
                symbol: ["none", "none"],
                silent: true,
                lineStyle: { color: "#43564d", width: 1.2, type: "dashed" },
                label: {
                  show: true,
                  formatter: "现在",
                  color: "#26382f",
                  backgroundColor: "#f0f4f1",
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
                itemStyle: { color: "#86251a", borderColor: "#fbfcfb", borderWidth: 2 },
                label: {
                  show: true,
                  formatter(params: any) {
                    return `峰值 ${Number(params.value).toFixed(0)}`;
                  },
                  position: "top",
                  distance: 7,
                  color: "#5c2a22",
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
          data: observations.map((point) => [point.time, point.value]),
          showSymbol: false,
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

onBeforeUnmount(() => {
  observer?.disconnect();
  chart?.dispose();
});
</script>

<template>
  <section class="trace-deck">
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
        </div>
      </div>
    </header>
    <div ref="el" class="trace-chart"></div>
    <footer>
      <span>当前窗口：{{ windowLabel }}</span>
      <span v-if="activeForecast?.points?.some((point) => point.lower_bound != null)">淡色区域为预测区间</span>
      <div class="band-key">
        <span>背景浓度等级</span>
        <i
          v-for="([label, color]) in PM25_BANDS"
          :key="label"
          :style="{ background: color }"
          :title="`PM2.5 ${label} µg/m³`"
        >{{ label }}</i>
      </div>
    </footer>
  </section>
</template>

<style scoped>
.trace-deck {
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
  box-shadow: 0 10px 30px rgba(24, 41, 34, .045);
}
.trace-header {
  min-height: 94px;
  padding: 17px 20px 12px;
  display: flex;
  justify-content: space-between;
  align-items: start;
  gap: 20px;
  border-bottom: 1px solid var(--hairline-soft);
}
.trace-header h3 {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-sub);
  font-weight: var(--fw-display);
  letter-spacing: var(--track-title);
}
.trace-header p {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: var(--fs-body);
  line-height: 1.55;
}
.header-tools {
  flex: 0 0 auto;
  display: grid;
  justify-items: end;
  gap: 10px;
}
.window-switch {
  padding: 3px;
  display: flex;
  gap: 2px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: var(--sheet-soft);
}
.window-switch button {
  min-height: 34px;
  padding: 0 12px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  font-size: var(--fs-label);
  font-weight: var(--fw-strong);
  cursor: pointer;
}
.window-switch button.active {
  background: var(--ink);
  color: white;
}
.trace-legend {
  display: flex;
  flex-wrap: wrap;
  justify-content: end;
  gap: 8px 16px;
  color: var(--ink-soft);
  font-size: var(--fs-label);
}
.trace-legend span { display: flex; align-items: center; gap: 6px; }
.trace-legend i { width: 19px; height: 0; border-top: 2px solid var(--model); }
.trace-legend .observation-line {
  border-top-color: var(--observation);
  border-top-width: 3px;
}
.trace-legend .forecast-line { border-top: 2px dashed var(--forecast); }
.trace-chart {
  width: 100%;
  height: 390px;
}
.trace-deck footer {
  min-height: 44px;
  padding: 10px 18px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 18px;
  border-top: 1px solid var(--hairline-soft);
  color: var(--muted);
  font-size: var(--fs-label);
}
.band-key {
  display: flex;
  align-items: center;
  gap: 2px;
}
.band-key > span {
  margin-right: 7px;
  color: var(--ink-soft);
}
.band-key i {
  min-width: 44px;
  padding: 3px 7px;
  border-radius: 3px;
  color: #fbfcfb;
  font-size: var(--fs-label);
  font-style: normal;
  font-weight: 600;
  text-align: center;
  text-shadow: 0 1px 2px rgba(0, 0, 0, .35);
}

@media (max-width: 760px) {
  .trace-header { display: grid; }
  .header-tools { justify-items: start; }
  .trace-legend { justify-content: start; }
  .trace-chart { height: 330px; }
}
</style>
