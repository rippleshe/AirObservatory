<!-- PCAStructurePanel — the weather×pollutant structure quad, fully hand-drawn:
     scree lollipop, loadings heatmap, hourly-scored scatter (points coloured
     by hour of day with marginal histograms — the diurnal structure the old
     blue cloud hid), and a correlation matrix with strength filter chips. -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { useInView } from "../composables/useInView";
import { interpolateRgb } from "d3-interpolate";
import { gsap, prefersReducedMotion } from "../lib/motion";

type Structure = components["schemas"]["CityStructureResponse"];

const props = defineProps<{ structure: Structure }>();

const shell = ref<HTMLElement | null>(null);
const inView = useInView(shell);

const FEATURE_LABELS: Record<string, string> = {
  pm25: "PM2.5",
  pm10: "PM10",
  no2: "NO₂",
  o3: "O₃",
  so2: "SO₂",
  co: "CO",
  temperature_2m: "气温",
  relative_humidity_2m: "湿度",
  pressure_msl: "气压",
  precipitation: "降水",
  wind_speed_10m: "风速",
  wind_direction_sin: "风向 sin",
  wind_direction_cos: "风向 cos",
  boundary_layer_height: "边界层高度",
};

function featureLabel(name: string) {
  return FEATURE_LABELS[name] ?? name;
}

/* Diverging mix through a paper-white midpoint: negative pools blue,
   positive pools red, |v| carries the saturation. */
const POLE_NEG = "#2563eb";
const POLE_POS = "#dc2626";
const MID = "#f8fafc";

function diverging(v: number): string {
  const clamped = Math.max(-1, Math.min(1, v));
  return clamped < 0
    ? interpolateRgb(MID, POLE_NEG)(-clamped)
    : interpolateRgb(MID, POLE_POS)(clamped);
}

/* Cyclical hour colour: deep blue at midnight, amber at noon. */
const NIGHT = "#1e40af";
const NOON = "#f59e0b";

function hourColor(hour: number): string {
  const t = 0.5 - 0.5 * Math.cos((2 * Math.PI * hour) / 24);
  return interpolateRgb(NIGHT, NOON)(t);
}

const explained = computed(() => props.structure.explained_variance);
const loadings = computed(() => props.structure.loadings);
const scores = computed(() => props.structure.scores);
const correlation = computed(() => props.structure.correlation);
const pcKeys = computed(() => explained.value.map((step) => step.component));

const pcLabels = computed(() => ({
  x: explained.value[0] ? `主成分 1 · ${Math.round(explained.value[0].variance_ratio * 100)}%` : "",
  y: explained.value[1] ? `主成分 2 · ${Math.round(explained.value[1].variance_ratio * 100)}%` : "",
}));

/* ── tooltip plumbing (one floating readout for all four plots) ── */
const tip = ref<{ x: number; y: number; lines: string[] } | null>(null);

function showTip(event: MouseEvent, lines: string[]) {
  const bounds = shell.value?.getBoundingClientRect();
  tip.value = {
    x: event.clientX - (bounds?.left ?? 0),
    y: event.clientY - (bounds?.top ?? 0),
    lines,
  };
}

function hideTip() {
  tip.value = null;
}

/* ── scree ── */
const SCREE_W = 600;
const SCREE_H = 190;
const screeBars = computed(() => {
  const ev = explained.value;
  const max = Math.max(0.05, ...ev.map((step) => step.variance_ratio));
  const slot = (SCREE_W - 70) / Math.max(1, ev.length);
  return ev.map((step, i) => {
    const h = (step.variance_ratio / max) * (SCREE_H - 66);
    return {
      component: step.component,
      x: 46 + i * slot + slot * 0.3,
      w: slot * 0.4,
      y: SCREE_H - 34 - h,
      h,
      ratio: step.variance_ratio,
      cumulative: step.cumulative_ratio,
      stepX: 46 + i * slot + slot * 0.5,
      stepY: SCREE_H - 34 - (step.cumulative_ratio / 1.05) * (SCREE_H - 56),
    };
  });
});

