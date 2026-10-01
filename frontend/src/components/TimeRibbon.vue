<script setup lang="ts">
/* The time machine — the one authored motion of this product.
 *
 * The ribbon carries 30 days of the national field as a single trace, and the
 * playhead is a real playhead: drag it, step it, or play the sweep, and the
 * map behind it re-reads that hour. The loop closes visually — the same
 * persisted history the analysis pages cite becomes a thing you can move
 * through. Values stay missing where they are missing: the trace breaks, it
 * never interpolates. */
import { computed, onBeforeUnmount, ref } from "vue";
import { PM25_BANDS, stageColor } from "../lib/palette";

const props = withDefaults(
  defineProps<{
    times: string[];
    values: (number | null)[];
    /** null = live, the playhead rests on 现在. */
    index: number | null;
    caption?: string;
    autoplay?: boolean;
  }>(),
  { caption: "31 省中位 PM2.5 · 近 30 天", autoplay: false },
);

const emit = defineEmits<{ "update:index": [index: number | null] }>();

const root = ref<HTMLElement | null>(null);
const width = ref(980);
const playing = ref(false);
const hovered = ref<number | null>(null);

const PLOT_H = 96;
const PAD_TOP = 14;
const AXIS_H = 22;
const HEIGHT = PLOT_H + PAD_TOP + AXIS_H;

const TICK = 45;
const STEPS = 240;

/* PM2.5 concentration bands as ruled zones: the scale legend is drawn into
   the plot (刻度图例), so severity reads without a hover. Thresholds are the
   HJ 633-2026 IAQI breaks for PM2.5, the same numbers the palette uses.
   Each zone is the strip BETWEEN two thresholds — a zone reaches down only
   to the rule below it, never to zero, or the fills stack into a wash. */
const ZONES = [
  { from: 0, upTo: 35, color: PM25_BANDS[0][1], label: "35" },
  { from: 35, upTo: 75, color: PM25_BANDS[1][1], label: "75" },
  { from: 75, upTo: 115, color: PM25_BANDS[2][1], label: "115" },
  { from: 115, upTo: 150, color: PM25_BANDS[3][1], label: "150" },
  { from: 150, upTo: Infinity, color: PM25_BANDS[4][1], label: "" },
];

const plotW = computed(() => Math.max(240, width.value));

/* The domain hugs the record — a 20 µg/m³ month must not be a flat line at
   the foot of a 160 µg/m³ frame — but never shows less than one full band
   so the drawn rules keep their meaning. Rules above the domain are not
   drawn at all; a scale legend stops where the scale stops. */
const domainMax = computed(() => {
  const finite = props.values.filter((v): v is number => v != null && Number.isFinite(v));
  const peak = finite.length ? Math.max(...finite) : 40;
  return Math.min(160, Math.max(60, Math.ceil((peak * 1.25) / 10) * 10));
});

function xAt(i: number) {
  const n = Math.max(1, props.times.length - 1);
  return (i / n) * plotW.value;
}

function yAt(v: number) {
  return PAD_TOP + PLOT_H - (Math.min(v, domainMax.value) / domainMax.value) * PLOT_H;
}

const visibleZones = computed(() =>
  ZONES.filter((zone) => zone.from < domainMax.value).map((zone) => ({
    ...zone,
    y: yAt(Math.min(zone.upTo, domainMax.value)),
    h: yAt(zone.from) - yAt(Math.min(zone.upTo, domainMax.value)),
  })),
);

/* Segments split on holes — a gap in the record stays a gap in the line. */
const segments = computed(() => {
  const out: { line: string; area: string }[] = [];
  let line = "";
  let area = "";
  const base = PAD_TOP + PLOT_H;
  props.values.forEach((v, i) => {
    const x = xAt(i);
    if (v == null || !Number.isFinite(v)) {
      if (line) out.push({ line, area: `${area} L ${x} ${base} Z` });
      line = "";
      area = "";
      return;
    }
    const y = yAt(v);
    if (line) {
      line += ` L ${x} ${y}`;
      area += ` L ${x} ${y}`;
    } else {
      line = `M ${x} ${y}`;
      area = `M ${x} ${base} L ${x} ${y}`;
    }
  });
  if (line) out.push({ line, area: `${area} L ${plotW.value} ${base} Z` });
  return out;
});

const activeIndex = computed(() =>
  props.index == null ? Math.max(0, props.times.length - 1) : props.index,
);

const activeValue = computed(() => props.values[activeIndex.value] ?? null);

