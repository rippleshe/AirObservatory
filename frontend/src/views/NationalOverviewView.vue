<script setup lang="ts">
import { computed, ref } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { Database, Layers3 } from "lucide-vue-next";
import { useRouter } from "vue-router";
import { api } from "../api/client";
import { expectData } from "../api/request";
import CityFingerprintPanel from "../components/CityFingerprintPanel.vue";
import HealthRiskCard from "../components/HealthRiskCard.vue";
import NationalFieldMap from "../components/NationalFieldMap.vue";
import NationalInsightDeck from "../components/NationalInsightDeck.vue";
import {
  AQI_LEVELS,
  CHANGE_COLORS,
  CHANGE_LEVELS,
  changeState,
  aqiColor,
  PM25_BANDS,
} from "../lib/palette";
import { useContextStore } from "../stores/context";

type MapMetric = "aqi" | "pm25" | "change";

const router = useRouter();
const context = useContextStore();
const mapMetric = ref<MapMetric>("aqi");

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

const cities = computed(() => national.data.value?.cities ?? []);
const summary = computed(() => national.data.value?.summary);
const regions = computed(() => national.data.value?.regions ?? []);
const rankedCities = computed(() =>
  [...cities.value]
    .filter((city) => city.china_aqi != null)
    .sort((a, b) => (b.china_aqi ?? -1) - (a.china_aqi ?? -1)),
);
const focusCity = computed(() => rankedCities.value[0]);

const goodCityCount = computed(() => {
  const counts = summary.value?.level_counts ?? {};
  return (counts["优"] ?? 0) + (counts["良"] ?? 0);
});
const concernCityCount = computed(() => {
  const counts = summary.value?.level_counts ?? {};
  return (
    (counts["轻度污染"] ?? 0) +
    (counts["中度污染"] ?? 0) +
    (counts["重度污染"] ?? 0) +
    (counts["严重污染"] ?? 0)
  );
});
const averageChange = computed(() => {
  const values = cities.value
    .map((city) => city.pm25_change_24h)
    .filter((value): value is number => value != null && Number.isFinite(value));
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
});
const worsenedCount = computed(
  () => cities.value.filter((city) => (city.pm25_change_24h ?? 0) >= 8).length,
);
const improvedCount = computed(
  () => cities.value.filter((city) => (city.pm25_change_24h ?? 0) <= -8).length,
);
const nationalHeadline = computed(() => {
  const total = summary.value?.city_count ?? 0;
  if (!total) return "正在读取全国空气态势";
  const goodRatio = goodCityCount.value / total;
  if (goodRatio >= 0.7) return "多数城市空气优良，但局地差异明显";
  if (goodRatio >= 0.5) return "全国整体尚可，部分城市污染偏高";
  return "多地空气需要关注，城市差异正在扩大";
});
const nationalLead = computed(() => {
  const worst = summary.value?.worst_city;
  const aqi = summary.value?.worst_city_aqi;
  const change = averageChange.value;
  const trend =
    change == null
      ? "24 小时变化数据暂不完整"
      : `全国 PM2.5 较 24 小时前平均${change >= 0 ? "上升" : "下降"} ${Math.abs(change).toFixed(1)} µg/m³`;
  return worst && aqi != null
    ? `${worst} 当前 AQI ${aqi}，为当前最需要关注的城市；${trend}。`
    : trend;
});

const legendItems = computed<[string, string][]>(() => {
  if (mapMetric.value === "pm25") return PM25_BANDS.map(([label, color]) => [label, color]);
  if (mapMetric.value === "change") return CHANGE_LEVELS.map((l) => [l, CHANGE_COLORS[l]]);
  return AQI_LEVELS.map((l) => [l, aqiColor(l)]);
});

