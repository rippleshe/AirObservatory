<script setup lang="ts">
import { computed, ref } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { useRouter } from "vue-router";
import { api } from "../api/client";
import { expectData } from "../api/request";
import CityFingerprintPanel from "../components/CityFingerprintPanel.vue";
import ChinaFieldMap from "../components/ChinaFieldMap.vue";
import HealthRiskCard from "../components/HealthRiskCard.vue";
import NationalInsightDeck from "../components/NationalInsightDeck.vue";
import PollutionWeave from "../components/PollutionWeave.vue";
import SeverityBand from "../components/SeverityBand.vue";
import TimeRibbon from "../components/TimeRibbon.vue";
import {
  AQI_LEVELS,
  CHANGE_COLORS,
  CHANGE_LEVELS,
  aqiColor,
  levelOfAqi,
  PM25_BANDS,
  stageColor,
} from "../lib/palette";
import {
  concernCount,
  provinceRepresentatives,
  regionSummary,
  type NationalCity,
} from "../lib/provinces";
import { useContextStore } from "../stores/context";

type MapMetric = "aqi" | "pm25" | "change";

async function fetchSeries(variable: string) {
  return expectData(
    api.GET("/api/overview/national/series", {
      params: { query: { variable, hours: 720 } },
    }),
  );
}

const router = useRouter();
const context = useContextStore();
const mapMetric = ref<MapMetric>("aqi");
/* The time machine: null rests on 现在, a number scrubs the whole first
   viewport back to that hour of the stored record. */
const scrubIndex = ref<number | null>(null);

const national = useQuery({
  queryKey: ["national-overview"],
  queryFn: () => expectData(api.GET("/api/overview/national")),
  refetchInterval: 5 * 60_000,
  staleTime: 60_000,
});

const fingerprint = useQuery({
  queryKey: ["city-fingerprint"],
  retry: false,
  queryFn: () => expectData(api.GET("/api/analysis/city-fingerprint")),
  staleTime: 30 * 60_000,
});

/* One aligned hourly field replaces N single-city calls. Two variables ride
   the same window: PM2.5 carries the ribbon's trace and the 24h change,
   reference_aqi carries the headline and the map's AQI coding. */
const pmSeries = useQuery({
  queryKey: ["national-series", "pm25", 720],
  queryFn: () => fetchSeries("pm25"),
  staleTime: 15 * 60_000,
});

const aqiSeries = useQuery({
  queryKey: ["national-series", "aqi", 720],
  queryFn: () => fetchSeries("aqi"),
  staleTime: 15 * 60_000,
});

const cities = computed(() => national.data.value?.cities ?? []);
/* One mark per province is the national layer's unit of reading. Reducing
   once here — not inside each chart — is what keeps the headline count, the
   band, the map, the matrix and the region bars describing the same set. */
const provinces = computed(() => provinceRepresentatives(cities.value));
const regions = computed(() => regionSummary(provinces.value));

/* ── time machine projection ──────────────────────────────
   Past hours are re-read from the stored field, never invented: AQI comes
   from the model's own reference_aqi series, the level word from the same
   HJ 633-2026 boundaries the backend uses, 24h change from the PM2.5 series
   against the same hour a day earlier. Fields a past hour cannot know —
   primary pollutants, health copy, ground-truth flags — arrive empty. */
const pmCities = computed(() => {
  const rows = pmSeries.data.value?.cities ?? [];
  return new Map(rows.map((city) => [city.location_id, city]));
});

const aqiCities = computed(() => {
  const rows = aqiSeries.data.value?.cities ?? [];
  return new Map(rows.map((city) => [city.location_id, city]));
});

const displayCities = computed<NationalCity[]>(() => {
  const index = scrubIndex.value;
  if (index == null) return provinces.value;
  const times = pmSeries.data.value?.times ?? [];
  const at = Math.min(Math.max(0, index), Math.max(0, times.length - 1));
  return provinces.value.flatMap((city) => {
    const pm = pmCities.value.get(city.location_id);
    const aq = aqiCities.value.get(city.location_id);
    const pm25 = pm?.values[at] ?? null;
    const prev = at >= 24 ? (pm?.values[at - 24] ?? null) : null;
    const aqi = aq?.values[at] ?? null;
    return {
      ...city,
      pm25,
      pm25_change_24h: pm25 != null && prev != null ? pm25 - prev : null,
      china_aqi: aqi == null ? null : Math.round(aqi),
      china_aqi_level: levelOfAqi(aqi),
      primary_pollutants: [],
      health_effect: null,
      advice: null,
      european_aqi_reference: null,
      has_recent_ground_observation: false,
      source_time: times[at] ?? city.source_time,
    };
  });
});

