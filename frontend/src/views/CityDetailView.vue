<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { useRoute } from "vue-router";
import { Activity, BarChart3, Clock3, Layers3, ShieldCheck } from "lucide-vue-next";
import { api } from "../api/client";
import { expectData } from "../api/request";
import BacktestAnatomy from "../components/BacktestAnatomy.vue";
import HorizonChart from "../components/HorizonChart.vue";
import HourRing from "../components/HourRing.vue";
import PCAStructurePanel from "../components/PCAStructurePanel.vue";
import WindClearance from "../components/WindClearance.vue";
import TraceDeck from "../components/TraceDeck.vue";
import TrustPanel from "../components/TrustPanel.vue";
import WaterfallChart from "../components/WaterfallChart.vue";
import { useLocationCatalog } from "../composables/useLocationCatalog";
import { useCountUp } from "../composables/useCountUp";
import { aqiColor, POLLUTANT_COLORS } from "../lib/palette";
import { useContextStore } from "../stores/context";

const route = useRoute();
const context = useContextStore();
const { locations } = useLocationCatalog();

const locationId = computed(() => Number(route.params.locationId));
const activeSection = ref("trend");
let spy: IntersectionObserver | null = null;

/* The editorial rail fills its hairline down to the section you're reading. */
const RAIL_SECTIONS = ["trend", "pollutants", "rhythm", "structure", "trust"] as const;
const railIndex = computed(() =>
  Math.max(0, RAIL_SECTIONS.indexOf(activeSection.value as (typeof RAIL_SECTIONS)[number])),
);

onMounted(() => {
  spy = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) activeSection.value = entry.target.id;
      }
    },
    { rootMargin: "-38% 0px -52% 0px" },
  );
  for (const id of ["trend", "pollutants", "rhythm", "structure", "trust"]) {
    const el = document.getElementById(id);
    if (el) spy.observe(el);
  }
});

onBeforeUnmount(() => spy?.disconnect());
const heatmap = ref<InstanceType<typeof HourRing> | null>(null);
const POLLUTANTS = ["pm25", "pm10", "no2", "o3", "so2", "co"] as const;
const POLLUTANT_LABELS: Record<string, string> = {
  pm25: "PM2.5",
  pm10: "PM10",
  no2: "NO₂",
  o3: "O₃",
  so2: "SO₂",
  co: "CO",
};
const HORIZON_COLORS = POLLUTANT_COLORS;

watch(
  [locationId, () => locations.data.value],
  ([id, catalog]) => {
    const location = catalog?.find((item) => item.location_id === id);
    if (location) context.selectLocation(location.location_id, location.city);
  },
  { immediate: true },
);

const snapshot = useQuery({
  queryKey: computed(() => ["city-detail-snapshot", locationId.value]),
  enabled: computed(() => Number.isInteger(locationId.value) && locationId.value > 0),
  queryFn: () =>
    expectData(
      api.GET("/api/locations/{location_id}/snapshot", {
        params: { path: { location_id: locationId.value } },
      }),
    ),
  refetchInterval: 60_000,
});

const national = useQuery({
  queryKey: ["city-detail-national"],
  queryFn: () => expectData(api.GET("/api/overview/national")),
  staleTime: 60_000,
});

const pulse = useQuery({
  queryKey: computed(() => ["city-pulse", locationId.value]),
  enabled: computed(() => Number.isInteger(locationId.value) && locationId.value > 0),
  queryFn: () =>
    Promise.all(
      POLLUTANTS.map((variable) =>
        expectData(
          api.GET("/api/locations/{location_id}/series", {
            params: {
              path: { location_id: locationId.value },
              query: { variable, data_kind: "model_analysis", hours: 720 },
            },
          }),
        ),
      ),
    ),
  staleTime: 60_000,
});

const observation = useQuery({
  queryKey: computed(() => ["city-detail-observation", locationId.value]),
  enabled: computed(() => Number.isInteger(locationId.value) && locationId.value > 0),
  queryFn: () =>
    expectData(
      api.GET("/api/locations/{location_id}/series", {
        params: {
          path: { location_id: locationId.value },
          query: { variable: "pm25", data_kind: "observation", hours: 720 },
        },
      }),
    ),
});

