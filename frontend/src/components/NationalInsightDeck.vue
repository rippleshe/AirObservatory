<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { init, type ECharts } from "../lib/charts";
import {
  AQI_LEVEL_COLORS,
  aqiColor,
  changeColor,
  changeState,
} from "../lib/palette";
import type { NationalCity, RegionRow } from "../lib/provinces";

const props = defineProps<{
  /* One city per province. Every chart on this deck plots this set. */
  cities: NationalCity[];
  /* All sixty cities — the table twin only, never a chart. */
  roster: NationalCity[];
  /* Region aggregates the parent already computed over `cities`. */
  regions: RegionRow[];
}>();

const matrixEl = ref<HTMLDivElement | null>(null);
const regionEl = ref<HTMLDivElement | null>(null);
const pollutantEl = ref<HTMLDivElement | null>(null);
const charts: ECharts[] = [];
let observer: ResizeObserver | null = null;
let frame = 0;
let lastRoomy = true;

/* The matrix labels only a handful of provinces; the rest stay hover-gated.
   This toggle exposes every value in a table twin. */
const showTable = ref(false);

const levelOrder = ["优", "良", "轻度污染", "中度污染", "重度污染", "严重污染"];

const provinceTotal = computed(() => props.cities.length);

const plottedCities = computed(() =>
  props.cities.filter(
    (city) => city.pm25 != null && city.pm25_change_24h != null && city.china_aqi != null,
  ),
);

/* The table twin carries the whole roster, worst first, missing values last:
   a city with no reading is a gap to show, not a row to drop. */
const rosterCities = computed(() =>
  [...props.roster].sort((a, b) => (b.china_aqi ?? -1) - (a.china_aqi ?? -1)),
);

/* The reference line is the mean of the set the matrix plots, so the quadrant
   the title counts is the quadrant the reader sees. */
const provinceMean = computed(() => {
  const values = plottedCities.value.map((city) => city.pm25 as number);
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
});

const aboveMean = computed(() =>
  plottedCities.value.filter((city) => (city.pm25 ?? 0) > provinceMean.value),
);

const highAndRising = computed(
  () => aboveMean.value.filter((city) => (city.pm25_change_24h ?? 0) > 0).length,
);
const highButImproving = computed(
  () => aboveMean.value.filter((city) => (city.pm25_change_24h ?? 0) < 0).length,
);

const matrixTitle = computed(() => {
  if (!plottedCities.value.length) return "暂无各省 PM2.5 与 24h 变化数据";
  if (!aboveMean.value.length) return "没有省高于均值";
  const parts: string[] = [];
  if (highAndRising.value) parts.push(`高且上升 ${highAndRising.value} 省`);
  if (highButImproving.value) parts.push(`高但改善 ${highButImproving.value} 省`);
  if (!parts.length) return `${aboveMean.value.length} 省高于均值，24h 变化都不明显`;
  return parts.join(" · ");
});

/* ── dumbbell: before → after per province ────────────────────────────
   The matrix already plots 24h change as a position. The dumbbell reads the
   same fact as a *transition* — how far each province travelled — which is a
   different question and a form the rest of the page does not use. */
const movers = computed(() => {
  return plottedCities.value
    .map((city) => {
      const now = city.pm25 as number;
      const delta = city.pm25_change_24h as number;
      return {
        id: city.location_id,
        name: city.name,
        before: now - delta,
        now,
        delta,
        state: changeState(delta),
        level: city.china_aqi_level,
      };
    })
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
    .slice(0, 11);
});

const moverTitle = computed(() => {
  const top = movers.value[0];
  if (!top) return "暂无各省 24h 变化数据";
  return `${top.name} 24h ${top.state.label} ${Math.abs(top.delta).toFixed(1)} µg/m³，${
    plottedCities.value.length
  } 省中位移最大`;
});

const moverScale = computed(() => {
  const values = movers.value.flatMap((row) => [row.before, row.now]);
  const max = values.length ? Math.max(...values) : 1;
  return { min: 0, max: Math.max(max * 1.06, 1) };
});

function moverPct(value: number) {
  const { min, max } = moverScale.value;
  return ((value - min) / (max - min)) * 100;
}

const regionRanking = computed(() =>
  [...props.regions].sort((a, b) => (b.mean_pm25 ?? 0) - (a.mean_pm25 ?? 0)),
);

