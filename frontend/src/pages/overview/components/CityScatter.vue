<script setup lang="ts">
/* ── CityScatter ────────────────────────────────────────────────────────
   The decision panel the page was missing: severity against movement. The map
   answers "where is it bad", the band answers "how do the provinces sit", and
   neither answers "which cities are bad *and* getting worse" — which is the
   question a reader actually acts on.

   x is the 24h change, y is the level, colour is the HJ 633 band, so a city in
   the top-right corner is polluted and rising. Only that quadrant gets name
   labels: labelling everything turns a scatter into a word cloud, and the rest of
   the roster is one hover away. No fit line and no r²: this is a position plot,
   not a claim that the change explains the level. */
import { computed, onMounted, ref } from "vue";
import { gsap, prefersReducedMotion } from "../../../lib/motion";
import { AQI_LEVEL_COLORS, MUTED_DATA_COLOR } from "../../../lib/palette";
import type { NationalCity } from "../provinces";
import { useElementSize } from "../../../lib/viz";

const props = withDefaults(
  defineProps<{ cities: NationalCity[]; focusId?: number | null }>(),
  { focusId: null },
);
const emit = defineEmits<{
  select: [id: number, name: string];
  pin: [id: number | null];
}>();

/* The two reference lines are the page's own vocabulary: ±8 µg/m³ is where
   changeState() starts calling it 上升/改善, and 100 is the 良 → 轻度污染 edge. */
const STEADY = 8;
const CONCERN_AQI = 100;
const MAX_LABELS = 5;

const plotEl = ref<HTMLElement | null>(null);
const size = useElementSize(plotEl);
/* Fixed height keeps the y-axis arithmetic honest; the CSS sets the same value so
   the resize observer reports a non-zero height on its first pass. */
const height = 300;

const PAD = { top: 16, right: 18, bottom: 40, left: 46 };

type Dot = {
  city: NationalCity;
  id: number;
  name: string;
  x: number;
  y: number;
  change: number;
  aqi: number;
  cx: number;
  cy: number;
  color: string;
};

const points = computed<NationalCity[]>(() => props.cities);

const plotted = computed(() =>
  points.value.filter((city) => city.china_aqi != null && city.pm25_change_24h != null),
);

const geometry = computed(() => {
  const w = size.value.w;
  const rows = plotted.value;
  if (!w || !rows.length) return null;
  const changes = rows.map((city) => city.pm25_change_24h as number);
  const aqis = rows.map((city) => city.china_aqi as number);
  const xPad = Math.max(6, (Math.max(...changes) - Math.min(...changes)) * 0.08);
  const xMin = Math.min(-STEADY, Math.min(...changes) - xPad);
  const xMax = Math.max(STEADY, Math.max(...changes) + xPad);
  const yMax = Math.max(CONCERN_AQI, Math.max(...aqis) * 1.06);
  const sx = (value: number) => PAD.left + ((value - xMin) / (xMax - xMin)) * (w - PAD.left - PAD.right);
  const sy = (value: number) => height - PAD.bottom - (value / yMax) * (height - PAD.top - PAD.bottom);
  return { w, xMin, xMax, yMax, sx, sy };
});

const dots = computed<Dot[]>(() => {
  const geo = geometry.value;
  if (!geo) return [];
  return plotted.value.map((city) => {
    const change = city.pm25_change_24h as number;
    const aqi = city.china_aqi as number;
    return {
      city,
      id: city.location_id,
      name: city.name,
      x: geo.sx(change),
      y: geo.sy(aqi),
      change,
      aqi,
      cx: geo.sx(change),
      cy: geo.sy(aqi),
      color: city.china_aqi_level
        ? (AQI_LEVEL_COLORS[city.china_aqi_level] ?? MUTED_DATA_COLOR)
        : MUTED_DATA_COLOR,
    };
  });
});