/* ── loadings heatmap ── */
const LOAD_W = 620;
const LOAD_LBL = 108;
const loadCells = computed(() => {
  const keys = pcKeys.value;
  const rows = loadings.value;
  if (!keys.length || !rows.length) return [];
  const cw = (LOAD_W - LOAD_LBL - 16) / keys.length;
  const ch = 18;
  return rows.map((row, y) =>
    keys.map((key, x) => ({
      row: y,
      col: x,
      feature: row.feature,
      key,
      value: row.values[key] ?? 0,
      x: LOAD_LBL + x * cw,
      y: 8 + y * ch,
      w: cw,
      h: ch,
    })),
  );
});
const loadRowH = computed(() => (loadCells.value[0]?.length ?? 5) * 18 + 26);

const loadRowLabels = computed(() =>
  loadings.value.map((row, y) => ({
    label: featureLabel(row.feature),
    y: 8 + y * 18 + 13,
  })),
);

/* ── scores scatter with hour-of-day colour + marginals ── */
const SCORE_W = 620;
const SCORE_H = 280;
const MARG = 34;

const scorePoints = computed(() => {
  const pts = scores.value;
  if (pts.length < 2) return [];
  const xs = pts.map((p) => p.values.PC1 ?? 0);
  const ys = pts.map((p) => p.values.PC2 ?? 0);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);
  const spanX = Math.max(0.5, xMax - xMin);
  const spanY = Math.max(0.5, yMax - yMin);
  const plotW = SCORE_W - 52 - MARG;
  const plotH = SCORE_H - 40 - 10;
  const sx = (v: number) => 52 + ((v - xMin) / spanX) * plotW;
  const sy = (v: number) => 10 + plotH - ((v - yMin) / spanY) * plotH;
  return pts.map((point, i) => {
    const hour = new Date(point.time).getHours();
    return {
      id: i,
      x: sx(point.values.PC1 ?? 0),
      y: sy(point.values.PC2 ?? 0),
      color: hourColor(hour),
      hour,
      pc1: point.values.PC1 ?? 0,
      pc2: point.values.PC2 ?? 0,
      time: point.time,
    };
  });
});

/* Marginal histograms: 26 bins per axis, drawn as slim ink bars. */
const scoreMarginals = computed(() => {
  const pts = scorePoints.value;
  if (pts.length < 10) return null;
  const binCount = 26;
  const xHist = new Array(binCount).fill(0);
  const yHist = new Array(binCount).fill(0);
  for (const p of pts) {
    xHist[Math.min(binCount - 1, Math.floor((p.x / SCORE_W) * binCount))]! += 1;
    yHist[Math.min(binCount - 1, Math.floor((p.y / SCORE_H) * binCount))]! += 1;
  }
  const xMax = Math.max(...xHist);
  const yMax = Math.max(...yHist);
  return {
    x: xHist.map((count, i) => ({
      x: (i / binCount) * (SCORE_W - 52 - MARG) + 52,
      w: (SCORE_W - 52 - MARG) / binCount - 1,
      h: (count / xMax) * 22,
    })),
    y: yHist.map((count, i) => ({
      y: (i / binCount) * (SCORE_H - 50) + 10,
      h: (SCORE_H - 50) / binCount - 1,
      w: (count / yMax) * 22,
    })),
  };
});

const hourRamp = computed(() =>
  Array.from({ length: 24 }, (_, hour) => ({ hour, color: hourColor(hour) })),
);

function onScoreMove(event: MouseEvent) {
  const bounds = shell.value?.getBoundingClientRect();
  if (!bounds) return;
  const mx = ((event.clientX - bounds.left) / (bounds.width || 1)) * SCORE_W;
  const my = ((event.clientY - bounds.top) / (bounds.height || 1)) * SCORE_H;
  let best = -1;
  let bestDist = Infinity;
  scorePoints.value.forEach((p, i) => {
    const d = (p.x - mx) ** 2 + (p.y - my) ** 2;
    if (d < bestDist) {
      bestDist = d;
      best = i;
    }
  });
  if (best >= 0 && bestDist < 24 * 24) {
    const p = scorePoints.value[best]!;
    showTip(event, [
      new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", hour12: false }).format(new Date(p.time)),
      `主成分1 ${p.pc1.toFixed(2)} · 主成分2 ${p.pc2.toFixed(2)}`,
      `${p.hour}:00`,
    ]);
  } else {
    hideTip();
  }
}

