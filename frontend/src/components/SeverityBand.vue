<script setup lang="ts">
import { computed } from "vue";
import { AQI_LEVELS, AQI_LEVEL_COLORS, MUTED_DATA_COLOR, changeState } from "../lib/palette";
import type { NationalCity } from "../lib/provinces";

const props = defineProps<{ cities: NationalCity[] }>();
const emit = defineEmits<{ select: [id: number, name: string] }>();

/* Missing stays missing: a province with no AQI sorts last and keeps the
   neutral mark rather than being folded into a level. */
const ordered = computed(() => {
  const rows = props.cities.map((city) => ({
    city,
    aqi: city.china_aqi ?? null,
    level: city.china_aqi_level ?? null,
  }));
  rows.sort((a, b) => {
    if (a.aqi == null) return 1;
    if (b.aqi == null) return -1;
    return a.aqi - b.aqi;
  });
  return rows;
});

const total = computed(() => props.cities.length || 1);

/** Index of the first unit in each level — the boundary ruler reads off these. */
const marks = computed(() => {
  const rows = ordered.value;
  const out: { level: string; count: number; start: number }[] = [];
  let cursor = 0;
  for (const level of AQI_LEVELS) {
    const count = rows.filter((row) => row.level === level).length;
    if (count === 0) continue;
    const at = rows.findIndex((row) => row.level === level);
    out.push({ level, count, start: at < 0 ? cursor : at });
    cursor += count;
  }
  const missing = rows.filter((row) => row.level == null).length;
  if (missing) out.push({ level: "暂无", count: missing, start: rows.length - missing });
  return out;
});

const medianPm25 = computed(() => {
  const values = props.cities
    .map((city) => city.pm25)
    .filter((value): value is number => value != null)
    .sort((a, b) => a - b);
  if (!values.length) return null;
  const mid = values.length >> 1;
  return values.length % 2 ? values[mid] : (values[mid - 1] + values[mid]) / 2;
});

const risingCount = computed(
  () => props.cities.filter((city) => (city.pm25_change_24h ?? 0) >= 8).length,
);
const fallingCount = computed(
  () => props.cities.filter((city) => (city.pm25_change_24h ?? 0) <= -8).length,
);

function bandColor(level: string | null) {
  if (!level) return MUTED_DATA_COLOR;
  return AQI_LEVEL_COLORS[level] ?? MUTED_DATA_COLOR;
}

function unitTip(row: { city: NationalCity; aqi: number | null; level: string | null }) {
  const state = changeState(row.city.pm25_change_24h);
  const change =
    row.city.pm25_change_24h == null
      ? "历史不足"
      : `${state.arrow} ${state.label} ${Math.abs(row.city.pm25_change_24h).toFixed(1)}`;
  return `${row.city.name} · ${row.city.province ?? row.city.region}\n${
    row.level ?? "暂无"
  } AQI ${row.aqi ?? "—"}\nPM2.5 ${row.city.pm25?.toFixed(1) ?? "—"} µg/m³ · 24h ${change}`;
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
  <section class="severity-band" aria-label="全国省级空气质量等级分布">
    <div class="band-plot">
      <div class="units" role="list">
        <button
          v-for="(row, index) in ordered"
          :key="row.city.location_id"
          type="button"
          role="listitem"
          class="unit"
          :style="{ background: bandColor(row.level) }"
          :title="unitTip(row)"
          :aria-label="`${index + 1}/${total} ${unitTip(row)}`"
          @click="emit('select', row.city.location_id, row.city.name)"
        >
          <span class="sr-only">{{ row.city.name }}</span>
        </button>
      </div>

      <div class="ruler" aria-hidden="true">
        <span
          v-for="mark in marks"
          :key="mark.level"
          class="ruler-mark"
          :style="rulerStyle(mark)"
        >
          <i class="tick" :style="tickStyle(mark)"></i>
          <i class="swatch" :style="{ background: bandColor(mark.level) }"></i>
          {{ mark.level }}
          <b class="data-mono">{{ mark.count }}</b>
        </span>
      </div>
    </div>

    <dl class="band-facts">
      <div>
        <dt>PM2.5 中位</dt>
        <dd>{{ medianPm25 == null ? "—" : medianPm25.toFixed(1) }}<small> µg/m³</small></dd>
      </div>
      <div>
        <dt>24h 上升</dt>
        <dd>{{ risingCount }}<small> 省</small></dd>
      </div>
      <div>
        <dt>24h 改善</dt>
        <dd>{{ fallingCount }}<small> 省</small></dd>
      </div>
      <div class="band-rule">
        <dt>排列</dt>
        <dd>一格一省，由低到高</dd>
      </div>
    </dl>
  </section>
</template>

<style scoped>
.severity-band {
  display: grid;
  gap: 16px;
  padding: 22px 28px 18px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-xl);
  background: var(--sheet);
  box-shadow: var(--shadow-sm);
  transition: all var(--duration-normal) var(--ease-out);
}
.severity-band:hover {
  border-color: var(--hairline-strong);
  box-shadow: var(--shadow-md);
}

.band-plot {
  min-width: 0;
  display: grid;
  gap: 14px;
}

.units {
  display: flex;
  gap: 4px;
}

/* 4px surface gap between fills — separation by whitespace, never a stroke
   drawn around each mark. Thirty-one units read as thirty-one provinces,
   not as a continuous gradient. */
.unit {
  flex: 1 1 0;
  min-width: 0;
  height: 80px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-xs);
  cursor: pointer;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  transition: transform var(--duration-fast) var(--ease-spring), box-shadow var(--duration-fast) ease;
}
.unit:hover,
.unit:focus-visible {
  transform: translateY(-6px) scaleY(1.04);
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.16);
  outline: 2px solid var(--ink);
  outline-offset: 1px;
}

.ruler {
  position: relative;
  height: 20px;
}
.ruler-mark {
  position: absolute;
  top: 0;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--muted);
  font-size: var(--fs-label);
  white-space: nowrap;
}
.ruler-mark .tick {
  position: absolute;
  top: -13px;
  left: 0;
  width: 1px;
  height: 11px;
  background: var(--hairline-strong);
}
.ruler-mark .swatch {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.ruler-mark b {
  color: var(--ink);
  font-weight: var(--fw-strong);
}

/* The supporting readings sit under the band as a data rail: label above
   value, rules between, so the strip reads as one instrument rather than a
   detached stat block beside the chart. */
.band-facts {
  margin: 0;
  padding-top: 13px;
  border-top: 1px solid var(--hairline-soft);
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 10px 0;
}
.band-facts > div {
  flex: 0 0 auto;
  padding: 0 22px;
  border-right: 1px solid var(--hairline-soft);
}
.band-facts > div:first-child { padding-left: 0; }
.band-facts > div:last-child { border-right: 0; }
.band-facts dt {
  color: var(--muted);
  font-size: var(--fs-label);
}
.band-facts dd {
  margin: 3px 0 0;
  color: var(--ink);
  font-size: 19px;
  font-weight: var(--fw-strong);
  line-height: 1.15;
}
.band-facts dd small {
  color: var(--muted);
  font-size: var(--fs-label);
  font-weight: var(--fw-body);
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
