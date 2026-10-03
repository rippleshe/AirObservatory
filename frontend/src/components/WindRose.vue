<!-- WindRose — where the dirty wind comes from, drawn as a proper meteorological
     rose: 24 bearing bins, petals stacked by wind-speed class with radial
     gradients, a luminous halo behind the dirtiest bearing, and a rotation
     sweep-in. Radius is sqrt(area-true), normalised to the busiest bin. -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { gsap, prefersReducedMotion } from "../lib/motion";
import { pm25Color } from "../lib/palette";
import { useElementSize } from "../lib/viz";

export type RoseSample = {
  speed: number;
  dir: number;
  pm25: number;
};

const props = defineProps<{ samples: RoseSample[] }>();

const shell = ref<HTMLElement | null>(null);
const size = useElementSize(shell);
const hoveredDir = ref<number | null>(null);
const hoveredBin = ref<{ dir: number; speed: number } | null>(null);

const DIRS = 24;
const SPEED_STOPS = [0.5, 2, 4, 7, Infinity];
const SPEED_LABELS = ["<2", "2–4", "4–7", "≥7"];
const PAD = 30;

const bins = computed(() => {
  const grid: Array<Array<{ count: number; pm25Sum: number } | null>> = Array.from(
    { length: DIRS },
    () => new Array(SPEED_STOPS.length - 1).fill(null),
  );
  let total = 0;
  for (const sample of props.samples) {
    if (!(sample.speed >= 0.5)) continue;
    const speedIdx = SPEED_STOPS.findIndex((stop, i) => i > 0 && sample.speed < stop);
    if (speedIdx === -1) continue;
    const dirIdx = Math.min(
      DIRS - 1,
      Math.max(0, Math.floor((((sample.dir % 360) + 360) % 360) / (360 / DIRS))),
    );
    const cell = grid[dirIdx]![speedIdx] ?? { count: 0, pm25Sum: 0 };
    cell.count += 1;
    cell.pm25Sum += sample.pm25;
    grid[dirIdx]![speedIdx] = cell;
    total += 1;
  }
  return { grid, total };
});

const geometry = computed(() => {
  const { w, h } = size.value;
  if (!w || !h) return null;
  return { w, h, cx: w / 2, cy: h / 2, radius: Math.max(40, Math.min(w, h) / 2 - PAD) };
});

const dirtiestDir = computed(() => {
  const { grid } = bins.value;
  let best = -1;
  let bestMean = -1;
  for (let dir = 0; dir < DIRS; dir++) {
    let sum = 0;
    let n = 0;
    for (const cell of grid[dir]!) {
      if (!cell) continue;
      sum += cell.pm25Sum;
      n += cell.count;
    }
    if (n < 20) continue;
    const mean = sum / n;
    if (mean > bestMean) {
      bestMean = mean;
      best = dir;
    }
  }
  return best;
});

const petals = computed(() => {
  const geo = geometry.value;
  const { grid, total } = bins.value;
  if (!geo || !total) return [];
  let maxShare = 0.001;
  const shares = grid.map((row) =>
    row.map((cell) => {
      if (!cell || !cell.count) return null;
      const share = cell.count / total;
      maxShare = Math.max(maxShare, share);
      return share;
    }),
  );
  const out: Array<{
    dir: number;
    speed: number;
    d: string;
    color: string;
    opacity: number;
    share: number;
    meanPm25: number;
  }> = [];
  const span = (360 / DIRS) * (Math.PI / 180);
  for (let dir = 0; dir < DIRS; dir++) {
    let r0 = geo.radius * 0.08;
    for (let speed = 0; speed < SPEED_STOPS.length - 1; speed++) {
      const cell = grid[dir]![speed];
      const share = shares[dir]![speed];
      if (!cell || !cell.count || share == null) continue;
      const r1 = r0 + Math.sqrt(share / maxShare) * geo.radius * 0.92;
      const a0 = (dir * 2 * Math.PI) / DIRS - Math.PI / 2 + span * 0.08;
      const a1 = ((dir + 1) * 2 * Math.PI) / DIRS - Math.PI / 2 - span * 0.08;
      const meanPm25 = cell.pm25Sum / cell.count;
      out.push({
        dir,
        speed,
        d: annularSector(geo.cx, geo.cy, r0, r1, a0, a1),
        color: pm25Color(meanPm25),
        opacity: 0.4 + (speed / (SPEED_STOPS.length - 2)) * 0.5,
        share,
        meanPm25,
      });
      r0 = r1;
    }
  }
  return out;
});

