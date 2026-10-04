<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { flipReorder, gsap, prefersReducedMotion } from "../lib/motion";
import {
  AQI_LEVEL_COLORS,
  CHANGE_COLORS,
  CHANGE_LEVELS,
  MUTED_DATA_COLOR,
  PM25_BANDS,
  changeState,
} from "../lib/palette";
import type { NationalCity } from "../lib/provinces";

type BandMetric = "aqi" | "pm25" | "change";

const props = withDefaults(
  defineProps<{ cities: NationalCity[]; metric?: BandMetric; focusId?: number | null }>(),
  { metric: "aqi", focusId: null },
);
const emit = defineEmits<{ select: [id: number, name: string] }>();

/* The band re-encodes itself to whatever the map above is speaking: AQI
   levels, PM2.5 bands or 24h change — one reading per metric, never a mix. */
function bandOf(city: NationalCity): { value: number | null; key: string; color: string } | null {
  if (props.metric === "pm25") {
    const v = city.pm25 ?? null;
    if (v == null) return null;
    const band = PM25_BANDS.find(([, color], i) => {
      const hi = [35, 75, 115, 150, Infinity][i]!;
      return v <= hi;
    });
    return { value: v, key: band?.[0] ?? "—", color: band?.[1] ?? MUTED_DATA_COLOR };
  }
  if (props.metric === "change") {
    const v = city.pm25_change_24h ?? null;
    if (v == null) return null;
    const key = changeState(v).label;
    return { value: v, key, color: CHANGE_COLORS[key as keyof typeof CHANGE_COLORS] ?? MUTED_DATA_COLOR };
  }
  const level = city.china_aqi_level;
  if (!level) return null;
  return {
    value: city.china_aqi ?? null,
    key: level,
    color: AQI_LEVEL_COLORS[level] ?? MUTED_DATA_COLOR,
  };
}

const BAND_ORDER: Record<BandMetric, string[]> = {
  aqi: Object.keys(AQI_LEVEL_COLORS),
  pm25: PM25_BANDS.map(([label]) => label),
  change: [...CHANGE_LEVELS],
};

/* Missing stays missing: a province with no reading sorts last and keeps the
   neutral mark rather than being folded into a band. */
const ordered = computed(() => {
  const rows = props.cities.map((city) => ({
    city,
    ...(bandOf(city) ?? { value: null, key: "暂无", color: MUTED_DATA_COLOR }),
  }));
  rows.sort((a, b) => {
    if (a.value == null) return 1;
    if (b.value == null) return -1;
    return a.value - b.value;
  });
  return rows;
});

const total = computed(() => props.cities.length || 1);

/* Dim only when the focused city actually lives in this band — a focus
   outside the dataset must not wash out the whole chart. */
const focusActive = computed(
  () => props.focusId != null && props.cities.some((city) => city.location_id === props.focusId),
);

/** Index of the first unit in each band — the boundary ruler reads off these. */
const marks = computed(() => {
  const rows = ordered.value;
  const out: { level: string; count: number; start: number }[] = [];
  let cursor = 0;
  for (const key of BAND_ORDER[props.metric]) {
    const at = rows.findIndex((row) => row.key === key);
    if (at < 0) continue;
    const count = rows.filter((row) => row.key === key).length;
    out.push({ level: key, count, start: at });
    cursor += count;
  }
  const missing = rows.filter((row) => row.key === "暂无").length;
  if (missing) out.push({ level: "暂无", count: missing, start: rows.length - missing });
  return out;
});

/* The fact row re-encodes with the metric too: the median and its unit move
   together, never a PM2.5 number sitting under an AQI headline. */