const worstCity = computed(
  () =>
    [...displayCities.value]
      .filter((city) => city.china_aqi != null)
      .sort((a, b) => (b.china_aqi ?? -1) - (a.china_aqi ?? -1))[0] ?? null,
);
const focusCity = computed(() =>
  [...provinces.value]
    .filter((city) => city.china_aqi != null)
    .sort((a, b) => (b.china_aqi ?? -1) - (a.china_aqi ?? -1))[0] ?? null,
);

/* Awwwards / Editorial clean headline: concise, impactful, no rambling */
const topLine = computed(() => {
  const worst = worstCity.value;
  if (!worst || worst.china_aqi == null) return "全国空气态势";
  const concerns = concernCount(displayCities.value);
  return `${worst.name} AQI ${worst.china_aqi} ${worst.china_aqi_level ?? ""} · ${concerns} 省关注`;
});

/* The structure-fingerprint section states its conclusion from the analysis
   product itself — components explained and modes found — never a static label. */
const fingerprintHeadline = computed(() => {
  const meta = fingerprint.data.value?.meta;
  const explained = fingerprint.data.value?.explained_variance ?? [];
  if (!meta || !explained.length) return "城市长期结构指纹";
  let used = 0;
  let covered = 0;
  for (const step of explained) {
    used += 1;
    covered = step.cumulative_ratio;
    if (covered >= 0.8) break;
  }
  return `前 ${used} 主成分解释 ${Math.round(covered * 100)}% 波动 · ${meta.cluster_count} 类污染模式`;
});

/* The legend is a ramp ruler with boundary ticks — instrument labelling,
   not a row of dots. Numeric scales get boundary numbers; the diverging
   change scale gets its five state words. */
const ramp = computed(() => {
  if (mapMetric.value === "aqi") {
    return {
      segments: AQI_LEVELS.map((level) => aqiColor(level)),
      ticks: ["0", "50", "100", "150", "200", "300", "500"],
      words: false,
    };
  }
  if (mapMetric.value === "pm25") {
    return {
      segments: PM25_BANDS.map(([, color]) => stageColor(color)),
      ticks: ["0", "35", "75", "115", "150", "+"],
      words: false,
    };
  }
  return {
    segments: CHANGE_LEVELS.map((level) => CHANGE_COLORS[level]),
    ticks: [...CHANGE_LEVELS],
    words: true,
  };
});

const METRIC_ORDER: MapMetric[] = ["aqi", "pm25", "change"];
const metricIndex = computed(() => METRIC_ORDER.indexOf(mapMetric.value));

/* The ribbon traces one number: the median PM2.5 of the same 31 provinces
   the band and the map speak for. Missing stays missing — the line breaks. */
const ribbon = computed(() => {
  const series = pmSeries.data.value;
  if (!series) return { times: [] as string[], values: [] as (number | null)[] };
  const ids = new Set(provinces.value.map((city) => city.location_id));
  const rows = series.cities.filter((city) => ids.has(city.location_id));
  const values = series.times.map((_, i) => {
    const xs = rows
      .map((city) => city.values[i])
      .filter((value): value is number => value != null && Number.isFinite(value))
      .sort((a, b) => a - b);
    return xs.length ? xs[Math.floor(xs.length / 2)] : null;
  });
  return { times: series.times, values };
});

