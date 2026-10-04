<!-- LiveStrip — the national now-bar: once the stage scrolls away, a slim
     glass strip pins under the context bar and carries the reading this page
     lives by — metric median, worst city, the 24h trace, update time. -->
<script setup lang="ts">
import { computed } from "vue";
import type { NationalCity } from "../lib/provinces";
import { aqiColor } from "../lib/palette";

type StripMetric = "aqi" | "pm25" | "change";

const props = withDefaults(
  defineProps<{
    cities: NationalCity[];
    metric?: StripMetric;
    updated?: string | null;
    spark?: number[];
    on?: boolean;
  }>(),
  { metric: "aqi", updated: null, spark: () => [], on: false },
);

function median(pick: (city: NationalCity) => number | null | undefined) {
  const values = props.cities
    .map(pick)
    .filter((value): value is number => value != null)
    .sort((a, b) => a - b);
  if (!values.length) return null;
  const mid = values.length >> 1;
  return values.length % 2 ? values[mid] : (values[mid - 1] + values[mid]) / 2;
}

const reading = computed(() => {
  if (props.metric === "pm25") {
    const m = median((city) => city.pm25);
    return { label: "PM2.5 中位", value: m == null ? "—" : m.toFixed(1), unit: "µg/m³" };
  }
  if (props.metric === "change") {
    const m = median((city) => city.pm25_change_24h);
    const text = m == null ? "—" : `${m > 0 ? "+" : ""}${m.toFixed(1)}`;
    return { label: "24h 变化中位", value: text, unit: "µg/m³" };
  }
  const m = median((city) => city.china_aqi);
  return { label: "AQI 中位", value: m == null ? "—" : String(Math.round(m)), unit: "" };
});

const worst = computed(() => {
  const pick:
    | ((city: NationalCity) => number | null | undefined)
    | null =
    props.metric === "pm25"
      ? (city) => city.pm25
      : props.metric === "change"
        ? (city) => city.pm25_change_24h
        : props.metric === "aqi"
          ? (city) => city.china_aqi
          : null;
  if (!pick) return null;
  let best: NationalCity | null = null;
  for (const city of props.cities) {
    const value = pick(city);
    if (value == null) continue;
    if (!best || (pick(best) ?? -Infinity) < value) best = city;
  }
  if (!best) return null;
  const value = pick(best);
  return {
    name: best.name,
    color: aqiColor(best.china_aqi_level),
    text:
      value == null
        ? "—"
        : props.metric === "change"
          ? `${value > 0 ? "+" : ""}${value.toFixed(1)}`
          : String(Math.round(value)),
  };
});

const worstLabel = computed(() => (props.metric === "change" ? "升最快" : "最差"));

const sparkPath = computed(() => {
  const series = props.spark;
  if (series.length < 2) return "";
  const min = Math.min(...series);
  const max = Math.max(...series);
  const span = Math.max(0.5, max - min);
  return series
    .map((value, i) => {
      const x = (i / (series.length - 1)) * 64;
      const y = 16 - ((value - min) / span) * 12;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
});

function fmtUpdated(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}
</script>

<template>
  <div class="live-clip">
    <div class="live-strip" :class="{ on }">
      <div class="live-cell">
        <span class="live-k">{{ reading.label }}</span>
        <b class="data-mono">{{ reading.value }}</b>
        <small v-if="reading.unit">{{ reading.unit }}</small>
      </div>
      <div v-if="worst" class="live-cell">
        <span class="live-k">{{ worstLabel }}</span>
        <span class="live-city">{{ worst.name }}</span>
        <b class="data-mono" :style="{ color: worst.color }">{{ worst.text }}</b>
      </div>
      <svg v-if="sparkPath" class="live-spark" viewBox="0 0 64 18" aria-hidden="true">
        <path :d="sparkPath" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
      </svg>
      <span class="live-time data-mono">{{ fmtUpdated(updated) }}</span>
    </div>
  </div>
</template>

<style scoped>
.live-clip {
  position: sticky;
  top: 60px;
  z-index: 30;
  height: 0;
  overflow: visible;
}

.live-strip {
  display: flex;
  align-items: center;
  gap: 26px;
  height: 44px;
  padding: 0 22px;
  border: 1px solid var(--hairline);
  border-top: 0;
  border-radius: 0 0 var(--radius-md) var(--radius-md);
  background: var(--sheet-glass);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  box-shadow: var(--shadow-sm);
  transform: translateY(-110%);
  opacity: 0;
  transition:
    transform 0.4s var(--ease-out),
    opacity 0.3s ease;
}

.live-strip.on {
  transform: translateY(0);
  opacity: 1;
}

.live-cell {
  display: flex;
  align-items: baseline;
  gap: 8px;
  white-space: nowrap;
}

.live-k {
  color: var(--muted);
  font-size: 11px;
  font-weight: 500;
}

.live-cell b {
  color: var(--ink);
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.live-cell small {
  color: var(--faint);
  font-size: 10.5px;
}

.live-city {
  color: var(--ink-soft);
  font-size: 12.5px;
  font-weight: 600;
}

.live-spark {
  flex: none;
  width: 64px;
  height: 18px;
  color: var(--ink-soft);
}

.live-time {
  margin-left: auto;
  color: var(--muted);
  font-size: 11px;
}
</style>
