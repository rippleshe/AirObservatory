<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { init, type ECharts } from "../lib/charts";
import {
  AQI_LEVEL_COLORS,
  aqiColor,
  changeColor,
  changeState,
} from "../lib/palette";

type NationalRegion = components["schemas"]["NationalRegion"];
type NationalCity = components["schemas"]["NationalCity"];
type NationalSummary = components["schemas"]["NationalSummary"];

const props = defineProps<{
  regions: NationalRegion[];
  cities: NationalCity[];
  summary: NationalSummary;
}>();

const matrixEl = ref<HTMLDivElement | null>(null);
const regionEl = ref<HTMLDivElement | null>(null);
const pollutantEl = ref<HTMLDivElement | null>(null);
const charts: ECharts[] = [];
let observer: ResizeObserver | null = null;

/* The scatter labels only ten of sixty cities; the rest would be
   hover-gated. This toggle exposes every value in a table twin. */
const showTable = ref(false);

const levelOrder = ["优", "良", "轻度污染", "中度污染", "重度污染", "严重污染"];

const validCities = computed(() =>
  props.cities.filter(
    (city) => city.pm25 != null && city.pm25_change_24h != null && city.china_aqi != null,
  ),
);

const rankedCities = computed(() =>
  [...validCities.value].sort((a, b) => (b.china_aqi ?? 0) - (a.china_aqi ?? 0)),
);

