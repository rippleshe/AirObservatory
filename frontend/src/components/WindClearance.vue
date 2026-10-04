<!-- WindClearance — how wind scrubs the air, drawn as one honest curve:
     wind speed binned, each bin carrying its median PM2.5 with a 25–75%
     band and a dot sized by sample count. The descending sweep (or its
     absence) is the whole story — no trajectory hairball. -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { drawIn } from "../lib/motion";
import { pm25Color } from "../lib/palette";
import { mean, smoothPath, useElementSize } from "../lib/viz";

export type ClearancePoint = {
  wind: number;
  pm25: number;
};

const props = defineProps<{ points: ClearancePoint[] }>();

const shell = ref<HTMLElement | null>(null);
const size = useElementSize(shell);
const hoverBin = ref<number | null>(null);

const PAD = { top: 20, right: 24, bottom: 34, left: 46 };

const EDGES = [0, 1, 2, 3, 4, 5, 6, 8, 10, 13, Infinity];

type Bin = {
  center: number;
  from: number;
  to: number | null;
  median: number;
  p25: number;
  p75: number;
  mean: number;
  n: number;
};

const bins = computed<Bin[]>(() => {
  const out: Bin[] = [];
  for (let i = 0; i < EDGES.length - 1; i++) {
    const from = EDGES[i]!;
    const to = EDGES[i + 1] === Infinity ? null : EDGES[i + 1]!;
    const inBin = props.points.filter((p) =>
      to == null ? p.wind >= from : p.wind >= from && p.wind < to,
    );
    if (inBin.length < 8) continue;
    const pm = inBin.map((p) => p.pm25).sort((a, b) => a - b);
    const pos = (q: number) => pm[Math.floor((pm.length - 1) * q)]!;
    out.push({
      center: to == null ? from + 2 : (from + to) / 2,
      from,
      to,
      median: pos(0.5),
      p25: pos(0.25),
      p75: pos(0.75),
      mean: mean(pm),
      n: inBin.length,
    });
  }
  return out;
});

const bounds = computed(() => {
  const windMax = Math.max(4, ...props.points.map((p) => p.wind)) * 1.04;
  const pmMax = Math.max(20, ...bins.value.map((b) => b.p75)) * 1.15;
  return { windMax, pmMax };
});

const geometry = computed(() => {
  const { w, h } = size.value;
  if (!w || !h || bins.value.length < 2) return null;
  const innerW = w - PAD.left - PAD.right;
  const innerH = h - PAD.top - PAD.bottom;
  const x = (wind: number) => PAD.left + (wind / bounds.value.windMax) * innerW;
  const y = (pm25: number) => PAD.top + innerH - (pm25 / bounds.value.pmMax) * innerH;
  return { w, h, x, y, innerW, innerH };
});

const medianPath = computed(() => {
  const geo = geometry.value;
  if (!geo) return "";
  return smoothPath(bins.value.map((b) => [geo.x(b.center), geo.y(b.median)] as [number, number]));
});

const bandPath = computed(() => {
  const geo = geometry.value;
  if (!geo) return "";
  const up = bins.value.map((b) => [geo.x(b.center), geo.y(b.p75)] as [number, number]);
  const down = bins.value.map((b) => [geo.x(b.center), geo.y(b.p25)] as [number, number]).reverse();
  return `${smoothPath(up)} L${down[0]![0].toFixed(1)},${down[0]![1].toFixed(1)} ${smoothPath(down).slice(1)} Z`;
});

const windTicks = computed(() => {
  const max = bounds.value.windMax;
  const step = max > 12 ? 4 : max > 6 ? 2 : 1;
  const ticks: number[] = [];
  for (let v = 0; v <= max; v += step) ticks.push(v);
  return ticks;
});

const pmTicks = computed(() => {
  const max = bounds.value.pmMax;
  const step = max > 200 ? 50 : max > 80 ? 25 : 10;
  const ticks: number[] = [];
  for (let v = 0; v <= max; v += step) ticks.push(v);
  return ticks;
});

const maxCount = computed(() => Math.max(1, ...bins.value.map((b) => b.n)));

function binRange(bin: Bin) {
  return bin.to == null ? `≥${bin.from}` : `${bin.from}–${bin.to}`;
}

