<script setup lang="ts">
import { computed, ref } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { useRouter } from "vue-router";
import { api } from "../api/client";
import { expectData } from "../api/request";
import BumpChart from "../components/BumpChart.vue";
import ChordDiagram from "../components/ChordDiagram.vue";
import CityFingerprintPanel from "../components/CityFingerprintPanel.vue";
import ChinaFieldMap from "../components/ChinaFieldMap.vue";
import HealthRiskCard from "../components/HealthRiskCard.vue";
import PollutionWeave from "../components/PollutionWeave.vue";
import SeverityBand from "../components/SeverityBand.vue";
import StreamGraph from "../components/StreamGraph.vue";
import TimeRibbon from "../components/TimeRibbon.vue";
import WindRose from "../components/WindRose.vue";
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

/* One aligned hourly field replaces N single-city calls. */
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

const weather = useQuery({
  queryKey: ["national-weather", 720],
  queryFn: () =>
    expectData(
      api.GET("/api/overview/national/weather", {
        params: { query: { hours: 720 } },
      }),
    ),
  staleTime: 15 * 60_000,
});

/* All six pollutants ride one parallel suite: the stream needs every mean,
   and the province roster filters each matrix the same way. */
const POLLUTANTS = [
  { key: "pm25", label: "PM2.5", color: "#2a78d6" },
  { key: "pm10", label: "PM10", color: "#eb6834" },
  { key: "no2", label: "NO₂", color: "#1baf7a" },
  { key: "o3", label: "O₃", color: "#eda100" },
  { key: "so2", label: "SO₂", color: "#e87ba4" },
  { key: "co", label: "CO", color: "#4a3aa7" },
] as const;

const pollutantSuite = useQuery({
  queryKey: ["national-series-suite", 720],
  queryFn: async () => Promise.all(POLLUTANTS.map((p) => fetchSeries(p.key))),
  staleTime: 15 * 60_000,
});

const cities = computed(() => national.data.value?.cities ?? []);
const provinces = computed(() => provinceRepresentatives(cities.value));
const provinceIds = computed(() => new Set(provinces.value.map((city) => city.location_id)));

/* ── time machine projection ────────────────────────────── */
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

/* Wind at the scrubbed hour: weather archives lag, so each city falls back
   to its most recent non-null hour within 72h — persistence, not invention. */
