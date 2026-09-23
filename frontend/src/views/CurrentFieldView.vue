<script setup lang="ts">
import { computed } from "vue";
import { Clock3, DatabaseZap, RotateCw, Waves } from "lucide-vue-next";
import GeoFieldMap from "../components/GeoFieldMap.vue";
import ReadoutLedger from "../components/ReadoutLedger.vue";
import TraceDeck from "../components/TraceDeck.vue";
import { useLiveField } from "../composables/useLiveField";

const {
  context,
  selectedId,
  status,
  overview,
  snapshot,
  modelHistory,
  observationHistory,
  forecast,
  retryPrimary,
} = useLiveField();

const locations = computed(() => overview.data.value?.locations ?? []);
const sourceTime = computed(() => overview.data.value?.meta.latest_source_time);
const health = computed(() => overview.data.value?.meta.provider_health ?? "empty");
const hasPrimaryError = computed(
  () =>
    overview.isError.value ||
    snapshot.isError.value ||
    modelHistory.isError.value ||
    forecast.isError.value,
);

function fmtTime(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function selectLocation(id: number, name: string) {
  context.selectLocation(id, name);
}

const metricLabel: Record<string, string> = {
  pm25: "PM2.5",
  pm10: "PM10",
  no2: "NO₂",
  o3: "O₃",
};
</script>

<template>
  <section class="live-workspace">
    <div class="provenance-strip">
      <div class="provenance-source">
        <DatabaseZap :size="13" />
        <span>CAMS / OPENAQ</span>
        <strong>双源</strong>
      </div>
      <div class="provenance-item">
        <Clock3 :size="12" />
        <span>模式源时间</span>
        <b class="data-mono">{{ fmtTime(sourceTime) }}</b>
      </div>
      <div class="provenance-item">
        <Waves :size="12" />
        <span>CAMS</span>
        <b :class="['health', health]">{{ health.toUpperCase() }}</b>
      </div>
      <div class="provenance-item">
        <span>OpenAQ</span>
        <b :class="['health', status.data.value?.providers.openaq.state]">
          {{ status.data.value?.providers.openaq.state?.toUpperCase() ?? "…" }}
        </b>
      </div>
      <button
        v-if="hasPrimaryError"
        type="button"
        class="retry-inline"
        @click="retryPrimary"
      >
        <RotateCw :size="12" />
        重试
      </button>
      <div class="provenance-warning">
        地面观测 {{ status.data.value?.counts.air_observations ?? 0 }} 条
        · CAMS 始终单独标识
      </div>
    </div>

    <div class="live-upper">
      <section class="map-plate">
        <div class="map-toolbar">
          <div>
            <span class="plate-title">中国重点城市 · CAMS 当前模式场</span>
            <span class="plate-subtitle">
              全国空间比较保持同一数据源；城市详情再叠加 OpenAQ 地面观测
            </span>
          </div>
          <label class="metric-select">
            <span>指标</span>
            <select v-model="context.selectedMetric">
              <option value="pm25">PM2.5</option>
              <option value="pm10">PM10</option>
              <option value="no2">NO₂</option>
              <option value="o3">O₃</option>
            </select>
          </label>
        </div>

        <GeoFieldMap
          v-if="locations.length"
          :locations="locations"
          :selected-id="selectedId"
          @select="selectLocation"
        />
        <div v-else-if="overview.isPending.value" class="map-state" role="status">
          <span class="state-line"></span>
          <p>正在读取空间场…</p>
        </div>
        <div v-else class="map-state error" role="alert">
          <span class="state-line"></span>
          <p>空间场加载失败，现有数据没有被替换为示例值。</p>
          <button type="button" @click="retryPrimary">重新连接</button>
        </div>

        <div class="map-corner-note">
          <span>{{ metricLabel[context.selectedMetric] }}</span>
          <b>CAMS MODEL FIELD</b>
        </div>
      </section>

      <ReadoutLedger
        :snapshot="snapshot.data.value"
        :locations="locations"
        :selected-id="selectedId"
        :metric="context.selectedMetric"
        :loading="snapshot.isPending.value"
        :error="snapshot.isError.value"
        @select="selectLocation"
        @retry="retryPrimary"
      />
    </div>

    <TraceDeck
      :history="modelHistory.data.value"
      :observations="observationHistory.data.value"
      :forecast="forecast.data.value"
    />
  </section>
</template>

<style scoped>
.live-workspace {
  height: calc(100vh - 54px);
  min-height: 720px;
  display: grid;
  grid-template-rows: 34px minmax(430px, 1fr) minmax(220px, 28vh);
  overflow: hidden;
}

.provenance-strip {
  display: flex;
  align-items: center;
  gap: 0;
  min-width: 0;
  background: #f2f4f1;
  border-bottom: 1px solid var(--hairline);
  color: var(--muted);
  font-size: 10px;
}

.provenance-source,
.provenance-item {
  height: 100%;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 14px;
  border-right: 1px solid var(--hairline);
  white-space: nowrap;
}
.provenance-source span { font-family: var(--mono); letter-spacing: .03em; }
.provenance-source strong {
  color: var(--model);
  font-size: 10px;
  font-weight: 650;
}
.provenance-item b { color: var(--ink); font-weight: 560; }
.health.fresh,
.health.healthy { color: var(--ok); }
.health.stale,
.health.error { color: var(--warning); }
.health.empty,
.health.disabled,
.health.unknown { color: var(--muted); }

.retry-inline {
  height: 100%;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 12px;
  border: 0;
  border-right: 1px solid var(--hairline);
  background: transparent;
  color: var(--error);
  cursor: pointer;
  font-size: 10px;
}
.retry-inline:hover { background: #ecefeb; }

.provenance-warning {
  margin-left: auto;
  padding: 0 14px;
  color: #6f654f;
  white-space: nowrap;
}

.live-upper {
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
}

.map-plate {
  min-width: 0;
  min-height: 0;
  position: relative;
  overflow: hidden;
  background: #e8eeea;
}

.map-toolbar {
  position: absolute;
  z-index: 5;
  top: 14px;
  left: 14px;
  right: 14px;
  min-height: 54px;
  display: flex;
  justify-content: space-between;
  align-items: start;
  gap: 20px;
  pointer-events: none;
}

.map-toolbar > div {
  max-width: 500px;
  padding: 9px 11px;
  background: rgba(249, 250, 247, .94);
  border: 1px solid rgba(24, 32, 30, .12);
  border-radius: 4px;
}

.plate-title {
  display: block;
  font-size: 12px;
  font-weight: 650;
}
.plate-subtitle {
  display: block;
  margin-top: 4px;
  color: var(--muted);
  font-size: 9px;
}

.metric-select {
  pointer-events: auto;
  min-height: 44px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px 8px 5px 10px;
  background: rgba(249, 250, 247, .96);
  border: 1px solid rgba(24, 32, 30, .15);
  border-radius: 4px;
  color: var(--muted);
  font-size: 10px;
}
.metric-select select {
  min-height: 32px;
  border: 0;
  background: transparent;
  color: var(--ink);
  font-size: 12px;
  font-weight: 600;
}

.map-corner-note {
  position: absolute;
  z-index: 4;
  left: 14px;
  bottom: 14px;
  display: grid;
  gap: 2px;
  padding: 7px 9px;
  background: rgba(249, 250, 247, .92);
  border: 1px solid rgba(24, 32, 30, .12);
  border-radius: 4px;
}
.map-corner-note span { font-size: 10px; }
.map-corner-note b {
  font: 600 8px/1.2 var(--mono);
  color: var(--muted);
  letter-spacing: .08em;
}

.map-state {
  height: 100%;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 12px;
  color: var(--muted);
  font-size: 12px;
}
.map-state p { margin: 0; }
.map-state button {
  min-height: 44px;
  padding: 0 16px;
  border: 1px solid var(--hairline-strong);
  border-radius: var(--radius);
  background: var(--sheet);
  color: var(--ink);
  cursor: pointer;
}
.state-line { width: 54px; height: 1px; background: var(--accent); }
.map-state.error .state-line { background: var(--error); }

@media (max-width: 1050px) {
  .live-workspace {
    height: auto;
    overflow: visible;
    grid-template-rows: 34px auto 300px;
  }
  .live-upper { grid-template-columns: 1fr; grid-template-rows: 520px auto; }
  :deep(.readout-ledger) {
    border-left: 0;
    border-top: 1px solid var(--hairline);
  }
}

@media (max-width: 760px) {
  .provenance-warning { display: none; }
  .provenance-source span { display: none; }
  .provenance-item:nth-of-type(3) { display: none; }
  .live-upper { grid-template-rows: 430px auto; }
  .map-toolbar { right: 8px; left: 8px; }
  .map-toolbar > div { max-width: 260px; }
  .plate-subtitle { display: none; }
}
</style>