/* Labels are earned, not assigned: the polluted-and-rising corner first, then the
   pinned city wherever it sits. */
const labels = computed(() => {
  const ranked = dots.value
    .filter((dot) => dot.change >= STEADY && dot.aqi >= CONCERN_AQI)
    .sort((a, b) => b.aqi - a.aqi || b.change - a.change)
    .slice(0, MAX_LABELS);
  const pinned = dots.value.find((dot) => dot.id === props.focusId);
  if (pinned && !ranked.some((dot) => dot.id === pinned.id)) ranked.push(pinned);
  return ranked;
});

const yTicks = computed(() => {
  const geo = geometry.value;
  if (!geo) return [];
  return [0, 50, 100, 150, 200, 300, 400]
    .filter((value) => value <= geo.yMax)
    .map((value) => ({ value, y: geo.sy(value) }));
});

const xTicks = computed(() => {
  const geo = geometry.value;
  if (!geo) return [];
  // The ±8 pair is the first thing to go when the panel is narrow: it would
  // otherwise collide with 0 and with each other.
  const wanted = geo.w < 520 ? [-50, -25, 0, 25, 50] : [-50, -25, -STEADY, 0, STEADY, 25, 50];
  return wanted
    .filter((value) => value >= geo.xMin && value <= geo.xMax)
    .map((value) => ({ value, x: geo.sx(value) }));
});

const hovered = ref<number | null>(null);
const hoverDot = computed(() => dots.value.find((dot) => dot.id === hovered.value) ?? null);

