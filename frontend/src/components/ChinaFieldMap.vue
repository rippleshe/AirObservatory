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
import { interpolateRgb } from "d3-interpolate";
import { select } from "d3-selection";
import { easeCubicOut } from "d3-ease";
import "d3-transition";
import { zoom as d3Zoom, zoomIdentity, type ZoomBehavior, type ZoomTransform } from "d3-zoom";
import type { Feature, MultiPolygon, Polygon } from "geojson";
import { Minus, Plus, RotateCcw } from "lucide-vue-next";
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";
import { gsap, prefersReducedMotion } from "../lib/motion";
import { pm25Color } from "../lib/palette";
import { aqiColor, changeColor, changeState } from "../lib/palette";
import type { NationalCity } from "../lib/provinces";

type MapMetric = "aqi" | "pm25" | "change";

export type WindFieldPoint = {
  location_id: number;
  lat: number;
  lon: number;
  speed: number;
  dir: number;
};

type ProvinceFeature = Feature<Polygon | MultiPolygon, { name?: string; adcode?: number }>;

const props = withDefaults(
  defineProps<{
    cities: NationalCity[];
    metric?: MapMetric;
    windField?: WindFieldPoint[] | null;
    sparks?: Record<number, number[]>;
  }>(),
  { metric: "aqi", windField: null, sparks: () => ({}) },
);
const emit = defineEmits<{
  select: [id: number, name: string];
  pin: [id: number | null];
}>();

const el = ref<HTMLDivElement | null>(null);
const svgEl = ref<SVGSVGElement | null>(null);
const size = ref({ w: 0, h: 0 });
const transform = ref<ZoomTransform>(zoomIdentity);
const mapError = ref(false);
const wide = ref(true);
const hoveredProvince = ref<string | null>(null);
const hoveredCity = ref<NationalCity | null>(null);
/* Click pins a city overview card: navigation becomes a decision, not an
   accident. The card is anchored to the dot and survives hover. */
const pinned = ref<NationalCity | null>(null);

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

/* ── time-machine interpolation ────────────────────────────────────────
   Scrubbing replaces the whole city array each tick. Snapping is what made
   the old ribbon feel like a flip-book, so the mark layer now tweens: the
   numbers roll, colours cross-fade between bands and label anchors glide to
   their new slots. `view` stays the target; `render` is what paints. */
type LiveLabel = Mark & { slot: Slot; w: number; h: number };
type LiveState = { marks: Mark[]; labels: LiveLabel[] };

const anim = ref<{ from: LiveState | null; t: number }>({ from: null, t: 1 });

function snapshot(state: LiveState): LiveState {
  return {
    marks: state.marks.map((mark) => ({ ...mark })),
    labels: state.labels.map((label) => ({ ...label, slot: { ...label.slot } })),
  };
}

