<script setup lang="ts">
import { computed, watch } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { useRoute } from "vue-router";
import { Activity, BarChart3, Clock3, Database, Layers3, ShieldCheck } from "lucide-vue-next";
import { api } from "../api/client";
import { expectData } from "../api/request";
import BacktestPanel from "../components/BacktestPanel.vue";
import HealthRiskCard from "../components/HealthRiskCard.vue";
import HourDayHeatmap from "../components/HourDayHeatmap.vue";
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
const POLLUTANTS = ["pm25", "pm10", "no2", "o3", "so2", "co"] as const;

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
  if (delta == null) return "历史不足";
  if (Math.abs(delta) < 2) return "基本持平";
  return `${delta > 0 ? "上升" : "下降"} ${Math.abs(delta).toFixed(1)}`;
});

const sourceGap = computed(() => {
  if (modelPm25.value == null || observedPm25.value == null) return null;
  return Number(modelPm25.value) - Number(observedPm25.value);
});

const heroSentence = computed(() => {
  const level = nationalCity.value?.china_aqi_level;
  const primary = nationalCity.value?.primary_pollutants?.[0];
  if (!level) return "正在读取当前空气状态。";
  if (primary) return `当前${level}，主要污染物为 ${primary.toUpperCase()}。`;
  return `当前空气质量为${level}。`;
});

const forecastOutlook = computed(() => {
  const points = forecast.data.value?.series?.[0]?.points ?? [];
  if (!points.length) return "未来预测正在准备";
  const first = points[0]?.value;
  const last = points.at(-1)?.value;
  const peak = Math.max(...points.map((point) => point.value));
  if (first == null || last == null) return `未来峰值约 ${peak.toFixed(1)} µg/m³`;
  const delta = last - first;
  const direction =
    Math.abs(delta) < 2 ? "整体平稳" : delta > 0 ? "仍有上升压力" : "有望逐步改善";
  return `${direction} · 预测峰值 ${peak.toFixed(1)} µg/m³`;
});
</script>

