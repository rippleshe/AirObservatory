<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { chartTheme, init, token, type ECharts } from "../lib/charts";
import { useInView } from "../composables/useInView";
import { VARIABLE_BANDS } from "../lib/palette";
import { gsap, prefersReducedMotion } from "../lib/motion";

/* Charts stay blank until the reader scrolls to them: the first paint is
   the animated entrance, never a show that already ended. */
const shell = ref<HTMLElement | null>(null);
const inView = useInView(shell);

type NationalSeriesResponse = components["schemas"]["NationalSeriesResponse"];
type NationalCity = components["schemas"]["NationalCity"];

const props = defineProps<{
  /* One series per weavable variable — the view already fetches them all;
     switching never waits on the network. */
  sources: Record<string, NationalSeriesResponse | undefined>;
  roster: NationalCity[];
  focusId?: number | null;
}>();

const active = ref<string>("pm25");
const series = computed(() => props.sources[active.value]);
const band = computed(() => VARIABLE_BANDS[active.value] ?? VARIABLE_BANDS.pm25);

const el = ref<HTMLDivElement | null>(null);
const showTable = ref(false);
let chart: ECharts | null = null;
let observer: ResizeObserver | null = null;

/* Rows are the same 31 provincial representatives as the band, the map and the
   matrix, so every mark on the national layer describes one set. Order is
   latitude, north first: a regional episode then reads as a band sweeping down
   the loom instead of as an arbitrary pile. */
const rows = computed(() => {
  const roster = new Map(props.roster.map((city) => [city.location_id, city]));
  return (series.value?.cities ?? [])
    .filter((city) => roster.has(city.location_id))
    .map((city) => ({
      ...city,
      province: roster.get(city.location_id)?.province ?? city.province,
    }))
    /* ECharts category axes draw index 0 at the bottom, so ascending latitude
       puts north at the top of the loom — reading top-down is 北→南. */
    .sort((a, b) => a.lat - b.lat);
});

const times = computed(() => series.value?.times ?? []);

/* The focused province keeps its ink label while the rest of the loom reads
   normally — a quiet anchor, not a strobe. */
const focusLabel = computed(() => {
  if (props.focusId == null) return null;
  const row = rows.value.find((city) => city.location_id === props.focusId);
  return row ? row.province || row.name : null;
});

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

const unitSuffix = computed(() => (band.value.unit ? ` ${band.value.unit}` : ""));

/* The loom's own conclusion: the hour when the most representatives sat at or
   above the variable's threshold at once. Numbers first, then the fabric. */
const headline = computed(() => {
  const ts = times.value;
  const rs = rows.value;
  const exceed = band.value.exceed;
  if (!ts.length || !rs.length) return "近 30 天逐小时时空演变";
  let best = -1;
  let bestAt = 0;
  ts.forEach((_, index) => {
    const count = rs.reduce(
      (sum, row) => sum + ((row.values[index] ?? 0) >= exceed ? 1 : 0),
      0,
    );
    if (count > best) {
      best = count;
      bestAt = index;
    }
  });
  if (best <= 0) return `${rs.length} 省全时段低于 ${exceed}${unitSuffix.value}`;
  return `${dayLabel(ts[bestAt]!)} ${String(new Date(ts[bestAt]!).getHours()).padStart(2, "0")}:00 · 峰值时刻（${best} 省超 ${exceed}）`;
});

/* One ceiling per variable: at least wide enough for the threshold plus
   headroom, else the data's own p98 — a static 160 µg/m³ would wash CO into
   the first band and clip O₃ spikes into one flat cell. */
const vmax = computed(() => {
  const all: number[] = [];
  rows.value.forEach((row) =>
    row.values.forEach((value) => {
      if (value != null) all.push(value);
    }),
  );
  all.sort((a, b) => a - b);
  const p98 = all[Math.floor(all.length * 0.98)] ?? 0;
  return Math.max(
    Math.ceil((band.value.exceed * 1.15) / 10) * 10,
    Math.ceil(p98 / 10) * 10,
  );
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
      if (value >= band.value.exceed) exceedHours += 1;
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
          return `${row.name} · ${timeLabel(ts[x]!)}<br/><b>${Number(value).toFixed(1)}</b>${unitSuffix.value}`;
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
        axisLabel: {
          color: inkSoft,
          fontSize: 12,
          formatter: (value: string) =>
            focusLabel.value && value === focusLabel.value ? `{f|${value}}` : value,
          rich: {
            f: { color: token("--ink", chartTheme().ink), fontWeight: 700 },
          },
        },
        splitLine: { show: false },
      },
      visualMap: {
        show: false,
        min: 0,
        max: vmax.value,
        inRange: {
          color: band.value.bands.map(([, color]) => color),
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

watch(() => [series.value, props.roster, props.focusId], render, { deep: true });
watch(inView, () => render());

/* A variable swap repaints every cell: dip the loom so the exchange reads as
   one deliberate dissolve instead of a hard cut. */
watch(active, () => {
  render();
  if (!el.value || prefersReducedMotion()) return;
  gsap.fromTo(
    el.value,
    { autoAlpha: 0.3 },
    { autoAlpha: 1, duration: 0.5, ease: "power2.out" },
  );
});

onBeforeUnmount(() => {
  observer?.disconnect();
  chart?.dispose();
});

defineExpose({ headline, peakStats });
</script>

<template>
  <article ref="shell" class="weave">
    <header class="weave-header">
      <div class="var-switch" role="tablist" aria-label="织物变量">
        <button
          v-for="(vb, id) in VARIABLE_BANDS"
          :key="id"
          type="button"
          :class="{ active: active === id }"
          @click="active = String(id)"
        >
          {{ vb.label }}
        </button>
      </div>
      <span class="weave-meta">{{ headline }}</span>
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
        <thead>
          <tr>
            <th scope="col">省</th>
            <th scope="col">代表城市</th>
            <th scope="col">均值{{ band.unit }}</th>
            <th scope="col">峰值{{ band.unit }}</th>
            <th scope="col">峰值时刻</th>
            <th scope="col">≥{{ band.exceed }} 小时</th>
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
      <span v-for="([label, color]) in band.bands" :key="label">
        <i :style="{ background: color }"></i>{{ label }}
      </span>
      <span class="key-rule">白线=日界</span>
    </footer>
  </article>
</template>

<style scoped>
.weave {
  min-width: 0;
}

.weave-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
}

.var-switch {
  flex: none;
  display: inline-flex;
  padding: 2px;
  gap: 2px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-pill);
  background: var(--sheet);
}

.var-switch button {
  border: 0;
  border-radius: var(--radius-pill);
  background: transparent;
  color: var(--muted);
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11px;
  font-weight: 500;
  padding: 3px 10px;
  cursor: pointer;
  transition: all var(--duration-fast) ease;
  white-space: nowrap;
}

.var-switch button:hover {
  color: var(--ink);
  background: var(--sheet-soft);
}

.var-switch button.active {
  background: var(--ink);
  color: #ffffff;
  font-weight: 600;
}

.weave-meta {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: right;
  color: var(--muted);
  font-size: var(--fs-label);
  font-variant-numeric: tabular-nums;
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