const nationalMean = computed(() => props.summary.mean_pm25 ?? 0);
const highAndRising = computed(
  () =>
    validCities.value.filter(
      (city) => (city.pm25 ?? 0) > nationalMean.value && (city.pm25_change_24h ?? 0) > 0,
    ).length,
);
const highButImproving = computed(
  () =>
    validCities.value.filter(
      (city) => (city.pm25 ?? 0) > nationalMean.value && (city.pm25_change_24h ?? 0) < 0,
    ).length,
);
const fastRising = computed(
  () => validCities.value.filter((city) => (city.pm25_change_24h ?? 0) >= 20).length,
);

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
  if (charts.length !== 3) return;
  const [matrixChart, regionChart, pollutantChart] = charts;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const cities = validCities.value;
  const axisInk = "#5b6d64";
  const axisSize = 12;

  const important = new Set([
    ...[...cities]
      .sort((a, b) => (b.china_aqi ?? 0) - (a.china_aqi ?? 0))
      .slice(0, 5)
      .map((city) => city.location_id),
    ...[...cities]
      .sort(
        (a, b) =>
          Math.abs(b.pm25_change_24h ?? 0) - Math.abs(a.pm25_change_24h ?? 0),
      )
      .slice(0, 5)
      .map((city) => city.location_id),
  ]);

  const maxAqi = Math.max(...cities.map((city) => city.china_aqi ?? 0), 1);
  matrixChart.setOption(
    {
      animation: !reducedMotion,
      aria: {
        enabled: true,
        description:
          "六十城污染水平与过去24小时变化矩阵。越往右表示当前PM2.5越高，越往上表示过去24小时上升越明显。",
      },
      grid: { left: 62, right: 34, top: 38, bottom: 58 },
      tooltip: {
        ...tooltipBase(),
        trigger: "item",
        formatter(params: any) {
          const city = params.data.raw as NationalCity;
          const state = changeState(city.pm25_change_24h);
          const primary = city.primary_pollutants?.join(" / ") || "暂无";
          return [
            `<b>${city.name}</b> · ${city.region}`,
            `PM2.5 <b>${city.pm25?.toFixed(1)}</b> µg/m³`,
            `24h ${state.arrow} <b>${state.label}</b> ${Math.abs(city.pm25_change_24h ?? 0).toFixed(1)} µg/m³`,
            `<b>${city.china_aqi_level ?? "—"}</b> · AQI ${city.china_aqi ?? "—"}`,
            `主要污染物 ${primary}`,
          ].join("<br/>");
        },
      },
      xAxis: {
        name: "当前 PM2.5 →",
        nameLocation: "middle",
        nameGap: 36,
        nameTextStyle: { color: "#506159", fontSize: axisSize, fontWeight: 650 },
        type: "value",
        min: 0,
        axisLine: { lineStyle: { color: "#a9b6af" } },
        axisTick: { show: false },
        axisLabel: { color: axisInk, fontSize: axisSize },
        splitLine: { lineStyle: { color: "#dde4e0" } },
      },
      yAxis: {
        name: "过去24h变化 ↑",
        nameGap: 42,
        nameTextStyle: { color: "#506159", fontSize: axisSize, fontWeight: 650 },
        type: "value",
        axisLine: { lineStyle: { color: "#a9b6af" } },
        axisTick: { show: false },
        axisLabel: {
          color: axisInk,
          fontSize: axisSize,
          formatter: (value: number) => (value > 0 ? `+${value}` : String(value)),
        },
        splitLine: { lineStyle: { color: "#dde4e0" } },
      },
      series: [
        {
          type: "scatter",
          data: cities.map((city) => ({
            value: [city.pm25, city.pm25_change_24h, city.china_aqi],
            raw: city,
            symbolSize: 13 + 14 * ((city.china_aqi ?? 0) / maxAqi),
            itemStyle: {
              color: aqiColor(city.china_aqi_level),
              borderColor: "#fff",
              borderWidth: 2,
              opacity: 0.92,
            },
            label: {
              show: important.has(city.location_id),
              formatter: city.name,
            },
          })),
          label: {
            position: "top",
            distance: 6,
            color: "#10221a",
            fontSize: 12,
            fontWeight: 700,
            textBorderColor: "#fff",
            textBorderWidth: 4,
          },
          emphasis: {
            scale: 1.25,
            itemStyle: { borderColor: "#10231c", borderWidth: 2.2 },
            label: {
              show: true,
              color: "#10221a",
              fontSize: 13,
              fontWeight: 750,
              backgroundColor: "rgba(255,255,255,.95)",
              borderRadius: 5,
              padding: [4, 6],
              textBorderWidth: 0,
            },
          },
          markLine: {
            silent: true,
            symbol: ["none", "none"],
            lineStyle: { color: "#8f9d96", width: 1, type: "dashed" },
            label: {
              color: "#5b6962",
              fontSize: 12,
              backgroundColor: "rgba(255,255,255,.9)",
              padding: [2, 5],
            },
            data: [
              {
                xAxis: nationalMean.value,
                label: { formatter: "全国平均" },
              },
              {
                yAxis: 0,
                label: { formatter: "24h 持平" },
              },
            ],
          },
        },
      ],
    },
    true,
  );

  const sortedRegions = [...props.regions].sort(
    (a, b) => (b.mean_pm25 ?? 0) - (a.mean_pm25 ?? 0),
  );
  const regionCounts = new Map<string, Record<string, number>>();
  for (const region of sortedRegions) {
    regionCounts.set(region.region, Object.fromEntries(levelOrder.map((level) => [level, 0])));
  }
  for (const city of props.cities) {
    const bucket = regionCounts.get(city.region);
    if (bucket && city.china_aqi_level) {
      bucket[city.china_aqi_level] = (bucket[city.china_aqi_level] ?? 0) + 1;
    }
  }

  regionChart.setOption(
    {
      animation: !reducedMotion,
      aria: { enabled: true, description: "各区域城市AQI等级构成。" },
      grid: { left: 88, right: 20, top: 16, bottom: 30 },
      tooltip: {
        ...tooltipBase(),
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter(params: any) {
          const rows = (Array.isArray(params) ? params : [params]).filter(
            (row: any) => Number(row.value) > 0,
          );
          const region = rows[0]?.axisValue ?? "";
          const source = sortedRegions.find((item) => item.region === region);
          const body = rows
            .map((row: any) => `${row.marker}${row.seriesName} <b>${row.value}</b> 城`)
            .join("<br/>");
          return `<b>${region}</b> · PM2.5 均值 ${source?.mean_pm25?.toFixed(1) ?? "—"}<br/>${body}`;
        },
      },
      xAxis: {
        type: "value",
        minInterval: 1,
        axisLabel: { color: axisInk, fontSize: axisSize },
        axisTick: { show: false },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: "#dde4e0" } },
      },
      yAxis: {
        type: "category",
        inverse: true,
        data: sortedRegions.map((item) => item.region),
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: {
          color: "#2a3d34",
          fontSize: axisSize,
          fontWeight: 700,
        },
      },
      series: levelOrder.map((level) => ({
        name: level,
        type: "bar",
        stack: "levels",
        barWidth: 20,
        data: sortedRegions.map((region) => regionCounts.get(region.region)?.[level] ?? 0),
        // 2px surface gaps between stack segments — separation by whitespace,
        // not by a stroke drawn around each segment.
        itemStyle: { color: AQI_LEVEL_COLORS[level], borderColor: "#fff", borderWidth: 2 },
        emphasis: { focus: "series" },
      })),
    },
    true,
  );

  const pollutantMap = new Map<string, { count: number; aqis: number[] }>();
  for (const city of props.cities) {
    const primary = city.primary_pollutants?.[0];
    if (!primary) continue;
    const bucket = pollutantMap.get(primary) ?? { count: 0, aqis: [] };
    bucket.count += 1;
    if (city.china_aqi != null) bucket.aqis.push(city.china_aqi);
    pollutantMap.set(primary, bucket);
  }
  const pollutants = [...pollutantMap.entries()]
    .map(([name, value]) => ({
      name,
      count: value.count,
      meanAqi: value.aqis.length
        ? value.aqis.reduce((sum, item) => sum + item, 0) / value.aqis.length
        : null,
    }))
    .sort((a, b) => b.count - a.count);

  pollutantChart.setOption(
    {
      animation: !reducedMotion,
      aria: { enabled: true, description: "六十城首要污染物分布。" },
      grid: { left: 66, right: 78, top: 14, bottom: 26 },
      tooltip: {
        ...tooltipBase(),
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter(params: any) {
          const row = Array.isArray(params) ? params[0] : params;
          const item = pollutants[row.dataIndex];
          return `<b>${item.name}</b><br/>作为首要污染物：<b>${item.count}</b> 城<br/>这些城市平均AQI：<b>${item.meanAqi?.toFixed(0) ?? "—"}</b>`;
        },
      },
      xAxis: { type: "value", show: false },
      yAxis: {
        type: "category",
        inverse: true,
        data: pollutants.map((item) => item.name),
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: { color: "#2a3d34", fontSize: axisSize, fontWeight: 700 },
      },
      series: [
        {
          type: "bar",
          data: pollutants.map((item, index) => ({
            value: item.count,
            itemStyle: {
              color: index === 0 ? "#315f56" : "#6f968b",
              borderRadius: [0, 5, 5, 0],
            },
          })),
          barWidth: 18,
          label: {
            show: true,
            position: "right",
            color: "#2a3d34",
            fontSize: axisSize,
            formatter(params: any) {
              const item = pollutants[params.dataIndex];
              return `${item.count} 城 · 平均 AQI ${item.meanAqi?.toFixed(0) ?? "—"}`;
            },
          },
        },
      ],
    },
    true,
  );
}

