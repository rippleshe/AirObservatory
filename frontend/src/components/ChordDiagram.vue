<!-- ChordDiagram — the synchrony network of the 31 province cities: whose
     PM2.5 hours rise and fall together. Pearson correlation over the aligned
     720h field; nodes sit on a circle ordered by pollution load, links are
     center-pulled bezier arcs whose weight and opacity carry |r|. Fully
     hand-written SVG, adjacency focus on hover. -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { gsap, prefersReducedMotion } from "../lib/motion";
import { pm25Color } from "../lib/palette";
import { useElementSize } from "../lib/viz";

export type ChordCity = {
  location_id: number;
  name: string;
  values: Array<number | null>;
};

const props = withDefaults(
  defineProps<{
    cities: ChordCity[];
    threshold?: number;
    maxEdges?: number;
  }>(),
  { threshold: 0.55, maxEdges: 96 },
);

const shell = ref<HTMLElement | null>(null);
const size = useElementSize(shell);
const hoveredNode = ref<string | null>(null);
const hoveredEdge = ref<number | null>(null);

const PAD = 64;

function pearson(a: Array<number | null>, b: Array<number | null>): number | null {
  let n = 0;
  let sa = 0;
  let sb = 0;
  let saa = 0;
  let sbb = 0;
  let sab = 0;
  for (let i = 0; i < a.length; i++) {
    const x = a[i];
    const y = b[i];
    if (x == null || y == null) continue;
    n += 1;
    sa += x;
    sb += y;
    saa += x * x;
    sbb += y * y;
    sab += x * y;
  }
  if (n < 48) return null;
  const cov = sab * n - sa * sb;
  const denom = Math.sqrt((saa * n - sa * sa) * (sbb * n - sb * sb));
  return denom > 0 ? cov / denom : null;
}

type ChordNode = {
  id: number;
  name: string;
  mean: number;
  color: string;
  angle: number;
  degree: number;
};

type ChordEdge = {
  index: number;
  source: ChordNode;
  target: ChordNode;
  r: number;
  d: string;
  width: number;
  opacity: number;
  from: string;
  to: string;
};

const geometry = computed(() => {
  const { w, h } = size.value;
  if (!w || !h) return null;
  return { w, h, cx: w / 2, cy: h / 2, R: Math.min(w, h) / 2 - PAD };
});

const nodes = computed<ChordNode[]>(() => {
  const geo = geometry.value;
  if (!geo) return [];
  const rows = props.cities
    .map((city) => {
      const valid = city.values.filter((v): v is number => v != null);
      const mean = valid.length ? valid.reduce((a, b) => a + b, 0) / valid.length : 0;
      return { id: city.location_id, name: city.name, mean };
    })
    .filter((row) => row.mean > 0)
    .sort((a, b) => b.mean - a.mean);
  /* Degree first, so arc length tracks how connected a province is. */
  const n = rows.length;
  return rows.map((row, i) => ({
    ...row,
    color: pm25Color(row.mean),
    angle: (i / n) * 2 * Math.PI - Math.PI / 2,
    degree: 1,
  }));
});

const edges = computed<ChordEdge[]>(() => {
  const geo = geometry.value;
  const list = nodes.value;
  if (!geo || list.length < 3) return [];
  const byId = new Map(props.cities.map((city) => [city.location_id, city.values]));
  const raw: Array<{ a: ChordNode; b: ChordNode; r: number }> = [];
  for (let i = 0; i < list.length; i++) {
    for (let j = i + 1; j < list.length; j++) {
      const va = byId.get(list[i]!.id);
      const vb = byId.get(list[j]!.id);
      if (!va || !vb) continue;
      const r = pearson(va, vb);
      if (r == null || r < props.threshold) continue;
      raw.push({ a: list[i]!, b: list[j]!, r });
    }
  }
  raw.sort((x, y) => y.r - x.r);
  const kept = raw.slice(0, props.maxEdges);
  const strength = new Map<number, number>();
  for (const edge of kept) {
    strength.set(edge.a.id, (strength.get(edge.a.id) ?? 0) + edge.r);
    strength.set(edge.b.id, (strength.get(edge.b.id) ?? 0) + edge.r);
  }
  const maxStrength = Math.max(0.001, ...strength.values());
  for (const node of list) node.degree = 0.5 + (strength.get(node.id) ?? 0) / maxStrength;

  const point = (angle: number, radius: number): [number, number] => [
    geo.cx + radius * Math.cos(angle),
    geo.cy + radius * Math.sin(angle),
  ];
  return kept.map((edge, index) => {
    const [x1, y1] = point(edge.a.angle, geo.R);
    const [x2, y2] = point(edge.b.angle, geo.R);
    const d = `M${x1.toFixed(1)},${y1.toFixed(1)} Q${geo.cx.toFixed(1)},${geo.cy.toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)}`;
    return {
      index,
      source: edge.a,
      target: edge.b,
      r: edge.r,
      d,
      width: 1.4 + (edge.r - props.threshold) * 16,
      opacity: Math.min(0.85, 0.3 + (edge.r - props.threshold) * 1.3),
      from: edge.a.color,
      to: edge.b.color,
    };
  });
});