const regionTitle = computed(() => {
  const top = regionRanking.value[0];
  if (!top) return "暂无区域等级构成数据";
  const rows = props.cities.filter((city) => city.region === top.region);
  if (!rows.length) return `PM2.5 均值最高：${top.region}`;
  const good = rows.filter(
    (city) => city.china_aqi_level === "优" || city.china_aqi_level === "良",
  ).length;
  return `${top.region} ${rows.length} 省中 ${good} 省优良`;
});

const pollutantRows = computed(() => {
  const buckets = new Map<string, { count: number; aqis: number[]; provinces: string[] }>();
  for (const city of props.cities) {
    const primary = city.primary_pollutants?.[0];
    if (!primary) continue;
    const bucket = buckets.get(primary) ?? { count: 0, aqis: [], provinces: [] };
    bucket.count += 1;
    bucket.provinces.push(city.name);
    if (city.china_aqi != null) bucket.aqis.push(city.china_aqi);
    buckets.set(primary, bucket);
  }
  return [...buckets.entries()]
    .map(([name, value]) => ({
      name,
      count: value.count,
      provinces: value.provinces,
      meanAqi: value.aqis.length
        ? value.aqis.reduce((sum, item) => sum + item, 0) / value.aqis.length
        : null,
    }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
});

const pollutantTitle = computed(() => {
  const top = pollutantRows.value[0];
  if (!top) return "暂无首要污染物数据";
  const total = provinceTotal.value;
  if (top.count >= total) return `${total} 省都由 ${top.name} 主导`;
  return `${total} 省中 ${top.count} 省由 ${top.name} 主导`;
});

/* An AQI at or below 50 reports no primary pollutant, so the rows do not sum
   to the province count. The invisible description closes that gap. */
const pollutantDescription = computed(() => {
  const rows = pollutantRows.value;
  if (!rows.length) return "各省首要污染物分布：当前没有可用的首要污染物数据。";
  const listed = rows.map((item) => `${item.count} 省由 ${item.name} 主导`).join("，");
  const rest = provinceTotal.value - rows.reduce((sum, item) => sum + item.count, 0);
  const tail = rest > 0 ? `，其余 ${rest} 省 AQI 不高于 50 没有首要污染物` : "";
  return `${provinceTotal.value} 省首要污染物分布：${listed}${tail}。`;
});

/* The panel grows with its rows instead of leaving the surplus height blank. */
const pollutantChartHeight = computed(
  () => Math.max(pollutantRows.value.length, 1) * 46 + 56,
);

function tooltipBase() {
  return {
    backgroundColor: "rgba(255,255,255,.985)",
    borderColor: "#8fa39b",
    borderWidth: 1,
    padding: [11, 13],
    textStyle: { color: "#0b1512", fontSize: 13, lineHeight: 21 },
    extraCssText: "box-shadow:0 12px 32px rgba(11,21,18,.14);border-radius:8px;",
  };
}

const WIDE_PLOT = 520;

function roomyPlot() {
  return (pollutantEl.value?.clientWidth ?? 640) >= WIDE_PLOT;
}

/* Names travel with the row only while the pollutant is the exception; past a
   handful of provinces the list stops being a reading. The ellipsis is inside
   the budget so a truncated note cannot overrun the gutter. */
function noteFor(row: { count: number; provinces: string[] }, budget: number) {
  if (row.count > 4) return "";
  const full = row.provinces.join("、");
  if (full.length <= budget) return full;
  let text = "";
  for (const name of row.provinces) {
    const next = text ? `${text}、${name}` : name;
    if (next.length > budget - 1) break;
    text = next;
  }
  return text ? `${text}…` : "";
}

function nameList(names: string[], limit: number) {
  if (names.length <= limit) return names.join("、");
  return `${names.slice(0, limit).join("、")}…`;
}

/* A count axis is only readable on whole provinces: pick the step first and
   let the axis end on a multiple of it, so the last tick is not a stub. The
   spare 35% is what the count labels and the mean AQI column sit in. */
function countAxis(maxCount: number) {
  const top = Math.max(maxCount, 1) * 1.35;
  const rough = top / 5;
  const step = rough <= 1 ? 1 : rough <= 2 ? 2 : rough <= 5 ? 5 : rough <= 10 ? 10 : 20;
  return { max: Math.max(step, Math.ceil(top / step) * step), interval: step };
}

/* ECharts draws an over-wide axis label straight off the canvas instead of
   trimming it, so the note budget has to follow the gutter: 12px per province
   name glyph, plus the gap between the label block and the axis line. */
function noteBudgetFor(gutter: number) {
  return Math.max(1, Math.floor((gutter - 12) / 12));
}

function render(animate = true) {
  if (charts.length !== 3) return;
  const [matrixChart, regionChart, pollutantChart] = charts;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const motion = animate && !reducedMotion;
  const cities = plottedCities.value;
  const axisInk = "#64748b";
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
  const maxPm25 = cities.length ? Math.max(...cities.map((city) => city.pm25 ?? 0)) : 1;
  const maxRise = cities.length
    ? Math.max(...cities.map((city) => city.pm25_change_24h ?? 0))
    : 1;
  matrixChart.setOption(
    {
      animation: motion,
      aria: {
        enabled: true,
        description:
          "各省代表城市的 PM2.5 与 24h 变化矩阵。越往右表示当前 PM2.5 越高，越往上表示 24h 上升越明显。",
      },
      grid: { left: 60, right: 30, top: 34, bottom: 56 },
      tooltip: {
        ...tooltipBase(),
        trigger: "item",
        formatter(params: any) {
          const city = params.data.raw as NationalCity;
          const state = changeState(city.pm25_change_24h);
          const primary = city.primary_pollutants?.join(" / ") || "暂无";
          return [
            `<b>${city.name}</b> · ${city.province ?? city.region}`,
            `PM2.5 <b>${city.pm25?.toFixed(1)}</b> µg/m³`,
            `24h ${state.arrow} <b>${state.label}</b> ${Math.abs(city.pm25_change_24h ?? 0).toFixed(1)} µg/m³`,
            `<b>${city.china_aqi_level ?? "—"}</b> · AQI ${city.china_aqi ?? "—"}`,
            `首要污染物 ${primary}`,
          ].join("<br/>");
        },
      },
      xAxis: {
        name: "当前 PM2.5",
        nameLocation: "middle",
        nameGap: 34,
        nameTextStyle: { color: "#243530", fontSize: axisSize, fontWeight: 650 },
        type: "value",
        min: 0,
        axisLine: { lineStyle: { color: "#a7b8b0" } },
        axisTick: { show: false },
        axisLabel: { color: axisInk, fontSize: axisSize },
        splitLine: { lineStyle: { color: "#c3d1cb" } },
      },
      yAxis: {
        name: "24h 变化",
        nameGap: 40,
        nameTextStyle: { color: "#243530", fontSize: axisSize, fontWeight: 650 },
        type: "value",
        axisLine: { lineStyle: { color: "#a7b8b0" } },
        axisTick: { show: false },
        axisLabel: {
          color: axisInk,
          fontSize: axisSize,
          formatter: (value: number) => (value > 0 ? `+${value}` : String(value)),
        },
        splitLine: { lineStyle: { color: "#c3d1cb" } },
      },
      series: [
        {
          type: "scatter",
          data: cities.map((city) => ({
            value: [city.pm25, city.pm25_change_24h, city.china_aqi],
            raw: city,
            symbolSize: 13 + 15 * ((city.china_aqi ?? 0) / maxAqi),
            itemStyle: {
              color: aqiColor(city.china_aqi_level),
              borderColor: "#fbfcfb",
              borderWidth: 2,
              opacity: 1,
            },
            label: {
              show: important.has(city.location_id),
              formatter: city.name,
            },
          })),
          label: {
            position: "top",
            distance: 6,
            color: "#0b1512",
            fontSize: 12,
            fontWeight: 700,
            textBorderColor: "#fbfcfb",
            textBorderWidth: 3,
          },
          emphasis: {
            scale: 1.2,
            itemStyle: { borderColor: "#0b1512", borderWidth: 2.2 },
            label: {
              show: true,
              color: "#0b1512",
              fontSize: 13,
              fontWeight: 700,
              backgroundColor: "rgba(255,255,255,.95)",
              borderRadius: 5,
              padding: [4, 6],
              textBorderWidth: 0,
            },
          },
          // Quadrant readings live ON the plot instead of in a caption under
          // it — the chart annotates itself.
          markLine: {
            silent: true,
            symbol: ["none", "none"],
            lineStyle: { color: "#7f968c", width: 1 },
            label: {
              color: "#566a61",
              fontSize: 12,
              backgroundColor: "rgba(251,252,251,.92)",
              padding: [2, 5],
            },
            data: [
              {
                xAxis: provinceMean.value,
                label: { formatter: `${cities.length} 省均值`, position: "insideEndTop" },
              },
              {
                yAxis: 0,
                label: { formatter: "此线以上仍在变差", position: "insideStartTop" },
              },
            ],
          },
          markArea: {
            silent: true,
            itemStyle: { color: "rgba(163,95,34,.07)" },
            label: { show: false },
            data: [
              [
                { xAxis: provinceMean.value, yAxis: 0 },
                { xAxis: maxPm25 * 1.05, yAxis: maxRise * 1.08 },
              ],
            ],
          },
        },
      ],
    },
    true,
  );

  const sortedRegions = regionRanking.value;
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
      animation: motion,
      aria: { enabled: true, description: "各区域省级 AQI 等级构成。" },
      grid: { left: 84, right: 20, top: 16, bottom: 30 },
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
            .map((row: any) => `${row.marker}${row.seriesName} <b>${row.value}</b> 省`)
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
        splitLine: { lineStyle: { color: "#c3d1cb" } },
      },
      yAxis: {
        type: "category",
        inverse: true,
        data: sortedRegions.map((item) => item.region),
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: {
          color: "#243530",
          fontSize: axisSize,
          fontWeight: 700,
        },
      },
      series: levelOrder.map((level) => ({
        name: level,
        type: "bar",
        stack: "levels",
        barWidth: 18,
        data: sortedRegions.map((region) => regionCounts.get(region.region)?.[level] ?? 0),
        // 2px surface gaps between stack segments — separation by whitespace,
        // not by a stroke drawn around each segment.
        itemStyle: { color: AQI_LEVEL_COLORS[level], borderColor: "#fbfcfb", borderWidth: 2 },
        emphasis: { focus: "series" },
      })),
    },
    true,
  );

  /* ── lollipop: a stem from zero and a dot at the count ───────────────
     The stem is the ranking, the dot is the reading, the count sits at the
     dot and the mean AQI closes the row as a second, separate figure. */
  const rows = pollutantRows.value;
  const axis = countAxis(Math.max(...rows.map((item) => item.count), 1));
  const roomy = roomyPlot();
  const gutter = roomy ? 132 : 96;
  const noteBudget = noteBudgetFor(gutter);

  pollutantChart.setOption(
    {
      animation: motion,
      aria: { enabled: true, description: pollutantDescription.value },
      grid: {
        left: gutter,
        right: roomy ? 132 : 24,
        top: 12,
        bottom: 46,
      },
      tooltip: {
        ...tooltipBase(),
        trigger: "item",
        formatter(params: any) {
          const item = rows[params.dataIndex];
          if (!item) return "";
          const aqi =
            item.meanAqi != null
              ? `平均 AQI <b>${item.meanAqi.toFixed(0)}</b>`
              : "平均 AQI —";
          return [
            `<b>${item.name}</b>`,
            `主导 <b>${item.count}</b> 省 · ${aqi}`,
            nameList(item.provinces, 8),
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "value",
        min: 0,
        max: axis.max,
        interval: axis.interval,
        name: "主导省数",
        nameLocation: "middle",
        nameGap: 24,
        nameTextStyle: { color: "#243530", fontSize: axisSize, fontWeight: 650 },
        axisLine: { lineStyle: { color: "#a7b8b0" } },
        axisTick: { show: false },
        axisLabel: { color: axisInk, fontSize: axisSize },
        splitLine: { lineStyle: { color: "#c3d1cb" } },
      },
      yAxis: {
        type: "category",
        inverse: true,
        data: rows.map((item) => item.name),
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: {
          color: "#243530",
          fontSize: 13,
          fontWeight: 700,
          formatter: (name: string) => {
            const row = rows.find((item) => item.name === name);
            const note = row ? noteFor(row, noteBudget) : "";
            return note ? `{name|${name}}\n{note|${note}}` : name;
          },
          rich: {
            name: { color: "#243530", fontSize: 13, fontWeight: 700, lineHeight: 17 },
            note: { color: "#566a61", fontSize: 12, fontWeight: 400, lineHeight: 16 },
          },
        },
      },
      series: [
        {
          type: "bar",
          barWidth: 2,
          silent: true,
          data: rows.map((item) => [item.count, item.name]),
          itemStyle: { color: "#a7b8b0", borderRadius: [0, 1, 1, 0] },
        },
        {
          type: "scatter",
          symbolSize: 13,
          data: rows.map((item) => [item.count, item.name]),
          itemStyle: {
            color: "#2f6a82",
            borderColor: "#fbfcfb",
            borderWidth: 2,
          },
          label: {
            show: true,
            position: "right",
            distance: 8,
            color: "#0b1512",
            fontSize: 12,
            fontWeight: 700,
            formatter: (params: any) => `${rows[params.dataIndex]?.count ?? "—"} 省`,
          },
        },
        {
          // Mean AQI is a different reading from the count, so it gets its own
          // column at the row end rather than sharing the count's label.
          type: "scatter",
          silent: true,
          symbolSize: 0,
          data: roomy ? rows.map((item) => [axis.max, item.name]) : [],
          itemStyle: { color: "transparent" },
          label: {
            show: true,
            position: "right",
            distance: 6,
            color: "#566a61",
            fontSize: 12,
            formatter: (params: any) => {
              const item = rows[params.dataIndex];
              return item?.meanAqi != null ? `平均 AQI ${item.meanAqi.toFixed(0)}` : "平均 AQI —";
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
  lastRoomy = roomyPlot();
  observer = new ResizeObserver(() => {
    charts.forEach((chart) => chart.resize());
    /* The lollipop grid is width-aware: crossing into the narrow layout has to
       rebuild the option, not just rescale it. */
    if (roomyPlot() === lastRoomy) return;
    lastRoomy = roomyPlot();
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => render(false));
  });
  [matrixEl.value, regionEl.value, pollutantEl.value].forEach(
    (el) => el && observer?.observe(el),
  );
  render();
});

watch(() => [props.regions, props.cities], () => render(), { deep: true });

watch(showTable, (visible) => {
  if (!visible) requestAnimationFrame(() => charts.forEach((chart) => chart.resize()));
});

onBeforeUnmount(() => {
  cancelAnimationFrame(frame);
  observer?.disconnect();
  charts.forEach((chart) => chart.dispose());
});
</script>

<template>
  <section class="insight-deck">
    <article class="matrix-card">
      <header>
        <h3 class="display-face">{{ matrixTitle }}</h3>
        <button
          type="button"
          class="table-toggle"
          :aria-pressed="showTable"
          @click="showTable = !showTable"
        >
          {{ showTable ? "看图" : "看数据" }}
        </button>
      </header>

      <div v-show="!showTable" ref="matrixEl" class="matrix-chart"></div>

      <div v-show="showTable" class="matrix-table-wrap">
        <table class="matrix-table">
          <caption class="sr-only">
            全部 {{ rosterCities.length }} 城当前 PM2.5、24h 变化与 AQI 等级；图表为
            {{ cities.length }} 省代表城市。
          </caption>
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
            <tr v-for="city in rosterCities" :key="city.location_id">
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

    <article class="mover-card">
      <header>
        <h3 class="display-face">{{ moverTitle }}</h3>
        <div class="dumbbell-key">
          <span><i class="dot before"></i>24h 前</span>
          <span><i class="dot now"></i>现在</span>
        </div>
      </header>

      <div class="dumbbell">
        <div
          v-for="row in movers"
          :key="row.id"
          class="dumb-row"
          :title="`${row.name}：${row.before.toFixed(1)} → ${row.now.toFixed(1)} µg/m³，${row.state.arrow} ${row.state.label}`"
        >
          <span class="dumb-name">{{ row.name }}</span>
          <div class="dumb-track">
            <i
              class="dumb-stem"
              :style="{
                left: Math.min(moverPct(row.before), moverPct(row.now)) + '%',
                width: Math.abs(moverPct(row.now) - moverPct(row.before)) + '%',
                background: changeColor(row.delta),
              }"
            ></i>
            <i class="dumb-dot before" :style="{ left: moverPct(row.before) + '%' }"></i>
            <i
              class="dumb-dot now"
              :style="{ left: moverPct(row.now) + '%', background: changeColor(row.delta) }"
            ></i>
          </div>
          <span class="dumb-value data-mono">
            {{ row.state.arrow }}{{ row.delta > 0 ? "+" : "" }}{{ row.delta.toFixed(1) }}
          </span>
        </div>
        <div class="dumb-axis">
          <span>0</span>
          <span>{{ Math.round(moverScale.max) }} µg/m³</span>
        </div>
      </div>
    </article>

    <article class="side-card">
      <header>
        <h3 class="display-face">{{ regionTitle }}</h3>
      </header>
      <div ref="regionEl" class="side-chart"></div>
    </article>

    <article class="side-card pollutant-card">
      <header>
        <h3 class="display-face">{{ pollutantTitle }}</h3>
      </header>
      <div
        ref="pollutantEl"
        class="side-chart pollutant-chart"
        :style="{ height: pollutantChartHeight + 'px' }"
      ></div>
    </article>
  </section>
</template>

<style scoped>
.insight-deck {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(320px, 1fr);
  gap: 16px;
}
.insight-deck article {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
  box-shadow: var(--shadow-sm);
  transition: border-color var(--duration-fast) ease;
}
.insight-deck article:hover {
  border-color: var(--hairline-strong);
}
.matrix-card {
  grid-row: 1 / 3;
  min-height: 560px;
  display: flex;
  flex-direction: column;
}
.insight-deck header {
  min-height: 56px;
  padding: 14px 20px 10px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.insight-deck h3 {
  margin: 0;
  color: var(--ink);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: var(--track-title);
}
.table-toggle {
  flex: 0 0 auto;
  min-height: 28px;
  padding: 0 12px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-pill);
  background: var(--sheet);
  color: var(--muted);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-fast) ease;
}
.table-toggle:hover {
  background: var(--sheet-soft);
  color: var(--ink);
}
.table-toggle[aria-pressed="true"] {
  background: var(--ink);
  border-color: var(--ink);
  color: #fff;
  font-weight: 600;
}

.matrix-chart {
  width: 100%;
  flex: 1 1 auto;
  min-height: 512px;
}

.matrix-table-wrap {
  flex: 1 1 auto;
  min-height: 300px;
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

/* ── dumbbell ───────────────────────────────────────────────────────── */
.dumbbell-key {
  display: flex;
  gap: 14px;
  color: var(--muted);
  font-size: var(--fs-label);
}
.dumbbell-key span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}
.dot.before {
  background: var(--sheet);
  border: 2px solid var(--hairline-strong);
}
.dot.now {
  background: var(--ink-soft);
}

.dumbbell {
  padding: 8px 20px 18px;
}
.dumb-row {
  display: grid;
  grid-template-columns: 5.2em minmax(0, 1fr) 3.2em;
  align-items: center;
  gap: 10px;
  min-height: 30px;
}
.dumb-name {
  color: var(--ink);
  font-size: var(--fs-label);
  font-weight: var(--fw-strong);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dumb-track {
  position: relative;
  height: 18px;
}
.dumb-stem {
  position: absolute;
  top: 8px;
  height: 3px;
  border-radius: 2px;
}
.dumb-dot {
  position: absolute;
  top: 4px;
  width: 11px;
  height: 11px;
  margin-left: -5.5px;
  border-radius: 50%;
}
.dumb-dot.before {
  background: var(--sheet);
  border: 2px solid var(--hairline-strong);
}
.dumb-dot.now {
  border: 2px solid var(--sheet);
}
.dumb-value {
  color: var(--muted);
  font-size: var(--fs-label);
  text-align: right;
}
.dumb-axis {
  margin-top: 6px;
  padding-left: 5.2em;
  padding-right: 3.2em;
  display: flex;
  justify-content: space-between;
  color: var(--faint);
  font-size: var(--fs-label);
}

.side-card {
  min-height: 292px;
}
.side-chart {
  width: 100%;
  height: 214px;
}
/* The lollipop row count decides this card's height, so it must not be
   stretched to the region card's. */
.pollutant-card {
  min-height: 0;
}

@media (max-width: 1120px) {
  .insight-deck {
    grid-template-columns: 1fr;
  }
  .matrix-card {
    grid-row: auto;
    min-height: 560px;
  }
  .matrix-chart { height: 470px; }
  .side-chart { height: 250px; }
}
@media (max-width: 700px) {
  .insight-deck { gap: 12px; }
  .matrix-card { min-height: 520px; }
  .matrix-chart { height: 400px; }
  .insight-deck h3 { font-size: 16px; }
  .dumb-row { grid-template-columns: 4.4em minmax(0, 1fr) 3em; }
}
</style>