const facts = computed(() => {
  const cities = props.cities;
  const median = (pick: (city: NationalCity) => number | null | undefined) => {
    const values = cities
      .map(pick)
      .filter((value): value is number => value != null)
      .sort((a, b) => a - b);
    if (!values.length) return null;
    const mid = values.length >> 1;
    return values.length % 2 ? values[mid] : (values[mid - 1] + values[mid]) / 2;
  };
  const rising = cities.filter((city) => (city.pm25_change_24h ?? 0) >= 8).length;
  const falling = cities.filter((city) => (city.pm25_change_24h ?? 0) <= -8).length;
  if (props.metric === "pm25") {
    const m = median((city) => city.pm25);
    return [
      { dt: "PM2.5 中位", dd: m == null ? "—" : m.toFixed(1), small: " µg/m³" },
      { dt: "24h 上升", dd: String(rising), small: " 省" },
      { dt: "24h 改善", dd: String(falling), small: " 省" },
    ];
  }
  if (props.metric === "change") {
    const m = median((city) => city.pm25_change_24h);
    const text = m == null ? "—" : `${m > 0 ? "+" : ""}${m.toFixed(1)}`;
    return [
      { dt: "24h 变化中位", dd: text, small: " µg/m³" },
      { dt: "上升", dd: String(rising), small: " 省" },
      { dt: "改善", dd: String(falling), small: " 省" },
    ];
  }
  const m = median((city) => city.china_aqi);
  return [
    { dt: "AQI 中位", dd: m == null ? "—" : String(Math.round(m)), small: "" },
    { dt: "24h 上升", dd: String(rising), small: " 省" },
    { dt: "24h 改善", dd: String(falling), small: " 省" },
  ];
});

/** The number inside each square is the metric's own reading, not always AQI. */
function readingText(row: { value: number | null }) {
  if (row.value == null) return "—";
  if (props.metric === "change") {
    return `${row.value > 0 ? "+" : ""}${row.value.toFixed(1)}`;
  }
  return String(Math.round(row.value));
}

const unitsEl = ref<HTMLElement | null>(null);

/* Metric swaps re-encode every square: slots glide to their new order (FLIP)
   while the numbers crossfade in place — nothing teleports or blinks. */
watch(
  () => props.metric,
  () => {
    const container = unitsEl.value;
    if (!container) return;
    const items = Array.from(container.querySelectorAll<HTMLElement>(".unit-col"));
    flipReorder(items, async () => {
      await nextTick();
    });
    if (prefersReducedMotion()) return;
    gsap.fromTo(
      container.querySelectorAll(".unit-aqi"),
      { autoAlpha: 0, y: 4 },
      {
        autoAlpha: 1,
        y: 0,
        duration: 0.45,
        stagger: 0.006,
        ease: "power2.out",
        clearProps: "transform",
      },
    );
  },
);

function shortName(name: string) {
  return name.slice(0, 2);
}



function unitTip(row: {
  city: NationalCity;
  value: number | null;
  key: string;
}) {
  const state = changeState(row.city.pm25_change_24h);
  const change =
    row.city.pm25_change_24h == null
      ? "历史不足"
      : `${state.arrow} ${state.label} ${Math.abs(row.city.pm25_change_24h).toFixed(1)}`;
  const reading =
    row.value == null ? "—" : props.metric === "change" ? row.value.toFixed(1) : row.value.toFixed(0);
  return `${row.city.name} · ${row.city.province ?? row.city.region}
${row.key} ${reading}
PM2.5 ${
    row.city.pm25?.toFixed(1) ?? "—"
  } µg/m³ · 24h ${change}`;
}

/* Position and alignment come from one function as inline styles, not from a
   class toggle: a label near the right edge must grow leftward from its
   boundary or the level name is clipped by the plot edge, and that must not
   be able to fail silently. */
function rulerStyle(mark: { start: number }) {
  const at = mark.start / total.value;
  const flip = at > 0.66;
  return {
    left: `${at * 100}%`,
    transform: flip ? "translateX(-100%)" : "translateX(-1px)",
    paddingLeft: flip ? "8px" : "0",
    paddingRight: flip ? "0" : "8px",
  };
}

/** The boundary tick sits on whichever edge of the label touches the boundary. */
function tickStyle(mark: { start: number }) {
  const flip = mark.start / total.value > 0.66;
  return flip ? { right: 0, left: "auto" } : { left: 0, right: "auto" };
}
</script>