const forecast = useQuery({
  queryKey: computed(() => ["city-detail-forecast", locationId.value]),
  enabled: computed(() => Number.isInteger(locationId.value) && locationId.value > 0),
  queryFn: () =>
    expectData(
      api.GET("/api/locations/{location_id}/forecast", {
        params: {
          path: { location_id: locationId.value },
          query: { variable: "pm25" },
        },
      }),
    ),
});

/* City-scoped slice of the national weather matrix: the phase path and the
   wind-clearance reading both need hourly wind beside the PM2.5 field. */
const cityWeather = useQuery({
  queryKey: computed(() => ["city-weather", locationId.value]),
  enabled: computed(() => Number.isInteger(locationId.value) && locationId.value > 0),
  queryFn: () =>
    expectData(
      api.GET("/api/overview/national/weather", {
        params: { query: { hours: 720, location_id: locationId.value } },
      }),
    ),
  staleTime: 15 * 60_000,
});

const structure = useQuery({
  queryKey: computed(() => ["city-detail-structure", locationId.value]),
  enabled: computed(() => Number.isInteger(locationId.value) && locationId.value > 0),
  retry: false,
  queryFn: () =>
    expectData(
      api.GET("/api/locations/{location_id}/structure", {
        params: { path: { location_id: locationId.value } },
      }),
    ),
});

const backtest = useQuery({
  queryKey: computed(() => ["city-detail-backtest", locationId.value]),
  enabled: computed(() => Number.isInteger(locationId.value) && locationId.value > 0),
  queryFn: () =>
    expectData(
      api.GET("/api/locations/{location_id}/backtest", {
        params: { path: { location_id: locationId.value } },
      }),
    ),
});

const coverage = useQuery({
  queryKey: computed(() => ["city-detail-coverage", locationId.value]),
  enabled: computed(() => Number.isInteger(locationId.value) && locationId.value > 0),
  queryFn: () =>
    expectData(
      api.GET("/api/locations/{location_id}/coverage", {
        params: {
          path: { location_id: locationId.value },
          query: { days: 30 },
        },
      }),
    ),
});

const nationalCity = computed(() =>
  national.data.value?.cities.find((city) => city.location_id === locationId.value),
);
const pm25Series = computed(() =>
  pulse.data.value?.find((series) => series.variable === "pm25"),
);
const modelPm25 = computed(() => snapshot.data.value?.model_analysis?.pm25);
const observedPm25 = computed(() => snapshot.data.value?.observation?.pm25);

/* 未来 24h: the CAMS peak for this city and the trend word against the
   current reading — the hero's action cell, no new request. */
const camsPoints = computed(
  () =>
    forecast.data.value?.series.find((series) => series.model_name === "CAMS")
      ?.points ?? [],
);
const nextPeak = computed(() => {
  const points = camsPoints.value;
  if (!points.length) return null;
  const peak = points.reduce((a, b) => (b.value > a.value ? b : a));
  return { value: peak.value, at: peak.target_at };
});
const basePm25 = computed(() =>
  modelPm25.value != null ? Number(modelPm25.value) : camsPoints.value[0]?.value ?? null,
);
const peakWord = computed(() => {
  if (nextPeak.value == null || basePm25.value == null) return "";
  const delta = nextPeak.value.value - basePm25.value;
  if (delta >= 5) return "↑升";
  if (delta <= -5) return "↓降";
  return "→平";
});
const peakAtText = computed(() => {
  if (!nextPeak.value) return "";
  const at = new Date(nextPeak.value.at);
  const now = new Date();
  const day = at.getDate() === now.getDate() ? "今" : "明";
  return `${day} ${String(at.getHours()).padStart(2, "0")}:00`;
});

/* Hero status numbers land with a count-up instead of popping in. */
const aqiTarget = computed(() =>
  nationalCity.value?.china_aqi == null
    ? null
    : Number(nationalCity.value.china_aqi),
);
const modelTarget = computed(() =>
  modelPm25.value != null && Number.isFinite(Number(modelPm25.value))
    ? Number(modelPm25.value)
    : null,
);
const observedTarget = computed(() =>
  observedPm25.value != null && Number.isFinite(Number(observedPm25.value))
    ? Number(observedPm25.value)
    : null,
);
const aqiDisplay = useCountUp(aqiTarget);
const modelDisplay = useCountUp(modelTarget);
const observedDisplay = useCountUp(observedTarget);

