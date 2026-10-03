<!-- StreamGraph — 30-day composition of six pollutants as a centered
     stream. Values arrive pre-normalized (each pollutant over its own P90),
     so stacking is a shape language, not a unit claim. Hand-written SVG:
     smooth Catmull-Rom layers, hover lifts one strand out of the river. -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { gsap, prefersReducedMotion } from "../lib/motion";
import { dayTicks, filled, smoothPath, useElementSize } from "../lib/viz";

export type StreamLayer = {
  key: string;
  label: string;
  color: string;
  values: Array<number | null>;
};

const props = defineProps<{
  times: string[];
  layers: StreamLayer[];
}>();

const shell = ref<HTMLElement | null>(null);
const size = useElementSize(shell);
const hoverIndex = ref<number | null>(null);
const hoveredKey = ref<string | null>(null);

const PAD = { top: 14, right: 10, bottom: 26, left: 10 };

const filledLayers = computed(() =>
  props.layers.map((layer) => ({ ...layer, filled: filled(layer.values) })),
);

/* Centered baseline: layer order is fixed (input order), so the river's
   silhouette is comparable across the whole window. */
const stacks = computed(() => {
  const layers = filledLayers.value;
  const n = props.times.length;
  const total = new Float64Array(n);
  for (const layer of layers) {
    for (let i = 0; i < n; i++) total[i] += Math.max(0, layer.filled[i] ?? 0);
  }
  const bottom: Float64Array[] = layers.map(() => new Float64Array(n));
  for (let i = 0; i < n; i++) {
    let acc = -total[i] / 2;
    for (const layer of layers) {
      bottom[layers.indexOf(layer)][i] = acc;
      acc += Math.max(0, layer.filled[i] ?? 0);
    }
  }
  return { bottom, total };
});

const geometry = computed(() => {
  const { w, h } = size.value;
  if (!w || !h || !props.times.length) return null;
  const innerW = w - PAD.left - PAD.right;
  const innerH = h - PAD.top - PAD.bottom;
  const maxTotal = Math.max(
    0.001,
    ...Array.from(stacks.value.total, (v) => Math.abs(v)),
  );
  const x = (i: number) =>
    PAD.left + (props.times.length > 1 ? (i / (props.times.length - 1)) * innerW : innerW / 2);
  const y = (v: number) => PAD.top + innerH / 2 - (v / maxTotal) * innerH;
  return { x, y, innerW, innerH, maxTotal };
});

const paths = computed(() => {
  const geo = geometry.value;
  if (!geo) return [];
  const n = props.times.length;
  return filledLayers.value.map((layer) => {
    const idx = filledLayers.value.indexOf(layer);
    const top = smoothPath(
      Array.from({ length: n }, (_, i) => [geo.x(i), geo.y(stacks.value.bottom[idx][i] + Math.max(0, layer.filled[i] ?? 0))] as [number, number]),
    );
    const bottomPts = Array.from({ length: n }, (_, i) => [geo.x(i), geo.y(stacks.value.bottom[idx][i])] as [number, number]).reverse();
    const bottom = smoothPath(bottomPts);
    return {
      key: layer.key,
      label: layer.label,
      color: layer.color,
      d: `${top} L${bottomPts[0][0]},${bottomPts[0][1]} ${bottom.slice(1)} Z`,
    };
  });
});

const ticks = computed(() => (geometry.value ? dayTicks(props.times, 7) : []));