const windField = computed(() => {
  const data = weather.data.value;
  if (!data) return null;
  const at =
    scrubIndex.value == null
      ? data.times.length - 1
      : Math.min(Math.max(0, scrubIndex.value), data.times.length - 1);
  return data.cities.flatMap((city) => {
    for (let back = 0; back <= 72 && at - back >= 0; back++) {
      const speed = city.wind_speed[at - back];
      const dir = city.wind_direction[at - back];
      if (speed != null && dir != null) {
        return [{ location_id: city.location_id, lat: city.lat, lon: city.lon, speed, dir }];
      }
    }
    return [];
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

const topLine = computed(() => {
  const worst = worstCity.value;
  if (!worst || worst.china_aqi == null) return "全国空气态势";
  const concerns = concernCount(displayCities.value);
  return `${worst.name} AQI ${worst.china_aqi} ${worst.china_aqi_level ?? ""} · ${concerns} 省关注`;
});

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

/* ── stream: composition pulse ────────────────────────────── */
const streamTimes = computed(() => pollutantSuite.data.value?.[0]?.times ?? []);

const streamLayers = computed(() => {
  const suite = pollutantSuite.data.value;
  if (!suite) return [];
  const ids = provinceIds.value;
  return POLLUTANTS.map((pollutant, i) => {
    const series = suite[i]!;
    const rows = series.cities.filter((city) => ids.has(city.location_id));
    const values = series.times.map((_, t) => {
      let sum = 0;
      let n = 0;
      for (const row of rows) {
        const value = row.values[t];
        if (value != null) {
          sum += value;
          n += 1;
        }
      }
      return n ? sum / n : null;
    });
    const valid = values.filter((v): v is number => v != null).sort((a, b) => a - b);
    const p90 = valid[Math.floor(valid.length * 0.9)] ?? 1;
    return {
      key: pollutant.key,
      label: pollutant.label,
      color: pollutant.color,
      values: values.map((v) => (v == null ? null : Math.min(1.6, v / Math.max(1, p90)))),
    };
  });
});

const dominantPollutant = computed(() => {
  const layers = streamLayers.value;
  if (!layers.length) return "—";
  let best = layers[0]!;
  let bestMean = -1;
  for (const layer of layers) {
    const valid = layer.values.filter((v): v is number => v != null);
    const mean = valid.reduce((a, b) => a + b, 0) / Math.max(1, valid.length);
    if (mean > bestMean) {
      bestMean = mean;
      best = layer;
    }
  }
  return best.label;
});

/* ── bump: rank race ──────────────────────────────────────── */
const bumpEntries = computed(() => {
  const series = pmSeries.data.value;
  if (!series) return [];
  const ids = provinceIds.value;
  return series.cities
    .filter((city) => ids.has(city.location_id))
    .map((city) => {
      const daily: Array<number | null> = [];
      for (let start = 0; start < city.values.length; start += 24) {
        const slice = city.values
          .slice(start, start + 24)
          .filter((v): v is number => v != null);
        daily.push(slice.length >= 12 ? slice.reduce((a, b) => a + b, 0) / slice.length : null);
      }
      return { location_id: city.location_id, name: city.name, daily };
    });
});

const bumpDays = computed(() => {
  const series = pmSeries.data.value;
  if (!series) return [];
  return series.times
    .filter((_, i) => i % 24 === 0)
    .map((t) => t.slice(5, 10).replace("-", "/"));
});

const bumpLeader = computed(() => {
  const entries = bumpEntries.value;
  if (!entries.length) return "—";
  let best = entries[0]!;
  let bestMean = -1;
  for (const entry of entries) {
    const valid = entry.daily.filter((v): v is number => v != null);
    const mean = valid.reduce((a, b) => a + b, 0) / Math.max(1, valid.length);
    if (mean > bestMean) {
      bestMean = mean;
      best = entry;
    }
  }
  return best.name;
});

/* ── wind rose samples: wind × PM2.5 over every province hour ── */
const roseSamples = computed(() => {
  const data = weather.data.value;
  const series = pmSeries.data.value;
  if (!data || !series) return [];
  const ids = provinceIds.value;
  const pmIndex = new Map(series.times.map((t, i) => [t, i]));
  const out: Array<{ speed: number; dir: number; pm25: number }> = [];
  for (const city of data.cities) {
    if (!ids.has(city.location_id)) continue;
    const pmRow = series.cities.find((c) => c.location_id === city.location_id);
    if (!pmRow) continue;
    data.times.forEach((time, i) => {
      const pi = pmIndex.get(time);
      if (pi == null) return;
      const speed = city.wind_speed[i];
      const dir = city.wind_direction[i];
      const pm25 = pmRow.values[pi];
      if (speed != null && dir != null && pm25 != null) {
        out.push({ speed, dir, pm25 });
      }
    });
  }
  return out;
});

const DIRTIEST_BINS = [
  { from: 337.5, to: 22.5, label: "北风" },
  { from: 22.5, to: 67.5, label: "东北风" },
  { from: 67.5, to: 112.5, label: "东风" },
  { from: 112.5, to: 157.5, label: "东南风" },
  { from: 157.5, to: 202.5, label: "南风" },
  { from: 202.5, to: 247.5, label: "西南风" },
  { from: 247.5, to: 292.5, label: "西风" },
  { from: 292.5, to: 337.5, label: "西北风" },
];

const roseHeadline = computed(() => {
  const samples = roseSamples.value;
  if (samples.length < 200) return "风与污染";
  const bins = new Map<number, { sum: number; n: number }>();
  for (const sample of samples) {
    const bin = Math.floor(((sample.dir % 360) + 360) % 360 / 45);
    const cell = bins.get(bin) ?? { sum: 0, n: 0 };
    cell.sum += sample.pm25;
    cell.n += 1;
    bins.set(bin, cell);
  }
  let bestBin = -1;
  let bestMean = -1;
  for (const [bin, cell] of bins) {
    if (cell.n < 100) continue;
    const mean = cell.sum / cell.n;
    if (mean > bestMean) {
      bestMean = mean;
      bestBin = bin;
    }
  }
  if (bestBin < 0) return "风与污染";
  const label = DIRTIEST_BINS[bestBin]?.label ?? "风";
  return `${label}携污最重 · ${bestMean.toFixed(0)} µg/m³`;
});

/* ── chord: synchrony network ─────────────────────────────── */
const chordCities = computed(() => {
  const series = pmSeries.data.value;
  if (!series) return [];
  const ids = provinceIds.value;
  return series.cities
    .filter((city) => ids.has(city.location_id))
    .map((city) => ({ location_id: city.location_id, name: city.name, values: city.values }));
});

const chordHeadline = computed(() => {
  const rows = chordCities.value;
  if (rows.length < 3) return "城市联动";
  let bestA = "";
  let bestB = "";
  let bestR = 0;
  for (let i = 0; i < rows.length; i++) {
    for (let j = i + 1; j < rows.length; j++) {
      let n = 0;
      let sa = 0;
      let sb = 0;
      let saa = 0;
      let sbb = 0;
      let sab = 0;
      for (let k = 0; k < rows[i]!.values.length; k++) {
        const x = rows[i]!.values[k];
        const y = rows[j]!.values[k];
        if (x == null || y == null) continue;
        n += 1;
        sa += x;
        sb += y;
        saa += x * x;
        sbb += y * y;
        sab += x * y;
      }
      if (n < 240) continue;
      const cov = sab * n - sa * sb;
      const denom = Math.sqrt((saa * n - sa * sa) * (sbb * n - sb * sb));
      const r = denom > 0 ? cov / denom : 0;
      if (r > bestR) {
        bestR = r;
        bestA = rows[i]!.name;
        bestB = rows[j]!.name;
      }
    }
  }
  return bestA ? `${bestA}–${bestB} 同呼吸 · r=${bestR.toFixed(2)}` : "城市联动";
});

/* The legend is a ramp ruler with boundary ticks. */
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

const ribbon = computed(() => {
  const series = pmSeries.data.value;
  if (!series) return { times: [] as string[], values: [] as (number | null)[] };
  const ids = provinceIds.value;
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
      <span>数据未加载</span>
      <button type="button" @click="national.refetch()">重试</button>
    </div>

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
          :wind-field="windField"
          @select="openCity"
        />
        <div v-else class="map-skeleton skeleton" role="status"></div>

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

        <div class="map-legend" aria-label="图例">
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
        <div v-else class="ribbon-skeleton skeleton" role="status"></div>
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

    <section v-if="streamLayers.length" v-reveal class="viz-section">
      <header class="viz-head">
        <h2 class="display-face">污染构成 · {{ dominantPollutant }} 领跑</h2>
        <span class="viz-meta data-mono">30 天 · 六污染物指数</span>
      </header>
      <div class="viz-body stream-body">
        <StreamGraph :times="streamTimes" :layers="streamLayers" />
      </div>
    </section>

    <section v-if="bumpEntries.length" v-reveal class="viz-section">
      <header class="viz-head">
        <h2 class="display-face">{{ bumpLeader }} 领跑 · 30 天排名流动</h2>
        <span class="viz-meta data-mono">逐日 PM2.5 均值</span>
      </header>
      <div class="duel-grid">
        <div class="viz-body duel-cell">
          <BumpChart :days="bumpDays" :entries="bumpEntries" :top-n="10" />
        </div>
        <div class="viz-body duel-cell">
          <WindRose :samples="roseSamples" />
        </div>
      </div>
      <div class="viz-subhead" v-if="roseSamples.length">
        <h3 class="display-face">{{ roseHeadline }}</h3>
      </div>
    </section>

    <section v-if="chordCities.length" v-reveal class="viz-section">
      <header class="viz-head">
        <h2 class="display-face">{{ chordHeadline }}</h2>
        <span class="viz-meta data-mono">PM2.5 同步性 · |r|≥0.55</span>
      </header>
      <div class="viz-body chord-body">
        <ChordDiagram :cities="chordCities" />
      </div>
    </section>

    <section v-reveal class="viz-section">
      <header class="viz-head">
        <h2 class="display-face">{{ fingerprintHeadline }}</h2>
      </header>
      <CityFingerprintPanel
        v-if="fingerprint.data.value"
        :fingerprint="fingerprint.data.value"
        @select="openCity"
      />
      <div v-else class="fingerprint-state">
        <div v-if="fingerprint.isPending.value" class="skeleton fingerprint-skeleton" role="status"></div>
      </div>
    </section>
  </section>
</template>

<style scoped>
.national-workspace {
  min-height: calc(100vh - 64px);
  padding: 28px var(--page-pad) 72px;
  display: grid;
  gap: 28px;
  align-content: start;
  background: var(--canvas);
}

/* ── The Stage ───────────────────────────────────────────── */
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

.map-area::before {
  content: "";
  position: absolute;
  inset: 12px;
  z-index: 6;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 10px;
  pointer-events: none;
}

.map-area::after {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 6;
  box-shadow: inset 0 0 44px rgba(51, 65, 92, 0.07);
  pointer-events: none;
}

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

/* ── Full-bleed viz sections: hairline-topped, no card boxes ── */
.viz-section {
  padding-top: 26px;
  border-top: 1px solid var(--hairline);
  display: grid;
  gap: 18px;
}

.viz-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 24px;
}

.viz-head h2 {
  margin: 0;
  color: var(--ink);
  font-size: 21px;
  font-weight: var(--fw-strong);
  letter-spacing: var(--track-title);
}

.viz-subhead {
  margin-top: 10px;
}

.viz-subhead h3 {
  margin: 0;
  color: var(--ink-soft);
  font-size: 15px;
  font-weight: var(--fw-medium);
}

.viz-meta {
  color: var(--faint);
  font-size: 11.5px;
  white-space: nowrap;
}

.viz-body {
  width: 100%;
}

.stream-body {
  height: clamp(260px, 34vh, 360px);
}

.duel-grid {
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 40px;
  align-items: stretch;
}

.duel-cell {
  height: 420px;
}

.chord-body {
  height: clamp(420px, 52vh, 560px);
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
  .national-workspace { padding: 16px 16px 40px; gap: 20px; }
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
  .duel-grid { grid-template-columns: 1fr; gap: 28px; }
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