const aqiText = computed(() =>
  aqiTarget.value == null ? "—" : Math.round(aqiDisplay.value).toString(),
);
const modelText = computed(() =>
  modelTarget.value == null ? "—" : modelDisplay.value.toFixed(1),
);
const observedText = computed(() =>
  observedTarget.value == null ? "—" : observedDisplay.value.toFixed(1),
);

function fmt(value: number | null | undefined, digits = 1) {
  return value == null || !Number.isFinite(value) ? "—" : value.toFixed(digits);
}

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

function average(values: number[]) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

const pm25Trend = computed(() => {
  const points = (pm25Series.value?.points ?? []).filter(
    (point): point is typeof point & { value: number } => point.value != null,
  );
  if (!points.length) {
    return {
      delta: null as number | null,
      peak: null as number | null,
      peakTime: null as string | null,
      recentAvg: null as number | null,
    };
  }
  const latestTime = new Date(points.at(-1)!.time).getTime();
  const recent = points.filter(
    (point) => new Date(point.time).getTime() >= latestTime - 24 * 3600 * 1000,
  );
  const previous = points.filter((point) => {
    const time = new Date(point.time).getTime();
    return time >= latestTime - 48 * 3600 * 1000 && time < latestTime - 24 * 3600 * 1000;
  });
  const recentAvg = average(recent.map((point) => Number(point.value)));
  const previousAvg = average(previous.map((point) => Number(point.value)));
  const peakPoint = recent.reduce(
    (best, point) => (Number(point.value) > Number(best.value) ? point : best),
    recent[0],
  );
  return {
    delta: recentAvg != null && previousAvg != null ? recentAvg - previousAvg : null,
    peak: peakPoint?.value ?? null,
    peakTime: peakPoint?.time ?? null,
    recentAvg,
  };
});

const trendSentence = computed(() => {
  const delta = pm25Trend.value.delta;
  if (delta == null) return "样本不足";
  if (Math.abs(delta) < 2) return "基本持平";
  return `${delta > 0 ? "上升" : "下降"} ${Math.abs(delta).toFixed(1)}`;
});





/* ── phase path: wind × PM2.5 ─────────────────────────────── */
const phasePoints = computed(() => {
  const series = pm25Series.value;
  const weatherData = cityWeather.data.value;
  if (!series || !weatherData) return [];
  const pmByTime = new Map(
    series.points
      .filter((point) => point.value != null)
      .map((point) => [point.time, Number(point.value)]),
  );
  const city = weatherData.cities[0];
  if (!city) return [];
  const out: Array<{ time: string; pm25: number; wind: number }> = [];
  weatherData.times.forEach((time, i) => {
    const wind = city.wind_speed[i];
    const pm25 = pmByTime.get(time);
    if (wind != null && pm25 != null) out.push({ time, pm25, wind });
  });
  return out;
});



/* ── horizon: six pollutants folded ───────────────────────── */
const horizonTimes = computed(
  () => pulse.data.value?.[0]?.points.map((point) => point.time) ?? [],
);

const horizonSeries = computed(() =>
  (pulse.data.value ?? []).map((item) => ({
    key: item.variable,
    label: POLLUTANT_LABELS[item.variable] ?? item.variable,
    color: HORIZON_COLORS[item.variable] ?? "#94a3b8",
    values: item.points.map((point) => point.value),
  })),
);

/* ── waterfall: how the month was built ───────────────────── */
const dailyPm = computed(() => {
  const points = (pm25Series.value?.points ?? []).filter(
    (point): point is typeof point & { value: number } => point.value != null,
  );
  const buckets = new Map<string, number[]>();
  for (const point of points) {
    const key = point.time.slice(0, 10);
    const arr = buckets.get(key) ?? [];
    arr.push(Number(point.value));
    buckets.set(key, arr);
  }
  const days = [...buckets.keys()].sort();
  const values = days.map((day) => {
    const arr = buckets.get(day)!;
    return arr.length >= 12
      ? arr.reduce((sum, value) => sum + value, 0) / arr.length
      : null;
  });
  return { days, values };
});




/* Model-vs-observation is only a statement about model bias when both readings
   describe the same hour. Comparability is a precondition of the claim. */
const COMPARABLE_HOURS = 3;

const observationTime = computed(() => snapshot.data.value?.observation?.source_time);

const observationLag = computed(() => {
  const observed = observationTime.value;
  const model = snapshot.data.value?.model_analysis?.source_time;
  if (!observed || !model) return null;
  return Math.abs(new Date(model).getTime() - new Date(observed).getTime()) / 3_600_000;
});

