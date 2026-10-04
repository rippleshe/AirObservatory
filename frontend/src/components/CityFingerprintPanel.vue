<!-- CityFingerprintPanel — 31 cities in PC space, hand-drawn: each cluster
     wears a convex-hull membrane (the group shape reads before any label),
     isolated cities get greedy anti-collision name tags, and the variance
     story collapses into one cumulative strip. No chart library. -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { components } from "../api/schema";
import { gsap, prefersReducedMotion } from "../lib/motion";
import { clusterColor, FORECAST_COLOR, MODEL_COLOR, MUTED_DATA_COLOR } from "../lib/palette";
import { useElementSize } from "../lib/viz";

type Fingerprint = components["schemas"]["CityFingerprintResponse"];

const props = withDefaults(
  defineProps<{ fingerprint: Fingerprint; focusId?: number | null }>(),
  { focusId: null },
);
const emit = defineEmits<{
  select: [locationId: number, city: string];
}>();

const shell = ref<HTMLElement | null>(null);
const plotEl = ref<HTMLElement | null>(null);
const size = useElementSize(plotEl);
const hovered = ref<number | null>(null);

const FEATURE_LABELS: Record<string, string> = {
  pm25_mean: "PM2.5 均值",
  pm25_p90: "PM2.5 高值",
  pm25_std: "PM2.5 波动",
  pm10_mean: "PM10 均值",
  pm10_p90: "PM10 高值",
  no2_mean: "NO₂ 均值",
  no2_p90: "NO₂ 高值",
  o3_mean: "O₃ 均值",
  o3_p90: "O₃ 高值",
  o3_std: "O₃ 波动",
  so2_mean: "SO₂ 均值",
  co_mean: "CO 均值",
  temperature_mean: "平均气温",
  humidity_mean: "平均湿度",
  wind_speed_mean: "平均风速",
  boundary_layer_height_mean: "平均边界层高度",
  precipitation_hour_fraction: "降水小时占比",
  pm25_diurnal_amplitude: "PM2.5 日内起伏",
  corr_pm25_wind: "PM2.5 与风速",
  corr_pm25_boundary_layer: "PM2.5 与边界层",
  corr_o3_temperature: "O₃ 与气温",
};

function featureLabel(name: string) {
  return FEATURE_LABELS[name] ?? name;
}

const SIGMA_COOL = MODEL_COLOR;
const SIGMA_WARM = FORECAST_COLOR;
const SIGMA_ZERO = MUTED_DATA_COLOR;

function sigmaColor(z: number) {
  if (z <= -0.05) return SIGMA_COOL;
  if (z >= 0.05) return SIGMA_WARM;
  return SIGMA_ZERO;
}

const sigmaMax = computed(() => {
  let max = 1;
  for (const cluster of props.fingerprint.cluster_profiles) {
    for (const feature of cluster.top_features) {
      max = Math.max(max, Math.abs(feature.zscore));
    }
  }
  return max;
});

const explained = computed(() => props.fingerprint.explained_variance);

const PAD = 34;

type Dot = {
  id: number;
  name: string;
  province: string | null;
  cluster: number;
  x: number;
  y: number;
  sampleHours: number;
};

const geometry = computed(() => {
  const { w, h } = size.value;
  if (!w || !h || !props.fingerprint.points.length) return null;
  const xs = props.fingerprint.points.map((p) => p.values.PC1 ?? 0);
  const ys = props.fingerprint.points.map((p) => p.values.PC2 ?? 0);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);
  const spanX = Math.max(0.5, xMax - xMin);
  const spanY = Math.max(0.5, yMax - yMin);
  const sx = (v: number) => PAD + ((v - xMin) / spanX) * (w - PAD * 2);
  const sy = (v: number) => h - PAD - ((v - yMin) / spanY) * (h - PAD * 2);
  return { w, h, sx, sy, xMid: sx(0), yMid: sy(0) };
});

const dots = computed<Dot[]>(() => {
  const geo = geometry.value;
  if (!geo) return [];
  return props.fingerprint.points.map((point) => ({
    id: point.location_id,
    name: point.city,
    province: point.province ?? null,
    cluster: point.cluster,
    x: geo.sx(point.values.PC1 ?? 0),
    y: geo.sy(point.values.PC2 ?? 0),
    sampleHours: point.sample_hours,
  }));
});

/* Monotone-chain convex hull, expanded outward from the centroid so the
   membrane breathes instead of hugging the dots. */
