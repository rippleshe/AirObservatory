<!-- PhasePath — the city's 30-day trajectory through (wind speed, PM2.5)
     space, one point per hour, coloured light→deep with time. Wind-driven
     clearance shows up as the classic sawtooth loop instead of a scatter
     cloud. Hand-written SVG with a single draw-in stroke. -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { drawIn } from "../lib/motion";
import { interpolateRgb } from "d3-interpolate";
import { mean, useElementSize } from "../lib/viz";

export type PhasePoint = {
  time: string;
  pm25: number;
  wind: number;
};

const props = defineProps<{ points: PhasePoint[] }>();

const shell = ref<HTMLElement | null>(null);
const size = useElementSize(shell);
const hover = ref<number | null>(null);

const PAD = { top: 18, right: 18, bottom: 30, left: 44 };
const OLD_COLOR = "#8fbde0";
const NEW_COLOR = "#075985";

const bounds = computed(() => {
  const windMax = Math.max(4, ...props.points.map((p) => p.wind)) * 1.05;
  const pmMax = Math.max(20, ...props.points.map((p) => p.pm25)) * 1.1;
  return { windMax, pmMax };
});

const geometry = computed(() => {
  const { w, h } = size.value;
  if (!w || !h || props.points.length < 2) return null;
  const innerW = w - PAD.left - PAD.right;
  const innerH = h - PAD.top - PAD.bottom;
  const x = (wind: number) => PAD.left + (wind / bounds.value.windMax) * innerW;
  const y = (pm25: number) => PAD.top + innerH - (pm25 / bounds.value.pmMax) * innerH;
  return { w, h, x, y, innerW, innerH };
});

/* 6-hour blocks with a light rolling pass: hourly (wind, PM2.5) pairs are
   genuine noise, but the synoptic loop — pollution building in calm air,
   collapsing in wind — only emerges at weather scale. Chunks stay day-sized
   so the tint + weight ramp makes recency readable without a legend. */
const chunks = computed(() => {
  const geo = geometry.value;
  if (!geo) return [];
  const blocks: Array<{ pm25: number; wind: number }> = [];
  for (let i = 0; i < props.points.length; i += 6) {
    const window = props.points.slice(i, i + 6);
    if (!window.length) break;
    blocks.push({
      pm25: mean(window.map((p) => p.pm25)),
      wind: mean(window.map((p) => p.wind)),
    });
  }
  const out: Array<{ d: string; color: string; width: number; opacity: number }> = [];
  const chunkSize = 4;
  for (let start = 0; start < blocks.length - 1; start += chunkSize) {
    const end = Math.min(blocks.length - 1, start + chunkSize);
    if (end <= start) continue;
    let d = `M${geo.x(blocks[start]!.wind).toFixed(1)},${geo.y(blocks[start]!.pm25).toFixed(1)}`;
    for (let i = start + 1; i <= end; i++) {
      d += ` L${geo.x(blocks[i]!.wind).toFixed(1)},${geo.y(blocks[i]!.pm25).toFixed(1)}`;
    }
    const t = (start + end) / 2 / Math.max(1, blocks.length - 1);
    out.push({
      d,
      color: timeColor(t),
      width: 1.6 + t * 2.2,
      opacity: 0.32 + t * 0.62,
    });
  }
  return out;
});

const endPoints = computed(() => {
  const geo = geometry.value;
  if (!geo || !props.points.length) return null;
  const first = props.points[0]!;
  const last = props.points[props.points.length - 1]!;
  return {
    start: { x: geo.x(first.wind), y: geo.y(first.pm25) },
    end: { x: geo.x(last.wind), y: geo.y(last.pm25) },
  };
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

function timeColor(index: number) {
  const t = props.points.length > 1 ? index / (props.points.length - 1) : 1;
  return interpolateRgb(OLD_COLOR, NEW_COLOR)(t);
}

function fmtHour(iso: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    hour12: false,
  }).format(new Date(iso));
}