/* ── correlation matrix + strength filters ── */
const CORR_W = 620;
const CORR_LBL = 96;
type CorrFilter = "strong-pos" | "strong-neg" | "weak" | null;
const corrFilter = ref<CorrFilter>(null);

const FILTERS: Array<{ id: Exclude<CorrFilter, null>; label: string }> = [
  { id: "strong-pos", label: "强正相关" },
  { id: "strong-neg", label: "强负相关" },
  { id: "weak", label: "弱相关" },
];

function toggleFilter(id: Exclude<CorrFilter, null>) {
  corrFilter.value = corrFilter.value === id ? null : id;
}

function inFilter(r: number): boolean {
  if (corrFilter.value === "strong-pos") return r >= 0.6;
  if (corrFilter.value === "strong-neg") return r <= -0.6;
  if (corrFilter.value === "weak") return Math.abs(r) < 0.3;
  return true;
}

const corrCells = computed(() => {
  const features = props.structure.meta.features;
  const rows = correlation.value;
  if (!features.length || !rows.length) return [];
  const n = features.length;
  const cw = (CORR_W - CORR_LBL - 12) / n;
  const ch = cw;
  const index = new Map(features.map((f, i) => [f, i]));
  const cells: Array<{
    x: number;
    y: number;
    rowFeature: string;
    colFeature: string;
    r: number;
    dim: boolean;
  }> = [];
  rows.forEach((row, y) => {
    features.forEach((feature, x) => {
      const r = row.values[feature] ?? 0;
      cells.push({
        x: CORR_LBL + x * cw,
        y: 6 + y * ch,
        rowFeature: row.feature,
        colFeature: feature,
        r,
        dim: !inFilter(r),
      });
    });
    void index;
  });
  return cells;
});

const corrSize = computed(() => {
  const n = props.structure.meta.features.length || 1;
  return { n, cell: (CORR_W - CORR_LBL - 12) / n, total: n * ((CORR_W - CORR_LBL - 12) / n) + 12 };
});

const corrLabels = computed(() => {
  const features = props.structure.meta.features;
  const cell = corrSize.value.cell;
  return {
    rows: features.map((f, y) => ({ label: featureLabel(f), y: 6 + y * cell + cell / 2 })),
    cols: features.map((f, x) => ({ label: featureLabel(f), x: CORR_LBL + x * cell + cell / 2 })),
  };
});

function onCorrCell(event: MouseEvent, cell: { rowFeature: string; colFeature: string; r: number }) {
  showTip(event, [
    `${featureLabel(cell.rowFeature)} × ${featureLabel(cell.colFeature)}`,
    `r = ${cell.r.toFixed(2)}`,
  ]);
}

/* ── entrance ── */
let played = false;
watch(inView, (visible) => {
  if (!visible || played || prefersReducedMotion()) return;
  played = true;
  requestAnimationFrame(() => {
    const groups = shell.value?.querySelectorAll<SVGGElement>(".quad-entrance");
    if (!groups?.length) return;
    groups.forEach((group, i) => {
      gsap.fromTo(
        group,
        { autoAlpha: 0, y: 12 },
        { autoAlpha: 1, y: 0, duration: 0.7, delay: i * 0.12, ease: "power2.out" },
      );
    });
  });
});

onMounted(() => {
  if (inView.value) {
    /* already on screen when mounted */
    played = true;
  }
});

onBeforeUnmount(() => {
  hideTip();
});
</script>

