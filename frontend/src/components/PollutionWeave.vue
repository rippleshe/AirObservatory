<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { chartTheme, init, token, type ECharts } from "../lib/charts";
import { useInView } from "../composables/useInView";

/* Charts stay blank until the reader scrolls to them: the first paint is
   the animated entrance, never a show that already ended. */
const shell = ref<HTMLElement | null>(null);
const inView = useInView(shell);
import { PM25_BANDS, pm25Color } from "../lib/palette";

type NationalSeriesResponse = components["schemas"]["NationalSeriesResponse"];
type NationalCity = components["schemas"]["NationalCity"];

const props = defineProps<{
  series: NationalSeriesResponse | undefined;
  roster: NationalCity[];
}>();

const el = ref<HTMLDivElement | null>(null);
const showTable = ref(false);
let chart: ECharts | null = null;
let observer: ResizeObserver | null = null;

const EXCEED = 75;

/* Rows are the same 31 provincial representatives as the band, the map and the
   matrix, so every mark on the national layer describes one set. Order is
   latitude, north first: a regional episode then reads as a band sweeping down
   the loom instead of as an arbitrary pile. */
const rows = computed(() => {
  const roster = new Map(props.roster.map((city) => [city.location_id, city]));
  return (props.series?.cities ?? [])
    .filter((city) => roster.has(city.location_id))
    .map((city) => ({
      ...city,
      province: roster.get(city.location_id)?.province ?? city.province,
    }))
    /* ECharts category axes draw index 0 at the bottom, so ascending latitude
       puts north at the top of the loom — reading top-down is 北→南. */
    .sort((a, b) => a.lat - b.lat);
});

const times = computed(() => props.series?.times ?? []);

function timeLabel(iso: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso));
}

function dayLabel(iso: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
  }).format(new Date(iso));
}

/* The loom's own conclusion: the hour when the most representatives sat at or
   above 75 µg/m³ at once. Numbers first, then the state of the fabric. */
const headline = computed(() => {
  const ts = times.value;
  const rs = rows.value;
  if (!ts.length || !rs.length) return "近 30 天逐小时时空演变";
  let best = -1;
  let bestAt = 0;
  ts.forEach((_, index) => {
    const count = rs.reduce(
      (sum, row) => sum + ((row.values[index] ?? 0) >= EXCEED ? 1 : 0),
      0,
    );
    if (count > best) {
      best = count;
      bestAt = index;
    }
  });
  if (best <= 0) return `${rs.length} 省全时段低于 75 µg/m³`;
  return `${dayLabel(ts[bestAt])} ${String(new Date(ts[bestAt]).getHours()).padStart(2, "0")}:00 · 峰值高位集中（${best} 省达标警戒）`;
});

const peakStats = computed(() =>
  rows.value.map((row) => {
    let peak = -Infinity;
    let peakAt: string | null = null;
    let exceedHours = 0;
    let sum = 0;
    let count = 0;
    row.values.forEach((value, index) => {
      if (value == null) return;
      sum += value;
      count += 1;
      if (value >= EXCEED) exceedHours += 1;
      if (value > peak) {
        peak = value;
        peakAt = times.value[index] ?? null;
      }
    });
    return {
      location_id: row.location_id,
      name: row.name,
      province: row.province,
      mean: count ? sum / count : null,
      peak: count ? peak : null,
      peakAt,
      exceedHours,
    };
  }),
);

function render() {
  if (!inView.value) return;
  if (!chart) return;
  const ts = times.value;
  const rs = rows.value;
  if (!ts.length || !rs.length) {
    chart.clear();
    return;
  }

  const surface = token("--sheet", chartTheme().surface);
  const hairline = token("--hairline-soft", chartTheme().splitLine);
  const inkSoft = token("--ink-soft", chartTheme().inkSoft);

  const data: [number, number, number][] = [];
  rs.forEach((row, y) => {
    row.values.forEach((value, x) => {
      if (value == null) return;
      data.push([x, y, value]);
    });
  });

  chart.setOption(
    {
      animation: true,
      animationDuration: 420,
      animationDurationUpdate: 240,
      grid: { left: 64, right: 14, top: 10, bottom: 34 },
      tooltip: {
        confine: true,
        backgroundColor: "rgba(255,255,255,.985)",
        borderColor: chartTheme().axisLine,
        padding: [9, 11],
        textStyle: { color: chartTheme().ink, fontSize: 13 },
        formatter(params: any) {
          const p = Array.isArray(params) ? params[0] : params;
          const [x, y, value] = p.value as [number, number, number];
          const row = rs[y];
          return `${row.name} · ${timeLabel(ts[x])}<br/><b>${Number(value).toFixed(1)}</b> µg/m³`;
        },
      },
      xAxis: {
        type: "category",
        /* Day labels live in the category data itself: an all-empty data array
           with a formatter-only label never painted an axis label here. */
        data: ts.map((time, index) => (index % 24 === 12 ? dayLabel(time) : "")),
        axisLine: { lineStyle: { color: hairline } },
        axisTick: { show: false },
        axisLabel: {
          interval: 0,
          hideOverlap: true,
          color: inkSoft,
          fontSize: 12,
        },
        splitLine: {
          show: true,
          interval: 23,
          lineStyle: { color: surface, width: 1.2 },
        },
      },
      yAxis: {
        type: "category",
        data: rs.map((row) => row.province || row.name),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: inkSoft, fontSize: 12 },
        splitLine: { show: false },
      },
      visualMap: {
        show: false,
        min: 0,
        max: 160,
        inRange: {
          color: [
            PM25_BANDS[0][1],
            PM25_BANDS[1][1],
            PM25_BANDS[2][1],
            PM25_BANDS[3][1],
            PM25_BANDS[4][1],
          ],
        },
      },
      series: [
        {
          type: "heatmap",
          data,
          itemStyle: { borderWidth: 0, borderColor: surface },
          emphasis: {
            itemStyle: {
              borderColor: token("--ink", chartTheme().ink),
              borderWidth: 1.5,
            },
          },
          progressive: 2000,
        },
      ],
    },
    true,
  );
}

