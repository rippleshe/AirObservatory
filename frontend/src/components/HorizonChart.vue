<!-- HorizonChart — six pollutants in six tight horizon strips. Each strip
     folds its series into two overlapping bands (peak excursions overprint a
     saturated second layer), so 30 days of hourly data read at a glance and
     cross-pollutant timing lines up vertically. Hand-written SVG. -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { wipeUp } from "../lib/motion";
import { dayTicks, useElementSize } from "../lib/viz";

export type HorizonSeries = {
  key: string;
  label: string;
  color: string;
  values: Array<number | null>;
};

const props = defineProps<{
  times: string[];
  series: HorizonSeries[];
}>();

const shell = ref<HTMLElement | null>(null);
const size = useElementSize(shell);
const hoverIndex = ref<number | null>(null);

const PAD = { top: 6, right: 64, bottom: 24, left: 52 };
const ROW_GAP = 14;

const rows = computed(() =>
  props.series.map((entry) => {
    const valid = entry.values.filter((v): v is number => v != null && Number.isFinite(v));
    const sorted = [...valid].sort((a, b) => a - b);
    const p98 = sorted[Math.floor(sorted.length * 0.98)] ?? Math.max(1, ...valid);
    const max = Math.max(1, p98);
    return { ...entry, max };
  }),
);

const geometry = computed(() => {
  const { w, h } = size.value;
  const n = rows.value.length;
  if (!w || !h || !n || !props.times.length) return null;
  const innerW = w - PAD.left - PAD.right;
  const rowH = (h - PAD.top - PAD.bottom - ROW_GAP * (n - 1)) / n;
  const x = (i: number) =>
    PAD.left + (props.times.length > 1 ? (i / (props.times.length - 1)) * innerW : 0);
  const rowY = (r: number) => PAD.top + r * (rowH + ROW_GAP);
  return { w, h, innerW, rowH, x, rowY };
});

/* One folded band path: y follows value inside the row, clipped by the row
   rect; band 2 carries only the part above the fold, drawn saturated. */
function bandPath(
  values: Array<number | null>,
  r: number,
  band: 0 | 1,
  max: number,
): string {
  const geo = geometry.value;
  if (!geo) return "";
  const rowH = geo.rowH;
  let d = "";
  let pen: Array<[number, number]> = [];
  const flush = () => {
    if (pen.length > 1) {
      d += `M${pen[0]![0]},${pen[0]![1]}`;
      for (let k = 1; k < pen.length; k++) d += ` L${pen[k]![0]},${pen[k]![1]}`;
    }
    pen = [];
  };
  values.forEach((value, i) => {
    if (value == null) {
      flush();
      return;
    }
    const v01 = value / max;
    const local = band === 0 ? Math.min(1, v01) : Math.max(0, v01 - 1);
    if (band === 1 && local <= 0) {
      flush();
      return;
    }
    const y = geo.rowY(r) + rowH - local * rowH;
    pen.push([geo.x(i), y]);
  });
  flush();
  return d;
}

const ticks = computed(() => (geometry.value ? dayTicks(props.times, 7) : []));

function onRowMove(event: MouseEvent) {
  const geo = geometry.value;
  const rect = shell.value?.getBoundingClientRect();
  if (!geo || !rect) return;
  const t = (event.clientX - rect.left - PAD.left) / Math.max(1, geo.innerW);
  hoverIndex.value = Math.min(
    props.times.length - 1,
    Math.max(0, Math.round(t * (props.times.length - 1))),
  );
}

const hoverReadout = computed(() => {
  const i = hoverIndex.value;
  if (i == null) return null;
  return rows.value.map((row) => ({
    label: row.label,
    color: row.color,
    value: row.values[i],
  }));
});

let played = false;
watch(geometry, (next) => {
  if (!next || played) return;
  played = true;
  requestAnimationFrame(() => {
    const nodes = shell.value?.querySelectorAll<SVGGElement>(".horizon-row");
    if (!nodes?.length) return;
    nodes.forEach((node, i) => wipeUp(node, i * 0.1));
  });
});
</script>

<template>
  <div ref="shell" class="horizon-chart" @mouseleave="hoverIndex = null">
    <svg :width="size.w" :height="size.h">
      <g
        v-for="(row, r) in rows"
        :key="row.key"
        class="horizon-row"
        @mousemove="onRowMove"
      >
        <path :d="bandPath(row.values, r, 0, row.max)" :fill="row.color" fill-opacity="0.42" />
        <path :d="bandPath(row.values, r, 1, row.max)" :fill="row.color" fill-opacity="0.95" />
      </g>

      <g class="row-labels">
        <text
          v-for="(row, r) in rows"
          :key="`label-${row.key}`"
          :x="PAD.left - 10"
          :y="(geometry?.rowY?.(r) ?? 0) + (geometry?.rowH ?? 0) / 2"
        >{{ row.label }}</text>
      </g>

      <g class="row-seps">
        <line
          v-for="(row, r) in rows"
          :key="`sep-${row.key}`"
          :x1="PAD.left"
          :x2="PAD.left + (geometry?.innerW ?? 0)"
          :y1="(geometry?.rowY?.(r) ?? 0) + (geometry?.rowH ?? 0) + ROW_GAP / 2"
          :y2="(geometry?.rowY?.(r) ?? 0) + (geometry?.rowH ?? 0) + ROW_GAP / 2"
        />
      </g>

      <line
        v-if="hoverIndex != null && geometry"
        class="cursor"
        :x1="geometry.x(hoverIndex)" :x2="geometry.x(hoverIndex)"
        :y1="PAD.top" :y2="size.h - PAD.bottom"
      />

      <g class="ticks">
        <g v-for="tick in ticks" :key="tick.index">
          <text :x="geometry?.x(tick.index)" :y="size.h - 8">{{ tick.label }}</text>
        </g>
      </g>
    </svg>

    <div v-if="hoverReadout && hoverIndex != null" class="horizon-tip">
      <span
        v-for="row in hoverReadout"
        :key="row.label"
        class="tip-row"
        :class="{ empty: row.value == null }"
      >
        <i :style="{ background: row.color }"></i>{{ row.label }}
        <b class="data-mono">{{ row.value?.toFixed(1) ?? "—" }}</b>
      </span>
    </div>
  </div>
</template>

<style scoped>
.horizon-chart {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 360px;
}

.horizon-row {
  cursor: crosshair;
}

.row-labels text {
  fill: var(--muted);
  font-family: var(--font-display);
  font-size: 11px;
  font-weight: 600;
  text-anchor: end;
  dominant-baseline: central;
}

.row-seps line {
  stroke: var(--hairline);
}

.cursor {
  stroke: var(--ink);
  stroke-opacity: 0.3;
  stroke-dasharray: 3 3;
  pointer-events: none;
}

.ticks text {
  fill: var(--muted);
  font-family: var(--font-display);
  font-size: 10.5px;
  text-anchor: middle;
}

.horizon-tip {
  position: absolute;
  top: 8px;
  right: 70px;
  display: grid;
  grid-template-columns: repeat(3, auto);
  gap: 4px 14px;
  padding: 9px 13px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: var(--shadow-sm);
  font-size: 11.5px;
  color: var(--ink-soft);
  pointer-events: none;
}

.tip-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tip-row.empty {
  opacity: 0.4;
}

.tip-row i {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}

.tip-row b {
  color: var(--ink);
}
</style>