function arcPath(node: ChordNode): string {
  const geo = geometry.value;
  if (!geo) return "";
  const span = 0.055 * node.degree;
  const a0 = node.angle - span;
  const a1 = node.angle + span;
  const r1 = geo.R + 5;
  const r0 = geo.R - 5;
  const p = (angle: number, radius: number): [number, number] => [
    geo.cx + radius * Math.cos(angle),
    geo.cy + radius * Math.sin(angle),
  ];
  const [x0, y0] = p(a0, r1);
  const [x1, y1] = p(a1, r1);
  const [x2, y2] = p(a1, r0);
  const [x3, y3] = p(a0, r0);
  return `M${x0},${y0} A${r1},${r1} 0 0 1 ${x1},${y1} L${x2},${y2} A${r0},${r0} 0 0 0 ${x3},${y3} Z`;
}

function labelTransform(node: ChordNode): string {
  const geo = geometry.value;
  if (!geo) return "";
  const deg = (node.angle * 180) / Math.PI;
  const x = geo.cx + (geo.R + 20) * Math.cos(node.angle);
  const y = geo.cy + (geo.R + 20) * Math.sin(node.angle);
  const flip = deg > 90 || deg < -90;
  return `rotate(${flip ? deg + 180 : deg} ${x} ${y})`;
}

function labelAnchor(node: ChordNode): string {
  const deg = (node.angle * 180) / Math.PI;
  const flip = deg > 90 || deg < -90;
  return flip ? "end" : "start";
}

const edgeActive = computed(() => {
  if (hoveredNode.value == null) return null;
  return (edge: ChordEdge) =>
    edge.source.name === hoveredNode.value || edge.target.name === hoveredNode.value;
});

const hoverTip = computed(() => {
  if (hoveredEdge.value != null) {
    const edge = edges.value[hoveredEdge.value];
    if (edge) return `${edge.source.name} ↔ ${edge.target.name} · r=${edge.r.toFixed(2)}`;
  }
  if (hoveredNode.value != null) {
    const node = nodes.value.find((n) => n.name === hoveredNode.value);
    if (node) return `${node.name} · 30 天均值 ${node.mean.toFixed(1)} µg/m³`;
  }
  return null;
});

watch(edges, (next) => {
  if (!next.length || prefersReducedMotion()) return;
  requestAnimationFrame(() => {
    const curves = shell.value?.querySelectorAll<SVGPathElement>(".chord-edge");
    if (curves?.length) {
      gsap.fromTo(
        curves,
        { opacity: 0 },
        { opacity: 1, duration: 1.1, stagger: 0.012, ease: "power1.inOut" },
      );
    }
  });
});
</script>

<template>
  <div ref="shell" class="chord-diagram">
    <svg :width="size.w" :height="size.h">
      <circle :cx="geometry?.cx" :cy="geometry?.cy" :r="geometry?.R" class="guide" />

      <path
        v-for="edge in edges"
        :key="edge.index"
        class="chord-edge"
        :d="edge.d"
        :stroke="edge.source.color"
        :stroke-width="edge.width"
        :style="{
          opacity: edgeActive
            ? (edgeActive(edge) ? 0.95 : 0.04)
            : (hoveredEdge === edge.index ? 1 : edge.opacity),
        }"
        fill="none"
        @mouseenter="hoveredEdge = edge.index"
        @mouseleave="hoveredEdge = null"
      />

      <g
        v-for="node in nodes"
        :key="node.id"
        @mouseenter="hoveredNode = node.name"
        @mouseleave="hoveredNode = null"
      >
        <path :d="arcPath(node)" :fill="node.color" />
        <text
          class="node-label"
          :x="geometry!.cx + (geometry!.R + 20) * Math.cos(node.angle)"
          :y="geometry!.cy + (geometry!.R + 20) * Math.sin(node.angle)"
          :text-anchor="labelAnchor(node)"
          :transform="labelTransform(node)"
          :style="{ opacity: hoveredNode && hoveredNode !== node.name ? 0.25 : 0.9 }"
        >{{ node.name }}</text>
      </g>
    </svg>

    <div v-if="hoverTip" class="chord-tip data-mono">{{ hoverTip }}</div>
  </div>
</template>

<style scoped>
.chord-diagram {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 420px;
}

.guide {
  fill: none;
  stroke: var(--hairline);
  stroke-dasharray: 2 5;
}

.chord-edge {
  fill: none;
  stroke-linecap: round;
  cursor: pointer;
  transition: opacity 220ms ease;
}

.node-label {
  fill: var(--ink-soft);
  font-family: var(--font-sans);
  font-size: 10.5px;
  font-weight: 600;
  dominant-baseline: central;
  transition: opacity 200ms ease;
}

.chord-tip {
  position: absolute;
  top: 10px;
  left: 12px;
  padding: 8px 13px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: var(--shadow-sm);
  font-size: 12px;
  color: var(--ink);
  pointer-events: none;
}
</style>