<template>
  <section class="severity-band" aria-label="省级等级分布">
    <div class="band-plot">
      <div ref="unitsEl" class="units" role="list">
        <div
          v-for="(row, index) in ordered"
          :key="row.city.location_id"
          class="unit-col"
          :class="{
            dimmed: focusActive && focusId !== row.city.location_id,
          }"
          role="listitem"
        >
          <button
            type="button"
            class="unit"
            :style="{ background: row.color }"
            :class="{ focused: focusId === row.city.location_id }"
            :title="unitTip(row)"
            :aria-label="`${index + 1}/${total} ${unitTip(row)}`"
            @click="emit('select', row.city.location_id, row.city.name)"
          >
            <b class="unit-aqi data-mono">{{ readingText(row) }}</b>
            <span class="sr-only">{{ row.city.name }}</span>
          </button>
          <span class="unit-name">{{ shortName(row.city.name) }}</span>
        </div>
      </div>

      <div class="ruler" aria-hidden="true">
        <span
          v-for="mark in marks"
          :key="mark.level"
          class="ruler-mark"
          :style="rulerStyle(mark)"
        >
          <i class="tick" :style="tickStyle(mark)"></i>
          <i class="swatch" :style="{ background: ordered[mark.start]?.color ?? MUTED_DATA_COLOR }"></i>
          {{ mark.level }}
          <b class="data-mono">{{ mark.count }}</b>
        </span>
      </div>
    </div>

    <dl class="band-facts">
      <div v-for="fact in facts" :key="fact.dt">
        <dt>{{ fact.dt }}</dt>
        <dd>{{ fact.dd }}<small>{{ fact.small }}</small></dd>
      </div>
    </dl>
  </section>
</template>

<style scoped>
.severity-band {
  display: grid;
  gap: 14px;
  padding: 0;
}

.band-plot {
  min-width: 0;
  display: grid;
  gap: 12px;
}

.units {
  display: flex;
  gap: 3px;
}

.unit-col {
  flex: 1 1 0;
  min-width: 0;
  display: grid;
  gap: 3px;
  justify-items: center;
  transition: opacity var(--duration-fast) ease;
}
.unit-col.dimmed {
  opacity: 0.28;
}

.unit {
  width: 100%;
  height: 46px;
  padding: 0;
  border: 0;
  border-radius: 2px;
  cursor: pointer;
  opacity: 0.92;
  display: grid;
  place-items: center;
  transition: transform var(--duration-fast) ease, opacity var(--duration-fast) ease;
}
.unit:hover,
.unit:focus-visible {
  opacity: 1;
  transform: scaleY(1.08);
  outline: 2px solid var(--ink);
  outline-offset: 1px;
}
.unit.focused {
  outline: 2px solid var(--ink);
  outline-offset: 2px;
}

.unit-aqi {
  color: #ffffff;
  font-size: 11.5px;
  font-weight: 700;
  text-shadow: 0 1px 2px rgba(15, 23, 42, 0.45);
  font-variant-numeric: tabular-nums;
}

.unit-name {
  color: var(--muted);
  font-family: var(--font-sans);
  font-size: 10px;
  line-height: 1;
  white-space: nowrap;
  overflow: hidden;
  max-width: 100%;
}

.ruler {
  position: relative;
  height: 18px;
}
.ruler-mark {
  position: absolute;
  top: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--muted);
  font-size: 11px;
  white-space: nowrap;
}
.ruler-mark .tick {
  position: absolute;
  top: -12px;
  left: 0;
  width: 1px;
  height: 10px;
  background: var(--hairline-strong);
}
.ruler-mark .swatch {
  width: 7px;
  height: 7px;
  border-radius: 2px;
}
.ruler-mark b {
  color: var(--ink);
  font-weight: 600;
}

.band-facts {
  margin: 0;
  padding-top: 12px;
  border-top: 1px solid var(--hairline-soft);
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 8px 0;
}
.band-facts > div {
  flex: 0 0 auto;
  padding: 0 20px;
  border-right: 1px solid var(--hairline-soft);
}
.band-facts > div:first-child { padding-left: 0; }
.band-facts > div:last-child { border-right: 0; }
.band-facts dt {
  color: var(--muted);
  font-size: 11px;
  font-weight: 500;
}
.band-facts dd {
  margin: 2px 0 0;
  color: var(--ink);
  font-size: 16px;
  font-weight: 600;
  line-height: 1.2;
}
.band-facts dd small {
  color: var(--muted);
  font-size: 11px;
  font-weight: 400;
}
.band-rule {
  margin-left: auto;
  border-right: 0;
}
.band-rule dd {
  color: var(--muted);
  font-size: var(--fs-label);
  font-weight: var(--fw-body);
}

@media (max-width: 860px) {
  .unit { height: 54px; }
  .ruler { display: none; }
  .band-facts { gap: 12px 0; }
  .band-facts > div { padding: 0 16px; }
  .band-rule {
    margin-left: 0;
    flex-basis: 100%;
    padding-left: 0;
  }
}
</style>