const observationComparable = computed(
  () => observationLag.value != null && observationLag.value <= COMPARABLE_HOURS,
);

const sourceGap = computed(() => {
  if (!observationComparable.value) return null;
  if (modelPm25.value == null || observedPm25.value == null) return null;
  return Number(modelPm25.value) - Number(observedPm25.value);
});

</script>

<template>
  <section class="city-detail">
    <header class="city-hero">
      <div class="hero-title">
        <h1 class="display-face">{{ snapshot.data.value?.city ?? context.selectedCityName }}</h1>
        <span class="city-province">{{ snapshot.data.value?.province ?? "" }}</span>
      </div>

      <section
        class="current-status"
        :style="{ '--aqi-tone': aqiColor(nationalCity?.china_aqi_level) }"
        aria-label="当前空气质量"
      >
        <article class="status-main">
          <span class="status-dot" aria-hidden="true"></span>
          <div>
            <strong>{{ nationalCity?.china_aqi_level ?? "暂无" }}</strong>
            <p>AQI {{ aqiText }}</p>
          </div>
        </article>
        <article>
          <small>PM2.5</small>
          <strong>{{ modelText }}</strong>
          <p>µg/m³</p>
        </article>
        <article>
          <small>24h 变化</small>
          <strong :class="{ bad: (pm25Trend.delta ?? 0) > 0, good: (pm25Trend.delta ?? 0) < 0 }">
            {{ trendSentence }}
          </strong>
          <p>日均 {{ fmt(pm25Trend.recentAvg) }}</p>
        </article>
        <article>
          <small>地面实测</small>
          <strong>{{ observedText }}</strong>
          <p v-if="sourceGap != null">{{ sourceGap > 0 ? "偏高" : "偏低" }} {{ Math.abs(sourceGap).toFixed(1) }}</p>
          <p v-else-if="observedPm25 != null">{{ fmtTime(observationTime) }}</p>
          <p v-else>—</p>
        </article>
        <article>
          <small>未来 24h</small>
          <strong>{{ nextPeak?.value.toFixed(0) ?? "—" }}</strong>
          <p v-if="nextPeak">{{ peakWord }} · 峰 {{ peakAtText }}</p>
          <p v-else>—</p>
        </article>
      </section>
    </header>


    <nav class="section-nav" aria-label="城市详情分区">
      <a href="#trend"><Activity :size="15" />趋势</a>
      <a href="#pollutants"><BarChart3 :size="15" />构成</a>
      <a href="#rhythm"><Clock3 :size="15" />节律</a>
      <a href="#structure"><Layers3 :size="15" />结构</a>
      <a href="#trust"><ShieldCheck :size="15" />回测</a>
    </nav>

    <div class="city-body">
    <nav class="section-rail" aria-label="城市详情分区">
      <span class="rail-line" aria-hidden="true"></span>
      <span
        class="rail-fill"
        :style="{ height: `calc(${railIndex} * var(--rail-pitch) + 12px)` }"
        aria-hidden="true"
      ></span>
      <a href="#trend" :class="{ active: activeSection === 'trend' }"><span class="rail-no">01</span><span class="rail-word">趋势</span></a>
      <a href="#pollutants" :class="{ active: activeSection === 'pollutants' }"><span class="rail-no">02</span><span class="rail-word">构成</span></a>
      <a href="#rhythm" :class="{ active: activeSection === 'rhythm' }"><span class="rail-no">03</span><span class="rail-word">节律</span></a>
      <a href="#structure" :class="{ active: activeSection === 'structure' }"><span class="rail-no">04</span><span class="rail-word">结构</span></a>
      <a href="#trust" :class="{ active: activeSection === 'trust' }"><span class="rail-no">05</span><span class="rail-word">回测</span></a>
    </nav>

    <div class="city-sections">
    <section id="trend" v-reveal class="detail-section first-section">
      <div class="section-heading">
        <h2 class="sec-label">趋势</h2>
      </div>
      <TraceDeck
        :history="pm25Series"
        :observations="observation.data.value"
        :forecast="forecast.data.value"
      />
    </section>

    <section id="pollutants" v-reveal class="detail-section">
      <div class="section-heading">
        <h2 class="sec-label">构成</h2>
      </div>
      <HorizonChart
        v-if="horizonSeries.length"
        class="horizon-body"
        :times="horizonTimes"
        :series="horizonSeries"
      />
      <div v-else class="section-grid-skeleton" role="status">
        <div class="skeleton"></div>
        <div class="skeleton"></div>
        <div class="skeleton"></div>
        <div class="skeleton"></div>
        <div class="skeleton"></div>
        <div class="skeleton"></div>
      </div>
    </section>

    <section id="rhythm" v-reveal class="detail-section">
      <div class="section-heading">
        <h2 class="sec-label">节律</h2>
      </div>

      <div class="rhythm-grid">
        <HourRing ref="heatmap" class="rhythm-cell" :series="pm25Series" />
        <div class="rhythm-cell rhythm-phase">
          <WindClearance v-if="phasePoints.length" :points="phasePoints" />
          <div v-else class="section-state">风场数据不足</div>
        </div>
      </div>
    </section>

    <section id="structure" v-reveal class="detail-section">
      <div class="section-heading">
        <h2 class="sec-label">结构</h2>
      </div>
      <PCAStructurePanel
        v-if="structure.data.value"
        :structure="structure.data.value"
      />
      <div v-else class="section-state">样本不足</div>
    </section>

    <section id="trust" v-reveal class="detail-section trust-section">
      <div class="section-heading">
        <h2 class="sec-label">回测</h2>
      </div>

      <div class="trust-waterfall">
        <WaterfallChart
          v-if="dailyPm.values.length"
          class="waterfall-body"
          :days="dailyPm.days"
          :values="dailyPm.values"
        />
      </div>
      <BacktestAnatomy :backtest="backtest.data.value" />
      <TrustPanel :coverage="coverage.data.value" />
    </section>
    </div>
    </div>
  </section>
