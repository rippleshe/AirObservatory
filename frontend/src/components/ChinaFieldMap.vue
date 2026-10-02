<script setup lang="ts">
/* ── ChinaFieldMap ──────────────────────────────────────────────────────
   An authored atlas plate, not a chart-library default. d3-geo draws the
   geometry (Albers-style equal-area conic — the projection China maps are
   actually printed with), Vue renders the SVG, d3-zoom supplies the
   gestures. Layers: ocean graticule → lifted landmass (dot-grid atlas
   texture + soft shadow) → province hairlines → city marks with sonar
   halos on the worst provinces → severity-ranked collision-free labels.
   Colours still come from the shared palette; the map owns no hues. */
import { geoConicEqualArea, geoGraticule, geoPath } from "d3-geo";
import { select } from "d3-selection";
import { easeCubicOut } from "d3-ease";
import "d3-transition";
import { zoom as d3Zoom, zoomIdentity, type ZoomBehavior, type ZoomTransform } from "d3-zoom";
import type { Feature, MultiPolygon, Polygon } from "geojson";
import { Minus, Plus, RotateCcw } from "lucide-vue-next";
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";
import { aqiColor, changeColor, changeState, pm25Color } from "../lib/palette";
import type { NationalCity } from "../lib/provinces";

type MapMetric = "aqi" | "pm25" | "change";

type ProvinceFeature = Feature<Polygon | MultiPolygon, { name?: string; adcode?: number }>;

const props = withDefaults(
  defineProps<{
    cities: NationalCity[];
    metric?: MapMetric;
  }>(),
  { metric: "aqi" },
);
const emit = defineEmits<{ select: [id: number, name: string] }>();

const el = ref<HTMLDivElement | null>(null);
const svgEl = ref<SVGSVGElement | null>(null);
const size = ref({ w: 0, h: 0 });
const transform = ref<ZoomTransform>(zoomIdentity);
const mapError = ref(false);
const wide = ref(true);
const hoveredProvince = ref<string | null>(null);
const hoveredCity = ref<NationalCity | null>(null);

const provinces = shallowRef<ProvinceFeature[] | null>(null);

let observer: ResizeObserver | null = null;
let zoomBehavior: ZoomBehavior<SVGSVGElement, unknown> | null = null;

/* ── projection & frame ─────────────────────────────────────────────── */

const projection = computed(() => {
  const features = provinces.value;
  if (!features || !size.value.w || !size.value.h) return null;
  // Equal-area conic with standard parallels tuned for China's latitudes;
  // fitExtent leaves room for the plate's inner rule and the label field.
  // The fit targets the mainland only — the nine-dash feature reaches down
  // to 3°N and would shrink and off-centre the whole plate.
  const pad = wide.value ? 30 : 14;
  const fitFeatures = features.filter((feature) => Boolean(feature.properties?.name));
  const proj = geoConicEqualArea().parallels([25, 47]).rotate([-105, 0]);
  proj.fitExtent(
    [
      [pad, pad],
      [size.value.w - pad, size.value.h - pad],
    ],
    { type: "FeatureCollection", features: fitFeatures },
  );
  return proj;
});

const path = computed(() => (projection.value ? geoPath(projection.value) : null));

const graticulePath = computed(() => {
  if (!path.value) return "";
  return path.value(geoGraticule().step([10, 10])()) ?? "";
});

const provinceShapes = computed(() => {
  const p = path.value;
  const features = provinces.value;
  if (!p || !features) return [];
  return features.map((feature, index) => ({
    index,
    name: String(feature.properties?.name ?? ""),
    d: p(feature) ?? "",
  }));
});

/* One merged silhouette carries the atlas texture and the drop shadow, so
   the whole country lifts off the ocean as a single plate. */
const silhouettePath = computed(() => provinceShapes.value.map((s) => s.d).join(" "));

/* ── metric encoding ────────────────────────────────────────────────── */

function metricValue(city: NationalCity) {
  if (props.metric === "pm25") return city.pm25;
  if (props.metric === "change") return city.pm25_change_24h;
  return city.china_aqi;
}

function cityColor(city: NationalCity) {
  if (props.metric === "pm25") return pm25Color(city.pm25);
  if (props.metric === "change") return changeColor(city.pm25_change_24h);
  return aqiColor(city.china_aqi_level);
}