function changeText(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}`;
}

function onBackground() {
  emit("pin", null);
}

onMounted(() => {
  if (prefersReducedMotion() || !plotEl.value) return;
  gsap.fromTo(
    plotEl.value.querySelectorAll(".cs-dot"),
    { scale: 0, opacity: 0, transformOrigin: "center" },
    { scale: 1, opacity: 1, duration: 0.45, stagger: 0.004, ease: "back.out(1.6)", delay: 0.15 },
  );
});
</script>

<template>
  <div class="city-scatter">
    <div ref="plotEl" class="cs-plot" @click.self="onBackground">
      <svg v-if="geometry" :width="geometry.w" :height="height" role="img"
        aria-label="城市：AQI 与 24h PM2.5 变化的分布">
        <!-- the corner that matters, stated once by the shading instead of a sentence -->
        <rect class="cs-quadrant" :x="geometry.sx(STEADY)" :y="PAD.top"
          :width="geometry.w - PAD.right - geometry.sx(STEADY)"
          :height="geometry.sy(CONCERN_AQI) - PAD.top" />

        <g class="cs-grid">
          <line v-for="tick in yTicks" :key="`y${tick.value}`"
            :x1="PAD.left" :x2="geometry.w - PAD.right" :y1="tick.y" :y2="tick.y" />
        </g>

        <g class="cs-axis">
          <text v-for="tick in yTicks" :key="`yt${tick.value}`" :x="PAD.left - 8" :y="tick.y + 3.5"
            text-anchor="end">{{ tick.value }}</text>
          <text v-for="tick in xTicks" :key="`xt${tick.value}`" :x="tick.x" :y="height - PAD.bottom + 15"
            text-anchor="middle">{{ tick.value > 0 ? `+${tick.value}` : tick.value }}</text>
          <text class="cs-unit" :x="geometry.w - PAD.right" :y="height - 8" text-anchor="end">
            ΔPM2.5 24h · µg/m³
          </text>
          <text class="cs-unit" :x="PAD.left - 8" :y="PAD.top - 4" text-anchor="end">AQI</text>
          <!-- Sample size sits on the plot, the way a corner note does on a paper
               figure: a ratio, so a city that could not be placed shows up here. -->
          <text class="cs-count" :x="geometry.w - PAD.right" :y="PAD.top + 4" text-anchor="end">
            n ＝ {{ plotted.length }} / {{ points.length }} 城
          </text>
        </g>

        <g class="cs-ref">
          <line :x1="geometry.sx(-STEADY)" :x2="geometry.sx(-STEADY)" :y1="PAD.top" :y2="height - PAD.bottom" />
          <line :x1="geometry.sx(STEADY)" :x2="geometry.sx(STEADY)" :y1="PAD.top" :y2="height - PAD.bottom" />
          <line :x1="PAD.left" :x2="geometry.w - PAD.right" :y1="geometry.sy(CONCERN_AQI)"
            :y2="geometry.sy(CONCERN_AQI)" />
        </g>

        <g class="cs-dots">
          <circle v-for="dot in dots" :key="dot.id" class="cs-dot" :cx="dot.cx" :cy="dot.cy" r="4.4"
            :fill="dot.color" :class="{ pinned: dot.id === focusId, faded: focusId != null && dot.id !== focusId }"
            @mouseenter="hovered = dot.id" @mouseleave="hovered = null"
            @click="emit('select', dot.id, dot.name)" />
        </g>

        <g class="cs-labels">
          <text v-for="dot in labels" :key="`l${dot.id}`" :x="dot.cx + 8" :y="dot.cy - 7"
            :class="{ pinned: dot.id === focusId }">{{ dot.name }}</text>
        </g>
      </svg>

      <div v-if="hoverDot" class="cs-tip" :style="{ left: `${hoverDot.cx - 8}px`, top: `${hoverDot.cy - 12}px` }">
        <strong>{{ hoverDot.name }}</strong>
        <span>{{ hoverDot.city.province ?? hoverDot.city.region }}</span>
        <span class="data-mono">{{ hoverDot.aqi }} {{ hoverDot.city.china_aqi_level ?? "—" }}</span>
        <span class="data-mono">PM2.5 {{ hoverDot.city.pm25?.toFixed(1) ?? "—" }}</span>
        <span class="data-mono">24h {{ changeText(hoverDot.change) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.city-scatter {
  min-width: 0;
  display: grid;
  gap: 10px;
}

.cs-plot {
  position: relative;
  min-width: 0;
  height: 300px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
  overflow: hidden;
}

.cs-quadrant {
  fill: color-mix(in srgb, var(--accent) 5%, transparent);
}

.cs-grid line {
  stroke: var(--hairline-soft);
  stroke-width: 1;
}

.cs-axis text {
  fill: var(--muted);
  font-size: 10.5px;
  font-variant-numeric: tabular-nums;
}

.cs-unit {
  fill: var(--faint);
  font-size: 10.5px;
}

.cs-count {
  fill: var(--faint);
  font-size: 10.5px;
  font-variant-numeric: tabular-nums;
}

.cs-ref line {
  stroke: var(--hairline-strong);
  stroke-width: 1;
  stroke-dasharray: 3 4;
}

.cs-dot {
  cursor: pointer;
  stroke: var(--sheet);
  stroke-width: 0.9;
  transition: opacity var(--duration-fast) ease;
}
.cs-dot.pinned {
  stroke: var(--ink);
  stroke-width: 1.6;
}
.cs-dot.faded {
  opacity: 0.45;
}

.cs-labels text {
  fill: var(--ink-secondary);
  font-size: 10.5px;
  font-weight: 600;
  paint-order: stroke;
  stroke: var(--sheet);
  stroke-width: 3;
  pointer-events: none;
}
.cs-labels text.pinned {
  fill: var(--ink);
}

.cs-tip {
  position: absolute;
  z-index: 2;
  transform: translate(-100%, -100%);
  display: grid;
  gap: 2px;
  padding: 9px 11px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: var(--sheet);
  box-shadow: var(--shadow-md);
  color: var(--ink-secondary);
  font-size: 11.5px;
  white-space: nowrap;
  pointer-events: none;
}
.cs-tip strong {
  color: var(--ink);
  font-size: 12.5px;
}
</style>