onMounted(() => {
  if (!el.value) return;
  chart = init(el.value, undefined, { renderer: "canvas" });
  observer = new ResizeObserver(() => chart?.resize());
  observer.observe(el.value);
  render();
});

watch(() => [props.series, props.roster], render, { deep: true });
watch(inView, () => render());

onBeforeUnmount(() => {
  observer?.disconnect();
  chart?.dispose();
});

defineExpose({ headline, peakStats, pm25Color });
</script>

<template>
  <article ref="shell" class="weave-card">
    <header class="weave-header">
      <h2 class="display-face">{{ headline }}</h2>
      <button
        type="button"
        class="table-toggle"
        :aria-pressed="showTable"
        @click="showTable = !showTable"
      >
        {{ showTable ? "看图" : "看数据" }}
      </button>
    </header>

    <div v-show="!showTable" ref="el" class="weave-stage"></div>

    <div v-show="showTable" class="weave-table-wrap">
      <table class="weave-table">
        <caption class="sr-only">
          31 省代表城市近 30 天逐小时 PM2.5 的汇总读数：均值、峰值与越过 75 µg/m³ 的小时数。
        </caption>
        <thead>
          <tr>
            <th scope="col">省</th>
            <th scope="col">代表城市</th>
            <th scope="col">30 天均值</th>
            <th scope="col">峰值</th>
            <th scope="col">峰值时刻</th>
            <th scope="col">≥75 小时数</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in peakStats" :key="row.location_id">
            <th scope="row">{{ row.province || "—" }}</th>
            <td>{{ row.name }}</td>
            <td class="data-mono">{{ row.mean?.toFixed(1) ?? "—" }}</td>
            <td class="data-mono">{{ row.peak?.toFixed(1) ?? "—" }}</td>
            <td>{{ row.peakAt ? timeLabel(row.peakAt) : "—" }}</td>
            <td class="data-mono">{{ row.exceedHours }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer class="weave-key" aria-label="织物图例">
      <span v-for="([label, color]) in PM25_BANDS" :key="label">
        <i :style="{ background: color }"></i>{{ label }}
      </span>
      <span class="key-rule">白线为日界</span>
    </footer>
  </article>
</template>

<style scoped>
.weave-card {
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
  box-shadow: var(--shadow-sm);
  padding: 18px 22px 14px;
  transition: border-color var(--duration-fast) ease;
}
.weave-card:hover {
  border-color: var(--hairline-strong);
}

.weave-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.weave-header h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: var(--track-title);
  color: var(--ink);
}

.table-toggle {
  flex: none;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-pill);
  background: var(--sheet);
  color: var(--muted);
  font-size: 11px;
  font-weight: 500;
  padding: 4px 12px;
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
  color: #ffffff;
  font-weight: 600;
}

.weave-stage {
  height: 552px;
  width: 100%;
}

.weave-table-wrap {
  max-height: 552px;
  overflow: auto;
}

.weave-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-data);
}

.weave-table th,
.weave-table td {
  text-align: left;
  padding: 7px 10px;
  border-bottom: 1px solid var(--hairline-soft);
  white-space: nowrap;
}

.weave-table thead th {
  position: sticky;
  top: 0;
  background: var(--sheet);
  color: var(--muted);
  font-weight: var(--fw-strong);
  font-size: var(--fs-label);
}

.weave-key {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 14px;
  margin-top: 10px;
  font-size: var(--fs-label);
  color: var(--muted);
}

.weave-key i {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 5px;
}

.key-rule {
  color: var(--faint);
}
</style>