function formatValue(city: NationalCity, value: number | null | undefined) {
  if (props.metric === "pm25") return value == null ? "—" : value.toFixed(0);
  if (props.metric === "change") {
    const state = changeState(value);
    if (value == null) return state.label;
    return `${state.arrow}${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
  }
  return value == null ? "—" : `${Math.round(value)}`;
}

function interpolateState(from: LiveState, t: number): LiveState {
  const to = view.value;
  const markFrom = new Map(from.marks.map((m) => [m.city.location_id, m]));
  const nextMarks = to.marks.map((mark) => {
    const prev = markFrom.get(mark.city.location_id);
    if (!prev) return mark;
    const a = metricValue(prev.city);
    const b = metricValue(mark.city);
    const value = a != null && b != null ? a + (b - a) * t : b;
    return {
      ...mark,
      fill: interpolateRgb(prev.fill, mark.fill)(t),
      valueText: formatValue(mark.city, value),
    };
  });
  const labelFrom = new Map(from.labels.map((l) => [l.city.location_id, l]));
  const nextLabels = to.labels.map((label) => {
    const prev = labelFrom.get(label.city.location_id);
    if (!prev) return label;
    return {
      ...label,
      slot: {
        ...label.slot,
        tx: prev.slot.tx + (label.slot.tx - prev.slot.tx) * t,
        ty: prev.slot.ty + (label.slot.ty - prev.slot.ty) * t,
      },
    };
  });
  return { marks: nextMarks, labels: nextLabels };
}

const render = computed<LiveState>(() => {
  const { from, t } = anim.value;
  if (!from || t >= 1) return { marks: view.value.marks, labels: view.value.labels };
  return interpolateState(from, t);
});

watch(view, () => {
  if (prefersReducedMotion()) {
    anim.value = { from: null, t: 1 };
    return;
  }
  const from = snapshot(render.value);
  anim.value = { from, t: 0 };
  gsap.to(anim.value, { t: 1, duration: 0.45, ease: "power2.out", overwrite: true });
});

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

/* ── wind-particle field ───────────────────────────────────────────────
   A canvas layer above the plate: particles ride the interpolated wind
   field (60 cities, IDW-smoothed) and pick up the local PM2.5 band colour.
   Streaks come from a destination-out fade, so the canvas never fully
   clears — the air reads as flow, not arrows. The layer is base-space: it
   lives under the same zoom transform as the SVG and pauses when idle. */
const fieldCanvas = ref<HTMLCanvasElement | null>(null);
let fieldCtx: CanvasRenderingContext2D | null = null;
let maskAlpha: Uint8ClampedArray | null = null;
let maskW = 0;
let maskH = 0;
let particles: Array<{ x: number; y: number; px: number; py: number; age: number; ttl: number }> = [];
let rafId = 0;
let lastTs = 0;
let fieldActive = false;
let fieldVisible = true;
let fieldHardClear = true;
const FIELD_CELL = 26;
const SPEED_SCALE = 7.5;
const fieldGrid = {
  cols: 0,
  rows: 0,
  u: new Float32Array(0),
  v: new Float32Array(0),
  c: new Float32Array(0),
};

function devicePixelScale() {
  return Math.min(window.devicePixelRatio || 1, 2);
}

function insideLand(x: number, y: number) {
  if (!maskAlpha) return false;
  const ix = x | 0;
  const iy = y | 0;
  if (ix < 0 || iy < 0 || ix >= maskW || iy >= maskH) return false;
  return maskAlpha[iy * maskW + ix] > 40;
}

function rebuildMask() {
  const proj = projection.value;
  const canvas = fieldCanvas.value;
  if (!proj || !canvas || !size.value.w || !size.value.h) return;
  const off = document.createElement("canvas");
  off.width = size.value.w;
  off.height = size.value.h;
  const ctx = off.getContext("2d");
  if (!ctx) return;
  ctx.fillStyle = "#000";
  const p = geoPath(proj);
  const features = provinces.value ?? [];
  for (const feature of features) {
    if (!feature.properties?.name) continue;
    const d = p(feature);
    if (d) ctx.fill(new Path2D(d));
  }
  const image = ctx.getImageData(0, 0, off.width, off.height);
  maskW = off.width;
  maskH = off.height;
  const alpha = new Uint8ClampedArray(maskW * maskH);
  for (let i = 0, j = 3; i < alpha.length; i++, j += 4) alpha[i] = image.data[j]!;
  maskAlpha = alpha;
  fieldHardClear = true;
}

function projectedWind() {
  const proj = projection.value;
  if (!proj || !props.windField?.length) return [];
  return props.windField.flatMap((point) => {
    const xy = proj([point.lon, point.lat]);
    if (!xy) return [];
    const rad = (point.dir * Math.PI) / 180;
    const u = -point.speed * Math.sin(rad);
    const northward = -point.speed * Math.cos(rad);
    return [{ x: xy[0]!, y: xy[1]!, u, v: -northward, speed: point.speed }];
  });
}

function rebuildGrid() {
  const proj = projection.value;
  if (!proj || !size.value.w || !size.value.h) return;
  const cols = Math.max(2, Math.ceil(size.value.w / FIELD_CELL) + 1);
  const rows = Math.max(2, Math.ceil(size.value.h / FIELD_CELL) + 1);
  const u = new Float32Array(cols * rows);
  const v = new Float32Array(cols * rows);
  const c = new Float32Array(cols * rows);
  const wind = projectedWind();
  const pm = props.cities.flatMap((city) => {
    const xy = proj([city.lon, city.lat]);
    if (!xy || city.pm25 == null) return [];
    return [{ x: xy[0]!, y: xy[1]!, value: city.pm25 }];
  });
  for (let r = 0; r < rows; r++) {
    for (let col = 0; col < cols; col++) {
      const gx = col * FIELD_CELL;
      const gy = r * FIELD_CELL;
      let wu = 0;
      let wv = 0;
      let wc = 0;
      let wsum = 0;
      for (const point of wind) {
        const d2 = (point.x - gx) ** 2 + (point.y - gy) ** 2 + 64;
        const weight = 1 / d2;
        wu += point.u * weight;
        wv += point.v * weight;
        wsum += weight;
      }
      let csum = 0;
      for (const point of pm) {
        const d2 = (point.x - gx) ** 2 + (point.y - gy) ** 2 + 100;
        const weight = 1 / d2;
        wc += point.value * weight;
        csum += weight;
      }
      const idx = r * cols + col;
      if (wsum > 0) {
        u[idx] = wu / wsum;
        v[idx] = wv / wsum;
      }
      c[idx] = csum > 0 ? wc / csum : -1;
    }
  }
  fieldGrid.cols = cols;
  fieldGrid.rows = rows;
  fieldGrid.u = u;
  fieldGrid.v = v;
  fieldGrid.c = c;
}

function sampleGrid(x: number, y: number): [number, number, number] {
  const gx = x / FIELD_CELL;
  const gy = y / FIELD_CELL;
  const x0 = Math.min(fieldGrid.cols - 1, Math.max(0, Math.floor(gx)));
  const y0 = Math.min(fieldGrid.rows - 1, Math.max(0, Math.floor(gy)));
  const x1 = Math.min(fieldGrid.cols - 1, x0 + 1);
  const y1 = Math.min(fieldGrid.rows - 1, y0 + 1);
  const fx = gx - x0;
  const fy = gy - y0;
  const idx = (xx: number, yy: number) => yy * fieldGrid.cols + xx;
  const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
  const u =
    lerp(lerp(fieldGrid.u[idx(x0, y0)]!, fieldGrid.u[idx(x1, y0)]!, fx), lerp(fieldGrid.u[idx(x0, y1)]!, fieldGrid.u[idx(x1, y1)]!, fx), fy);
  const v =
    lerp(lerp(fieldGrid.v[idx(x0, y0)]!, fieldGrid.v[idx(x1, y0)]!, fx), lerp(fieldGrid.v[idx(x0, y1)]!, fieldGrid.v[idx(x1, y1)]!, fx), fy);
  const c =
    lerp(lerp(fieldGrid.c[idx(x0, y0)]!, fieldGrid.c[idx(x1, y0)]!, fx), lerp(fieldGrid.c[idx(x0, y1)]!, fieldGrid.c[idx(x1, y1)]!, fx), fy);
  return [u, v, c];
}

function spawnParticle(p: { x: number; y: number; age: number; ttl: number }) {
  for (let attempt = 0; attempt < 16; attempt++) {
    const x = Math.random() * maskW;
    const y = Math.random() * maskH;
    if (insideLand(x, y)) {
      p.x = x;
      p.y = y;
      p.age = 0;
      p.ttl = 2.5 + Math.random() * 3.5;
      return;
    }
  }
  p.age = p.ttl;
}

function syncCanvasSize() {
  const canvas = fieldCanvas.value;
  if (!canvas || !size.value.w || !size.value.h) return;
  const dpr = devicePixelScale();
  const w = Math.round(size.value.w * dpr);
  const h = Math.round(size.value.h * dpr);
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
    fieldHardClear = true;
  }
  fieldCtx = canvas.getContext("2d");
}

function clearField() {
  const ctx = fieldCtx;
  if (!ctx) return;
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  ctx.restore();
}

function drawStaticField() {
  const ctx = fieldCtx;
  if (!ctx) return;
  clearField();
  const t = transform.value;
  const dpr = devicePixelScale();
  ctx.setTransform(t.k * dpr, 0, 0, t.k * dpr, t.x * dpr, t.y * dpr);
  ctx.lineWidth = 1.2 / Math.max(0.7, t.k);
  ctx.lineCap = "round";
  for (let r = 0; r < fieldGrid.rows; r++) {
    for (let col = 0; col < fieldGrid.cols; col++) {
      const x = col * FIELD_CELL;
      const y = r * FIELD_CELL;
      if (!insideLand(x, y)) continue;
      const idx = r * fieldGrid.cols + col;
      const [u, v, c] = [fieldGrid.u[idx]!, fieldGrid.v[idx]!, fieldGrid.c[idx]!];
      const speed = Math.hypot(u, v);
      if (speed < 0.2) continue;
      const len = Math.min(18, 5 + speed * 1.8);
      ctx.strokeStyle = c >= 0 ? pm25Color(c) : "#94a3b8";
      ctx.globalAlpha = 0.7;
      ctx.lineWidth = 1.6 / Math.max(0.7, t.k);
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + (u / speed) * len, y + (v / speed) * len);
      ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;
}

function fieldFrame(ts: number) {
  if (!fieldActive) return;
  rafId = requestAnimationFrame(fieldFrame);
  const ctx = fieldCtx;
  if (!ctx || document.hidden || !fieldVisible) return;
  const dt = Math.min(0.05, (ts - lastTs) / 1000 || 0.016);
  lastTs = ts;

  if (fieldHardClear) {
    clearField();
    fieldHardClear = false;
    for (const particle of particles) spawnParticle(particle);
  } else {
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalCompositeOperation = "destination-out";
    ctx.fillStyle = "rgba(0,0,0,0.085)";
    ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    ctx.restore();
  }

  const t = transform.value;
  const dpr = devicePixelScale();
  ctx.setTransform(t.k * dpr, 0, 0, t.k * dpr, t.x * dpr, t.y * dpr);
  ctx.lineWidth = 1.5 / Math.max(0.7, t.k);
  ctx.lineCap = "round";

  for (const particle of particles) {
    const [u, v, c] = sampleGrid(particle.x, particle.y);
    particle.px = particle.x;
    particle.py = particle.y;
    particle.x += u * SPEED_SCALE * dt;
    particle.y += v * SPEED_SCALE * dt;
    particle.age += dt;
    const speed = Math.hypot(u, v);
    if (
      particle.age > particle.ttl ||
      speed < 0.05 ||
      !insideLand(particle.x, particle.y)
    ) {
      spawnParticle(particle);
      continue;
    }
    ctx.strokeStyle = c >= 0 ? pm25Color(c) : "#94a3b8";
    ctx.globalAlpha = 0.62;
    ctx.beginPath();
    ctx.moveTo(particle.px, particle.py);
    ctx.lineTo(particle.x, particle.y);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
}

function ensureParticleCount() {
  const target = Math.round(
    Math.min(2000, Math.max(600, (size.value.w * size.value.h) / 700)),
  );
  if (particles.length === target) return;
  particles = Array.from({ length: target }, () => {
    const particle = { x: 0, y: 0, px: 0, py: 0, age: 0, ttl: 0 };
    spawnParticle(particle);
    return particle;
  });
}

function startField() {
  if (fieldActive || prefersReducedMotion()) {
    if (prefersReducedMotion()) drawStaticField();
    return;
  }
  fieldActive = true;
  lastTs = performance.now();
  rafId = requestAnimationFrame(fieldFrame);
}

function stopField() {
  fieldActive = false;
  cancelAnimationFrame(rafId);
}

let fieldObserver: IntersectionObserver | null = null;

function refreshFieldLayer() {
  syncCanvasSize();
  rebuildMask();
  rebuildGrid();
  ensureParticleCount();
  fieldHardClear = true;
  if (prefersReducedMotion()) drawStaticField();
}

watch([projection, () => props.windField], () => {
  refreshFieldLayer();
});

watch(() => props.cities, () => {
  if (maskAlpha) rebuildGrid();
});

watch(transform, () => {
  fieldHardClear = true;
});

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
  pinned.value = pinned.value?.location_id === city.location_id ? null : city;
  emit("pin", pinned.value?.location_id ?? null);
}

const pinnedStyle = computed(() => {
  const mark = render.value.marks.find((m) => m.city === pinned.value);
  if (!mark) return {};
  const t = transform.value;
  const x = mark.x * t.k + t.x;
  const y = mark.y * t.k + t.y;
  return {
    left: `${Math.min(Math.max(x + 14, 12), size.value.w - 264)}px`,
    top: `${Math.min(Math.max(y - 40, 12), size.value.w - 240)}px`,
  };
});

const pinnedSpark = computed(() => props.sparks[pinned.value?.location_id ?? -1] ?? []);

const pinnedSparkPath = computed(() => {
  const series = pinnedSpark.value;
  if (series.length < 2) return "";
  const min = Math.min(...series);
  const max = Math.max(...series);
  const span = Math.max(0.5, max - min);
  return series
    .map((v, i) => {
      const x = (i / (series.length - 1)) * 118;
      const y = 28 - ((v - min) / span) * 24;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
});

function openPinned() {
  if (!pinned.value) return;
  emit("select", pinned.value.location_id, pinned.value.name);
  pinned.value = null;
  emit("pin", null);
}

function onStageClick() {
  if (pinned.value == null) return;
  pinned.value = null;
  emit("pin", null);
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

  if (fieldCanvas.value) {
    fieldObserver = new IntersectionObserver(
      (entries) => {
        fieldVisible = entries[0]?.isIntersecting ?? true;
        if (fieldVisible) startField();
        else stopField();
      },
      { rootMargin: "120px" },
    );
    fieldObserver.observe(fieldCanvas.value);
    refreshFieldLayer();
    startField();
  }
});

watch(() => [props.cities, props.metric], () => {
  hoveredCity.value = null;
});

onBeforeUnmount(() => {
  observer?.disconnect();
  fieldObserver?.disconnect();
  stopField();
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
      aria-label="全国空气质量地图"
      @click="onStageClick"
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
          <template v-for="mark in render.marks" :key="mark.city.location_id">
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
              @click.stop="onMarkClick(mark.city)"
            />
          </template>
        </g>

        <!-- Labels: severity-ranked, collision-free, haloed ink -->
        <g class="labels" aria-hidden="true">
          <g
            v-for="label in render.labels"
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

    <!-- Wind particles ride above the plate: translucent streaks, no pointer
         capture, same zoom transform as the SVG geometry. -->
    <canvas ref="fieldCanvas" class="field-canvas" aria-hidden="true"></canvas>

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

    <!-- Pinned overview card: the city at a glance without leaving the map -->
    <div v-if="pinned" class="city-card" :style="pinnedStyle">
      <header>
        <strong>{{ pinned.name }}</strong>
        <span>{{ pinned.province }}</span>
        <button type="button" class="card-close" aria-label="关闭" @click.stop="pinned = null">✕</button>
      </header>
      <div class="card-stats">
        <div class="card-stat main">
          <b :style="{ color: cityColor(pinned) }">{{ pinned.china_aqi ?? "—" }}</b>
          <small>{{ pinned.china_aqi_level ?? "暂无" }}</small>
        </div>
        <div class="card-stat">
          <b>{{ pinned.pm25?.toFixed(1) ?? "—" }}</b>
          <small>PM2.5</small>
        </div>
        <div class="card-stat">
          <b :class="pinned.pm25_change_24h != null && pinned.pm25_change_24h < 0 ? 'good' : 'bad'">
            {{ pinned.pm25_change_24h == null ? "—" : changeState(pinned.pm25_change_24h).arrow + Math.abs(pinned.pm25_change_24h).toFixed(1) }}
          </b>
          <small>24h</small>
        </div>
      </div>
      <svg v-if="pinnedSparkPath" class="card-spark" viewBox="0 0 118 30">
        <path :d="pinnedSparkPath" fill="none" stroke="#0284c7" stroke-width="1.8" stroke-linecap="round" />
      </svg>
      <button type="button" class="card-open" @click.stop="openPinned">
        进入详情 →
      </button>
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

.field-canvas {
  position: absolute;
  inset: 0;
  z-index: 2;
  width: 100%;
  height: 100%;
  pointer-events: none;
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

.city-card {
  position: absolute;
  z-index: 14;
  width: 240px;
  padding: 13px 14px 12px;
  border: 1px solid var(--hairline);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.97);
  box-shadow: 0 18px 44px rgba(15, 23, 42, 0.18);
  backdrop-filter: blur(8px);
}

.city-card header {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.city-card header strong {
  color: var(--ink);
  font-size: 15px;
}

.city-card header span {
  color: var(--muted);
  font-size: 11px;
}

.card-close {
  margin-left: auto;
  border: 0;
  background: transparent;
  color: var(--faint);
  font-size: 11px;
  cursor: pointer;
  padding: 2px 4px;
}

.card-close:hover {
  color: var(--ink);
}

.card-stats {
  margin-top: 9px;
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr;
  gap: 8px;
}

.card-stat {
  display: grid;
  gap: 1px;
}

.card-stat b {
  color: var(--ink);
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 700;
  line-height: 1.1;
}

.card-stat.main b {
  font-size: 21px;
}

.card-stat b.good { color: var(--ok); }
.card-stat b.bad { color: var(--error); }

.card-stat small {
  color: var(--faint);
  font-size: 9.5px;
}

.card-spark {
  width: 100%;
  height: 30px;
  margin-top: 9px;
}

.card-open {
  margin-top: 9px;
  width: 100%;
  min-height: 28px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: var(--ink);
  color: #ffffff;
  font-size: 11.5px;
  font-weight: var(--fw-strong);
  cursor: pointer;
  transition: all var(--duration-fast) ease;
}

.card-open:hover {
  background: var(--ink-soft);
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