<template>
  <section ref="shell" class="structure-panel" @mouseleave="hideTip">
    <div class="structure-grid">
      <article>
        <span class="mini-label">解释方差</span>
        <svg :viewBox="`0 0 ${SCREE_W} ${SCREE_H}`" class="quad-svg">
          <g class="quad-entrance">
            <line class="axis" :x1="40" :x2="SCREE_W - 14" :y1="SCREE_H - 34" :y2="SCREE_H - 34" />
            <g v-for="bar in screeBars" :key="bar.component">
              <rect
                :x="bar.x" :y="bar.y" :width="bar.w" :height="bar.h" rx="2.5"
                fill="#0369a1" fill-opacity="0.85"
              />
              <text class="bar-value" :x="bar.x + bar.w / 2" :y="bar.y - 6">
                {{ Math.round(bar.ratio * 100) }}%
              </text>
              <text class="bar-key" :x="bar.x + bar.w / 2" :y="SCREE_H - 18">{{ bar.component }}</text>
              <circle v-if="bar.cumulative" :cx="bar.stepX" :cy="bar.stepY" r="3" class="step-dot" />
            </g>
            <path
              class="step-line"
              :d="screeBars.map((bar, i) => `${i === 0 ? 'M' : 'L'}${bar.stepX},${bar.stepY}`).join(' ')"
            />
          </g>
        </svg>
      </article>

      <article>
        <span class="mini-label">因子载荷</span>
        <svg :viewBox="`0 0 ${LOAD_W} ${loadRowH}`" class="quad-svg">
          <g class="quad-entrance">
            <g v-for="(cellRow, y) in loadCells" :key="`lr-${y}`">
              <rect
                v-for="cell in cellRow"
                :key="`${cell.row}-${cell.col}`"
                :x="cell.x" :y="cell.y" :width="cell.w - 1.5" :height="cell.h - 1.5" rx="2"
                :fill="diverging(cell.value)"
                @mouseenter="showTip($event, [featureLabel(cell.feature) + ' · ' + cell.key, `权重 ${cell.value.toFixed(3)}`])"
                @mousemove="showTip($event, [featureLabel(cell.feature) + ' · ' + cell.key, `权重 ${cell.value.toFixed(3)}`])"
                @mouseleave="hideTip"
              />
            </g>
            <text
              v-for="label in loadRowLabels"
              :key="`ll-${label.label}-${label.y}`"
              class="row-label"
              :x="LOAD_LBL - 8"
              :y="label.y"
            >{{ label.label }}</text>
            <text
              v-for="(key, x) in pcKeys"
              :key="`lc-${key}`"
              class="col-label"
              :x="LOAD_LBL + x * ((LOAD_W - LOAD_LBL - 16) / pcKeys.length) + ((LOAD_W - LOAD_LBL - 16) / pcKeys.length) / 2"
              :y="loadRowH - 8"
            >{{ key }}</text>
          </g>
        </svg>
      </article>

      <article>
        <span class="mini-label">分时投影</span>
        <svg :viewBox="`0 0 ${SCORE_W} ${SCORE_H}`" class="quad-svg" @mousemove="onScoreMove" @mouseleave="hideTip">
          <g class="quad-entrance">
            <g v-if="scoreMarginals">
              <rect
                v-for="(bar, i) in scoreMarginals.x"
                :key="`mx-${i}`"
                class="marginal"
                :x="bar.x" :y="10" :width="bar.w" :height="bar.h"
              />
              <rect
                v-for="(bar, i) in scoreMarginals.y"
                :key="`my-${i}`"
                class="marginal"
                :x="SCORE_W - MARG + 6" :y="bar.y" :width="bar.w" :height="bar.h"
              />
            </g>
            <line class="axis" :x1="52" :x2="SCORE_W - MARG" :y1="SCORE_H - 30" :y2="SCORE_H - 30" />
            <circle
              v-for="point in scorePoints"
              :key="point.id"
              :cx="point.x" :cy="point.y" r="2.1"
              :fill="point.color" fill-opacity="0.62"
            />
            <text class="pc-label x" :x="(52 + SCORE_W - MARG) / 2" :y="SCORE_H - 10">{{ pcLabels.x }}</text>
            <text class="pc-label y" :x="54" :y="24">{{ pcLabels.y }}</text>
          </g>
        </svg>
        <div class="hour-ramp" aria-hidden="true">
          <i v-for="slot in hourRamp" :key="slot.hour" :style="{ background: slot.color }"></i>
          <b>0时</b>
          <b class="mid">12时</b>
          <b class="end">24时</b>
        </div>
      </article>

      <article>
        <span class="mini-label">相关矩阵</span>
        <div class="filter-chips">
          <button
            v-for="filter in FILTERS"
            :key="filter.id"
            type="button"
            :class="{ active: corrFilter === filter.id }"
            @click="toggleFilter(filter.id)"
          >{{ filter.label }}</button>
        </div>
        <svg :viewBox="`0 0 ${CORR_W} ${corrSize.total + 14}`" class="quad-svg">
          <g class="quad-entrance">
            <rect
              v-for="(cell, i) in corrCells"
              :key="i"
              :x="cell.x" :y="cell.y" :width="corrSize.cell - 1.5" :height="corrSize.cell - 1.5" rx="1.5"
              :fill="diverging(cell.r)"
              :opacity="cell.dim ? 0.08 : 1"
              :stroke="cell.dim ? 'none' : 'none'"
              @mouseenter="onCorrCell($event, cell)"
              @mousemove="onCorrCell($event, cell)"
              @mouseleave="hideTip"
            />
            <text
              v-for="(label, i) in corrLabels.rows"
              :key="`cr-${i}`"
              class="row-label"
              :x="CORR_LBL - 6"
              :y="label.y"
            >{{ label.label }}</text>
            <text
              v-for="(label, i) in corrLabels.cols"
              :key="`cc-${i}`"
              class="col-label rot"
              :x="label.x"
              :y="corrSize.total + 10"
            >{{ label.label }}</text>
          </g>
        </svg>
      </article>
    </div>

    <div
      v-if="tip"
      class="quad-tip"
      :style="{ left: `${tip.x + 14}px`, top: `${tip.y + 12}px` }"
    >
      <span v-for="(line, i) in tip.lines" :key="i" :class="{ strong: i === 0 }">{{ line }}</span>
    </div>
  </section>