const timeFmt = new Intl.DateTimeFormat("zh-CN", {
  month: "numeric",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const dayFmt = new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" });

function fmtTime(iso: string | undefined) {
  return iso ? timeFmt.format(new Date(iso)) : "—";
}

function fmtDay(iso: string | undefined) {
  return iso ? dayFmt.format(new Date(iso)) : "";
}

/** How far the playhead sits from now, in plain language. */
const positionLabel = computed(() => {
  if (props.index == null) return "现在";
  const from = props.times[props.index];
  const to = props.times[props.times.length - 1];
  if (!from || !to) return "回放";
  const hours = Math.round((new Date(to).getTime() - new Date(from).getTime()) / 3_600_000);
  if (hours <= 0) return "现在";
  if (hours < 48) return `${hours} 小时前`;
  return `${Math.round(hours / 24)} 天前`;
});

const axisMarks = computed(() => {
  const n = props.times.length;
  if (n < 2) return [];
  const picks = [0, Math.floor(n / 2), n - 1];
  return picks.map((i) => ({ x: xAt(i), label: i === n - 1 ? "现在" : fmtDay(props.times[i]) }));
});

function setFromClientX(clientX: number) {
  const box = root.value?.getBoundingClientRect();
  if (!box || props.times.length < 2) return;
  const ratio = (clientX - box.left) / Math.max(1, box.width);
  const i = Math.round(Math.min(1, Math.max(0, ratio)) * (props.times.length - 1));
  emit("update:index", i >= props.times.length - 1 ? null : i);
}

function onPointerDown(event: PointerEvent) {
  stop();
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  setFromClientX(event.clientX);
}

function onPointerMove(event: PointerEvent) {
  const box = root.value?.getBoundingClientRect();
  if (box) {
    const ratio = (event.clientX - box.left) / Math.max(1, box.width);
    hovered.value = Math.round(Math.min(1, Math.max(0, ratio)) * (props.times.length - 1));
  }
  if (event.buttons === 1) setFromClientX(event.clientX);
}

function onKey(event: KeyboardEvent) {
  const n = props.times.length;
  if (!n) return;
  const step = event.shiftKey ? 24 : 1;
  const cur = activeIndex.value;
  let next: number | null = null;
  if (event.key === "ArrowLeft") next = Math.max(0, cur - step);
  else if (event.key === "ArrowRight") next = Math.min(n - 1, cur + step);
  else if (event.key === "Home") next = 0;
  else if (event.key === "End") next = n - 1;
  else return;
  event.preventDefault();
  stop();
  emit("update:index", next >= n - 1 ? null : next);
}

/* Playback: one sweep through the window, ~11s whatever its length, then it
   rests on 现在 and hands the page back. Any interaction cancels it. */
let timer: number | null = null;

function tick() {
  const n = props.times.length;
  if (!n) return stop();
  const stride = Math.max(1, Math.ceil(n / STEPS));
  const next = (props.index == null ? n - 1 : props.index) + stride;
  if (next >= n - 1) {
    emit("update:index", null);
    stop();
    return;
  }
  emit("update:index", next);
}

function play() {
  if (playing.value || props.times.length < 2) return;
  if (props.index == null || props.index >= props.times.length - 1) emit("update:index", 0);
  playing.value = true;
  timer = window.setInterval(tick, TICK);
}

function stop() {
  playing.value = false;
  if (timer != null) window.clearInterval(timer);
  timer = null;
}

function toggle() {
  if (playing.value) stop();
  else play();
}

function backToNow() {
  stop();
  emit("update:index", null);
}

/* The sweep is user-initiated: the page opens on 现在 and stays still until
   the reader presses play. An auto-sweeping map is a moving target — for the
   eye and for anything reading the DOM. */
if (
  props.autoplay &&
  props.times.length > 2 &&
  !window.matchMedia("(prefers-reduced-motion: reduce)").matches
) {
  window.setTimeout(() => {
    if (props.index == null && !playing.value) play();
  }, 900);
}

onBeforeUnmount(stop);
</script>

<template>
  <div
    ref="root"
    class="time-ribbon"
    role="slider"
    tabindex="0"
    aria-label="近 30 天全国时间轴，拖动可回看每小时的空气状态"
    :aria-valuemin="0"
    :aria-valuemax="Math.max(0, times.length - 1)"
    :aria-valuenow="activeIndex"
    :aria-valuetext="`${fmtTime(times[activeIndex])} ${positionLabel}`"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerleave="hovered = null"
    @keydown="onKey"
  >
    <div class="ribbon-head">
      <button
        type="button"
        class="play"
        :aria-label="playing ? '暂停回放' : '回放近 30 天'"
        @click="toggle"
      >
        <svg v-if="playing" viewBox="0 0 16 16" aria-hidden="true">
          <rect x="3" y="2.5" width="3.4" height="11" rx="1" />
          <rect x="9.6" y="2.5" width="3.4" height="11" rx="1" />
        </svg>
        <svg v-else viewBox="0 0 16 16" aria-hidden="true">
          <path d="M4 2.6 L13.2 8 L4 13.4 Z" />
        </svg>
      </button>

      <div class="readout">
        <strong class="data-mono clock">{{ fmtTime(times[activeIndex]) }}</strong>
        <span class="position" :class="{ live: index == null }">{{ positionLabel }}</span>
        <span v-if="activeValue != null" class="data-mono value">
          中位 PM2.5 {{ activeValue.toFixed(1) }} µg/m³
        </span>
      </div>

      <div class="head-right">
        <span class="caption">{{ caption }}</span>
        <button v-if="index != null" type="button" class="now" @click="backToNow">
          回到现在
        </button>
      </div>
    </div>

    <svg
      class="ribbon-plot"
      :width="plotW"
      :height="HEIGHT"
      :viewBox="`0 0 ${plotW} ${HEIGHT}`"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="ribbon-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#0284c7" stop-opacity=".15" />
          <stop offset="100%" stop-color="#0284c7" stop-opacity=".01" />
        </linearGradient>
      </defs>

      <!-- ruled severity zones, the scale legend -->
      <template v-for="zone in visibleZones" :key="zone.label || 'top'">
        <rect
          :x="0"
          :y="zone.y"
          :width="plotW"
          :height="Math.max(0, zone.h)"
          :fill="stageColor(zone.color)"
          opacity=".06"
        />
        <line
          v-if="zone.upTo !== Infinity && zone.label"
          :x1="0"
          :x2="plotW"
          :y1="zone.y"
          :y2="zone.y"
          :stroke="stageColor(zone.color)"
          stroke-opacity=".25"
          stroke-width="1"
        />
        <text
          v-if="zone.label"
          :x="5"
          :y="zone.y - 3"
          :fill="stageColor(zone.color)"
          font-size="11"
          opacity=".8"
        >
          {{ zone.label }}
        </text>
      </template>

      <g v-for="(seg, i) in segments" :key="i">
        <path :d="seg.area" fill="url(#ribbon-fill)" />
        <path
          :d="seg.line"
          fill="none"
          stroke="#0f172a"
          stroke-width="1.8"
          stroke-linejoin="round"
          stroke-linecap="round"
        />
      </g>

      <!-- axis -->
      <g>
        <text
          v-for="mark in axisMarks"
          :key="mark.label + mark.x"
          :x="Math.min(Math.max(mark.x, 2), plotW - 30)"
          :y="HEIGHT - 6"
          fill="#64748b"
          font-size="11"
          :text-anchor="mark.x < 40 ? 'start' : mark.x > plotW - 40 ? 'end' : 'middle'"
        >
          {{ mark.label }}
        </text>
      </g>

      <!-- hover guide -->
      <g v-if="hovered != null && hovered !== activeIndex">
        <line
          :x1="xAt(hovered)"
          :x2="xAt(hovered)"
          :y1="PAD_TOP"
          :y2="PAD_TOP + PLOT_H"
          stroke="#94a3b8"
          stroke-opacity=".4"
          stroke-width="1"
        />
      </g>

      <!-- playhead -->
      <g>
        <line
          :x1="xAt(activeIndex)"
          :x2="xAt(activeIndex)"
          :y1="PAD_TOP - 4"
          :y2="PAD_TOP + PLOT_H + 4"
          stroke="#0f172a"
          stroke-width="1.5"
        />
        <circle
          v-if="activeValue != null"
          :cx="xAt(activeIndex)"
          :cy="yAt(activeValue)"
          r="8"
          fill="#0284c7"
          opacity=".18"
        />
        <circle
          v-if="activeValue != null"
          :cx="xAt(activeIndex)"
          :cy="yAt(activeValue)"
          r="3.5"
          fill="#0284c7"
        />
      </g>
    </svg>
  </div>
</template>

<style scoped>
.time-ribbon {
  display: grid;
  gap: 6px;
  user-select: none;
  touch-action: none;
  cursor: ew-resize;
}
.time-ribbon:focus-visible {
  outline: 2px solid var(--stage-border);
  outline-offset: 4px;
  border-radius: 6px;
}

.ribbon-head {
  min-height: 44px;
  display: flex;
  align-items: center;
  gap: 14px;
}

.play {
  width: 36px;
  height: 36px;
  flex: none;
  display: grid;
  place-items: center;
  border: 1px solid var(--hairline);
  border-radius: 50%;
  background: var(--sheet);
  color: var(--ink);
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: all var(--duration-fast) ease;
}
.play:hover {
  background: var(--sheet-soft);
  color: var(--accent);
}
.play svg {
  width: 14px;
  height: 14px;
  fill: currentColor;
}

.readout {
  display: flex;
  align-items: baseline;
  gap: 12px;
  min-width: 0;
}
.clock {
  color: var(--stage-ink);
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.02em;
}
.position {
  padding: 2px 8px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-pill);
  color: var(--muted);
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
}
.position.live {
  color: #ffffff;
  background: var(--ink);
  border-color: var(--ink);
  font-weight: 600;
}
.value {
  color: var(--muted);
  font-size: var(--fs-label);
  font-weight: 500;
  white-space: nowrap;
}

.head-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
}
.caption {
  color: var(--muted);
  font-size: var(--fs-label);
  font-weight: 500;
  white-space: nowrap;
}
.now {
  min-height: 28px;
  padding: 0 12px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-pill);
  background: var(--sheet);
  color: var(--ink);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: all var(--duration-fast) ease;
}
.now:hover {
  background: var(--sheet-soft);
}

.ribbon-plot {
  display: block;
  overflow: visible;
}

@media (max-width: 900px) {
  .clock { font-size: 19px; }
  .caption { display: none; }
  .value { display: none; }
}
</style>
