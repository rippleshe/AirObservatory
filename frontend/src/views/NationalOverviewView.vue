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
import SeverityBand from "../components/SeverityBand.vue";
import {
  AQI_LEVELS,
  CHANGE_COLORS,
  CHANGE_LEVELS,
  aqiColor,
  PM25_BANDS,
} from "../lib/palette";
import {
  concernCount,
  provinceRepresentatives,
  regionSummary,
} from "../lib/provinces";
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
/* One mark per province is the national layer's unit of reading. Reducing
   once here — not inside each chart — is what keeps the headline count, the
   band, the map, the matrix and the region bars describing the same set. */
const provinces = computed(() => provinceRepresentatives(cities.value));
const regions = computed(() => regionSummary(provinces.value));
/* The worst province leads both the headline and the health strip — one
   value, computed once, so the two can never disagree. */
const worstCity = computed(
  () =>
    [...provinces.value]
      .filter((city) => city.china_aqi != null)
      .sort((a, b) => (b.china_aqi ?? -1) - (a.china_aqi ?? -1))[0] ?? null,
);
const focusCity = worstCity;

/* The first line is a readout of the finding, not a sentence about it.
   Prose here used to say "多数城市空气优良，但局地差异明显 …" — a caption
   standing in for the chart. The severity band below is that chart. */
const topLine = computed(() => {
  const worst = worstCity.value;
  if (!worst || worst.china_aqi == null) return "全国省级空气态势";
  return `${worst.name} AQI ${worst.china_aqi} ${worst.china_aqi_level ?? ""} · ${concernCount(
    provinces.value,
  )} 省需要关注`;
});

const fingerprintLine = computed(() => {
  const meta = fingerprint.data.value?.meta;
  if (!meta) return "城市的长期结构指纹";
  return `${meta.city_count} 个省代表分成 ${meta.cluster_count} 种长期模式`;
});

const legendItems = computed<[string, string][]>(() => {
  if (mapMetric.value === "pm25") return PM25_BANDS.map(([label, color]) => [label, color]);
  if (mapMetric.value === "change") return CHANGE_LEVELS.map((l) => [l, CHANGE_COLORS[l]]);
  return AQI_LEVELS.map((l) => [l, aqiColor(l)]);
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
      <h1 class="display-face">{{ topLine }}</h1>
      <div class="update-note">
        <strong class="data-mono">{{ formatTime(national.data.value?.latest_source_time) }}</strong>
        <span>{{ national.data.value?.aqi_standard ?? "HJ 633-2026" }}</span>
      </div>
    </header>

    <div v-if="national.isError.value" class="national-error" role="alert">
      <span>全国数据暂时没有加载成功。</span>
      <button type="button" @click="national.refetch()">重新读取</button>
    </div>

    <SeverityBand
      v-if="provinces.length"
      :cities="provinces"
      @select="openCity"
    />

    <section class="map-stage">
      <NationalFieldMap
        v-if="provinces.length"
        :cities="provinces"
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
        <span class="legend-key"><i class="ring"></i>有近期地面观测</span>
        <span class="legend-rule">一省一点，取该省当前 AQI 最高的城市；浓度由 CAMS 模式换算，非地面监测值</span>
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
  gap: 14px;
  align-content: start;
  background: var(--canvas);
}
/* Compact conclusion + timestamp. DESIGN.md: 不让大标题吞掉首屏. */
.national-header {
  min-height: 54px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 28px;
}
.national-header h1 {
  margin: 0;
  color: var(--ink);
  font-size: clamp(22px, 2.1vw, 30px);
  letter-spacing: var(--track-title);
}
.update-note {
  display: flex;
  align-items: baseline;
  gap: 12px;
  color: var(--muted);
  font-size: var(--fs-label);
  white-space: nowrap;
}
.update-note strong {
  color: var(--ink);
  font-size: var(--fs-body);
  font-weight: var(--fw-strong);
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

.map-stage {
  min-height: 640px;
  position: relative;
  overflow: hidden;
  border: 1px solid var(--hairline-strong);
  border-radius: var(--radius-lg);
  background: var(--map-sea);
}

.metric-switch {
  position: absolute;
  z-index: 10;
  top: 18px;
  right: 18px;
  padding: 4px;
  display: flex;
  gap: 3px;
  border: 1px solid var(--hairline-strong);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, .96);
}
.metric-switch button {
  min-height: 38px;
  padding: 0 14px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--muted);
  font-family: var(--font-display);
  font-size: var(--fs-label);
  font-weight: var(--fw-strong);
  letter-spacing: .03em;
  cursor: pointer;
}
.metric-switch button:hover { background: var(--sheet-sunken); }
.metric-switch button.active {
  background: var(--ink);
  color: #fff;
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
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, .96);
  color: var(--ink-soft);
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
  border: 2px solid var(--ink);
}
.legend-rule {
  color: var(--muted);
}
.map-loading {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: var(--fs-body);
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
  .national-header { display: grid; gap: 6px; }
  .map-stage { min-height: 560px; }
}
@media (max-width: 700px) {
  .map-stage { min-height: 520px; }
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