function polar(cx: number, cy: number, r: number, angle: number): [number, number] {
  return [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
}

function annularSector(
  cx: number,
  cy: number,
  r0: number,
  r1: number,
  a0: number,
  a1: number,
): string {
  const [x0, y0] = polar(cx, cy, r1, a0);
  const [x1, y1] = polar(cx, cy, r1, a1);
  const [x2, y2] = polar(cx, cy, r0, a1);
  const [x3, y3] = polar(cx, cy, r0, a0);
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return [
    `M${x0.toFixed(2)},${y0.toFixed(2)}`,
    `A${r1.toFixed(2)},${r1.toFixed(2)} 0 ${large} 1 ${x1.toFixed(2)},${y1.toFixed(2)}`,
    `L${x2.toFixed(2)},${y2.toFixed(2)}`,
    `A${r0.toFixed(2)},${r0.toFixed(2)} 0 ${large} 0 ${x3.toFixed(2)},${y3.toFixed(2)}`,
    "Z",
  ].join(" ");
}

const rings = computed(() => {
  const geo = geometry.value;
  if (!geo) return [];
  return [0.33, 0.66, 1].map((f) => ({ r: geo.radius * f }));
});

const spokes = computed(() => {
  const geo = geometry.value;
  if (!geo) return [];
  return Array.from({ length: 24 }, (_, i) => {
    const angle = (i * 2 * Math.PI) / DIRS;
    return {
      major: i % 6 === 0,
      x1: geo.cx + geo.radius * 0.08 * Math.sin(angle),
      y1: geo.cy - geo.radius * 0.08 * Math.cos(angle),
      x2: geo.cx + geo.radius * Math.sin(angle),
      y2: geo.cy - geo.radius * Math.cos(angle),
    };
  });
});

const compass = computed(() => {
  const geo = geometry.value;
  if (!geo) return [];
  return [
    { label: "北", x: geo.cx, y: geo.cy - geo.radius - 14 },
    { label: "东", x: geo.cx + geo.radius + 13, y: geo.cy },
    { label: "南", x: geo.cx, y: geo.cy + geo.radius + 18 },
    { label: "西", x: geo.cx - geo.radius - 13, y: geo.cy },
  ];
});

const halo = computed(() => {
  const geo = geometry.value;
  const dir = dirtiestDir.value;
  if (!geo || dir < 0) return null;
  const angle = ((dir + 0.5) * 2 * Math.PI) / DIRS - Math.PI / 2;
  const [hx, hy] = polar(geo.cx, geo.cy, geo.radius * 0.42, angle);
  return { cx: hx, cy: hy, r: geo.radius * 0.42 };
});

const overall = computed(() => {
  if (!props.samples.length) return null;
  let sum = 0;
  for (const sample of props.samples) sum += sample.pm25;
  return sum / props.samples.length;
});

const hoverTip = computed(() => {
  const bin = hoveredBin.value;
  if (!bin) return null;
  const petal = petals.value.find((p) => p.dir === bin.dir && p.speed === bin.speed);
  if (!petal) return null;
  const from = ((bin.dir * 360) / DIRS).toFixed(0);
  const to = (((bin.dir + 1) * 360) / DIRS).toFixed(0);
  return {
    dir: `${from}°–${to}°`,
    speed: SPEED_LABELS[bin.speed],
    share: (petal.share * 100).toFixed(1),
    pm25: petal.meanPm25.toFixed(1),
    color: petal.color,
  };
});

watch(petals, (next) => {
  if (!next.length || prefersReducedMotion()) return;
  requestAnimationFrame(() => {
    const group = shell.value?.querySelector<SVGGElement>(".rose-plot");
    if (!group) return;
    gsap.fromTo(
      group,
      { rotation: -70, opacity: 0, transformOrigin: "50% 50%", svgOrigin: `${geometry.value?.cx ?? 0} ${geometry.value?.cy ?? 0}` },
      { rotation: 0, opacity: 1, duration: 1.4, ease: "power3.out" },
    );
  });
});
</script>

<template>
  <div ref="shell" class="wind-rose">
    <svg :width="size.w" :height="size.h">
      <defs>
        <radialGradient id="rose-halo">
          <stop offset="0%" stop-color="#f97316" stop-opacity="0.28" />
          <stop offset="100%" stop-color="#f97316" stop-opacity="0" />
        </radialGradient>
      </defs>

      <circle
        v-for="(ring, i) in rings"
        :key="i"
        :cx="geometry?.cx"
        :cy="geometry?.cy"
        :r="ring.r"
        class="ring"
      />

      <circle v-if="halo" :cx="halo.cx" :cy="halo.cy" :r="halo.r" fill="url(#rose-halo)" />

      <g class="rose-plot">
        <g
          v-for="petal in petals"
          :key="`${petal.dir}-${petal.speed}`"
          class="petal"
          :style="{ opacity: hoveredDir != null && hoveredDir !== petal.dir ? 0.22 : petal.opacity }"
          @mouseenter="hoveredDir = petal.dir; hoveredBin = { dir: petal.dir, speed: petal.speed }"
          @mouseleave="hoveredDir = null; hoveredBin = null"
        >
          <path :d="petal.d" :fill="petal.color" stroke="#ffffff" stroke-width="0.5" />
        </g>
      </g>

      <g class="spokes">
        <line
          v-for="(spoke, i) in spokes"
          :key="i"
          :class="{ major: spoke.major }"
          :x1="spoke.x1" :y1="spoke.y1" :x2="spoke.x2" :y2="spoke.y2"
        />
      </g>

      <text
        v-for="point in compass"
        :key="point.label"
        class="compass-label"
        :x="point.x"
        :y="point.y"
      >{{ point.label }}</text>

      <text class="center-value" :x="geometry?.cx" :y="(geometry?.cy ?? 0) - 2">
        {{ overall?.toFixed(0) ?? "—" }}
      </text>
      <text class="center-unit" :x="geometry?.cx" :y="(geometry?.cy ?? 0) + 14">µg/m³</text>
    </svg>

    <div v-if="hoverTip" class="rose-tip">
      <span class="data-mono">{{ hoverTip.dir }}</span>
      <span>风速 {{ hoverTip.speed }} m/s</span>
      <span>占比 <b class="data-mono">{{ hoverTip.share }}%</b></span>
      <span>PM2.5 <b class="data-mono" :style="{ color: hoverTip.color }">{{ hoverTip.pm25 }}</b></span>
    </div>
  </div>
</template>

<style scoped>
.wind-rose {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 300px;
}

.ring {
  fill: none;
  stroke: var(--hairline);
  stroke-dasharray: 2 5;
}

.spokes line {
  stroke: var(--hairline);
  stroke-opacity: 0.55;
}

.spokes line.major {
  stroke: var(--hairline-strong);
  stroke-opacity: 0.8;
}

.petal {
  cursor: pointer;
  transition: opacity 180ms ease;
}

.petal:hover path {
  stroke-width: 1;
}

.compass-label {
  fill: var(--muted);
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 600;
  text-anchor: middle;
  dominant-baseline: central;
}

.center-value {
  fill: var(--ink);
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 700;
  text-anchor: middle;
}

.center-unit {
  fill: var(--muted);
  font-family: var(--font-display);
  font-size: 9.5px;
  text-anchor: middle;
}

.rose-tip {
  position: absolute;
  top: 10px;
  left: 12px;
  display: grid;
  gap: 3px;
  padding: 9px 13px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: var(--shadow-sm);
  font-size: 12px;
  color: var(--ink-soft);
  pointer-events: none;
}
</style>