function hullPath(points: Array<{ x: number; y: number }>): string {
  if (points.length < 3) return "";
  const sorted = [...points].sort((a, b) => a.x - b.x || a.y - b.y);
  const cross = (
    o: { x: number; y: number },
    a: { x: number; y: number },
    b: { x: number; y: number },
  ) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const lower: typeof sorted = [];
  for (const p of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2]!, lower[lower.length - 1]!, p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper: typeof sorted = [];
  for (let i = sorted.length - 1; i >= 0; i--) {
    const p = sorted[i]!;
    while (upper.length >= 2 && cross(upper[upper.length - 2]!, upper[upper.length - 1]!, p) <= 0) upper.pop();
    upper.push(p);
  }
  const hull = lower.slice(0, -1).concat(upper.slice(0, -1));
  if (hull.length < 3) return "";
  const cx = hull.reduce((sum, p) => sum + p.x, 0) / hull.length;
  const cy = hull.reduce((sum, p) => sum + p.y, 0) / hull.length;
  const grown = hull.map((p) => {
    const dx = p.x - cx;
    const dy = p.y - cy;
    const dist = Math.max(1, Math.hypot(dx, dy));
    return { x: cx + (dx / dist) * (dist + 16), y: cy + (dy / dist) * (dist + 16) };
  });
  return grown.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ") + " Z";
}

const clusters = computed(() => {
  const byId = new Map<number, Dot[]>();
  for (const dot of dots.value) {
    const list = byId.get(dot.cluster) ?? [];
    list.push(dot);
    byId.set(dot.cluster, list);
  }
  return [...byId.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([cluster, list]) => ({
      cluster,
      color: clusterColor(cluster),
      path: hullPath(list),
      centroid: {
        x: list.reduce((sum, p) => sum + p.x, 0) / list.length,
        y: list.reduce((sum, p) => sum + p.y, 0) / list.length,
      },
    }));
});

/* Greedy tags: most-isolated cities claim a label first, later ones only if
   the text box stays clear — dense cores stay clean, outliers stay named. */
const labels = computed(() => {
  const placed: Array<{ x: number; y: number; name: string; cluster: number }> = [];
  const boxes: Array<{ x: number; y: number; w: number; h: number }> = [];
  const isolation = (dot: Dot) => {
    let min = Infinity;
    for (const other of dots.value) {
      if (other.id === dot.id) continue;
      min = Math.min(min, Math.hypot(other.x - dot.x, other.y - dot.y));
    }
    return min;
  };
  const ranked = [...dots.value].sort((a, b) => isolation(b) - isolation(a));
  for (const dot of ranked) {
    if (placed.length >= 14) break;
    const w = dot.name.length * 11 + 10;
    /* keep the tag inside the plot: edge cities clamp instead of clipping */
    const lx = Math.min(dot.x + 9, (geometry.value?.w ?? 0) - w - 6);
    const box = { x: lx, y: dot.y - 21, w, h: 15 };
    if (boxes.some((b) => !(box.x + box.w + 4 <= b.x || b.x + b.w + 4 <= box.x || box.y + box.h + 3 <= b.y || b.y + b.h + 3 <= box.y))) continue;
    boxes.push(box);
    placed.push({ x: lx, y: dot.y - 9, name: dot.name, cluster: dot.cluster });
  }
  return placed;
});

const varianceStrip = computed(() => {
  const ev = explained.value;
  const total = ev.reduce((sum, step) => sum + step.variance_ratio, 0);
  if (total <= 0) return [];
  let acc = 0;
  return ev.map((step) => {
    const from = acc / total;
    acc += step.variance_ratio;
    return {
      component: step.component,
      share: step.variance_ratio / total,
      ratio: step.variance_ratio,
      /* the strip widths normalise to 100%, but the readout stays honest:
         cumulative is the share of TOTAL variance the components explain. */
      cumulative: step.cumulative_ratio,
      from,
    };
  });
});

const pcLabels = computed(() => ({
  x: explained.value[0] ? `主成分 1 · ${Math.round(explained.value[0].variance_ratio * 100)}%` : "",
  y: explained.value[1] ? `主成分 2 · ${Math.round(explained.value[1].variance_ratio * 100)}%` : "",
}));

const hoverDot = computed(() => dots.value.find((d) => d.id === hovered.value) ?? null);

function onDotEnter(id: number) {
  hovered.value = id;
}

