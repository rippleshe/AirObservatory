<!-- WaterfallChart — how the month was built: the first day's level, every
     day's delta stacked as a floating step, and the closing level. Rising
     steps burn orange, falling steps cool green; totals take the PM2.5 band
     colour they actually reached. Hand-written SVG. -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { gsap, prefersReducedMotion } from "../lib/motion";
import { CHANGE_COLORS, pm25Color } from "../lib/palette";
import { useElementSize } from "../lib/viz";

const props = defineProps<{
  days: string[];
  values: Array<number | null>;
}>();

const shell = ref<HTMLElement | null>(null);
const size = useElementSize(shell);
const hover = ref<number | null>(null);

const PAD = { top: 16, right: 12, bottom: 30, left: 44 };

type Step = {
  label: string;
  kind: "total" | "delta";
  from: number;
  to: number;
  color: string;
};

const steps = computed<Step[]>(() => {
  const out: Step[] = [];
  let previous: number | null = null;
  props.values.forEach((value, i) => {
    const label = props.days[i] ?? "";
    if (value == null) return;
    if (previous == null) {
      out.push({ label, kind: "total", from: 0, to: value, color: pm25Color(value) });
      previous = value;
      return;
    }
    const delta = value - previous;
    const to = previous + delta;
    out.push({
      label,
      kind: "delta",
      from: previous,
      to,
      color: delta >= 0 ? CHANGE_COLORS["上升"] : CHANGE_COLORS["改善"],
    });
    previous = to;
  });
  return out;
});

const yMax = computed(() => {
  let peak = 10;
  for (const step of steps.value) peak = Math.max(peak, step.from, step.to);
  return peak * 1.08;
});

const geometry = computed(() => {
  const { w, h } = size.value;
  if (!w || !h || steps.value.length < 2) return null;
  const innerW = w - PAD.left - PAD.right;
  const innerH = h - PAD.top - PAD.bottom;
  const n = steps.value.length;
  const slot = innerW / n;
  const barW = Math.max(2.5, slot * 0.62);
  const x = (i: number) => PAD.left + i * slot + (slot - barW) / 2;
  const y = (v: number) => PAD.top + innerH - (v / yMax.value) * innerH;
  return { w, h, innerW, innerH, slot, barW, x, y, n };
});

const bars = computed(() => {
  const geo = geometry.value;
  if (!geo) return [];
  return steps.value.map((step, i) => {
    const top = geo.y(Math.max(step.from, step.to));
    const bottom = geo.y(Math.min(step.from, step.to));
    return {
      ...step,
      i,
      x: geo.x(i),
      y: top,
      height: Math.max(1.5, bottom - top),
      color: step.kind === "total" ? step.color : step.color,
    };
  });
});

const connectors = computed(() => {
  const geo = geometry.value;
  if (!geo) return [];
  const lines: Array<{ x1: number; x2: number; y: number }> = [];
  for (let i = 1; i < bars.value.length; i++) {
    const prev = bars.value[i - 1]!;
    const cur = bars.value[i]!;
    lines.push({ x1: prev.x + geo.barW, x2: cur.x, y: geo.y(prev.to) });
  }
  return lines;
});

const gridLines = computed(() => {
  const geo = geometry.value;
  if (!geo) return [];
  const step = yMax.value > 200 ? 50 : yMax.value > 80 ? 25 : 10;
  const out: Array<{ y: number; v: number }> = [];
  for (let v = 0; v <= yMax.value; v += step) out.push({ y: geo.y(v), v });
  return out;
});

const xTicks = computed(() =>
  bars.value.filter((_, i) => i % 5 === 0 || i === bars.value.length - 1),
);

function fmtDay(label: string) {
  return label.slice(5).replace("-", "/");
}

const hoverInfo = computed(() => {
  if (hover.value == null) return null;
  const bar = bars.value[hover.value];
  if (!bar) return null;
  return {
    label: bar.label,
    kind: bar.kind,
    delta: bar.to - bar.from,
    level: bar.to,
  };
});

let played = false;
watch(bars, (next) => {
  if (!next.length || played || prefersReducedMotion()) return;
  played = true;
  requestAnimationFrame(() => {
    const nodes = shell.value?.querySelectorAll<SVGRectElement>(".wf-bar");
    if (!nodes?.length) return;
    gsap.fromTo(
      nodes,
      { scaleY: 0, transformOrigin: "center bottom" },
      {
        scaleY: 1,
        duration: 0.7,
        stagger: 0.02,
        ease: "power2.out",
      },
    );
  });
});
</script>

<template>
  <div ref="shell" class="waterfall" @mouseleave="hover = null">
    <svg :width="geometry?.w" :height="geometry?.h" v-if="geometry">
      <g class="grid">
        <g v-for="line in gridLines" :key="line.v">
          <line :x1="PAD.left" :x2="PAD.left + geometry.innerW" :y1="line.y" :y2="line.y" />
          <text :x="PAD.left - 8" :y="line.y">{{ line.v }}</text>
        </g>
      </g>

      <line
        v-for="(line, i) in connectors"
        :key="`c-${i}`"
        class="connector"
        :x1="line.x1" :x2="line.x2" :y1="line.y" :y2="line.y"
      />

      <rect
        v-for="bar in bars"
        :key="bar.i"
        class="wf-bar"
        :class="{ dim: hover != null && hover !== bar.i }"
        :x="bar.x"
        :y="bar.y"
        :width="geometry.barW"
        :height="bar.height"
        :fill="bar.color"
        @mouseenter="hover = bar.i"
      />

      <g class="ticks">
        <text
          v-for="bar in xTicks"
          :key="`t-${bar.i}`"
          :x="bar.x + geometry.barW / 2"
          :y="geometry.h - PAD.bottom + 16"
        >{{ fmtDay(bar.label) }}</text>
      </g>
    </svg>

    <div v-if="hoverInfo" class="wf-tip">
      <span class="data-mono">{{ fmtDay(hoverInfo.label) }}</span>
      <span v-if="hoverInfo.kind === 'delta'">
        Δ <b :style="{ color: hoverInfo.delta >= 0 ? CHANGE_COLORS['上升'] : CHANGE_COLORS['改善'] }">
          {{ hoverInfo.delta >= 0 ? "+" : "" }}{{ hoverInfo.delta.toFixed(1) }}
        </b>
      </span>
      <span>→ <b>{{ hoverInfo.level.toFixed(1) }}</b> µg/m³</span>
    </div>
  </div>
</template>

<style scoped>
.waterfall {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 260px;
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

.connector {
  stroke: var(--hairline-strong);
  stroke-dasharray: 2 3;
}

.wf-bar {
  cursor: pointer;
  transition: opacity 180ms ease;
}

.wf-bar.dim {
  opacity: 0.35;
}

.ticks text {
  fill: var(--muted);
  font-family: var(--font-display);
  font-size: 10px;
  text-anchor: middle;
}

.wf-tip {
  position: absolute;
  top: 8px;
  right: 12px;
  display: flex;
  gap: 12px;
  padding: 7px 12px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: var(--shadow-sm);
  font-size: 11.5px;
  color: var(--ink-soft);
  pointer-events: none;
}
</style>