const mapReadout = computed(() => {
  if (mapMetric.value === "pm25") {
    return {
      label: "全国 PM2.5 均值",
      value: summary.value?.mean_pm25 == null ? "—" : summary.value.mean_pm25.toFixed(1),
      unit: "µg/m³",
      note: "颜色越暖，颗粒物浓度越高",
    };
  }
  if (mapMetric.value === "change") {
    const value = averageChange.value;
    const state = changeState(value);
    return {
      label: "24h 平均变化",
      value: value == null ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(1)}`,
      unit: "µg/m³",
      note: `${state.arrow} 全国整体${state.label}，绿色代表改善`,
    };
  }
  return {
    label: "空气优良城市",
    value: summary.value ? `${goodCityCount.value}/${summary.value.city_count}` : "—",
    unit: "城",
    note: "颜色直接对应中国 AQI 等级",
  };
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
    <header class="national-header">
      <div>
        <h1>全国空气态势</h1>
        <p><strong>{{ nationalHeadline }}</strong> {{ nationalLead }}</p>
      </div>
      <div class="update-note">
        <span>最近数据</span>
        <strong>{{ formatTime(national.data.value?.latest_source_time) }}</strong>
        <small>{{ national.data.value?.aqi_standard ?? "HJ 633-2026" }}</small>
      </div>
    </header>

    <div v-if="national.isError.value" class="national-error" role="alert">
      <span>全国数据暂时没有加载成功。</span>
      <button type="button" @click="national.refetch()">重新读取</button>
    </div>

    <section class="map-stage">
      <NationalFieldMap
        v-if="cities.length"
        :cities="cities"
        :metric="mapMetric"
        @select="openCity"
      />
      <div v-else class="map-loading" role="status">正在绘制全国空气状态…</div>

      <div class="map-overview-card">
        <span>{{ mapReadout.label }}</span>
        <div class="map-main-value">
          <strong>{{ mapReadout.value }}</strong>
          <small>{{ mapReadout.unit }}</small>
        </div>
        <p>{{ mapReadout.note }}</p>
        <div class="map-mini-stats">
          <span><b>{{ goodCityCount }}</b> 优良</span>
          <span><b>{{ concernCityCount }}</b> 需关注</span>
          <span><b>{{ improvedCount }}</b> 改善</span>
          <span><b>{{ worsenedCount }}</b> 上升</span>
        </div>
      </div>

      <div class="metric-switch" aria-label="地图指标">
        <button :class="{ active: mapMetric === 'aqi' }" @click="mapMetric = 'aqi'">AQI</button>
        <button :class="{ active: mapMetric === 'pm25' }" @click="mapMetric = 'pm25'">PM2.5</button>
        <button :class="{ active: mapMetric === 'change' }" @click="mapMetric = 'change'">24h 变化</button>
      </div>

      <div class="map-legend" aria-label="地图图例">
        <span v-for="[label, color] in legendItems" :key="String(label)">
          <i :style="{ background: color }"></i>{{ label }}
        </span>
      </div>
    </section>

    <HealthRiskCard
      v-if="focusCity"
      class="health-strip"
      compact
      :city="focusCity.name"
      :level="focusCity.china_aqi_level"
      :health-effect="focusCity.health_effect"
      :advice="focusCity.advice"
    />

    <section v-if="summary" class="analysis-section">
      <div class="section-heading">
        <div>
          <h2>60 座城市，不只看「谁最高」</h2>
          <p>把当前污染水平、24 小时变化、区域结构和首要污染物放在同一组视图里，才能看清「哪里高、哪里还在升、为什么区域内部也不同」。</p>
        </div>
      </div>
      <NationalInsightDeck
        :regions="regions"
        :cities="cities"
        :summary="summary"
      />
    </section>

    <details class="deep-analysis">
      <summary>
        <span><Layers3 :size="17" /> 进一步看：哪些城市的长期变化模式更相似？</span>
        <small>60 城长期污染—气象结构 · PCA / 探索性分组</small>
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

    <footer class="national-footer">
      <Database :size="15" />
      <span>全国空间比较使用同一套模式数据；真实地面观测仅在存在时以外环标出，不用于补齐其他城市。</span>
    </footer>
  </section>
</template>

<style scoped>
.national-workspace {
  min-height: calc(100vh - 60px);
  padding: 26px 32px 48px;
  background: var(--canvas);
}
.national-header {
  min-height: 108px;
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 36px;
}
.national-header h1 {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-hero);
  font-weight: var(--fw-display);
  letter-spacing: var(--track-display);
  line-height: 1;
}
.national-header p {
  max-width: 900px;
  margin: 12px 0 0;
  color: var(--muted);
  font-size: var(--fs-body);
  line-height: 1.7;
}
.national-header p strong {
  color: var(--ink-soft);
  font-size: 16px;
}
.update-note {
  min-width: 170px;
  padding-top: 8px;
  display: grid;
  justify-items: end;
  gap: 3px;
  color: var(--muted);
  font-size: var(--fs-label);
}
.update-note strong {
  color: var(--ink);
  font-size: var(--fs-body);
  font-weight: var(--fw-strong);
}
.update-note small { font-size: var(--fs-label); }

.national-error {
  min-height: 48px;
  margin-bottom: 14px;
  padding: 0 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid #d8b7b2;
  border-radius: var(--radius-sm);
  background: #fff7f5;
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

.map-stage {
  min-height: 660px;
  position: relative;
  overflow: hidden;
  border: 1px solid var(--hairline-strong);
  border-radius: 20px;
  background: var(--sheet-sunken);
  box-shadow: 0 18px 48px rgba(23, 43, 34, .07);
}
.map-overview-card {
  position: absolute;
  z-index: 10;
  top: 20px;
  left: 20px;
  width: 268px;
  padding: 16px 18px;
  border: 1px solid rgba(169, 182, 175, .92);
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, .965);
  box-shadow: 0 12px 34px rgba(17, 37, 29, .09);
  pointer-events: none;
}
.map-overview-card > span {
  color: var(--muted);
  font-size: var(--fs-label);
  font-weight: var(--fw-strong);
}
.map-main-value {
  display: flex;
  align-items: baseline;
  gap: 7px;
  margin-top: 2px;
}
/* Hero figure: proportional digits, same sans as everything else. */
.map-main-value strong {
  color: var(--ink);
  font-size: 38px;
  font-weight: var(--fw-display);
  letter-spacing: -.04em;
}
.map-main-value small {
  color: var(--muted);
  font-size: var(--fs-label);
}
.map-overview-card p {
  margin: 3px 0 14px;
  color: var(--muted);
  font-size: var(--fs-label);
  line-height: 1.5;
}
.map-mini-stats {
  padding-top: 12px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 7px 12px;
  border-top: 1px solid var(--hairline-soft);
  color: var(--muted);
  font-size: var(--fs-label);
}
.map-mini-stats b {
  margin-right: 4px;
  color: var(--ink);
  font-size: 16px;
}

.metric-switch {
  position: absolute;
  z-index: 10;
  top: 20px;
  right: 20px;
  padding: 4px;
  display: flex;
  gap: 3px;
  border: 1px solid var(--hairline-strong);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, .96);
  box-shadow: 0 10px 28px rgba(20, 38, 31, .07);
}
.metric-switch button {
  min-height: 38px;
  padding: 0 14px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--muted);
  font-size: var(--fs-label);
  font-weight: var(--fw-strong);
  cursor: pointer;
}
.metric-switch button:hover { background: var(--soft); }
.metric-switch button.active {
  background: var(--ink);
  color: #fff;
}

.map-legend {
  position: absolute;
  z-index: 9;
  left: 20px;
  bottom: 18px;
  min-height: 42px;
  padding: 9px 14px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 15px;
  border: 1px solid rgba(169, 182, 175, .94);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, .96);
  box-shadow: 0 8px 24px rgba(21, 37, 31, .06);
  color: var(--ink-soft);
  font-size: var(--fs-label);
}
.map-legend span { display: inline-flex; align-items: center; gap: 6px; }
.map-legend i {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.map-loading {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: var(--fs-body);
}
.health-strip { margin-top: 14px; }

.analysis-section { margin-top: 42px; }
.section-heading {
  max-width: 980px;
  margin-bottom: 18px;
}
.section-heading h2 {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-title);
  font-weight: var(--fw-display);
  letter-spacing: var(--track-display);
}
.section-heading p {
  margin: 8px 0 0;
  color: var(--muted);
  font-size: var(--fs-body);
  line-height: 1.7;
}

.deep-analysis {
  margin-top: 28px;
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
}
.deep-analysis > summary {
  min-height: 78px;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  cursor: pointer;
}
.deep-analysis > summary:hover { background: var(--sheet-soft); }
.deep-analysis summary > span {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  color: var(--ink);
  font-size: var(--fs-body);
  font-weight: var(--fw-strong);
}
.deep-analysis summary small {
  color: var(--muted);
  font-size: var(--fs-label);
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
.national-footer {
  min-height: 58px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--muted);
  font-size: var(--fs-label);
  line-height: 1.5;
}

@media (max-width: 900px) {
  .national-workspace { padding: 22px 18px 40px; }
  .national-header { display: grid; gap: 8px; }
  .update-note { justify-items: start; }
  .map-stage { min-height: 600px; }
  .map-overview-card { width: 240px; }
}
@media (max-width: 700px) {
  .national-workspace { padding: 18px 12px 34px; }
  .national-header h1 { font-size: 38px; }
  .national-header p { font-size: var(--fs-body); }
  .map-stage { min-height: 560px; border-radius: 14px; }
  .map-overview-card {
    top: 12px;
    left: 12px;
    width: calc(100% - 24px);
    padding: 13px 15px;
  }
  .map-main-value strong { font-size: 31px; }
  .map-mini-stats { grid-template-columns: repeat(4, auto); justify-content: start; }
  .metric-switch {
    top: 196px;
    left: 12px;
    right: auto;
  }
  .metric-switch button { padding: 0 11px; }
  .map-legend {
    left: 12px;
    right: 64px;
    bottom: 58px;
  }
  .section-heading h2 { font-size: 23px; }
  .deep-analysis > summary {
    align-items: start;
    padding: 16px;
    flex-direction: column;
    justify-content: center;
    gap: 4px;
  }
}
</style>