<template>
  <section class="city-detail">
    <header class="city-hero">
      <div class="hero-title">
        <span class="city-kicker">{{ snapshot.data.value?.province ?? "—" }} · 城市空气画像</span>
        <h1>{{ snapshot.data.value?.city ?? context.selectedCityName }}</h1>
        <p>{{ heroSentence }}</p>
      </div>

      <section
        class="current-status"
        :style="{ '--aqi-tone': aqiColor(nationalCity?.china_aqi_level) }"
        aria-label="当前空气质量"
      >
        <article class="status-main">
          <span class="status-dot" aria-hidden="true"></span>
          <div>
            <small>当前空气质量</small>
            <strong>{{ nationalCity?.china_aqi_level ?? "暂无" }}</strong>
            <p>AQI {{ nationalCity?.china_aqi ?? "—" }}</p>
          </div>
        </article>
        <article>
          <small>PM2.5 当前</small>
          <strong>{{ fmt(modelPm25) }}</strong>
          <p>µg/m³ · {{ fmtTime(snapshot.data.value?.model_analysis?.source_time) }}</p>
        </article>
        <article>
          <small>过去 24h</small>
          <strong :class="{ bad: (pm25Trend.delta ?? 0) > 0, good: (pm25Trend.delta ?? 0) < 0 }">
            {{ trendSentence }}
          </strong>
          <p>日均约 {{ fmt(pm25Trend.recentAvg) }} µg/m³</p>
        </article>
        <article>
          <small>近期地面观测</small>
          <strong>{{ fmt(observedPm25) }}</strong>
          <p v-if="sourceGap != null">模式{{ sourceGap > 0 ? "偏高" : "偏低" }} {{ Math.abs(sourceGap).toFixed(1) }} µg/m³</p>
          <p v-else>当前暂无同屏对照</p>
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
        <div>
          <h2>过去发生了什么，接下来会怎样？</h2>
          <p>模式历史、真实地面观测、当前时刻、未来预测和浓度等级都放在同一条时间线上；可切换 24 小时、7 天和 30 天。</p>
        </div>
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
        <div>
          <h2>当前数值放到过去 30 天里，才知道它算不算高</h2>
          <p>每张卡同时给出当前值、24 小时变化、近 30 天历史位置、中位数、P90 与最近 7 天趋势。</p>
        </div>
      </div>
      <PollutantSmallMultiples
        v-if="pulse.data.value?.length"
        :series="pulse.data.value"
      />
      <div v-else class="section-state">正在读取污染物历史…</div>
    </section>

    <section id="rhythm" class="detail-section">
      <div class="section-heading">
        <div>
          <h2>污染高值集中在什么时段？</h2>
          <p>把最近 30 天每一天的 24 小时铺开，既能看到稳定的日内规律，也能看到某几天的异常污染过程。</p>
        </div>
      </div>

      <div class="change-summary">
        <article>
          <span>24h 相对前一天</span>
          <strong v-if="pm25Trend.delta != null">
            {{ pm25Trend.delta > 0 ? "↑" : "↓" }} {{ Math.abs(pm25Trend.delta).toFixed(1) }} µg/m³
          </strong>
          <strong v-else>历史不足</strong>
        </article>
        <article>
          <span>最近 24h 峰值</span>
          <strong>{{ fmt(pm25Trend.peak) }} <small>µg/m³</small></strong>
          <p>{{ fmtTime(pm25Trend.peakTime) }}</p>
        </article>
        <article>
          <span>模式与地面观测</span>
          <strong v-if="sourceGap != null">
            {{ sourceGap > 0 ? "模式偏高" : "模式偏低" }} {{ Math.abs(sourceGap).toFixed(1) }}
            <small>µg/m³</small>
          </strong>
          <strong v-else>暂无同时段对照</strong>
          <p>两种来源保持分开，不互相补值</p>
        </article>
      </div>

      <HourDayHeatmap :series="pm25Series" />
    </section>

    <section id="structure" class="detail-section">
      <div class="section-heading">
        <div>
          <h2>哪些污染与气象因素经常一起变化？</h2>
          <p>这一层服务于深入探索：看共同变化、相关结构和空气状态分布，但不把相关性解释成因果。</p>
        </div>
        <span class="advanced-label">深度分析</span>
      </div>
      <PCAStructurePanel
        v-if="structure.data.value"
        :structure="structure.data.value"
      />
      <div v-else class="section-state">当前城市还没有足够的数据生成结构分析。</div>
    </section>

    <section id="trust" class="detail-section trust-section">
      <div class="section-heading">
        <div>
          <h2>这些判断值得信到什么程度？</h2>
          <p>把回测、覆盖率、站点来源和离线分析产物留在最后一层，让老师可以追溯，但不干扰普通用户先读懂空气变化。</p>
        </div>
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
  grid-template-columns: minmax(280px, .7fr) minmax(760px, 1.7fr);
  gap: 34px;
  align-items: end;
  padding: 12px 0 22px;
  border-bottom: 1px solid var(--hairline);
}
.city-kicker {
  display: block;
  color: var(--muted);
  font-size: var(--fs-label);
  font-weight: var(--fw-strong);
}
.hero-title h1 {
  margin: 5px 0 0;
  color: var(--ink);
  font-size: clamp(46px, 4.5vw, 62px);
  font-weight: var(--fw-display);
  letter-spacing: var(--track-display);
  line-height: 1;
}
.hero-title p {
  max-width: 35ch;
  margin: 12px 0 0;
  color: var(--muted);
  font-size: 16px;
  line-height: 1.55;
}

.current-status {
  min-height: 138px;
  display: grid;
  grid-template-columns: 1.15fr repeat(3, 1fr);
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
  box-shadow: 0 10px 30px rgba(23, 41, 34, .04);
}
.current-status article {
  min-width: 0;
  padding: 19px 18px;
  display: grid;
  align-content: center;
  gap: 3px;
}
.current-status article + article { border-left: 1px solid var(--hairline-soft); }
.current-status small {
  color: var(--muted);
  font-size: var(--fs-label);
}
/* Hero figures: proportional digits. */
.current-status strong {
  color: var(--ink);
  font-size: 29px;
  font-weight: var(--fw-display);
  letter-spacing: -.035em;
}
.current-status strong.bad { color: var(--error); }
.current-status strong.good { color: var(--ok); }
.current-status p {
  margin: 0;
  color: var(--muted);
  font-size: var(--fs-label);
  line-height: 1.45;
}
.status-main {
  grid-template-columns: 12px 1fr;
  column-gap: 9px;
}
.status-main > div { grid-column: 2; }
.status-dot {
  grid-row: 1 / 4;
  width: 10px;
  height: 10px;
  margin-top: 5px;
  border-radius: 50%;
  background: var(--aqi-tone);
}
.status-main strong { font-size: 25px; }