</template>

<style scoped>
.structure-panel {
  position: relative;
}

.structure-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 36px 44px;
}

.structure-grid article {
  min-width: 0;
  display: grid;
  gap: 8px;
  align-content: start;
}

.mini-label {
  color: var(--muted);
  font-size: 11px;
  font-weight: var(--fw-strong);
  letter-spacing: 0.18em;
  text-align: center;
}

.quad-svg {
  width: 100%;
  height: auto;
  display: block;
}

.axis {
  stroke: var(--hairline-strong);
}

.bar-value {
  fill: var(--ink-soft);
  font-family: var(--font-display);
  font-size: 10px;
  font-weight: 600;
  text-anchor: middle;
}

.bar-key {
  fill: var(--muted);
  font-family: var(--font-display);
  font-size: 10.5px;
  text-anchor: middle;
}

.step-dot {
  fill: #ffffff;
  stroke: #d97706;
  stroke-width: 1.6;
}

.step-line {
  fill: none;
  stroke: #d97706;
  stroke-width: 1.6;
}

.row-label {
  fill: var(--muted);
  font-family: var(--font-sans);
  font-size: 10.5px;
  text-anchor: end;
  dominant-baseline: central;
}

.col-label {
  fill: var(--muted);
  font-family: var(--font-sans);
  font-size: 10.5px;
  text-anchor: middle;
}

.col-label.rot {
  transform-origin: center;
}

.marginal {
  fill: var(--ink);
  fill-opacity: 0.09;
}

.pc-label {
  fill: var(--muted);
  font-family: var(--font-display);
  font-size: 10.5px;
}

.pc-label.x {
  text-anchor: middle;
}

.hour-ramp {
  display: flex;
  align-items: center;
  gap: 1px;
  padding: 2px 40px 0 52px;
  position: relative;
}

.hour-ramp i {
  flex: 1;
  height: 6px;
}

.hour-ramp b {
  position: absolute;
  top: 14px;
  font-size: 9.5px;
  color: var(--faint);
  font-weight: 500;
}

.hour-ramp b.mid {
  left: 50%;
  transform: translateX(-50%);
}

.hour-ramp b.end {
  right: 40px;
}

.filter-chips {
  display: flex;
  justify-content: center;
  gap: 8px;
}

.filter-chips button {
  padding: 4px 12px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-pill);
  background: var(--sheet);
  color: var(--muted);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-fast) ease;
}

.filter-chips button:hover {
  color: var(--ink);
  background: var(--sheet-soft);
}

.filter-chips button.active {
  background: var(--ink);
  border-color: var(--ink);
  color: #ffffff;
}

.quad-tip {
  position: absolute;
  z-index: 5;
  display: grid;
  gap: 2px;
  padding: 8px 12px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.96);
  box-shadow: var(--shadow-sm);
  font-size: 11.5px;
  color: var(--muted);
  pointer-events: none;
  white-space: nowrap;
}

.quad-tip .strong {
  color: var(--ink);
  font-weight: var(--fw-strong);
}

@media (max-width: 1180px) {
  .structure-grid {
    grid-template-columns: 1fr;
  }
}
</style>
