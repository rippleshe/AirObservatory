<!-- WindRose — where the dirty wind comes from. 16 bearing bins, each petal
     stacked by wind-speed class; radius is sqrt(frequency) (area-true) and
     segment colour is the mean PM2.5 carried at that speed. Hand-written
     SVG annular sectors on a compass rose. -->
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
const hovered = ref<{ dir: number; speed: number } | null>(null);

const DIRS = 16;
const SPEED_STOPS = [0.5, 2, 4, 7, Infinity];
const SPEED_LABELS = ["<2", "2–4", "4–7", "≥7"];
const PAD = 26;

const bins = computed(() => {
  const grid: Array<Array<{ count: number; pm25Sum: number } | null>> = Array.from(
    { length: DIRS },
    () => new Array(SPEED_STOPS.length - 1).fill(null),
  );
  let total = 0;
  for (const sample of props.samples) {
    if (!(sample.speed >= 0.5)) continue;
    const speedIdx = SPEED_STOPS.findIndex(
      (stop, i) => i > 0 && sample.speed < stop,
    );
    if (speedIdx === -1) continue;
    const dirIdx = Math.min(
      DIRS - 1,
      Math.max(0, Math.floor(((sample.dir % 360) + 360) % 360 / (360 / DIRS))),
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
  const cx = w / 2;
  const cy = h / 2;
  const radius = Math.min(w, h) / 2 - PAD;
  return { w, h, cx, cy, radius };
});

const petals = computed(() => {
  const geo = geometry.value;
  const { grid, total } = bins.value;
  if (!geo || !total) return [];
  /* Radius keeps sqrt(area-true) scaling but anchors the busiest bin near the
     rim, so the rose fills its compass instead of huddling at the centre. */
  let maxShare = 0.001;
  const shares: Array<Array<number | null>> = grid.map((row) =>
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
    share: number;
    meanPm25: number;
  }> = [];
  for (let dir = 0; dir < DIRS; dir++) {
    let r0 = geo.radius * 0.1;
    for (let speed = 0; speed < SPEED_STOPS.length - 1; speed++) {
      const cell = grid[dir]![speed];
      const share = shares[dir]![speed];
      if (!cell || !cell.count || share == null) {
        continue;
      }
      const r1 = r0 + Math.sqrt(share / maxShare) * geo.radius * 0.9;
      const a0 = ((dir * 360) / DIRS - 90 + 2) * (Math.PI / 180);
      const a1 = (((dir + 1) * 360) / DIRS - 90 - 2) * (Math.PI / 180);
      const meanPm25 = cell.pm25Sum / cell.count;
      out.push({
        dir,
        speed,
        d: annularSector(geo.cx, geo.cy, r0, r1, a0, a1),
        color: pm25Color(meanPm25),
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

const spokes = computed(() => {
  const geo = geometry.value;
  if (!geo) return [];
  return Array.from({ length: DIRS }, (_, i) => {
    const angle = (i * 2 * Math.PI) / DIRS;
    return {
      x1: geo.cx + geo.radius * 0.1 * Math.sin(angle),
      y1: geo.cy - geo.radius * 0.1 * Math.cos(angle),
      x2: geo.cx + geo.radius * Math.sin(angle),
      y2: geo.cy - geo.radius * Math.cos(angle),
    };
  });
});

const rings = computed(() => {
  const geo = geometry.value;
  if (!geo) return [];
  return [0.25, 0.5, 0.75, 1].map((f) => ({
    r: geo.radius * f * 0.94 + geo.radius * 0.06,
  }));
});

const compass = computed(() => {
  const geo = geometry.value;
  if (!geo) return [];
  return [
    { label: "北", x: geo.cx, y: geo.cy - geo.radius - 12 },
    { label: "东", x: geo.cx + geo.radius + 12, y: geo.cy },
    { label: "南", x: geo.cx, y: geo.cy + geo.radius + 16 },
    { label: "西", x: geo.cx - geo.radius - 12, y: geo.cy },
  ];
});

const overall = computed(() => {
  if (!props.samples.length) return null;
  let sum = 0;
  for (const sample of props.samples) sum += sample.pm25;
  return sum / props.samples.length;
});

const hoverTip = computed(() => {
  const petal = petals.value.find(
    (p) => hovered.value && p.dir === hovered.value.dir && p.speed === hovered.value.speed,
  );
  if (!petal) return null;
  return {
    dir: `${((petal.dir * 360) / 16).toFixed(0)}°–${(((petal.dir + 1) * 360) / 16).toFixed(0)}°`,
    speed: SPEED_LABELS[petal.speed],
    share: (petal.share * 100).toFixed(1),
    pm25: petal.meanPm25.toFixed(1),
    color: petal.color,
  };
});

watch(petals, (next) => {
  if (!next.length || prefersReducedMotion()) return;
  requestAnimationFrame(() => {
    const nodes = shell.value?.querySelectorAll<SVGGElement>(".petal");
    if (!nodes?.length) return;
    gsap.fromTo(
      nodes,
      { scale: 0.55, opacity: 0, transformOrigin: "50% 50%" },
      { scale: 1, opacity: 1, duration: 0.7, stagger: 0.018, ease: "back.out(1.6)" },
    );
  });
});
</script>

<template>
  <div ref="shell" class="wind-rose">
    <svg :width="size.w" :height="size.h">
      <circle
        v-for="(ring, i) in rings"
        :key="i"
        :cx="geometry?.cx"
        :cy="geometry?.cy"
        :r="ring.r"
        class="ring"
      />

      <g
        v-for="petal in petals"
        :key="`${petal.dir}-${petal.speed}`"
        class="petal"
        @mouseenter="hovered = { dir: petal.dir, speed: petal.speed }"
        @mouseleave="hovered = null"
      >
        <path :d="petal.d" :fill="petal.color" fill-opacity="0.82" />
      </g>

      <g v-for="(spoke, i) in spokes" :key="`spoke-${i}`" class="spoke">
        <line :x1="spoke.x1" :y1="spoke.y1" :x2="spoke.x2" :y2="spoke.y2" />
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

.spoke line {
  stroke: var(--hairline);
  stroke-opacity: 0.7;
}

.petal {
  cursor: pointer;
}

.petal:hover path {
  fill-opacity: 1;
  stroke: #ffffff;
  stroke-width: 0.8;
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
  font-size: 17px;
  font-weight: 700;
  text-anchor: middle;
}

.center-unit {
  fill: var(--muted);
  font-family: var(--font-display);
  font-size: 10px;
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