function formatTime(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function openCity(id: number, name: string) {
  context.selectLocation(id, name);
  void router.push({ name: "city", params: { locationId: id } });
}
</script>

<template>
  <section class="national-workspace">
    <div v-if="national.isError.value" class="national-error" role="alert">
      <span>全国数据暂时没有加载成功。</span>
      <button type="button" @click="national.refetch()">重新读取</button>
    </div>

    <!-- The night observatory: the conclusion, the field, and the time
         machine are one stage — the first viewport is a place, not a card. -->
    <section v-reveal class="stage">
      <header class="stage-head">
        <h1 class="display-face">{{ topLine }}</h1>
        <div class="update-note">
          <strong class="data-mono">{{ formatTime(national.data.value?.latest_source_time) }}</strong>
          <span>{{ national.data.value?.aqi_standard ?? "HJ 633-2026" }}</span>
        </div>
      </header>

      <div class="map-area">
        <ChinaFieldMap
          v-if="provinces.length"
          :cities="displayCities"
          :metric="mapMetric"
          @select="openCity"
        />
        <div v-else class="map-skeleton skeleton" role="status" aria-label="正在绘制全国空气状态"></div>

        <div class="metric-switch" aria-label="地图指标">
          <span
            class="switch-thumb"
            :style="{ transform: `translateX(${metricIndex * 100}%)` }"
            aria-hidden="true"
          ></span>
          <button :class="{ active: mapMetric === 'aqi' }" @click="mapMetric = 'aqi'">AQI</button>
          <button :class="{ active: mapMetric === 'pm25' }" @click="mapMetric = 'pm25'">PM2.5</button>
          <button :class="{ active: mapMetric === 'change' }" @click="mapMetric = 'change'">24h 变化</button>
        </div>

        <div class="map-legend" aria-label="地图图例">
          <div class="legend-ramp">
            <div class="ramp-track">
              <span
                v-for="(color, i) in ramp.segments"
                :key="i"
                class="ramp-seg"
                :style="{ background: color }"
              ></span>
            </div>
            <div class="ramp-ticks" :class="{ words: ramp.words }">
              <span v-for="tick in ramp.ticks" :key="tick" class="ramp-tick">{{ tick }}</span>
            </div>
          </div>
          <span class="legend-rule">CAMS 模式换算 · 等积圆锥投影</span>
        </div>
      </div>

      <div class="ribbon-dock">
        <TimeRibbon
          v-if="ribbon.times.length"
          :times="ribbon.times"
          :values="ribbon.values"
          :index="scrubIndex"
          @update:index="scrubIndex = $event"
        />
        <div v-else class="ribbon-skeleton skeleton" role="status" aria-label="正在读取近 30 天的历史场"></div>
      </div>
    </section>

    <SeverityBand
      v-if="displayCities.length"
      v-reveal="60"
      :cities="displayCities"
      @select="openCity"
    />

    <HealthRiskCard
      v-if="focusCity"
      v-reveal="100"
      class="health-strip"
      compact
      :city="focusCity.name"
      :level="focusCity.china_aqi_level"
      :health-effect="focusCity.health_effect"
      :advice="focusCity.advice"
    />

    <PollutionWeave
      v-if="pmSeries.data.value"
      v-reveal
      :series="pmSeries.data.value"
      :roster="provinces"
    />

    <section v-if="provinces.length" v-reveal class="analysis-section">
      <NationalInsightDeck
        :regions="regions"
        :cities="provinces"
        :roster="cities"
      />
    </section>

    <section v-reveal class="deep-section">
      <div class="section-heading">
        <h2 class="display-face">{{ fingerprintHeadline }}</h2>
      </div>
      <CityFingerprintPanel
        v-if="fingerprint.data.value"
        :fingerprint="fingerprint.data.value"
        @select="openCity"
      />
      <div v-else class="fingerprint-state">
        <div v-if="fingerprint.isPending.value" class="skeleton fingerprint-skeleton" role="status" aria-label="正在读取城市长期结构"></div>
      </div>
    </section>
  </section>
</template>

<style scoped>
.national-workspace {
  min-height: calc(100vh - 64px);
  padding: 28px var(--page-pad) 56px;
  display: grid;
  gap: 24px;
  align-content: start;
  background: var(--canvas);
}

/* ── The Stage ─────────────────────────────────────────────
   A printed atlas plate: gradient sea, an inner rule framing the map
   field, and the landmass lifted on its own soft shadow. */
.stage {
  position: relative;
  display: grid;
  grid-template-rows: auto minmax(580px, 64vh) auto;
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-xl);
  background: radial-gradient(130% 100% at 50% 0%, #eef3f9 0%, #e8eef5 52%, #e2eaf2 100%);
  box-shadow: var(--shadow-sm);
}

.stage-head {
  padding: 24px 32px 14px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 32px;
}

.stage-head h1 {
  margin: 0;
  color: var(--stage-ink);
  font-size: var(--fs-display-lg);
  line-height: 1.15;
  letter-spacing: var(--track-display);
}

.update-note {
  display: flex;
  align-items: baseline;
  gap: 10px;
  color: var(--stage-muted);
  font-size: var(--fs-label);
  white-space: nowrap;
}

.update-note strong {
  color: var(--ink);
  font-size: var(--fs-body);
  font-weight: var(--fw-strong);
}

.map-area {
  position: relative;
  min-height: 580px;
}

/* The plate rule: a printed-atlas frame drawn just inside the map field. */
.map-area::before {
  content: "";
  position: absolute;
  inset: 12px;
  z-index: 6;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 10px;
  pointer-events: none;
}

/* A breath of vignette settles the field into the plate. */
.map-area::after {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 6;
  box-shadow: inset 0 0 44px rgba(51, 65, 92, 0.07);
  pointer-events: none;
}

/* Metric switch: one ink thumb slides across three equal stops. */
.metric-switch {
  position: absolute;
  z-index: 10;
  top: 18px;
  right: 20px;
  padding: 3px;
  display: grid;
  grid-template-columns: repeat(3, minmax(64px, 1fr));
  border: 1px solid var(--hairline);
  border-radius: var(--radius-pill);
  background: var(--sheet-glass);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--shadow-sm);
}