</template>

<style scoped>
.city-detail {
  min-height: calc(100vh - 60px);
  padding: 26px var(--page-pad) 48px;
  background: var(--canvas);
}
.city-hero {
  display: grid;
  grid-template-columns: minmax(260px, .6fr) minmax(700px, 1.8fr);
  gap: 32px;
  align-items: center;
  padding: 16px 0 24px;
  border-bottom: 1px solid var(--hairline);
}
.hero-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.hero-title h1 {
  margin: 0;
  color: var(--ink);
  font-size: clamp(36px, 4vw, 52px);
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1;
}
.city-province {
  color: var(--muted);
  font-size: 14px;
  font-weight: 500;
}

.current-status {
  min-height: 104px;
  display: grid;
  grid-template-columns: 1.1fr repeat(4, 1fr);
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
  box-shadow: var(--shadow-sm);
}
.current-status article {
  min-width: 0;
  padding: 16px 18px;
  display: grid;
  align-content: center;
  gap: 3px;
}
.current-status article + article { border-left: 1px solid var(--hairline); }
.current-status small {
  color: var(--muted);
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.current-status strong {
  color: var(--ink);
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.1;
}
.current-status strong.bad { color: var(--error); }
.current-status strong.good { color: var(--ok); }
.current-status p {
  margin: 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.3;
}
.status-main {
  grid-template-columns: 10px 1fr;
  column-gap: 10px;
}
.status-main > div { grid-column: 2; }
.status-dot {
  grid-row: 1 / 4;
  width: 9px;
  height: 9px;
  margin-top: 5px;
  border-radius: 50%;
  background: var(--aqi-tone);
}
.status-main strong { font-size: 24px; }

.section-nav {
  position: sticky;
  top: 60px;
  z-index: 25;
  min-height: 48px;
  margin: 0 -32px;
  padding: 0 32px;
  display: flex;
  align-items: center;
  gap: 4px;
  overflow-x: auto;
  border-bottom: 1px solid var(--hairline);
  background: var(--sheet-glass);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
.section-nav a {
  min-height: 32px;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: var(--radius-sm);
  color: var(--muted);
  font-size: var(--fs-label);
  font-weight: 500;
  text-decoration: none;
  white-space: nowrap;
  transition: all var(--duration-fast) ease;
}
.section-nav a:hover {
  color: var(--ink);
  background: var(--sheet-soft);
}

.city-body {
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

/* Editorial running rail: a bare hairline with numbered stops — no pill, no
   icons, no tooltips. The ink fill grows to the section in view. */
.section-rail {
  --rail-pitch: 42px;
  position: sticky;
  top: 50%;
  transform: translateY(-50%);
  display: grid;
  gap: calc(var(--rail-pitch) - 24px);
  justify-items: start;
  padding: 6px 0;
}

.rail-line,
.rail-fill {
  position: absolute;
  left: 0;
  top: 6px;
  bottom: 6px;
  width: 1px;
  pointer-events: none;
}

.rail-line {
  background: var(--hairline);
}

.rail-fill {
  bottom: auto;
  width: 1.5px;
  background: var(--ink);
  transition: height 0.45s var(--ease-out);
}

.section-rail a {
  position: relative;
  height: 24px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding-left: 14px;
  color: var(--muted);
  text-decoration: none;
  white-space: nowrap;
}

/* The stop dot sits centred on the hairline. */
.section-rail a::before {
  content: "";
  position: absolute;
  left: 0.5px;
  top: 50%;
  width: 5px;
  height: 5px;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: var(--hairline-strong);
  transition: background var(--duration-fast) ease, transform var(--duration-fast) ease;
}

.rail-no {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.04em;
  color: var(--faint);
  transition: color var(--duration-fast) ease;
}

.rail-word {
  font-size: 12px;
  font-weight: 500;
  transition: color var(--duration-fast) ease;
}

.section-rail a:hover .rail-word,
.section-rail a:hover .rail-no {
  color: var(--ink);
}

.section-rail a.active .rail-no,
.section-rail a.active .rail-word {
  color: var(--ink);
}

.section-rail a.active .rail-word {
  font-weight: 700;
}

.section-rail a.active::before {
  background: var(--ink);
  transform: translate(-50%, -50%) scale(1.35);
}

.city-sections {
  min-width: 0;
}

.detail-section {
  scroll-margin-top: 110px;
  padding-top: 32px;
}

@media (min-width: 1181px) {
  .section-nav { display: none; }
}

@media (max-width: 1180px) {
  .section-rail { display: none; }
  .city-body {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }
}
.first-section { padding-top: 24px; }
.section-heading {
  min-height: 48px;
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 24px;
  margin-bottom: 14px;
}
.section-heading h2 {
  margin: 0;
  color: var(--muted);
  font-size: 11.5px;
  font-weight: var(--fw-strong);
  letter-spacing: 0.2em;
}
.forecast-note {
  font-size: var(--fs-label);
  color: var(--muted);
  font-weight: 500;
}
.section-state {
  min-height: 100px;
  padding: 18px;
  display: grid;
  place-items: center;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
  color: var(--muted);
  font-size: var(--fs-body);
}

.section-grid-skeleton {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.section-grid-skeleton .skeleton {
  height: 168px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--hairline-soft);
}

.horizon-body {
  height: clamp(360px, 46vh, 460px);
}

.rhythm-grid {
  display: grid;
  grid-template-columns: minmax(300px, 5fr) 7fr;
  gap: 40px;
  align-items: stretch;
}

.rhythm-cell {
  height: 440px;
}

.trust-section {
  padding-bottom: 14px;
  display: grid;
  gap: 16px;
}

.trust-waterfall {
  display: grid;
  gap: 10px;
}

.trust-waterfall h3 {
  margin: 0;
  color: var(--ink-soft);
  font-size: 15px;
  font-weight: var(--fw-medium);
}

.waterfall-body {
  height: 280px;
}

@media (max-width: 1180px) {
  .city-hero { grid-template-columns: 1fr; }
  .rhythm-grid { grid-template-columns: 1fr; }
}
@media (max-width: 760px) {
  .city-detail { padding: 16px var(--page-pad) 32px; }
  .city-hero { gap: 14px; }
  .hero-title h1 { font-size: 32px; }
  .current-status { grid-template-columns: 1fr 1fr; }
  .current-status article:nth-child(3) {
    border-left: 0;
    border-top: 1px solid var(--hairline-soft);
  }
  .current-status article:nth-child(4) { border-top: 1px solid var(--hairline-soft); }
  .section-nav {
    top: 60px;
    margin: 0 calc(-1 * var(--page-pad));
    padding: 0 var(--page-pad);
  }
  .section-heading { display: grid; }
  .section-heading h2 { font-size: 18px; }
  .forecast-note { justify-self: start; }
  .section-grid-skeleton { grid-template-columns: 1fr 1fr; }
}
</style>
