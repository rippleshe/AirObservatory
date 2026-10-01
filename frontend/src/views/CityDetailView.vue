<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { useRoute } from "vue-router";
import { Activity, BarChart3, Clock3, Database, Layers3, ShieldCheck } from "lucide-vue-next";
import { api } from "../api/client";
import { expectData } from "../api/request";
import BacktestPanel from "../components/BacktestPanel.vue";
import HealthRiskCard from "../components/HealthRiskCard.vue";
import HourRing from "../components/HourRing.vue";
import PCAStructurePanel from "../components/PCAStructurePanel.vue";
import PollutantSmallMultiples from "../components/PollutantSmallMultiples.vue";
import TraceDeck from "../components/TraceDeck.vue";
import TrustPanel from "../components/TrustPanel.vue";
import { useLocationCatalog } from "../composables/useLocationCatalog";
import { aqiColor } from "../lib/palette";
import { useContextStore } from "../stores/context";

const route = useRoute();
const context = useContextStore();
const { locations } = useLocationCatalog();

const locationId = computed(() => Number(route.params.locationId));
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
/* The forecast gap has one wording on this page. */
const FORECAST_PENDING = "未来预测尚未就绪";

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

const trendHeadline = computed(() => {
  const recentAvg = pm25Trend.value.recentAvg;
  if (recentAvg == null) return "近 24 小时 PM2.5 趋势";
  const delta = pm25Trend.value.delta;
  const change = delta == null ? "" : ` · 较昨日 ${delta > 0 ? "+" : ""}${delta.toFixed(1)}`;
  return `24h 日均 ${recentAvg.toFixed(1)} µg/m³${change}`;
});

const pollutantStandings = computed(() =>
  (pulse.data.value ?? []).flatMap((item) => {
    const values = item.points
      .filter((point) => point.value != null)
      .map((point) => Number(point.value));
    if (values.length < 2) return [];
    const latest = values[values.length - 1];
    return [
      {
        variable: item.variable,
        label: POLLUTANT_LABELS[item.variable] ?? item.variable,
        percentile: (values.filter((value) => value <= latest).length / values.length) * 100,
      },
    ];
  }),
);

const pollutantHeadline = computed(() => {
  const rows = pollutantStandings.value;
  if (!rows.length) return "多污染物动态监测";
  const focus = rows.find((row) => row.variable === "pm25") ?? rows[0];
  const high = rows.filter((row) => row.percentile >= 65).length;
  const tail = high ? `${high} 项偏高` : "全部正常";
  return `${focus.label} 处于历史 ${Math.round(focus.percentile)}% 分位 · ${tail}`;
});

const rhythmHeadline = computed(
  () => heatmap.value?.peakCopy ?? "时段节律特征",
);

const structureHeadline = computed(() => {
  const item = structure.data.value;
  const samples = item?.meta.sample_count ?? 0;
  const features = item?.meta.features.length ?? 0;
  const explained = item?.explained_variance ?? [];
  if (!item || !samples || !features || !explained.length) {
    return "气象与污染物关联结构";
  }
  let used = 0;
  let covered = 0;
  for (const step of explained) {
    used += 1;
    covered = step.cumulative_ratio;
    if (covered >= 0.8) break;
  }
  return `${samples}h 样本 · 前 ${used} 主成分解释 ${Math.round(covered * 100)}% 波动`;
});

const trustHeadline = computed(() => {
  const days = coverage.data.value?.coverage ?? [];
  if (!days.length) return "数据源可信度与覆盖度";
  const mean = (key: "observation_coverage" | "model_coverage" | "weather_coverage") =>
    Math.round((days.reduce((sum, day) => sum + day[key], 0) / days.length) * 100);
  return `近 30 天覆盖：实测 ${mean("observation_coverage")}% · 模式 ${mean("model_coverage")}%`;
});

/* Model-vs-observation is only a statement about model bias when both readings
   describe the same hour. 武汉's newest ground reading is from 2025-08 while its
   model field is current, and differencing them printed a "模式偏高 119.3 µg/m³"
   claim that was arithmetic across thirteen months, not a comparison.
   Comparability is a precondition of the claim, not a nicety. */
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