let played = false;
watch(dots, (next) => {
  if (!next.length || played || prefersReducedMotion()) return;
  played = true;
  requestAnimationFrame(() => {
    const membranes = shell.value?.querySelectorAll<SVGPathElement>(".membrane");
    if (membranes?.length) {
      membranes.forEach((path, i) => {
        const cluster = clusters.value[i];
        gsap.fromTo(
          path,
          { opacity: 0 },
          {
            opacity: 1,
            duration: 0.9,
            delay: i * 0.15,
            ease: "power2.out",
            svgOrigin: `${cluster?.centroid.x ?? 0} ${cluster?.centroid.y ?? 0}`,
            scale: 0.85,
          },
        );
      });
    }
    const nodes = shell.value?.querySelectorAll<SVGCircleElement>(".city-dot");
    if (nodes?.length) {
      gsap.fromTo(
        nodes,
        { scale: 0, opacity: 0, transformOrigin: "center" },
        { scale: 1, opacity: 1, duration: 0.5, stagger: 0.02, delay: 0.25, ease: "back.out(1.8)" },
      );
    }
  });
});


</script>

<template>
  <section ref="shell" class="fingerprint-panel">
    <div class="fingerprint-layout">
      <article ref="plotEl" class="scatter-cell">
        <svg :width="geometry?.w" :height="geometry?.h" v-if="geometry" role="img" aria-label="城市指纹投影">
          <line class="axis-zero" :x1="geometry.xMid" :x2="geometry.xMid" :y1="PAD - 12" :y2="geometry.h - PAD + 12" />
          <line class="axis-zero" :x1="PAD - 12" :x2="geometry.w - PAD + 12" :y1="geometry.yMid" :y2="geometry.yMid" />

          <path
            v-for="cluster in clusters"
            :key="`hull-${cluster.cluster}`"
            class="membrane"
            :d="cluster.path"
            :fill="cluster.color"
            fill-opacity="0.08"
            :stroke="cluster.color"
            stroke-opacity="0.35"
            stroke-width="1.2"
          />

          <circle
            v-for="dot in dots"
            :key="dot.id"
            class="city-dot"
            :cx="dot.x"
            :cy="dot.y"
            r="5.5"
            :fill="clusterColor(dot.cluster)"
            :stroke="hovered === dot.id || focusId === dot.id ? 'var(--ink)' : '#ffffff'"
            :stroke-width="hovered === dot.id || focusId === dot.id ? 2 : 1.5"
            :opacity="focusId != null && focusId !== dot.id ? 0.18 : 1"
            @mouseenter="onDotEnter(dot.id)"
            @mouseleave="hovered = null"
            @click="emit('select', dot.id, dot.name)"
          />

          <text
            v-for="label in labels"
            :key="`l-${label.name}`"
            class="dot-label"
            :x="label.x"
            :y="label.y"
            :fill="clusterColor(label.cluster)"
          >{{ label.name }}</text>

          <text class="pc-label x" :x="geometry.w / 2" :y="geometry.h - 8">{{ pcLabels.x }}</text>
          <text class="pc-label y" :x="12" :y="PAD - 14">{{ pcLabels.y }}</text>
        </svg>

        <div v-if="hoverDot" class="scatter-tip">
          <strong>{{ hoverDot.name }}</strong>
          <span>{{ hoverDot.province ?? "" }} · 第 {{ hoverDot.cluster }} 组</span>
          <span class="data-mono">{{ hoverDot.sampleHours }}h 样本</span>
        </div>

      </article>

      <div class="cluster-chips">
        <span v-for="cluster in clusters" :key="`chip-${cluster.cluster}`">
          <i :style="{ background: cluster.color }"></i>第 {{ cluster.cluster }} 组
        </span>
      </div>

      <aside class="fingerprint-ledger">
        <section>
          <div v-if="varianceStrip.length" class="variance-strip">
            <div class="strip-bar">
              <span
                v-for="seg in varianceStrip"
                :key="seg.component"
                :style="{
                  width: `${seg.share * 100}%`,
                  left: `${seg.from * 100}%`,
                  background: `rgba(2, 132, 199, ${0.32 + seg.from * 0.6})`,
                }"
              ></span>
            </div>
            <div class="strip-labels">
              <span
                v-for="seg in varianceStrip"
                :key="`sl-${seg.component}`"
                class="data-mono"
              >{{ seg.component }} {{ Math.round(seg.ratio * 100) }}%</span>
            </div>
            <div class="strip-cumulative data-mono">累计 {{ Math.round((varianceStrip.at(-1)?.cumulative ?? 0) * 100) }}%</div>
          </div>
        </section>

        <section class="cluster-section">
          <div class="cluster-list">
            <div
              v-for="cluster in fingerprint.cluster_profiles"
              :key="cluster.cluster"
              class="cluster-row"
            >
              <div class="cluster-title">
                <i :style="{ background: clusterColor(cluster.cluster) }"></i>
                <b>第 {{ cluster.cluster }} 组</b>
                <span>{{ cluster.city_count }} 城</span>
              </div>

              <div class="sigma-list">
                <div
                  v-for="feature in cluster.top_features"
                  :key="feature.feature"
                  class="sigma-row"
                >
                  <span class="sigma-name">{{ featureLabel(feature.feature) }}</span>
                  <div class="sigma-track">
                    <i class="sigma-zero"></i>
                    <i
                      class="sigma-bar"
                      :style="{
                        background: sigmaColor(feature.zscore),
                        left: feature.zscore >= 0 ? '50%' : undefined,
                        right: feature.zscore < 0 ? '50%' : undefined,
                        width: (Math.abs(feature.zscore) / sigmaMax) * 50 + '%',
                      }"
                    ></i>
                  </div>
                  <b class="sigma-value data-mono" :style="{ color: sigmaColor(feature.zscore) }">
                    {{ feature.zscore > 0 ? "+" : "" }}{{ feature.zscore.toFixed(1) }}σ
                  </b>
                </div>
              </div>
            </div>
          </div>
        </section>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.fingerprint-panel {
  width: 100%;
}

