<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { init, type ECharts } from "../lib/charts";
import { MODEL_COLOR } from "../lib/palette";

type SeriesResponse = components["schemas"]["SeriesResponse"];

const props = defineProps<{ series: SeriesResponse[] }>();
const els = ref<HTMLDivElement[]>([]);
const charts: ECharts[] = [];
let observer: ResizeObserver | null = null;

const LABELS: Record<string, string> = {
  pm25: "PM2.5",
  pm10: "PM10",
  no2: "NO₂",
  o3: "O₃",
  so2: "SO₂",
  co: "CO",
};

function setEl(el: unknown, index: number) {
  if (el instanceof HTMLDivElement) els.value[index] = el;
}

function validPoints(item: SeriesResponse) {
  return item.points.filter((point) => point.value != null);
}

function quantile(values: number[], q: number) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const pos = (sorted.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  const next = sorted[base + 1];
  return next == null ? sorted[base] : sorted[base] + rest * (next - sorted[base]);
}

function meta(item: SeriesResponse) {
  const points = validPoints(item);
  if (!points.length) {
    return {
      latest: null,
      change: null,
      peak: null,
      median: null,
      p90: null,
      percentile: null,
      recent: [],
    };
  }
  const latest = Number(points.at(-1)?.value);
  const latestTime = new Date(points.at(-1)?.time ?? 0).getTime();
  const target = latestTime - 24 * 3600 * 1000;
  const weekStart = latestTime - 7 * 24 * 3600 * 1000;
  const previous = [...points]
    .reverse()
    .find((point) => new Date(point.time).getTime() <= target);
  const change = previous?.value == null ? null : latest - Number(previous.value);
  const recent24 = points.filter((point) => new Date(point.time).getTime() >= target);
  const peak = recent24.length
    ? Math.max(...recent24.map((point) => Number(point.value)))
    : null;
  const values = points.map((point) => Number(point.value));
  const percentile =
    values.length > 1
      ? (values.filter((value) => value <= latest).length / values.length) * 100
      : 50;
  return {
    latest,
    change,
    peak,
    median: quantile(values, 0.5),
    p90: quantile(values, 0.9),
    percentile,
    recent: points.filter((point) => new Date(point.time).getTime() >= weekStart),
  };
}

function trendText(item: SeriesResponse) {
  const change = meta(item).change;
  if (change == null) return "24h 对比不足";
  if (Math.abs(change) < 1) return "与 24h 前接近";
  return `${change > 0 ? "↑" : "↓"} ${Math.abs(change).toFixed(1)} / 24h`;
}

function percentileText(item: SeriesResponse) {
  const percentile = meta(item).percentile;
  if (percentile == null) return "历史位置不足";
  if (percentile >= 85) return "近30天高位";
  if (percentile >= 65) return "近30天偏高";
  if (percentile <= 15) return "近30天低位";
  if (percentile <= 35) return "近30天偏低";
  return "接近30天常态";
}

function render() {
  props.series.forEach((item, index) => {
    const chart = charts[index];
    if (!chart) return;
    const info = meta(item);
    const values = info.recent;

    chart.setOption(
      {
        animation: false,
        aria: { enabled: true, description: `${LABELS[item.variable]} 最近7天变化趋势，并标出30天中位数。` },
        grid: { left: 4, right: 4, top: 12, bottom: 4 },
        tooltip: {
          trigger: "axis",
          confine: true,
          backgroundColor: "rgba(255,255,255,.985)",
          borderColor: "#bec9c3",
          padding: [9, 11],
          textStyle: { color: "#17231e", fontSize: 13 },
          formatter(params: any) {
            const row = Array.isArray(params) ? params[0] : params;
            const time = new Intl.DateTimeFormat("zh-CN", {
              month: "numeric",
              day: "numeric",
              hour: "2-digit",
              hour12: false,
            }).format(new Date(row.value[0]));
            return `${time}<br/><b>${Number(row.value[1]).toFixed(1)}</b> ${item.unit}`;
          },
        },
        xAxis: { type: "time", show: false },
        yAxis: { type: "value", scale: true, show: false },
        series: [
          {
            type: "line",
            data: values.map((point) => [point.time, point.value]),
            showSymbol: false,
            connectNulls: false,
            smooth: 0.12,
            lineStyle: { color: MODEL_COLOR, width: 2 },
            areaStyle: { color: "rgba(53,111,135,.085)" },
            itemStyle: { color: MODEL_COLOR },
            // An unlabelled reference line is invisible meaning — name it.
            markLine:
              info.median == null
                ? undefined
                : {
                    silent: true,
                    symbol: ["none", "none"],
                    lineStyle: { color: "#8f9d96", width: 1, type: "dashed" },
                    label: {
                      show: true,
                      formatter: "30天中位",
                      position: "insideStartTop",
                      color: "#5b6d64",
                      fontSize: 12,
                      backgroundColor: "rgba(255,255,255,.88)",
                      borderRadius: 3,
                      padding: [1, 4],
                    },
                    data: [{ yAxis: info.median }],
                  },
          },
        ],
      },
      true,
    );
  });
}

