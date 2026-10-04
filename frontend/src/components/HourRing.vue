<!-- HourRing — the day's rhythm as a readable clock: one sector per hour,
     radius = 30-day hourly mean, the translucent envelope behind it spans
     the 25–75% band so "always bad at night" separates from "one bad night".
     The peak sector wears an ink reticle. -->
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import type { components } from "../api/schema";
import { gsap } from "../lib/motion";
import { PM25_BANDS, pm25Color } from "../lib/palette";

type SeriesResponse = components["schemas"]["SeriesResponse"];
const props = defineProps<{ series: SeriesResponse | undefined }>();

const showTable = ref(false);
const hover = ref<{ x: number; y: number; label: string; value: number } | null>(null);
const root = ref<SVGSVGElement | null>(null);

const SIZE = 560;
const CENTER = SIZE / 2;
const RING_OUTER = 218;
const RING_INNER = 96;
const HOURS = 24;

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

const dayKeys = computed(() => [
  ...new Set((props.series?.points ?? []).map((point) => dayKey(point.time))),
]);

const grid = computed(() => {
  const days = dayKeys.value;
  const index = new Map(days.map((day, i) => [day, i]));
  const cells: (number | null)[][] = days.map(() => Array<number | null>(HOURS).fill(null));
  for (const point of props.series?.points ?? []) {
    if (point.value == null) continue;
    const day = index.get(dayKey(point.time));
    if (day == null) continue;
    cells[day][new Date(point.time).getHours()] = Number(point.value);
  }
  return cells;
});

const hourColumns = computed(() =>
  Array.from({ length: HOURS }, (_, hour) =>
    grid.value.map((row) => row[hour]).filter((v): v is number => v != null),
  ),
);

const hourMeans = computed(() =>
  hourColumns.value.map((values) =>
    values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null,
  ),
);

function quantile(sorted: number[], q: number): number | null {
  if (!sorted.length) return null;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo]! + (sorted[hi]! - sorted[lo]!) * (pos - lo);
}

const hourBands = computed(() =>
  hourColumns.value.map((values) => {
    if (values.length < 4) return null;
    const sorted = [...values].sort((a, b) => a - b);
    return { p25: quantile(sorted, 0.25)!, p75: quantile(sorted, 0.75)! };
  }),
);

const peakHour = computed(() => {
  let best: number | null = null;
  hourMeans.value.forEach((mean, hour) => {
    if (mean == null) return;
    if (best == null || mean > (hourMeans.value[best] ?? 0)) best = hour;
  });
  return best;
});

const windowCopy = computed(() => {
  const days = dayKeys.value.length;
  return days >= 30 ? "近 30 天" : `近 ${days} 天`;
});

const peakCopy = computed(() => {
  if (peakHour.value == null) return "样本不足";
  return `${hourRange(peakHour.value)} 浓度最高`;
});

const peakRangeCopy = computed(() => {
  const peak = peakHour.value;
  if (peak == null) return "分时均值待生成";
  return `${hourRange(peak)} 均值 ${(hourMeans.value[peak] ?? 0).toFixed(1)} µg/m³`;
});

const hourTable = computed(() =>
  hourMeans.value.map((mean, hour) => {
    const values = grid.value.map((row) => row[hour]).filter((v): v is number => v != null);
    return {
      hour,
      mean,
      min: values.length ? Math.min(...values) : null,
      max: values.length ? Math.max(...values) : null,
      n: values.length,
    };
  }),
);

/* Scale: the band's p75 tops the clock, so normal hours keep headroom. */
const rScale = computed(() => {
  let max = 10;
  for (const band of hourBands.value) if (band) max = Math.max(max, band.p75);
  hourMeans.value.forEach((mean) => {
    if (mean != null) max = Math.max(max, mean);
  });
  return (value: number) => RING_INNER + (Math.max(0, value) / max) * (RING_OUTER - RING_INNER);
});

function sectorPath(hour: number, r0: number, r1: number): string {
  const gap = 0.012;
  const a0 = ((hour / HOURS) * 2 * Math.PI - Math.PI / 2) + gap;
  const a1 = (((hour + 1) / HOURS) * 2 * Math.PI - Math.PI / 2) - gap;
  const p = (angle: number, radius: number): [number, number] => [
    CENTER + radius * Math.cos(angle),
    CENTER + radius * Math.sin(angle),
  ];
  const [x0, y0] = p(a0, r1);
  const [x1, y1] = p(a1, r1);
  const [x2, y2] = p(a1, r0);
  const [x3, y3] = p(a0, r0);
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return `M${x0.toFixed(2)},${y0.toFixed(2)} A${r1.toFixed(2)},${r1.toFixed(2)} 0 ${large} 1 ${x1.toFixed(2)},${y1.toFixed(2)} L${x2.toFixed(2)},${y2.toFixed(2)} A${r0.toFixed(2)},${r0.toFixed(2)} 0 ${large} 0 ${x3.toFixed(2)},${y3.toFixed(2)} Z`;
}