onMounted(() => {
  [matrixEl.value, regionEl.value, pollutantEl.value].forEach((el) => {
    if (el) charts.push(init(el, undefined, { renderer: "svg" }));
  });
  observer = new ResizeObserver(() => charts.forEach((chart) => chart.resize()));
  [matrixEl.value, regionEl.value, pollutantEl.value].forEach(
    (el) => el && observer?.observe(el),
  );
  render();
});

watch(() => [props.regions, props.cities, props.summary], render, { deep: true });

watch(showTable, (visible) => {
  if (!visible) requestAnimationFrame(() => charts.forEach((chart) => chart.resize()));
});

onBeforeUnmount(() => {
  observer?.disconnect();
  charts.forEach((chart) => chart.dispose());
});
</script>

<template>
  <section class="insight-deck">
    <article class="matrix-card">
      <header>
        <div>
          <span class="card-label">60 城变化矩阵</span>
          <h3>现在污染高的城市，还在继续变差吗？</h3>
          <p>横轴看当前 PM2.5，纵轴看过去 24 小时变化；圆点越大，AQI 越高。颜色是 AQI 等级，图右下角表格给全量数值。</p>
        </div>
        <div class="matrix-tools">
          <div class="matrix-summary" aria-label="变化矩阵摘要">
            <span><b>{{ highAndRising }}</b> 高且上升</span>
            <span><b>{{ highButImproving }}</b> 高但改善</span>
            <span><b>{{ fastRising }}</b> 快速上升</span>
          </div>
          <button
            type="button"
            class="table-toggle"
            :aria-pressed="showTable"
            @click="showTable = !showTable"
          >
            {{ showTable ? "看图" : "看数据" }}
          </button>
        </div>
      </header>

      <div v-show="!showTable" ref="matrixEl" class="matrix-chart"></div>

      <div v-show="showTable" class="matrix-table-wrap">
        <table class="matrix-table">
          <caption class="sr-only">60 城当前 PM2.5、24 小时变化与 AQI 等级</caption>
          <thead>
            <tr>
              <th scope="col">城市</th>
              <th scope="col">区域</th>
              <th scope="col">PM2.5</th>
              <th scope="col">24h 变化</th>
              <th scope="col">AQI</th>
              <th scope="col">等级</th>
              <th scope="col">首要污染物</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="city in rankedCities" :key="city.location_id">
              <th scope="row">{{ city.name }}</th>
              <td>{{ city.region }}</td>
              <td class="data-mono">{{ city.pm25?.toFixed(1) ?? "—" }}</td>
              <td>
                <span class="change-cell" :style="{ color: changeColor(city.pm25_change_24h) }">
                  {{ changeState(city.pm25_change_24h).arrow }}
                </span>
                <span class="data-mono">{{ Math.abs(city.pm25_change_24h ?? 0).toFixed(1) }}</span>
                <span class="change-word">{{ changeState(city.pm25_change_24h).label }}</span>
              </td>
              <td class="data-mono">{{ city.china_aqi ?? "—" }}</td>
              <td>
                <span class="level-cell">
                  <i :style="{ background: aqiColor(city.china_aqi_level) }"></i>
                  {{ city.china_aqi_level ?? "—" }}
                </span>
              </td>
              <td>{{ city.primary_pollutants?.join(" / ") || "—" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>

    <article class="side-card">
      <header>
        <span class="card-label">区域结构</span>
        <h3>同一地区内部，也不是同一种空气状态</h3>
        <p>每一行是一片区域，颜色直接表示其中城市的 AQI 等级构成。</p>
      </header>
      <div ref="regionEl" class="side-chart"></div>
    </article>

    <article class="side-card">
      <header>
        <span class="card-label">污染物结构</span>
        <h3>当前主要由什么污染物主导？</h3>
        <p>统计 60 城的首要污染物，并同时给出对应城市的平均 AQI。</p>
      </header>
      <div ref="pollutantEl" class="side-chart pollutant-chart"></div>
    </article>
  </section>
</template>

<style scoped>
.insight-deck {
  display: grid;
  grid-template-columns: minmax(0, 1.72fr) minmax(360px, .9fr);
  grid-template-rows: 1fr 1fr;
  gap: 14px;
}
.insight-deck article {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
  box-shadow: 0 10px 30px rgba(24, 41, 34, .045);
}
.matrix-card {
  grid-row: 1 / 3;
  min-height: 600px;
}
.insight-deck header {
  min-height: 100px;
  padding: 18px 20px 12px;
}
/* Plain secondary label — no all-caps tracking, which is template chrome
   competing with the conclusion. */
.card-label {
  display: block;
  margin-bottom: 5px;
  color: var(--muted);
  font-size: var(--fs-label);
  font-weight: var(--fw-strong);
}
.insight-deck h3 {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-sub);
  font-weight: var(--fw-display);
  letter-spacing: var(--track-title);
}
.insight-deck p {
  max-width: 58ch;
  margin: 6px 0 0;
  color: var(--muted);
  font-size: var(--fs-label);
  line-height: 1.6;
}
.matrix-card header {
  display: flex;
  justify-content: space-between;
  align-items: start;
  gap: 24px;
}
.matrix-tools {
  flex: 0 0 auto;
  display: grid;
  justify-items: end;
  gap: 10px;
}
.matrix-summary {
  display: grid;
  gap: 4px;
  padding-top: 2px;
  color: var(--muted);
  font-size: var(--fs-label);
  text-align: right;
}
.matrix-summary b {
  display: inline-block;
  min-width: 26px;
  color: var(--ink);
  font-size: 16px;
}
.table-toggle {
  min-height: 34px;
  padding: 0 14px;
  border: 1px solid var(--hairline-strong);
  border-radius: var(--radius-pill);
  background: var(--sheet-soft);
  color: var(--ink-soft);
  font-size: var(--fs-label);
  font-weight: var(--fw-strong);
  cursor: pointer;
}
.table-toggle:hover { background: var(--soft); }
.table-toggle[aria-pressed="true"] {
  background: var(--ink);
  border-color: var(--ink);
  color: #fff;
}

.matrix-chart {
  width: 100%;
  height: 492px;
}

.matrix-table-wrap {
  max-height: 492px;
  overflow: auto;
  border-top: 1px solid var(--hairline-soft);
}
.matrix-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-label);
}
.matrix-table th,
.matrix-table td {
  padding: 9px 12px;
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid var(--hairline-soft);
}
.matrix-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--sheet-soft);
  color: var(--muted);
  font-weight: var(--fw-strong);
}
.matrix-table tbody th {
  color: var(--ink);
  font-weight: var(--fw-strong);
}
.matrix-table td {
  color: var(--ink-soft);
}
/* Text carries the direction; the colour is the redundant channel. */
.change-cell {
  font-weight: var(--fw-strong);
}
.change-word {
  margin-left: 5px;
  color: var(--muted);
}
.level-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--ink);
  font-weight: var(--fw-strong);
}
.level-cell i {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.side-card {
  min-height: 293px;
}
.side-chart {
  width: 100%;
  height: 190px;
}
.pollutant-chart {
  height: 188px;
}

@media (max-width: 1120px) {
  .insight-deck {
    grid-template-columns: 1fr;
    grid-template-rows: auto;
  }
  .matrix-card {
    grid-row: auto;
    min-height: 560px;
  }
  .matrix-chart { height: 450px; }
  .side-chart { height: 250px; }
}
@media (max-width: 700px) {
  .insight-deck { gap: 12px; }
  .matrix-card { min-height: 520px; }
  .matrix-card header { display: block; }
  .matrix-tools {
    margin-top: 12px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: start;
    gap: 10px 14px;
  }
  .matrix-summary {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 14px;
    text-align: left;
  }
  .matrix-chart { height: 385px; }
  .insight-deck h3 { font-size: 16px; }
}
</style>
