<script setup lang="ts">
import { computed, ref } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { Layers3 } from "lucide-vue-next";
import { useRouter } from "vue-router";
import { api } from "../api/client";
import { expectData } from "../api/request";
import CityFingerprintPanel from "../components/CityFingerprintPanel.vue";
import HealthRiskCard from "../components/HealthRiskCard.vue";
import NationalFieldMap from "../components/NationalFieldMap.vue";
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

/* The first line is a readout of the finding, not a sentence about it. It
   follows the playhead, so the headline is the conclusion of whatever hour
   the stage is showing. */
const topLine = computed(() => {
  const worst = worstCity.value;
  if (!worst || worst.china_aqi == null) return "全国省级空气态势";
  return `${worst.name} AQI ${worst.china_aqi} ${worst.china_aqi_level ?? ""} · ${concernCount(
    displayCities.value,
  )} 省需要关注`;
});

const fingerprintLine = computed(() => {
  const meta = fingerprint.data.value?.meta;
  if (!meta) return "城市的长期结构指纹";
  return `${meta.city_count} 个省代表分成 ${meta.cluster_count} 种长期模式`;
});

const legendItems = computed<[string, string][]>(() => {
  const pairs: [string, string][] =
    mapMetric.value === "pm25"
      ? PM25_BANDS.map(([label, color]) => [label, color])
      : mapMetric.value === "change"
        ? CHANGE_LEVELS.map((l) => [l, CHANGE_COLORS[l]])
        : AQI_LEVELS.map((l) => [l, aqiColor(l)]);
  return pairs.map(([label, color]) => [label, stageColor(color)]);
});

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
    <section class="stage">
      <header class="stage-head">
        <h1 class="display-face">{{ topLine }}</h1>
        <div class="update-note">
          <strong class="data-mono">{{ formatTime(national.data.value?.latest_source_time) }}</strong>
          <span>{{ national.data.value?.aqi_standard ?? "HJ 633-2026" }}</span>
        </div>
      </header>

      <div class="map-area">
        <NationalFieldMap
          v-if="provinces.length"
          :cities="displayCities"
          :metric="mapMetric"
          @select="openCity"
        />
        <div v-else class="map-loading" role="status">正在绘制全国空气状态…</div>

        <div class="metric-switch" aria-label="地图指标">
          <button :class="{ active: mapMetric === 'aqi' }" @click="mapMetric = 'aqi'">AQI</button>
          <button :class="{ active: mapMetric === 'pm25' }" @click="mapMetric = 'pm25'">PM2.5</button>
          <button :class="{ active: mapMetric === 'change' }" @click="mapMetric = 'change'">24h 变化</button>
        </div>

        <div class="map-legend" aria-label="地图图例">
          <span v-for="[label, color] in legendItems" :key="String(label)">
            <i :style="{ background: color }"></i>{{ label }}
          </span>
          <span class="legend-key"><i class="ring"></i>地面观测</span>
          <span class="legend-rule">CAMS 模式换算，非地面监测值</span>
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
        <div v-else class="ribbon-empty">正在读取近 30 天的历史场…</div>
      </div>
    </section>

    <SeverityBand
      v-if="displayCities.length"
      :cities="displayCities"
      @select="openCity"
    />

    <HealthRiskCard
      v-if="focusCity"
      class="health-strip"
      compact
      :city="focusCity.name"
      :level="focusCity.china_aqi_level"
      :health-effect="focusCity.health_effect"
      :advice="focusCity.advice"
    />

    <PollutionWeave
      v-if="pmSeries.data.value"
      :series="pmSeries.data.value"
      :roster="provinces"
    />

    <section v-if="provinces.length" class="analysis-section">
      <NationalInsightDeck
        :regions="regions"
        :cities="provinces"
        :roster="cities"
      />
    </section>

    <details class="deep-analysis">
      <summary>
        <span class="display-face"><Layers3 :size="17" /> {{ fingerprintLine }}</span>
      </summary>
      <div class="deep-analysis-body">
        <CityFingerprintPanel
          v-if="fingerprint.data.value"
          :fingerprint="fingerprint.data.value"
          @select="openCity"
        />
        <div v-else class="fingerprint-state">
          {{ fingerprint.isPending.value ? "正在读取城市长期结构…" : "当前没有可用的城市结构分析。" }}
        </div>
      </div>
    </details>
  </section>
</template>

<style scoped>
.national-workspace {
  min-height: calc(100vh - 60px);
  padding: 22px 28px 40px;
  display: grid;
  gap: 16px;
  align-content: start;
  background: var(--canvas);
}

/* ── the stage ─────────────────────────────────────────────
   One printed chart field: the header, the map and the ribbon share the
   sea tone, so the map's water runs to the frame edge and the land is
   paper white on top of it. The conclusion is read from the top of the
   chart, in ink, and the evidence below is the same sheet. */