const forecastOutlook = computed(() => {
  const points = forecast.data.value?.series?.[0]?.points ?? [];
  if (!points.length) return "";
  const first = points[0]?.value;
  const last = points.at(-1)?.value;
  const peak = Math.max(...points.map((point) => point.value));
  if (first == null || last == null) return `预测峰值 ${peak.toFixed(1)}`;
  const delta = last - first;
  const trend = Math.abs(delta) < 2 ? "平稳" : delta > 0 ? "偏高" : "改善";
  return `未来预测 ${trend} · 峰值 ${peak.toFixed(0)}`;
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
            <p>AQI {{ nationalCity?.china_aqi ?? "—" }}</p>
          </div>
        </article>
        <article>
          <small>PM2.5</small>
          <strong>{{ fmt(modelPm25) }}</strong>
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
          <strong>{{ fmt(observedPm25) }}</strong>
          <p v-if="sourceGap != null">{{ sourceGap > 0 ? "偏高" : "偏低" }} {{ Math.abs(sourceGap).toFixed(1) }}</p>
          <p v-else-if="observedPm25 != null">{{ fmtTime(observationTime) }}</p>
          <p v-else>—</p>
        </article>
      </section>
    </header>

    <HealthRiskCard
      class="city-health-card"
      :city="snapshot.data.value?.city"
      :level="nationalCity?.china_aqi_level"
      :health-effect="nationalCity?.health_effect"
      :advice="nationalCity?.advice"
    />

    <nav class="section-nav" aria-label="城市详情分区">
      <a href="#trend"><Activity :size="15" />总趋势</a>
      <a href="#pollutants"><BarChart3 :size="15" />污染物</a>
      <a href="#rhythm"><Clock3 :size="15" />时段</a>
      <a href="#structure"><Layers3 :size="15" />关联</a>
      <a href="#trust"><ShieldCheck :size="15" />可信度</a>
    </nav>

    <section id="trend" class="detail-section first-section">
      <div class="section-heading">
        <h2 class="display-face">{{ trendHeadline }}</h2>
        <span class="forecast-note">{{ forecastOutlook }}</span>
      </div>
      <TraceDeck
        :history="pm25Series"
        :observations="observation.data.value"
        :forecast="forecast.data.value"
      />
    </section>

    <section id="pollutants" class="detail-section">
      <div class="section-heading">
        <h2 class="display-face">{{ pollutantHeadline }}</h2>
      </div>
      <PollutantSmallMultiples
        v-if="pulse.data.value?.length"
        :series="pulse.data.value"
      />
      <div v-else class="section-state">正在读取污染物历史…</div>
    </section>

    <section id="rhythm" class="detail-section">
      <div class="section-heading">
        <h2 class="display-face">{{ rhythmHeadline }}</h2>
      </div>

      <HourRing ref="heatmap" :series="pm25Series" />
    </section>

    <section id="structure" class="detail-section">
      <div class="section-heading">
        <h2 class="display-face">{{ structureHeadline }}</h2>
      </div>
      <PCAStructurePanel
        v-if="structure.data.value"
        :structure="structure.data.value"
      />
      <div v-else class="section-state">当前城市还没有足够样本做结构分析。</div>
    </section>

    <section id="trust" class="detail-section trust-section">
      <div class="section-heading">
        <h2 class="display-face">{{ trustHeadline }}</h2>
      </div>

      <div class="trust-accordions">
        <details class="technical-details">
          <summary>查看预测回测与误差</summary>
          <div class="details-body">
            <BacktestPanel :backtest="backtest.data.value" />
          </div>
        </details>

        <details class="technical-details">
          <summary><Database :size="15" /> 查看数据来源、覆盖率与分析产物</summary>
          <div class="details-body">
            <TrustPanel :coverage="coverage.data.value" />
          </div>
        </details>
      </div>
    </section>
  </section>
</template>

<style scoped>
.city-detail {
  min-height: calc(100vh - 60px);
  padding: 26px 30px 48px;
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
  grid-template-columns: 1.1fr repeat(3, 1fr);
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

.city-health-card { margin-top: 16px; }

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

.detail-section {
  scroll-margin-top: 110px;
  padding-top: 32px;
}
.first-section { padding-top: 24px; }
.section-heading {
  min-height: 48px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 14px;
}
.section-heading h2 {
  margin: 0;
  color: var(--ink);
  font-size: 20px;
  font-weight: 700;
  letter-spacing: var(--track-title);
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

.trust-section { padding-bottom: 14px; }
.trust-accordions {
  display: grid;
  gap: 12px;
}
.technical-details {
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-xl);
  background: var(--sheet);
  box-shadow: var(--shadow-sm);
  transition: all var(--duration-normal) var(--ease-out);
}
.technical-details:hover {
  border-color: var(--hairline-strong);
  box-shadow: var(--shadow-md);
}
.technical-details summary {
  min-height: 60px;
  padding: 0 22px;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  color: var(--ink-soft);
  font-size: var(--fs-body);
  font-weight: var(--fw-strong);
  transition: background var(--duration-fast) ease;
}
.technical-details summary:hover { background: var(--sheet-soft); }
/* Panels inside an accordion keep their own card: same radius, same surface,
   so opening one never looks like a different product. */
.details-body {
  padding: 16px;
  border-top: 1px solid var(--hairline-soft);
  background: var(--sheet-sunken);
}

@media (max-width: 1180px) {
  .city-hero { grid-template-columns: 1fr; }
}
@media (max-width: 760px) {
  .city-detail { padding: 16px 14px 32px; }
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
    margin: 0 -14px;
    padding: 0 14px;
  }
  .section-heading { display: grid; }
  .section-heading h2 { font-size: 18px; }
  .forecast-note { justify-self: start; }
}
</style>
