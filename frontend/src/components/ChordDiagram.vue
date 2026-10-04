<!-- ChordDiagram — province PM2.5 synchrony as a true ribbon chord: every
     correlation is a filled two-arc ribbon (width ∝ |r|, gradient running
     source→target colour), nodes are degree-weighted arcs ordered by load so
     the ring reads as a pollution gradient. Hover lifts adjacency. -->
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
    focusId?: number | null;
  }>(),
  { threshold: 0.55, maxEdges: 110, focusId: null },
);

const emit = defineEmits<{ select: [id: number, name: string] }>();

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

type Ribbon = {
  index: number;
  source: ChordNode;
  target: ChordNode;
  r: number;
  d: string;
  gradId: string;
  from: string;
  to: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  opacity: number;
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
  const n = rows.length;
  return rows.map((row, i) => ({
    ...row,
    color: pm25Color(row.mean),
    angle: (i / n) * 2 * Math.PI - Math.PI / 2,
    degree: 1,
  }));
});

/* Hover wins, but a pinned city elsewhere on the page keeps its adjacency
   lifted here too — one focus, every view answers. */
const activeName = computed(() => {
  if (hoveredNode.value != null) return hoveredNode.value;
  if (props.focusId == null) return null;
  return nodes.value.find((node) => node.id === props.focusId)?.name ?? null;
});

const ribbons = computed<Ribbon[]>(() => {
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
  for (const node of list) node.degree = 0.6 + (strength.get(node.id) ?? 0) / maxStrength;

  const point = (angle: number, radius: number): [number, number] => [
    geo.cx + radius * Math.cos(angle),
    geo.cy + radius * Math.sin(angle),
  ];

  return kept.map((edge, index) => {
    const wa = 0.02 * edge.a.degree;
    const wb = 0.02 * edge.b.degree;
    const [ax0, ay0] = point(edge.a.angle - wa, geo.R);
    const [ax1, ay1] = point(edge.a.angle + wa, geo.R);
    const [bx1, by1] = point(edge.b.angle + wb, geo.R);
    const [bx0, by0] = point(edge.b.angle - wb, geo.R);
    /* Control points pulled hard toward the centre give the classic chord
       bow without a full crossing at the origin. */
    const c1: [number, number] = [geo.cx + (ax1 - geo.cx) * 0.14, geo.cy + (ay1 - geo.cy) * 0.14];
    const c2: [number, number] = [geo.cx + (bx1 - geo.cx) * 0.14, geo.cy + (by1 - geo.cy) * 0.14];
    const c3: [number, number] = [geo.cx + (bx0 - geo.cx) * 0.14, geo.cy + (by0 - geo.cy) * 0.14];
    const c4: [number, number] = [geo.cx + (ax0 - geo.cx) * 0.14, geo.cy + (ay0 - geo.cy) * 0.14];
    const large = 0;
    const d = [
      `M${ax0.toFixed(1)},${ay0.toFixed(1)}`,
      `A${geo.R},${geo.R} 0 ${large} 1 ${ax1.toFixed(1)},${ay1.toFixed(1)}`,
      `C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${bx1.toFixed(1)},${by1.toFixed(1)}`,
      `A${geo.R},${geo.R} 0 ${large} 1 ${bx0.toFixed(1)},${by0.toFixed(1)}`,
      `C${c3[0].toFixed(1)},${c3[1].toFixed(1)} ${c4[0].toFixed(1)},${c4[1].toFixed(1)} ${ax0.toFixed(1)},${ay0.toFixed(1)}`,
      "Z",
    ].join(" ");
    const [mx1, my1] = point(edge.a.angle, geo.R);
    const [mx2, my2] = point(edge.b.angle, geo.R);
    return {
      index,
      source: edge.a,
      target: edge.b,
      r: edge.r,
      d,
      gradId: `chord-grad-${index}`,
      from: edge.a.color,
      to: edge.b.color,
      x1: mx1,
      y1: my1,
      x2: mx2,
      y2: my2,
      opacity: Math.min(0.75, 0.18 + (edge.r - props.threshold) * 1.1),
    };
  });
});

function arcPath(node: ChordNode): string {
  const geo = geometry.value;
  if (!geo) return "";
  const span = 0.05 * node.degree;
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

const hoverTip = computed(() => {
  if (hoveredEdge.value != null) {
    const edge = ribbons.value[hoveredEdge.value];
    if (edge) return `${edge.source.name} ↔ ${edge.target.name} · r=${edge.r.toFixed(2)}`;
  }
  if (hoveredNode.value != null) {
    const node = nodes.value.find((n) => n.name === hoveredNode.value);
    if (node) return `${node.name} · 30 天均值 ${node.mean.toFixed(1)} µg/m³`;
  }
  return null;
});

let swept = false;
watch(ribbons, (next) => {
  if (!next.length || swept || prefersReducedMotion()) return;
  swept = true;
  requestAnimationFrame(() => {
    const group = shell.value?.querySelector<SVGGElement>(".chord-plot");
    if (!group) return;
    gsap.fromTo(
      group,
      { rotation: -40, opacity: 0, svgOrigin: `${geometry.value?.cx ?? 0} ${geometry.value?.cy ?? 0}` },
      { rotation: 0, opacity: 1, duration: 1.5, ease: "power3.out" },
    );
  });
});
</script>

<template>
  <div ref="shell" class="chord-diagram">
    <svg :width="size.w" :height="size.h">
      <defs>
        <linearGradient
          v-for="ribbon in ribbons"
          :key="ribbon.gradId"
          :id="ribbon.gradId"
          gradientUnits="userSpaceOnUse"
          :x1="ribbon.x1" :y1="ribbon.y1" :x2="ribbon.x2" :y2="ribbon.y2"
        >
          <stop offset="0%" :stop-color="ribbon.from" />
          <stop offset="100%" :stop-color="ribbon.to" />
        </linearGradient>
      </defs>

      <circle :cx="geometry?.cx" :cy="geometry?.cy" :r="geometry?.R" class="guide" />

      <g class="chord-plot">
        <path
          v-for="ribbon in ribbons"
          :key="ribbon.index"
          class="chord-ribbon"
          :d="ribbon.d"
          :fill="`url(#${ribbon.gradId})`"
          :style="{
            opacity: activeName != null
              ? (ribbon.source.name === activeName || ribbon.target.name === activeName ? 0.9 : 0.04)
              : (hoveredEdge === ribbon.index ? 0.95 : ribbon.opacity),
          }"
          @mouseenter="hoveredEdge = ribbon.index"
          @mouseleave="hoveredEdge = null"
        />
      </g>

      <g
        v-for="node in nodes"
        :key="node.id"
        class="node"
        :class="{ 'node-focus': focusId === node.id }"
        @mouseenter="hoveredNode = node.name"
        @mouseleave="hoveredNode = null"
        @click.stop="emit('select', node.id, node.name)"
      >
        <path :d="arcPath(node)" :fill="node.color" />
        <text
          class="node-label"
          :x="geometry!.cx + (geometry!.R + 20) * Math.cos(node.angle)"
          :y="geometry!.cy + (geometry!.R + 20) * Math.sin(node.angle)"
          :text-anchor="labelAnchor(node)"
          :transform="labelTransform(node)"
          :style="{ opacity: activeName && activeName !== node.name ? 0.25 : 0.9 }"
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

.chord-ribbon {
  cursor: pointer;
  transition: opacity 220ms ease;
}

.node {
  cursor: pointer;
}

.node.node-focus > path {
  stroke: var(--ink);
  stroke-width: 1.4;
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