const sectors = computed(() => {
  const scale = rScale.value;
  const out: Array<{ d: string; value: number; label: string; hour: number }> = [];
  hourMeans.value.forEach((mean, hour) => {
    if (mean == null) return;
    out.push({
      d: sectorPath(hour, RING_INNER - 4, scale(mean)),
      value: mean,
      label: `${dayKeys.value[0] ?? ""} · ${hourRange(hour)}`.replace(/^ · /, ""),
      hour,
    });
  });
  return out;
});

/* The IQR envelope: outer edge walks p75, inner edge walks p25. */
const envelopePath = computed(() => {
  const scale = rScale.value;
  const outer: Array<[number, number]> = [];
  const inner: Array<[number, number]> = [];
  hourBands.value.forEach((band, hour) => {
    if (!band) return;
    const mid = ((hour + 0.5) / HOURS) * 2 * Math.PI - Math.PI / 2;
    outer.push([
      CENTER + scale(band.p75) * Math.cos(mid),
      CENTER + scale(band.p75) * Math.sin(mid),
    ]);
    inner.push([
      CENTER + scale(band.p25) * Math.cos(mid),
      CENTER + scale(band.p25) * Math.sin(mid),
    ]);
  });
  if (outer.length < 4) return "";
  const path = outer.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`);
  for (const [x, y] of inner.reverse()) path.push(`L${x.toFixed(1)},${y.toFixed(1)}`);
  return path.join(" ") + " Z";
});

const peakMarker = computed(() => {
  const peak = peakHour.value;
  const scale = rScale.value;
  const mean = peak != null ? hourMeans.value[peak] : null;
  if (peak == null || mean == null) return null;
  const mid = ((peak + 0.5) / HOURS) * 2 * Math.PI - Math.PI / 2;
  const r = scale(mean) + 12;
  return {
    x: CENTER + r * Math.cos(mid),
    y: CENTER + r * Math.sin(mid),
    d: sectorPath(peak, RING_INNER - 4, scale(mean)),
  };
});

const hourTicks = computed(() =>
  Array.from({ length: HOURS }, (_, hour) => {
    const angle = (((hour + 0.5) / HOURS) * 2 * Math.PI - Math.PI / 2);
    return {
      hour,
      x: CENTER + (RING_OUTER + 20) * Math.cos(angle),
      y: CENTER + (RING_OUTER + 20) * Math.sin(angle),
    };
  }).filter((tick) => tick.hour % 3 === 0),
);

function onMove(event: MouseEvent, sector: { value: number; label: string }) {
  const bounds = root.value?.getBoundingClientRect();
  hover.value = {
    x: event.clientX - (bounds?.left ?? 0),
    y: event.clientY - (bounds?.top ?? 0),
    label: hourRange(Number(event.currentTarget instanceof Element ? (event.currentTarget as SVGPathElement).dataset.hour : 0)),
    value: sector.value,
  };
}

function sweepIn() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const paths = root.value?.querySelectorAll<SVGPathElement>(".sectors path");
  if (!paths?.length) return;
  paths.forEach((path) => {
    const hour = Number(path.dataset.hour ?? 0);
    gsap.fromTo(
      path,
      { opacity: 0 },
      { opacity: 1, duration: 0.36, delay: 0.06 + (hour / 24) * 0.85, ease: "power1.out" },
    );
  });
}

let swept = false;
watch(sectors, (next) => {
  if (swept || !next.length) return;
  swept = true;
  requestAnimationFrame(sweepIn);
});

onBeforeUnmount(() => {
  hover.value = null;
});
</script>

<template>
  <section class="hour-ring-panel">
    <header>
      <h3 class="display-face">{{ peakRangeCopy }}</h3>
      <button
        type="button"
        class="table-toggle"
        :aria-pressed="showTable"
        @click="showTable = !showTable"
      >
        {{ showTable ? "看图" : "看数据" }}
      </button>
    </header>

    <div v-show="!showTable" class="ring-stage">
      <svg
        ref="root"
        class="ring-svg"
        :viewBox="`0 0 ${SIZE} ${SIZE}`"
        role="img"
        :aria-label="`PM2.5 均值钟 ${windowCopy}`"
      >
        <path v-if="envelopePath" class="envelope" :d="envelopePath" />
        <circle class="inner-ring" :cx="CENTER" :cy="CENTER" :r="RING_INNER - 4" />

        <g class="sectors">
          <path
            v-for="sector in sectors"
            :key="sector.hour"
            :d="sector.d"
            :fill="pm25Color(sector.value)"
            :data-hour="sector.hour"
            @mousemove="onMove($event, sector)"
            @mouseleave="hover = null"
          />
        </g>

        <path
          v-if="peakMarker"
          class="peak-outline"
          :d="peakMarker.d"
        />
        <circle v-if="peakMarker" class="peak-dot" :cx="peakMarker.x" :cy="peakMarker.y" r="3.2" />

        <text class="ring-title" :x="CENTER" :y="CENTER - 26" text-anchor="middle">
          {{ peakHour != null ? hourRange(peakHour) : "—" }}
        </text>
        <text class="ring-readout" :x="CENTER" :y="CENTER + 8" text-anchor="middle">
          {{ peakHour != null ? `${(hourMeans[peakHour] ?? 0).toFixed(1)} µg/m³` : "样本不足" }}
        </text>
        <text class="ring-caption" :x="CENTER" :y="CENTER + 30" text-anchor="middle">
          峰值时段
        </text>
        <text
          v-for="tick in hourTicks"
          :key="tick.hour"
          class="ring-hour"
          :x="tick.x"
          :y="tick.y"
          text-anchor="middle"
          dominant-baseline="middle"
        >
          {{ tick.hour }}时
        </text>
      </svg>

      <div
        v-if="hover"
        class="ring-tip"
        :style="{ left: `${hover.x + 14}px`, top: `${hover.y - 10}px` }"
      >
        {{ hover.label }}<br /><b>{{ hover.value.toFixed(1) }}</b> µg/m³
      </div>

      <div class="ring-legend" aria-label="浓度图例">
        <span v-for="([label, color]) in PM25_BANDS" :key="label">
          <i :style="{ background: color }"></i>{{ label }}
        </span>
        <span class="key-rule">扇区=均值 · 底纹=波动</span>
      </div>
    </div>

    <div v-show="showTable" class="ring-table-wrap">
      <table class="ring-table">
        <caption class="sr-only">
          {{ windowCopy }} PM2.5 分时读数
        </caption>
        <thead>
          <tr>
            <th scope="col">时段</th>
            <th scope="col">均值</th>
            <th scope="col">最低</th>
            <th scope="col">最高</th>
            <th scope="col">样本</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in hourTable" :key="row.hour">
            <th scope="row">{{ hourRange(row.hour) }}</th>
            <td class="data-mono">{{ row.mean?.toFixed(1) ?? "—" }}</td>
            <td class="data-mono">{{ row.min?.toFixed(1) ?? "—" }}</td>
            <td class="data-mono">{{ row.max?.toFixed(1) ?? "—" }}</td>
            <td class="data-mono">{{ row.n }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.hour-ring-panel {
  overflow: hidden;
  display: flex;
  flex-direction: column;
  height: 100%;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
  box-shadow: var(--shadow-sm);
  transition: border-color var(--duration-fast) ease;
}
.hour-ring-panel:hover {
  border-color: var(--hairline-strong);
}

.hour-ring-panel header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  min-height: 52px;
  padding: 14px 20px 10px;
  border-bottom: 1px solid var(--hairline);
}

.hour-ring-panel h3 {
  margin: 0;
  color: var(--ink);
  font-size: 13.5px;
  font-weight: var(--fw-strong);
  letter-spacing: var(--track-title);
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

.ring-stage {
  position: relative;
  flex: 1;
  min-height: 0;
  display: grid;
  place-items: center;
  padding: 8px 0;
}

.ring-svg {
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
}

.envelope {
  fill: var(--ink);
  fill-opacity: 0.055;
  stroke: none;
}

.inner-ring {
  fill: var(--sheet);
  stroke: var(--hairline);
}

.sectors path {
  stroke: #ffffff;
  stroke-width: 1.2;
  cursor: crosshair;
}

.sectors path:hover {
  stroke: var(--ink);
  stroke-width: 1.4;
}

.peak-outline {
  fill: none;
  stroke: var(--ink);
  stroke-width: 1.6;
  pointer-events: none;
}

.peak-dot {
  fill: var(--ink);
  pointer-events: none;
}

.ring-title {
  font-family: var(--mono);
  font-size: 15px;
  font-weight: 700;
  fill: var(--ink);
}

.ring-readout {
  font-family: var(--mono);
  font-size: 26px;
  font-weight: 700;
  fill: var(--ink);
}

.ring-caption {
  font-family: var(--font-display);
  font-size: 11px;
  fill: var(--muted);
}

.ring-hour {
  font-family: var(--font-display);
  font-size: 12px;
  font-weight: 500;
  fill: var(--muted);
}

.ring-tip {
  position: absolute;
  z-index: 3;
  padding: 7px 11px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.96);
  box-shadow: var(--shadow-sm);
  font-size: 11.5px;
  color: var(--ink-soft);
  pointer-events: none;
  white-space: nowrap;
}

.ring-tip b {
  color: var(--ink);
}

.ring-legend {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 12px;
  padding: 8px 20px 14px;
  font-size: 10.5px;
  color: var(--muted);
}

.ring-legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.ring-legend i {
  width: 9px;
  height: 9px;
  border-radius: 2px;
}

.key-rule {
  margin-left: auto;
  color: var(--faint);
}

.ring-table-wrap {
  max-height: 460px;
  overflow: auto;
  padding: 0 20px 18px;
}

.ring-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-label);
}

.ring-table th,
.ring-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--hairline);
  text-align: left;
}

.ring-table thead th {
  color: var(--muted);
  font-weight: var(--fw-strong);
  position: sticky;
  top: 0;
  background: var(--sheet);
}
</style>