function onMove(event: MouseEvent) {
  const geo = geometry.value;
  const rect = shell.value?.getBoundingClientRect();
  if (!geo || !rect) return;
  const mx = event.clientX - rect.left;
  const my = event.clientY - rect.top;
  let best = -1;
  let bestDist = Infinity;
  props.points.forEach((point, i) => {
    const dx = geo.x(point.wind) - mx;
    const dy = geo.y(point.pm25) - my;
    const dist = dx * dx + dy * dy;
    if (dist < bestDist) {
      bestDist = dist;
      best = i;
    }
  });
  hover.value = bestDist < 40 * 40 ? best : null;
}

const hoverPoint = computed(() =>
  hover.value == null ? null : {
    ...props.points[hover.value]!,
    x: geometry.value?.x(props.points[hover.value]!.wind) ?? 0,
    y: geometry.value?.y(props.points[hover.value]!.pm25) ?? 0,
    color: timeColor(hover.value),
  },
);

let played = false;
watch(chunks, (next) => {
  if (!next.length || played) return;
  played = true;
  requestAnimationFrame(() => {
    drawIn(shell.value?.querySelectorAll(".phase-trace") ?? [], {
      duration: 1.2,
      stagger: 0.05,
    });
  });
});
</script>

<template>
  <div ref="shell" class="phase-path" @mousemove="onMove" @mouseleave="hover = null">
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

      <path
        v-for="(chunk, i) in chunks"
        :key="i"
        class="phase-trace"
        :d="chunk.d"
        :stroke="chunk.color"
        :stroke-width="chunk.width"
        :stroke-opacity="chunk.opacity"
      />

      <g v-if="endPoints">
        <circle class="end-dot start" :cx="endPoints.start.x" :cy="endPoints.start.y" r="4" :fill="OLD_COLOR" />
        <circle class="end-dot end" :cx="endPoints.end.x" :cy="endPoints.end.y" r="5" :fill="NEW_COLOR" />
        <circle class="end-pulse" :cx="endPoints.end.x" :cy="endPoints.end.y" r="5" :stroke="NEW_COLOR" />
      </g>

      <g v-if="hoverPoint">
        <circle :cx="hoverPoint.x" :cy="hoverPoint.y" r="4.5" :fill="hoverPoint.color" stroke="#fff" stroke-width="1.4" />
      </g>

      <text class="axis-title" :x="PAD.left + geometry.innerW / 2" :y="geometry.h - 2">风速 m/s</text>
    </svg>

    <div v-if="hoverPoint" class="phase-tip" :style="{ left: `${hoverPoint.x + 12}px`, top: `${hoverPoint.y - 44}px` }">
      <span class="data-mono">{{ fmtHour(hoverPoint.time) }}</span>
      <span>PM2.5 <b>{{ hoverPoint.pm25.toFixed(1) }}</b> · 风 <b>{{ hoverPoint.wind.toFixed(1) }}</b> m/s</span>
    </div>
  </div>
</template>

<style scoped>
.phase-path {
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
}

.grid g:first-child text {
  text-anchor: middle;
}

.grid g text {
  dominant-baseline: central;
}

.grid g:first-of-type line:first-child {
  stroke: var(--hairline-strong);
}

.phase-trace {
  fill: none;
  stroke-width: 1.7;
  stroke-opacity: 0.78;
  stroke-linejoin: round;
  stroke-linecap: round;
  pointer-events: none;
}

.end-dot.start {
  opacity: 0.55;
}

.end-pulse {
  fill: none;
  stroke-width: 1.4;
  transform-box: fill-box;
  transform-origin: center;
  animation: phase-ping 3s cubic-bezier(0.16, 1, 0.3, 1) infinite;
  pointer-events: none;
}

@keyframes phase-ping {
  0% { transform: scale(1); opacity: 0.7; }
  70%, 100% { transform: scale(3); opacity: 0; }
}

.axis-title {
  fill: var(--faint);
  font-family: var(--font-display);
  font-size: 10.5px;
  text-anchor: middle;
}

.phase-tip {
  position: absolute;
  display: grid;
  gap: 2px;
  padding: 7px 11px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.95);
  box-shadow: var(--shadow-sm);
  font-size: 11.5px;
  color: var(--ink-soft);
  pointer-events: none;
  white-space: nowrap;
  z-index: 3;
}
</style>