function metricLabel(city: NationalCity) {
  if (props.metric === "pm25") {
    return city.pm25 == null ? "—" : `${city.pm25.toFixed(0)}`;
  }
  if (props.metric === "change") {
    const state = changeState(city.pm25_change_24h);
    if (city.pm25_change_24h == null) return state.label;
    const value = city.pm25_change_24h;
    return `${state.arrow}${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
  }
  return city.china_aqi == null ? "—" : `${city.china_aqi}`;
}

/* Uniform precision dots: magnitude lives in the reading chips, the tooltip
   and the charts — the map's only job is "where to look". Equal size keeps
   the field calm and dense clusters legible; severity is carried by colour
   plus crisp geometric emphasis rings, never by bubble volume. */
const MARK_R = 5.5;
const MARK_GAP = 2.5;

/* The reading row appears only where there is something to read — a province
   that is genuinely polluted or genuinely moving — so the crowded east
   carries names while the story-carrying provinces carry numbers. */
function hasReading(city: NationalCity) {
  if (props.metric === "pm25") return (city.pm25 ?? 0) > 75;
  if (props.metric === "change") return Math.abs(city.pm25_change_24h ?? 0) >= 25;
  return (city.china_aqi ?? 0) > 100;
}

/* ── marks & collision-ranked labels ─────────────────────────────────── */

type Mark = {
  city: NationalCity;
  x: number;
  y: number;
  r: number;
  fill: string;
  reading: boolean;
  valueText: string;
  emphasis: boolean;
  ping: boolean;
  ground: boolean;
};

type Box = { x: number; y: number; w: number; h: number };
type Slot = { tx: number; ty: number; anchor: "start" | "middle" | "end" };

function textWidth(text: string, sizePx: number) {
  let width = 0;
  for (const ch of text) {
    width += /[⺀-鿿＀-￯]/.test(ch) ? sizePx : sizePx * 0.56;
  }
  return width;
}

function hits(a: Box, b: Box, gap = 7) {
  return !(
    a.x + a.w + gap <= b.x ||
    b.x + b.w + gap <= a.x ||
    a.y + a.h + gap <= b.y ||
    b.y + b.h + gap <= a.y
  );
}

/* Three rings of anchors, nearest first: right → left → top → bottom → the
   four diagonals. A name drifts further from its dot rather than vanishing —
   this map's whole job is naming where to look. */
function slotsFor(cx: number, cy: number, r: number, w: number, h: number): Slot[] {
  const gap = 8;
  const diag = r + gap + 8;
  const mid = h / 2;
  return [
    { tx: cx + r + gap, ty: cy, anchor: "start" as const },
    { tx: cx - r - gap, ty: cy, anchor: "end" as const },
    { tx: cx, ty: cy - r - gap, anchor: "middle" as const },
    { tx: cx, ty: cy + r + gap + h / 2, anchor: "middle" as const },
    { tx: cx + diag, ty: cy - mid - 6, anchor: "start" as const },
    { tx: cx - diag, ty: cy - mid - 6, anchor: "end" as const },
    { tx: cx + diag, ty: cy + mid + 8, anchor: "start" as const },
    { tx: cx - diag, ty: cy + mid + 8, anchor: "end" as const },
    { tx: cx + diag + 16, ty: cy - mid - 22, anchor: "start" as const },
    { tx: cx - diag - 16, ty: cy - mid - 22, anchor: "end" as const },
    { tx: cx + diag + 16, ty: cy + mid + 26, anchor: "start" as const },
    { tx: cx - diag - 16, ty: cy + mid + 26, anchor: "end" as const },
  ];
}

function boxFor(cx: number, cy: number, r: number, w: number, h: number, slot: Slot): Box {
  const x = slot.anchor === "middle" ? slot.tx - w / 2 : slot.anchor === "end" ? slot.tx - w : slot.tx;
  return { x, y: slot.ty - h / 2, w, h };
}

const view = computed(() => {
  const proj = projection.value;
  if (!proj) return { marks: [] as Mark[], labels: [] as (Mark & { slot: Slot; w: number; h: number })[] };

  // Severity order, worst first: it drives emphasis, label priority and which
  // dot keeps its exact position when the collision relaxer nudges a cluster.
  const ranked = [...props.cities]
    .map((city) => ({ city, value: metricValue(city) }))
    .sort((a, b) => (b.value ?? -Infinity) - (a.value ?? -Infinity));
  const rankById = new Map(ranked.map((r, rank) => [r.city.location_id, rank]));

  const marks: Mark[] = props.cities.map((city) => {
    const xy = proj([city.lon, city.lat]);
    return {
      city,
      x: xy?.[0] ?? -100,
      y: xy?.[1] ?? -100,
      r: MARK_R,
      fill: cityColor(city),
      reading: hasReading(city),
      valueText: metricLabel(city),
      emphasis: false,
      ping: false,
      ground: city.has_recent_ground_observation,
    };
  });

  // Crisp geometric emphasis: the three most severe provinces wear a thin
  // reticle ring, and the worst one alone carries the radar ping.
  const severe = ranked.slice(0, 3).filter((r) => r.value != null).map((r) => r.city.location_id);
  for (const mark of marks) {
    mark.emphasis = severe.includes(mark.city.location_id);
    mark.ping = severe[0] === mark.city.location_id;
  }

  // Dot-collision relaxation: severity-ordered, a dot that would fuse with a
  // more severe one slides away (max ~10px) so dense clusters never merge.
  const ordered = [...marks].sort(
    (a, b) => (rankById.get(a.city.location_id) ?? 0) - (rankById.get(b.city.location_id) ?? 0),
  );
  const minDist = MARK_R * 2 + MARK_GAP;
  for (let iter = 0; iter < 8; iter++) {
    let moved = false;
    for (let i = 0; i < ordered.length; i++) {
      for (let j = i + 1; j < ordered.length; j++) {
        const a = ordered[i];
        const b = ordered[j];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let dist = Math.hypot(dx, dy);
        if (dist >= minDist) continue;
        if (dist < 0.01) {
          dx = 1;
          dy = -0.6;
          dist = 1;
        }
        const push = (minDist - dist) / Math.min(dist, 24);
        const cap = (minDist - dist) / 2 + 1.2;
        const step = Math.min(push, cap);
        b.x += dx * step;
        b.y += dy * step;
        moved = true;
      }
    }
    if (!moved) break;
  }

  // Severity-ranked label placement: the provinces the page is about claim
  // the readable positions before the quiet ones take them.
  const placed: Box[] = [];
  const slots = new Map<number, { slot: Slot; w: number; h: number }>();
  for (const mark of ordered) {
    const name = mark.city.name;
    const w = Math.max(textWidth(name, 12.5), mark.reading ? textWidth(mark.valueText, 11) : 0) + 6;
    const h = mark.reading ? 30 : 16;
    let chosen: Slot | null = null;
    for (const slot of slotsFor(mark.x, mark.y, mark.r, w, h)) {
      const box = boxFor(mark.x, mark.y, mark.r, w, h, slot);
      if (!placed.some((other) => hits(box, other))) {
        placed.push(box);
        chosen = slot;
        break;
      }
    }
    if (chosen) slots.set(mark.city.location_id, { slot: chosen, w, h });
  }

  const labels = marks
    .filter((mark) => slots.has(mark.city.location_id))
    .map((mark) => ({ ...mark, ...slots.get(mark.city.location_id)! }));

  return { marks, labels };
});

/* Tooltip anchors to the mark's on-screen position (zoom transform applied),
   so it never detaches from its dot while panning. */
const tooltipStyle = computed(() => {
  const mark = marks.value.find((m) => m.city === hoveredCity.value);
  if (!mark) return {};
  const t = transform.value;
  const x = mark.x * t.k + t.x;
  const y = mark.y * t.k + t.y;
  return {
    left: `${Math.min(Math.max(x + 16, 12), size.value.w - 280)}px`,
    top: `${Math.min(Math.max(y - 12, 12), size.value.h - 190)}px`,
  };
});

const marks = computed(() => view.value.marks);
const labels = computed(() => view.value.labels);

function fmtTime(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

/* ── zoom gestures ───────────────────────────────────────────────────── */

function zoomBy(factor: number) {
  if (!svgEl.value || !zoomBehavior) return;
  select(svgEl.value)
    .transition()
    .duration(280)
    .ease(easeCubicOut)
    .call(zoomBehavior.scaleBy, factor);
}

function zoomIn() {
  zoomBy(1.4);
}
function zoomOut() {
  zoomBy(1 / 1.4);
}
function resetView() {
  if (!svgEl.value || !zoomBehavior) return;
  select(svgEl.value)
    .transition()
    .duration(320)
    .ease(easeCubicOut)
    .call(zoomBehavior.transform, zoomIdentity);
}

function onMarkEnter(city: NationalCity) {
  hoveredCity.value = city;
}
function onMarkLeave() {
  hoveredCity.value = null;
}
function onMarkClick(city: NationalCity) {
  emit("select", city.location_id, city.name);
}

function syncWidth() {
  const next = (el.value?.clientWidth ?? window.innerWidth) >= 700;
  if (next !== wide.value) wide.value = next;
}

/* ── winding order ─────────────────────────────────────────────────────
   d3-geo reads polygon rings as SPHERICAL polygons: an exterior ring must
   wind clockwise, or d3 renders the complement — "everything except the
   province". RFC 7946 sources (this atlas) wind exteriors counterclockwise,
   so every polygon whose exterior winds CCW gets all its rings reversed. */
function ringArea(ring: number[][]) {
  let sum = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    sum += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1];
  }
  return sum;
}

function fixPolygonWinding(polygon: number[][][]) {
  return ringArea(polygon[0]) > 0
    ? polygon.map((ring) => [...ring].reverse())
    : polygon;
}

function normalizeWinding(feature: ProvinceFeature): ProvinceFeature {
  const geometry = feature.geometry;
  if (geometry.type === "Polygon") {
    return { ...feature, geometry: { ...geometry, coordinates: fixPolygonWinding(geometry.coordinates) } };
  }
  if (geometry.type === "MultiPolygon") {
    return {
      ...feature,
      geometry: { ...geometry, coordinates: geometry.coordinates.map(fixPolygonWinding) },
    };
  }
  return feature;
}

onMounted(async () => {
  if (!el.value) return;
  observer = new ResizeObserver((entries) => {
    const entry = entries[0];
    if (!entry) return;
    const { width, height } = entry.contentRect;
    if (width > 0 && height > 0) {
      size.value = { w: width, h: height };
      syncWidth();
    }
  });
  observer.observe(el.value);

  zoomBehavior = d3Zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.9, 4.5])
    .on("zoom", (event) => {
      transform.value = event.transform;
    });
  if (svgEl.value) select(svgEl.value).call(zoomBehavior);

  try {
    const response = await fetch("/maps/china.json");
    if (!response.ok) throw new Error(String(response.status));
    const geoJson = await response.json();
    provinces.value = (geoJson.features as ProvinceFeature[]).map(normalizeWinding);
  } catch {
    mapError.value = true;
  }
});

watch(() => [props.cities, props.metric], () => {
  hoveredCity.value = null;
});

onBeforeUnmount(() => {
  observer?.disconnect();
});
</script>

<template>
  <div ref="el" class="china-map-shell">
    <svg
      ref="svgEl"
      class="china-map"
      :width="size.w"
      :height="size.h"
      role="img"
      aria-label="全国省级空气质量地图，一省一点，取该省当前 AQI 最高的城市。可切换 AQI、PM2.5 与 24 小时变化，点击进入城市详情。"
    >
      <defs>
        <pattern id="atlas-dots" width="7" height="7" patternUnits="userSpaceOnUse">
          <circle cx="1.1" cy="1.1" r="0.55" fill="#0f172a" opacity="0.07" />
        </pattern>
        <filter id="plate-shadow" x="-15%" y="-15%" width="130%" height="130%">
          <feDropShadow dx="0" dy="7" stdDeviation="9" flood-color="#33415c" flood-opacity="0.18" />
          <feDropShadow dx="0" dy="1.5" stdDeviation="2.2" flood-color="#33415c" flood-opacity="0.14" />
        </filter>
      </defs>

      <g
        class="viewport"
        :transform="`translate(${transform.x},${transform.y}) scale(${transform.k})`"
      >
        <path class="graticule" :d="graticulePath" />

        <!-- Landmass: one silhouette for shadow + texture, provinces for fill -->
        <g class="landmass">
          <path class="silhouette" :d="silhouettePath" filter="url(#plate-shadow)" />
          <path class="silhouette-fill" :d="silhouettePath" />
          <path class="silhouette-dots" :d="silhouettePath" fill="url(#atlas-dots)" />
          <path
            v-for="shape in provinceShapes"
            :key="shape.index"
            class="province"
            :class="{ hovered: hoveredProvince === shape.name }"
            :d="shape.d"
            @mouseenter="hoveredProvince = shape.name"
            @mouseleave="hoveredProvince = null"
          />
        </g>

        <!-- City marks: uniform precision dots. Emphasis is geometry, not
             glow — a thin reticle on the three most severe provinces and a
             single radar ping on the worst one. -->
        <g class="marks">
          <template v-for="mark in marks" :key="mark.city.location_id">
            <circle
              v-if="mark.ping"
              class="ping"
              :cx="mark.x"
              :cy="mark.y"
              :r="MARK_R + 2.5"
              :stroke="mark.fill"
            />
            <circle
              v-if="mark.emphasis"
              class="reticle"
              :cx="mark.x"
              :cy="mark.y"
              :r="MARK_R + 3.5"
            />
            <circle
              v-else-if="mark.ground"
              class="ground-ring"
              :cx="mark.x"
              :cy="mark.y"
              :r="MARK_R + 2.6"
            />
            <circle
              class="mark"
              :class="{ active: hoveredCity === mark.city }"
              :cx="mark.x"
              :cy="mark.y"
              :r="mark.r"
              :fill="mark.fill"
              @mouseenter="onMarkEnter(mark.city)"
              @mouseleave="onMarkLeave()"
              @click="onMarkClick(mark.city)"
            />
          </template>
        </g>

        <!-- Labels: severity-ranked, collision-free, haloed ink -->
        <g class="labels" aria-hidden="true">
          <g
            v-for="label in labels"
            :key="label.city.location_id"
            class="label"
            :class="{ reading: label.reading }"
          >
            <text
              :x="label.slot.tx"
              :y="label.slot.ty"
              :text-anchor="label.slot.anchor"
              dominant-baseline="central"
              class="label-name"
            >
              {{ label.city.name }}
              <tspan
                v-if="label.reading"
                :x="label.slot.tx"
                dy="14"
                class="label-value"
                :fill="label.fill"
              >{{ label.valueText }}</tspan>
            </text>
          </g>
        </g>
      </g>
    </svg>

    <!-- Tooltip: the same reading the page would give, anchored to the dot -->
    <div
      v-if="hoveredCity"
      class="map-tip"
      :style="tooltipStyle"
      @mouseenter="onMarkLeave"
    >
      <div class="tip-head">
        <strong>{{ hoveredCity.name }}</strong>
        <span>{{ hoveredCity.province }}</span>
      </div>
      <div class="tip-metric">{{ metricLabel(hoveredCity) }}</div>
      <div class="tip-line">
        <b>{{ hoveredCity.china_aqi_level ?? "暂无" }}</b> · AQI {{ hoveredCity.china_aqi ?? "—" }}
      </div>
      <div class="tip-line">
        PM2.5 {{ hoveredCity.pm25 == null ? "—" : hoveredCity.pm25.toFixed(1) }} µg/m³ ·
        24h
        <template v-if="hoveredCity.pm25_change_24h == null"> 历史不足 </template>
        <template v-else>
          {{ changeState(hoveredCity.pm25_change_24h).arrow }}
          {{ changeState(hoveredCity.pm25_change_24h).label }}
          {{ Math.abs(hoveredCity.pm25_change_24h).toFixed(1) }}
        </template>
      </div>
      <div class="tip-line">主要污染物 {{ hoveredCity.primary_pollutants?.join(" / ") || "暂无" }}</div>
      <div class="tip-meta">
        更新 {{ fmtTime(hoveredCity.source_time)
        }}<template v-if="hoveredCity.has_recent_ground_observation"> · 有近期地面观测</template>
      </div>
    </div>

    <div class="map-actions" aria-label="地图缩放控制">
      <button type="button" aria-label="放大地图" @click="zoomIn"><Plus :size="16" /></button>
      <button type="button" aria-label="缩小地图" @click="zoomOut"><Minus :size="16" /></button>
      <button type="button" aria-label="复位地图" @click="resetView"><RotateCcw :size="15" /></button>
    </div>

    <p v-if="mapError" class="map-error" role="alert">地图底图加载失败，请刷新后重试。</p>
  </div>
</template>

<style scoped>
.china-map-shell,
.china-map {
  position: absolute;
  inset: 0;
}

.china-map {
  display: block;
  cursor: grab;
  touch-action: none;
}

.china-map:active {
  cursor: grabbing;
}

/* Sea: a barely-there radial lift behind the plate, then graticule ink. */
.graticule {
  fill: none;
  stroke: #0f172a;
  stroke-opacity: 0.05;
  stroke-width: 0.6;
  vector-effect: non-scaling-stroke;
}

.landmass .silhouette {
  fill: #ffffff;
}

.landmass .silhouette-fill {
  fill: #ffffff;
}

.landmass .silhouette-dots {
  fill: url(#atlas-dots);
  pointer-events: none;
}

.province {
  fill: transparent;
  stroke: var(--map-border);
  stroke-width: 0.8;
  vector-effect: non-scaling-stroke;
  transition: fill var(--duration-fast) ease, stroke var(--duration-fast) ease;
}

.province.hovered {
  fill: rgba(2, 132, 199, 0.055);
  stroke: var(--ink);
  stroke-width: 1.3;
}

.marks .mark {
  stroke: #ffffff;
  stroke-width: 1.3;
  cursor: pointer;
  transition: stroke var(--duration-fast) ease;
  pointer-events: all;
}

.marks .mark.active {
  stroke: var(--ink);
  stroke-width: 1.8;
}

/* Emphasis is crisp geometry: a hairline reticle on the severe provinces and
   one expanding hairline ping on the worst — no glows, no blurred halos. */
.reticle {
  fill: none;
  stroke: var(--ink);
  stroke-width: 1.2;
  opacity: 0.7;
  pointer-events: none;
}

.ping {
  fill: none;
  stroke-width: 1.4;
  transform-box: fill-box;
  transform-origin: center;
  animation: ping 3.4s cubic-bezier(0.16, 1, 0.3, 1) infinite;
  pointer-events: none;
}

@keyframes ping {
  0% { transform: scale(1); opacity: 0.6; }
  70% { transform: scale(3.4); opacity: 0; }
  100% { transform: scale(3.4); opacity: 0; }
}

.ground-ring {
  fill: none;
  stroke: var(--ink);
  stroke-width: 1;
  opacity: 0.45;
  pointer-events: none;
}

.label {
  pointer-events: none;
}

.label-name {
  font-family: var(--font-sans);
  font-size: 12.5px;
  font-weight: 500;
  fill: var(--ink);
  paint-order: stroke;
  stroke: rgba(255, 255, 255, 0.88);
  stroke-width: 2.6px;
  stroke-linejoin: round;
}

.label-value {
  font-family: var(--font-display);
  font-size: 11px;
  font-weight: 700;
  paint-order: stroke;
  stroke: rgba(255, 255, 255, 0.92);
  stroke-width: 3px;
  stroke-linejoin: round;
}

/* Tooltip */
.map-tip {
  position: absolute;
  z-index: 12;
  min-width: 250px;
  max-width: 300px;
  padding: 13px 15px;
  border: 1px solid var(--hairline);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.97);
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.16);
  pointer-events: none;
  font-size: 13px;
  line-height: 1.55;
  color: var(--ink-soft);
}

.tip-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 18px;
}

.tip-head strong {
  font-size: 17px;
  color: var(--ink);
}

.tip-head span {
  font-size: 12px;
  color: var(--muted);
}

.tip-metric {
  margin-top: 8px;
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 700;
  color: var(--ink);
}

.tip-line {
  margin-top: 4px;
}

.tip-meta {
  margin-top: 6px;
  font-size: 12px;
  color: var(--muted);
}

/* Zoom controls: unchanged placement, glass over the plate */
.map-actions {
  position: absolute;
  z-index: 8;
  right: 20px;
  bottom: 20px;
  display: grid;
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: var(--sheet-glass);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--shadow-sm);
}

.map-actions button {
  width: 34px;
  height: 32px;
  display: grid;
  place-items: center;
  border: 0;
  border-bottom: 1px solid var(--hairline);
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  transition: all var(--duration-fast) ease;
}

.map-actions button:last-child { border-bottom: 0; }

.map-actions button:hover {
  background: var(--sheet-soft);
  color: var(--ink);
}

.map-actions button:active {
  transform: scale(0.94);
}

.map-error {
  position: absolute;
  left: 18px;
  bottom: 18px;
  margin: 0;
  padding: 10px 14px;
  border: 1px solid #fed7aa;
  border-radius: var(--radius-sm);
  background: #fff7ed;
  color: var(--error);
  font-size: var(--fs-label);
}

@media (prefers-reduced-motion: reduce) {
  .ping { animation: none; opacity: 0; }
}

@media (max-width: 700px) {
  .map-actions {
    right: 12px;
    bottom: 12px;
  }
}
</style>