onMounted(() => {
  props.series.forEach((_, index) => {
    const el = els.value[index];
    if (el) charts[index] = init(el, undefined, { renderer: "svg" });
  });
  observer = new ResizeObserver(() => charts.forEach((chart) => chart?.resize()));
  els.value.forEach((el) => observer?.observe(el));
  render();
});

watch(() => props.series, render, { deep: true });

onBeforeUnmount(() => {
  observer?.disconnect();
  charts.forEach((chart) => chart?.dispose());
});
</script>

<template>
  <div class="pollutant-grid">
    <article v-for="(item, index) in series" :key="item.variable">
      <header>
        <div>
          <h3>{{ LABELS[item.variable] ?? item.variable }}</h3>
          <span>{{ item.unit }}</span>
        </div>
        <b :class="{ rising: (meta(item).change ?? 0) > 0, falling: (meta(item).change ?? 0) < 0 }">
          {{ trendText(item) }}
        </b>
      </header>

      <div class="readout-row">
        <div class="readout">
          <strong>{{ meta(item).latest == null ? "—" : meta(item).latest?.toFixed(1) }}</strong>
          <span>当前</span>
        </div>
        <div class="relative-state">
          <b>{{ percentileText(item) }}</b>
          <span v-if="meta(item).percentile != null">
            高于近30天 {{ Math.round(meta(item).percentile ?? 0) }}% 的时刻
          </span>
        </div>
      </div>

      <div class="percentile-track" aria-hidden="true">
        <span :style="{ width: `${Math.min(100, Math.max(0, meta(item).percentile ?? 0))}%` }"></span>
        <i :style="{ left: `${Math.min(98, Math.max(2, meta(item).percentile ?? 50))}%` }"></i>
      </div>

      <div :ref="(el) => setEl(el, index)" class="mini-chart"></div>

      <footer>
        <span>30天中位 <b>{{ meta(item).median == null ? "—" : meta(item).median?.toFixed(1) }}</b></span>
        <span>P90 <b>{{ meta(item).p90 == null ? "—" : meta(item).p90?.toFixed(1) }}</b></span>
        <span>24h峰值 <b>{{ meta(item).peak == null ? "—" : meta(item).peak?.toFixed(1) }}</b></span>
      </footer>
    </article>
  </div>
</template>

<style scoped>
.pollutant-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}
.pollutant-grid article {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
  box-shadow: 0 8px 24px rgba(24, 41, 34, .035);
}
.pollutant-grid header {
  padding: 16px 18px 0;
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 12px;
}
.pollutant-grid header > div {
  display: flex;
  align-items: baseline;
  gap: 7px;
}
.pollutant-grid h3 {
  margin: 0;
  color: var(--ink);
  font-size: 16px;
  font-weight: var(--fw-display);
  letter-spacing: var(--track-title);
}
.pollutant-grid header span {
  color: var(--muted);
  font-size: var(--fs-label);
}
.pollutant-grid header > b {
  color: var(--muted);
  font-size: var(--fs-label);
  font-weight: var(--fw-strong);
  white-space: nowrap;
}
.pollutant-grid header > b.rising { color: var(--error); }
.pollutant-grid header > b.falling { color: var(--ok); }

.readout-row {
  padding: 6px 18px 10px;
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 14px;
}
.readout {
  display: flex;
  align-items: baseline;
  gap: 7px;
}
/* Hero figure: proportional digits, same sans. */
.readout strong {
  color: var(--ink);
  font-size: 36px;
  font-weight: var(--fw-display);
  letter-spacing: -.04em;
}
.readout span {
  color: var(--muted);
  font-size: var(--fs-label);
}
.relative-state {
  max-width: 155px;
  display: grid;
  justify-items: end;
  gap: 2px;
  text-align: right;
}
.relative-state b {
  color: var(--ink-soft);
  font-size: var(--fs-label);
  font-weight: var(--fw-strong);
}
.relative-state span {
  color: var(--muted);
  font-size: var(--fs-label);
  line-height: 1.35;
}
.percentile-track {
  position: relative;
  height: 5px;
  margin: 0 18px 6px;
  border-radius: 99px;
  background: #e7ece9;
}
.percentile-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #45a274, #c9a521, #c8702b, #86251a);
  opacity: .7;
}
.percentile-track i {
  position: absolute;
  top: 50%;
  width: 10px;
  height: 10px;
  transform: translate(-50%, -50%);
  border: 2px solid white;
  border-radius: 50%;
  background: var(--ink);
  box-shadow: 0 0 0 1px var(--muted);
}
.mini-chart {
  width: 100%;
  height: 118px;
}
.pollutant-grid footer {
  min-height: 46px;
  padding: 0 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border-top: 1px solid var(--hairline-soft);
  color: var(--muted);
  font-size: var(--fs-label);
}
.pollutant-grid footer span {
  min-width: 0;
  white-space: nowrap;
}
.pollutant-grid footer b {
  color: var(--ink);
  font-family: var(--mono);
  font-size: var(--fs-label);
}

@media (max-width: 1050px) {
  .pollutant-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 650px) {
  .pollutant-grid { grid-template-columns: 1fr; }
  .readout strong { font-size: 32px; }
}
</style>