const hoverReadout = computed(() => {
  const i = hoverIndex.value;
  if (i == null) return null;
  const rows = filledLayers.value
    .map((layer) => ({ label: layer.label, color: layer.color, value: Math.max(0, layer.filled[i] ?? 0) }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 4);
  const total = stacks.value.total[i];
  return {
    time: props.times[i],
    rows,
    total,
  };
});

function layerStyle(index: number) {
  const dim = hoveredKey.value != null && hoveredKey.value !== paths.value[index].key;
  return {
    fill: `url(#stream-grad-${paths.value[index].key})`,
    opacity: dim ? 0.28 : 1,
    transition: "opacity 200ms ease",
  };
}

function onMove(event: MouseEvent) {
  const geo = geometry.value;
  if (!geo) return;
  const rect = shell.value?.getBoundingClientRect();
  if (!rect) return;
  const px = event.clientX - rect.left;
  const t = (px - PAD.left) / Math.max(1, geo.innerW);
  hoverIndex.value = Math.min(props.times.length - 1, Math.max(0, Math.round(t * (props.times.length - 1))));
}

let played = false;
watch(paths, (next) => {
  if (!next.length || played || prefersReducedMotion()) {
    played = !!next.length;
    return;
  }
  played = true;
  const nodes = shell.value?.querySelectorAll<SVGPathElement>(".stream-layer");
  if (!nodes?.length) return;
  nodes.forEach((node, i) => {
    gsap.fromTo(
      node,
      { autoAlpha: 0, y: 10 },
      { autoAlpha: 1, y: 0, duration: 0.9, delay: i * 0.09, ease: "power3.out" },
    );
  });
});
</script>

<template>
  <div ref="shell" class="stream-graph" @mousemove="onMove" @mouseleave="hoverIndex = null; hoveredKey = null">
    <svg :width="size.w" :height="size.h">
      <defs>
        <linearGradient
          v-for="layer in paths"
          :key="layer.key"
          :id="`stream-grad-${layer.key}`"
          x1="0" y1="0" x2="0" y2="1"
        >
          <stop offset="0%" :stop-color="layer.color" stop-opacity="0.85" />
          <stop offset="100%" :stop-color="layer.color" stop-opacity="0.45" />
        </linearGradient>
      </defs>

      <path
        v-for="(layer, i) in paths"
        :key="layer.key"
        class="stream-layer"
        :d="layer.d"
        :style="layerStyle(i)"
        @mouseenter="hoveredKey = layer.key"
      />
      <path
        v-for="(layer, i) in paths"
        :key="`edge-${layer.key}`"
        class="stream-edge"
        :d="layer.d"
        :style="{ stroke: layer.color, opacity: hoveredKey && hoveredKey !== layer.key ? 0.15 : 0.9 }"
        @mouseenter="hoveredKey = layer.key"
      />

      <line
        v-if="hoverIndex != null && geometry"
        class="cursor"
        :x1="geometry.x(hoverIndex)" :x2="geometry.x(hoverIndex)"
        :y1="PAD.top" :y2="size.h - PAD.bottom"
      />

      <g class="ticks">
        <g v-for="tick in ticks" :key="tick.index">
          <line
            :x1="geometry?.x(tick.index)" :x2="geometry?.x(tick.index)"
            :y1="size.h - PAD.bottom" :y2="size.h - PAD.bottom + 4"
          />
          <text :x="geometry?.x(tick.index)" :y="size.h - PAD.bottom + 16">{{ tick.label }}</text>
        </g>
      </g>
    </svg>

    <div v-if="hoverReadout" class="stream-tip">
      <span class="tip-time data-mono">{{ new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", hour12: false }).format(new Date(hoverReadout.time)) }}</span>
      <span
        v-for="row in hoverReadout.rows"
        :key="row.label"
        class="tip-row"
      >
        <i :style="{ background: row.color }"></i>{{ row.label }}
        <b class="data-mono">{{ (row.value * 100).toFixed(0) }}</b>
      </span>
    </div>
  </div>
</template>

<style scoped>
.stream-graph {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 240px;
}

.stream-layer {
  stroke: none;
  cursor: crosshair;
}

.stream-edge {
  fill: none;
  stroke-width: 1.1;
  pointer-events: none;
}

.cursor {
  stroke: var(--ink);
  stroke-opacity: 0.35;
  stroke-dasharray: 3 3;
  pointer-events: none;
}

.ticks line {
  stroke: var(--hairline-strong);
}

.ticks text {
  fill: var(--muted);
  font-family: var(--font-display);
  font-size: 10.5px;
  text-anchor: middle;
}

.stream-tip {
  position: absolute;
  top: 10px;
  left: 12px;
  display: grid;
  gap: 3px;
  padding: 10px 13px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: var(--shadow-sm);
  pointer-events: none;
  font-size: 12px;
  color: var(--ink-soft);
}

.tip-time {
  color: var(--muted);
  font-size: 11px;
}

.tip-row {
  display: flex;
  align-items: center;
  gap: 7px;
}

.tip-row i {
  width: 9px;
  height: 9px;
  border-radius: 2px;
}

.tip-row b {
  margin-left: auto;
  color: var(--ink);
}
</style>