const hoverPoint = computed(() => {
  if (hoverBin.value == null) return null;
  const bin = bins.value[hoverBin.value];
  const geo = geometry.value;
  if (!bin || !geo) return null;
  return { bin, x: geo.x(bin.center), y: geo.y(bin.median) };
});

let played = false;
watch(medianPath, (next) => {
  if (!next || played) return;
  played = true;
  requestAnimationFrame(() => {
    drawIn(shell.value?.querySelectorAll(".clearance-curve") ?? [], { duration: 1.6 });
  });
});
</script>

<template>
  <div ref="shell" class="wind-clearance" @mouseleave="hoverBin = null">
    <svg :width="geometry?.w" :height="geometry?.h" v-if="geometry">
      <g class="grid">
        <g v-for="tick in windTicks" :key="`w-${tick}`">
          <line :x1="geometry.x(tick)" :x2="geometry.x(tick)" :y1="PAD.top" :y2="PAD.top + geometry.innerH" />
          <text :x="geometry.x(tick)" :y="PAD.top + geometry.innerH + 16">{{ tick }}</text>
        </g>
        <g v-for="tick in pmTicks" :key="`p-${tick}`">
          <line :x1="PAD.left" :x2="PAD.left + geometry.innerW" :y1="geometry.y(tick)" :y2="geometry.y(tick)" />
          <text :x="PAD.left - 8" :y="geometry.y(tick)">{{ tick }}</text>
        </g>
      </g>

      <path class="band" :d="bandPath" />

      <path
        v-for="(bin, i) in bins"
        :key="`hit-${i}`"
        class="hit-zone"
        :x="geometry.x(bin.from ?? bin.center - 1)"
        :y="PAD.top"
        :width="geometry.x(bin.to ?? bin.center + 2) - geometry.x(bin.from ?? bin.center - 1)"
        :height="geometry.innerH"
        @mouseenter="hoverBin = i"
      />

      <path class="clearance-curve" :d="medianPath" />

      <circle
        v-for="(bin, i) in bins"
        :key="`d-${i}`"
        class="bin-dot"
        :cx="geometry.x(bin.center)"
        :cy="geometry.y(bin.median)"
        :r="3 + Math.sqrt(bin.n / maxCount) * 6"
        :fill="pm25Color(bin.median)"
        :opacity="hoverBin == null || hoverBin === i ? 1 : 0.35"
      />

      <circle v-if="hoverPoint" :cx="hoverPoint.x" :cy="hoverPoint.y" r="4" fill="#0f172a" stroke="#fff" stroke-width="1.4" />

      <text class="axis-title" :x="PAD.left + geometry.innerW / 2" :y="geometry.h - 4">风速 m/s</text>
    </svg>

    <div v-if="hoverPoint" class="clearance-tip">
      <span class="data-mono">{{ binRange(hoverPoint.bin) }} m/s</span>
      <span>中位 <b>{{ hoverPoint.bin.median.toFixed(1) }}</b></span>
      <span>四分位 <b>{{ hoverPoint.bin.p25.toFixed(0) }}–{{ hoverPoint.bin.p75.toFixed(0) }}</b></span>
      <span>N <b>{{ hoverPoint.bin.n }}</b></span>
    </div>
  </div>
</template>

<style scoped>
.wind-clearance {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 300px;
}

.grid line {
  stroke: var(--hairline);
}

.grid text {
  fill: var(--faint);
  font-family: var(--font-display);
  font-size: 10.5px;
  dominant-baseline: central;
}

.grid g:first-child text {
  text-anchor: middle;
  dominant-baseline: unset;
}

.band {
  fill: #0369a1;
  fill-opacity: 0.1;
  stroke: none;
}

.clearance-curve {
  fill: none;
  stroke: #075985;
  stroke-width: 2.6;
  stroke-linecap: round;
  pointer-events: none;
}

.bin-dot {
  stroke: #ffffff;
  stroke-width: 1.6;
}

.hit-zone {
  fill: transparent;
}

.axis-title {
  fill: var(--faint);
  font-family: var(--font-display);
  font-size: 10.5px;
  text-anchor: middle;
}

.clearance-tip {
  position: absolute;
  top: 10px;
  left: 12px;
  display: flex;
  gap: 12px;
  padding: 8px 13px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.95);
  box-shadow: var(--shadow-sm);
  font-size: 11.5px;
  color: var(--ink-soft);
  pointer-events: none;
  white-space: nowrap;
}

.clearance-tip b {
  color: var(--ink);
}
</style>