.fingerprint-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(280px, 1fr);
  gap: 32px;
  align-items: start;
}

.scatter-cell {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 10;
  min-height: 480px;
}

.axis-zero {
  stroke: var(--hairline);
  stroke-dasharray: 3 4;
}

.membrane {
  stroke-linejoin: round;
}

.city-dot {
  cursor: pointer;
}

.dot-label {
  font-family: var(--font-sans);
  font-size: 10.5px;
  font-weight: 600;
  paint-order: stroke;
  stroke: rgba(255, 255, 255, 0.9);
  stroke-width: 3px;
  stroke-linejoin: round;
  pointer-events: none;
}

.pc-label {
  fill: var(--muted);
  font-family: var(--font-display);
  font-size: 10.5px;
}

.pc-label.x {
  text-anchor: middle;
}

.scatter-tip {
  position: absolute;
  top: 12px;
  left: 12px;
  display: grid;
  gap: 2px;
  padding: 10px 13px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.96);
  box-shadow: var(--shadow-sm);
  font-size: 11.5px;
  color: var(--muted);
  pointer-events: none;
}

.scatter-tip strong {
  color: var(--ink);
  font-size: 13px;
}

.cluster-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  padding-top: 10px;
  font-size: 11px;
  color: var(--ink-soft);
}

.cluster-chips span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.cluster-chips i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.variance-strip {
  display: grid;
  gap: 8px;
  padding: 4px 0 10px;
}

.strip-bar {
  position: relative;
  height: 10px;
  border-radius: var(--radius-pill);
  background: var(--canvas-subtle);
  overflow: hidden;
}

.strip-bar span {
  position: absolute;
  top: 0;
  bottom: 0;
}

.strip-labels {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  color: var(--muted);
  font-size: 10px;
}

.strip-cumulative {
  color: var(--ink-soft);
  font-size: 11px;
}

.cluster-section {
  border-top: 1px solid var(--hairline);
  padding-top: 12px;
}


.fingerprint-ledger {
  min-width: 0;
}

.fingerprint-ledger > section {
  padding: 18px 4px;
}

.cluster-list {
  display: grid;
}

.cluster-row {
  padding: 14px 0;
  border-top: 1px solid var(--hairline-soft);
}

.cluster-row:first-child {
  border-top: 0;
  padding-top: 2px;
}

.cluster-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cluster-title i {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.cluster-title b {
  color: var(--ink);
  font-size: var(--fs-label);
  font-weight: var(--fw-strong);
}

.cluster-title span {
  margin-left: auto;
  color: var(--muted);
  font-size: var(--fs-label);
}

.sigma-list {
  margin-top: 10px;
  display: grid;
  gap: 7px;
}

.sigma-row {
  display: grid;
  grid-template-columns: 8.5em minmax(0, 1fr) 3.6em;
  align-items: center;
  gap: 10px;
}

.sigma-name {
  color: var(--muted);
  font-size: var(--fs-label);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sigma-track {
  position: relative;
  height: 12px;
  border-radius: 2px;
  background: var(--sheet-sunken);
}

.sigma-zero {
  position: absolute;
  top: -2px;
  bottom: -2px;
  left: 50%;
  width: 1px;
  background: var(--hairline-strong);
}

.sigma-bar {
  position: absolute;
  top: 1px;
  bottom: 1px;
  border-radius: 2px;
}

.sigma-value {
  text-align: right;
  font-size: var(--fs-label);
  font-weight: var(--fw-strong);
}

/* The scatter+ledger pairing follows the PANEL's own width, not the
   viewport: inside a duo column it must keep two columns down to ~900px
   of its own box, then stack. */
.fingerprint-panel {
  container-type: inline-size;
}

@container (max-width: 680px) {
  .fingerprint-layout {
    grid-template-columns: 1fr;
  }
}
</style>