.city-health-card { margin-top: 14px; }

.section-nav {
  position: sticky;
  top: 60px;
  z-index: 8;
  min-height: 52px;
  margin: 0 -30px;
  padding: 0 30px;
  display: flex;
  align-items: center;
  gap: 5px;
  overflow-x: auto;
  border-bottom: 1px solid var(--hairline);
  background: rgba(242, 245, 243, .97);
  backdrop-filter: blur(8px);
}
.section-nav a {
  min-height: 38px;
  padding: 0 13px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 8px;
  color: var(--muted);
  font-size: var(--fs-label);
  font-weight: var(--fw-strong);
  text-decoration: none;
  white-space: nowrap;
}
.section-nav a:hover {
  color: var(--ink);
  background: var(--soft);
}

.detail-section {
  scroll-margin-top: 118px;
  padding-top: 40px;
}
.first-section { padding-top: 30px; }
.section-heading {
  min-height: 78px;
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 24px;
}
.section-heading h2 {
  margin: 4px 0 0;
  color: var(--ink);
  font-size: var(--fs-title);
  font-weight: var(--fw-display);
  letter-spacing: var(--track-display);
}
.section-heading p {
  max-width: 780px;
  margin: 7px 0 0;
  color: var(--muted);
  font-size: var(--fs-body);
  line-height: 1.65;
}
.forecast-note,
.advanced-label {
  max-width: 260px;
  min-height: 34px;
  padding: 8px 12px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-pill);
  background: var(--sheet);
  color: var(--ink-soft);
  font-size: var(--fs-label);
  font-weight: var(--fw-strong);
  line-height: 1.45;
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

.change-summary {
  display: grid;
  grid-template-columns: 1.35fr .85fr 1fr;
  margin-bottom: 14px;
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
}
.change-summary article {
  min-width: 0;
  min-height: 100px;
  padding: 16px 18px;
  display: grid;
  align-content: center;
  gap: 5px;
}
.change-summary article + article { border-left: 1px solid var(--hairline-soft); }
.change-summary span,
.change-summary p {
  margin: 0;
  color: var(--muted);
  font-size: var(--fs-label);
}
.change-summary strong {
  color: var(--ink);
  font-size: 18px;
  font-weight: var(--fw-display);
  line-height: 1.35;
}
.change-summary article:nth-child(2) strong { font-size: 27px; }
.change-summary small {
  color: var(--muted);
  font-size: var(--fs-label);
  font-weight: 500;
}

.trust-section { padding-bottom: 14px; }
.trust-accordions {
  display: grid;
  gap: 12px;
}
.technical-details {
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
}
.technical-details summary {
  min-height: 58px;
  padding: 0 18px;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: var(--ink-soft);
  font-size: var(--fs-body);
  font-weight: var(--fw-strong);
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
  .change-summary { grid-template-columns: 1fr 1fr; }
  .change-summary article:nth-child(3) {
    grid-column: 1 / -1;
    border-left: 0;
    border-top: 1px solid var(--hairline-soft);
  }
}
@media (max-width: 760px) {
  .city-detail { padding: 18px 12px 36px; }
  .city-hero { gap: 18px; }
  .hero-title h1 { font-size: 46px; }
  .current-status { grid-template-columns: 1fr 1fr; }
  .current-status article:nth-child(3) {
    border-left: 0;
    border-top: 1px solid var(--hairline-soft);
  }
  .current-status article:nth-child(4) { border-top: 1px solid var(--hairline-soft); }
  .section-nav {
    top: 60px;
    margin: 0 -12px;
    padding: 0 12px;
  }
  .section-heading { display: grid; }
  .section-heading h2 { font-size: 23px; }
  .forecast-note,
  .advanced-label { justify-self: start; }
  .change-summary { grid-template-columns: 1fr; }
  .change-summary article + article,
  .change-summary article:nth-child(3) {
    grid-column: auto;
    border-left: 0;
    border-top: 1px solid var(--hairline-soft);
  }
}
</style>
