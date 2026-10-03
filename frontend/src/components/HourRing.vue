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

const hourMeans = computed(() => {
  const buckets = Array.from({ length: HOURS }, () => [] as number[]);
  for (const row of grid.value) {
    row.forEach((value, hour) => {
      if (value != null) buckets[hour].push(value);
    });
  }
  return buckets.map((values) =>
    values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null,
  );
});

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
  if (peakHour.value == null) return "近 30 天样本不足，暂无法判断高值时段";
  return `${windowCopy.value}，${hourRange(peakHour.value)} 平均浓度最高`;
});

const peakRangeCopy = computed(() => {
  const peak = peakHour.value;
  if (peak == null) return "日内分时均值待生成";
  const filled = hourMeans.value.filter((mean): mean is number => mean != null);
  return `${hourRange(peak)} 均值 ${(hourMeans.value[peak] ?? 0).toFixed(1)} µg/m³，最低时段 ${Math.min(...filled).toFixed(1)} µg/m³`;
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

/* Annular sectors: angle = hour of day (a clock face), radius = day (tree
   rings, outer = newest). Colour is the PM2.5 band, so the form carries no
   decoration — a dark arc at one angle is the evening peak, a dark run across
   rings is a multi-day episode. */
const sectors = computed(() => {
  const days = dayKeys.value.length;
  const rStep = (RING_OUTER - RING_INNER) / Math.max(1, days);
  const gap = 0.12;
  const out: { d: string; value: number; label: string; cx: number; cy: number; hour: number }[] = [];
  grid.value.forEach((row, dayIndex) => {
    const r0 = RING_INNER + dayIndex * rStep + gap;
    const r1 = RING_INNER + (dayIndex + 1) * rStep - gap;
    row.forEach((value, hour) => {
      if (value == null) return;
      const a0 = ((hour / HOURS) * 360 - 90) * (Math.PI / 180);
      const a1 = (((hour + 1) / HOURS) * 360 - 90) * (Math.PI / 180);
      const pad = 0.008;
      const s0 = a0 + pad;
      const s1 = a1 - pad;
      const large = s1 - s0 > Math.PI ? 1 : 0;
      const x0 = CENTER + r0 * Math.cos(s0);
      const y0 = CENTER + r0 * Math.sin(s0);
      const x1 = CENTER + r1 * Math.cos(s0);
      const y1 = CENTER + r1 * Math.sin(s0);
      const x2 = CENTER + r1 * Math.cos(s1);
      const y2 = CENTER + r1 * Math.sin(s1);
      const x3 = CENTER + r0 * Math.cos(s1);
      const y3 = CENTER + r0 * Math.sin(s1);
      const mid = (s0 + s1) / 2;
      out.push({
        d: `M${x0.toFixed(2)} ${y0.toFixed(2)} L${x1.toFixed(2)} ${y1.toFixed(2)} A${r1.toFixed(2)} ${r1.toFixed(2)} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} L${x3.toFixed(2)} ${y3.toFixed(2)} A${r0.toFixed(2)} ${r0.toFixed(2)} 0 ${large} 0 ${x0.toFixed(2)} ${y0.toFixed(2)} Z`,
        value,
        label: `${dayKeys.value[dayIndex]} · ${String(hour).padStart(2, "0")}:00`,
        cx: CENTER + ((r0 + r1) / 2) * Math.cos(mid),
        cy: CENTER + ((r0 + r1) / 2) * Math.sin(mid),
        hour,
      });
    });
  });
  return out;
});

const hourTicks = computed(() =>
  Array.from({ length: HOURS }, (_, hour) => {
    const angle = (((hour + 0.5) / HOURS) * 360 - 90) * (Math.PI / 180);
    return {
      hour,
      x: CENTER + (RING_OUTER + 18) * Math.cos(angle),
      y: CENTER + (RING_OUTER + 18) * Math.sin(angle),
    };
  }).filter((tick) => tick.hour % 3 === 0),
);

const newestDay = computed(() => dayKeys.value.at(-1) ?? "");
const oldestDay = computed(() => dayKeys.value[0] ?? "");

/* Short month/day form — the full locale date overruns the ring's inner hole. */
function shortDay(key: string) {
  const [, month, day] = key.split(/[/\-.]/);
  return month && day ? `${Number(month)}/${Number(day)}` : key;
}

function onMove(event: MouseEvent, sector: { value: number; label: string }) {
  const bounds = root.value?.getBoundingClientRect();
  hover.value = {
    x: event.clientX - (bounds?.left ?? 0),
    y: event.clientY - (bounds?.top ?? 0),
    label: sector.label,
    value: sector.value,
  };
}

function sweepIn() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  /* Radial sweep: every ring's same hour lights together, the sweep walks
     the clock once — the ring is read as a clock, so it enters as one. */
  const paths = root.value?.querySelectorAll<SVGPathElement>(".sectors path");
  if (!paths?.length) return;
  paths.forEach((path) => {
    const hour = Number(path.dataset.hour ?? 0);
    gsap.fromTo(
      path,
      { opacity: 0 },
      {
        opacity: 1,
        duration: 0.36,
        delay: 0.06 + (hour / 24) * 0.85,
        ease: "power1.out",
      },
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

defineExpose({ peakCopy });
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
        :aria-label="`PM2.5 日轮 ${windowCopy}`"
      >
        <g class="sectors">
          <path
            v-for="(sector, index) in sectors"
            :key="index"
            :d="sector.d"
            :fill="pm25Color(sector.value)"
            :data-hour="sector.hour"
            @mousemove="onMove($event, sector)"
            @mouseleave="hover = null"
          />
        </g>
        <text class="ring-title" :x="CENTER" :y="CENTER - 30" text-anchor="middle">
          {{ peakHour != null ? hourRange(peakHour) : "—" }}
        </text>
        <text class="ring-readout" :x="CENTER" :y="CENTER + 8" text-anchor="middle">
          {{ peakHour != null ? `${(hourMeans[peakHour] ?? 0).toFixed(1)} µg/m³` : "样本不足" }}
        </text>
        <text class="ring-caption" :x="CENTER" :y="CENTER + 32" text-anchor="middle">
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
        <text class="ring-day" :x="CENTER" :y="CENTER + 58" text-anchor="middle">
          内圈 {{ shortDay(oldestDay) }} · 外圈 {{ shortDay(newestDay) }}
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
        <span class="key-rule">外圈=今天</span>
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
  min-height: 56px;
  padding: 14px 20px 10px;
  border-bottom: 1px solid var(--hairline);
}

.hour-ring-panel h3 {
  margin: 0;
  color: var(--ink);
  font-size: 15px;
  font-weight: 600;
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

.table-toggle[aria-pressed="true"] {
  background: var(--ink);
  border-color: var(--ink);
  color: #ffffff;
  font-weight: 600;
}

.ring-stage {
  position: relative;
  display: grid;
  justify-items: center;
  padding: 8px 12px 14px;
}

.ring-svg {
  width: min(100%, 560px);
  height: auto;
  overflow: visible;
}

.sectors path {
  stroke: var(--sheet);
  stroke-width: 0.4;
  transition: opacity 120ms ease;
}

.sectors:hover path {
  opacity: 0.45;
}

.sectors path:hover {
  opacity: 1;
  stroke: var(--ink);
  stroke-width: 1.2;
}

.ring-title {
  font-family: var(--mono);
  font-size: 17px;
  font-weight: 700;
  fill: var(--ink);
}

.ring-readout {
  font-family: var(--mono);
  font-size: 22px;
  font-weight: 700;
  fill: var(--ink);
}

.ring-caption {
  font-size: 12px;
  fill: var(--muted);
}

.ring-hour {
  font-size: 12px;
  fill: var(--ink-soft);
}

.ring-day {
  font-size: 12px;
  fill: var(--faint);
}

.ring-tip {
  position: absolute;
  z-index: 3;
  pointer-events: none;
  background: rgba(255, 255, 255, .985);
  border: 1px solid #bec9c3;
  border-radius: 8px;
  padding: 8px 11px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--ink);
  box-shadow: 0 12px 32px rgba(21, 36, 30, .12);
  white-space: nowrap;
}

.ring-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 14px;
  margin-top: 6px;
  font-size: var(--fs-label);
  color: var(--muted);
}

.ring-legend i {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 5px;
}

.key-rule {
  color: var(--faint);
}

.ring-table-wrap {
  max-height: 480px;
  overflow: auto;
}

.ring-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-data);
}

.ring-table th,
.ring-table td {
  text-align: left;
  padding: 7px 14px;
  border-bottom: 1px solid var(--hairline-soft);
}

.ring-table thead th {
  position: sticky;
  top: 0;
  background: var(--sheet);
  color: var(--muted);
  font-weight: var(--fw-strong);
  font-size: var(--fs-label);
}
</style>