.switch-thumb {
  position: absolute;
  top: 3px;
  bottom: 3px;
  left: 3px;
  width: calc((100% - 6px) / 3);
  border-radius: var(--radius-pill);
  background: var(--ink);
  box-shadow: var(--shadow-sm);
  transition: transform 320ms var(--ease-spring);
}

.metric-switch button {
  position: relative;
  z-index: 1;
  min-height: 32px;
  padding: 0 14px;
  border: 0;
  border-radius: var(--radius-pill);
  background: transparent;
  color: var(--muted);
  font-family: var(--font-display);
  font-size: var(--fs-label);
  font-weight: var(--fw-medium);
  letter-spacing: 0.02em;
  white-space: nowrap;
  cursor: pointer;
  transition: color var(--duration-fast) ease;
}

.metric-switch button:hover {
  color: var(--ink);
}

.metric-switch button.active {
  color: #ffffff;
  font-weight: var(--fw-strong);
}

.map-legend {
  position: absolute;
  z-index: 9;
  left: 20px;
  right: 80px;
  bottom: 18px;
  min-height: 44px;
  padding: 9px 16px 7px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 18px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-md);
  background: var(--sheet-glass);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  color: var(--muted);
  font-size: var(--fs-label);
  box-shadow: var(--shadow-sm);
}

/* Ramp ruler: connected segments with boundary ticks beneath. */
.legend-ramp {
  min-width: 240px;
  flex: 1;
  max-width: 380px;
}

.ramp-track {
  display: flex;
  height: 6px;
  border-radius: var(--radius-pill);
  overflow: hidden;
  box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.06);
}

.ramp-seg {
  flex: 1;
  transition: background var(--duration-normal) var(--ease-out);
}

.ramp-ticks {
  margin-top: 4px;
  display: flex;
  justify-content: space-between;
  color: var(--muted);
  font-family: var(--font-display);
  font-size: 10.5px;
  font-weight: var(--fw-medium);
  letter-spacing: 0.02em;
  font-variant-numeric: tabular-nums;
}

.ramp-ticks.words {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  justify-content: unset;
}

.legend-rule {
  color: var(--muted);
  opacity: 0.85;
  font-size: 11px;
}

.map-skeleton {
  position: absolute;
  inset: 16px;
  border-radius: var(--radius-lg);
}

.ribbon-skeleton {
  height: 120px;
  border-radius: var(--radius-md);
}

.ribbon-dock {
  padding: 10px 28px 20px;
  border-top: 1px solid var(--hairline);
  background: rgba(255, 255, 255, 0.5);
}

.national-error {
  min-height: 48px;
  padding: 0 18px;
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid #fecaca;
  border-radius: var(--radius-md);
  background: #fef2f2;
  color: var(--error);
  font-size: var(--fs-label);
}

.national-error button {
  margin-left: auto;
  min-height: 32px;
  padding: 0 14px;
  border: 1px solid #fca5a5;
  border-radius: var(--radius-sm);
  background: #ffffff;
  color: inherit;
  cursor: pointer;
  font-weight: var(--fw-strong);
}

.analysis-section {
  margin-top: 4px;
}

.deep-section {
  padding-top: 8px;
}

.section-heading {
  min-height: 44px;
  display: flex;
  align-items: baseline;
  gap: 24px;
  margin-bottom: 6px;
}

.section-heading h2 {
  margin: 0;
  color: var(--ink);
  font-size: 20px;
  font-weight: 700;
  letter-spacing: var(--track-title);
}

.fingerprint-state {
  min-height: 120px;
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: var(--fs-body);
}

.fingerprint-skeleton {
  width: min(100%, 760px);
  height: 320px;
  border-radius: var(--radius-lg);
}

@media (max-width: 900px) {
  .national-workspace { padding: 16px 16px 36px; gap: 16px; }
  .stage {
    grid-template-rows: auto minmax(460px, 58vh) auto;
    border-radius: var(--radius-lg);
  }
  .stage-head {
    padding: 20px 20px 12px;
    display: grid;
    gap: 8px;
  }
  .map-area { min-height: 460px; }
  .ribbon-dock { padding: 10px 16px 20px; }
}

@media (max-width: 700px) {
  .stage { grid-template-rows: auto minmax(420px, 56vh) auto; }
  .map-area { min-height: 420px; }
  .metric-switch {
    top: 14px;
    left: 14px;
    right: auto;
  }
  .metric-switch button { padding: 0 12px; }
  .map-legend {
    left: 14px;
    right: 70px;
    bottom: 64px;
  }
}
</style>