.stage {
  display: grid;
  grid-template-rows: auto minmax(560px, 62vh) auto;
  overflow: hidden;
  border: 1px solid var(--stage-hairline);
  border-radius: var(--radius-lg);
  background: var(--stage-bg);
}
.stage-head {
  padding: 26px 30px 12px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 28px;
}
.stage-head h1 {
  margin: 0;
  color: var(--stage-ink);
  font-size: clamp(28px, 3.3vw, 46px);
  line-height: 1.12;
  letter-spacing: var(--track-display);
}
.update-note {
  display: flex;
  align-items: baseline;
  gap: 12px;
  color: var(--stage-muted);
  font-size: var(--fs-label);
  white-space: nowrap;
}
.update-note strong {
  color: var(--stage-ink);
  font-size: var(--fs-body);
  font-weight: var(--fw-strong);
}

.map-area {
  position: relative;
  min-height: 560px;
}

.metric-switch {
  position: absolute;
  z-index: 10;
  top: 18px;
  right: 18px;
  padding: 4px;
  display: flex;
  gap: 3px;
  border: 1px solid var(--stage-hairline);
  border-radius: var(--radius-sm);
  background: var(--stage-panel);
  backdrop-filter: blur(8px);
}
.metric-switch button {
  min-height: 38px;
  padding: 0 14px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--stage-muted);
  font-family: var(--font-display);
  font-size: var(--fs-label);
  font-weight: var(--fw-strong);
  letter-spacing: .03em;
  cursor: pointer;
}
.metric-switch button:hover { background: var(--stage-panel); color: var(--stage-ink); }
.metric-switch button.active {
  background: var(--stage-ink);
  color: var(--stage-bg);
}

.map-legend {
  position: absolute;
  z-index: 9;
  left: 18px;
  right: 74px;
  bottom: 16px;
  min-height: 42px;
  padding: 9px 14px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 15px;
  border: 1px solid var(--stage-hairline);
  border-radius: var(--radius-sm);
  background: var(--stage-panel);
  backdrop-filter: blur(8px);
  color: var(--stage-muted);
  font-size: var(--fs-label);
}
.map-legend span { display: inline-flex; align-items: center; gap: 6px; }
.map-legend i {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.map-legend i.ring {
  background: transparent;
  border: 2px solid var(--stage-ink);
}
.legend-rule {
  color: var(--stage-muted);
  opacity: .85;
}
.map-loading {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: var(--stage-muted);
  font-size: var(--fs-body);
}

.ribbon-dock {
  padding: 10px 26px 22px;
  border-top: 1px solid var(--stage-hairline);
}
.ribbon-empty {
  min-height: 120px;
  display: grid;
  place-items: center;
  color: var(--stage-muted);
  font-size: var(--fs-body);
}

.national-error {
  min-height: 48px;
  padding: 0 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid #c8a29c;
  border-radius: var(--radius-sm);
  background: #fdf5f3;
  color: var(--error);
  font-size: var(--fs-label);
}
.national-error button {
  margin-left: auto;
  min-height: 36px;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-weight: var(--fw-strong);
}

.analysis-section { margin-top: 22px; }

.deep-analysis {
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
}
.deep-analysis > summary {
  min-height: 64px;
  padding: 0 20px;
  display: flex;
  align-items: center;
  gap: 9px;
  cursor: pointer;
  list-style: none;
}
.deep-analysis > summary::-webkit-details-marker { display: none; }
.deep-analysis > summary:hover { background: var(--sheet-soft); }
.deep-analysis summary > span {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  color: var(--ink);
  font-size: var(--fs-sub);
  letter-spacing: var(--track-title);
}
.deep-analysis-body {
  padding: 16px;
  border-top: 1px solid var(--hairline-soft);
  background: var(--sheet-sunken);
}
.fingerprint-state {
  min-height: 100px;
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: var(--fs-body);
}

@media (max-width: 900px) {
  .national-workspace { padding: 18px 16px 34px; }
  .stage { grid-template-rows: auto minmax(460px, 58vh) auto; }
  .stage-head {
    padding: 20px 18px 10px;
    display: grid;
    gap: 6px;
  }
  .map-area { min-height: 460px; }
  .ribbon-dock { padding: 8px 14px 18px; }
}
@media (max-width: 700px) {
  .stage { grid-template-rows: auto minmax(420px, 56vh) auto; }
  .map-area { min-height: 420px; }
  .metric-switch {
    top: 12px;
    left: 12px;
    right: auto;
  }
  .metric-switch button { padding: 0 11px; }
  .map-legend {
    left: 12px;
    right: 64px;
    bottom: 58px;
  }
  .deep-analysis > summary { min-height: 56px; }
}
</style>
