<script setup lang="ts">
import { computed } from "vue";
import type { components } from "../api/schema";

type AirState = components["schemas"]["AirState"];
type Snapshot = components["schemas"]["SnapshotResponse"];
type Location = components["schemas"]["OverviewLocation"];

const props = defineProps<{
  snapshot: Snapshot | undefined;
  locations: Location[];
  selectedId: number | null;
  metric: string;
  loading?: boolean;
  error?: boolean;
}>();

const emit = defineEmits<{
  select: [id: number, name: string];
  retry: [];
}>();

const metricMeta: Record<string, { label: string; unit: string }> = {
  pm25: { label: "PM2.5", unit: "µg/m³" },
  pm10: { label: "PM10", unit: "µg/m³" },
  no2: { label: "NO₂", unit: "µg/m³" },
  o3: { label: "O₃", unit: "µg/m³" },
};

function valueFor(state: AirState | null | undefined, metric: string) {
  if (!state) return null;
  if (metric === "pm25") return state.pm25;
  if (metric === "pm10") return state.pm10;
  if (metric === "no2") return state.no2;
  if (metric === "o3") return state.o3;
  return null;
}

function number(value: number | null | undefined, digits = 1) {
  return value == null ? "—" : value.toFixed(digits);
}

function time(value: string | undefined | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function ageHours(value: string | undefined | null) {
  if (!value) return Number.POSITIVE_INFINITY;
  return Math.max(0, (Date.now() - new Date(value).getTime()) / 3_600_000);
}

const observationValue = computed(() =>
  valueFor(props.snapshot?.observation, props.metric),
);
const modelValue = computed(() =>
  valueFor(props.snapshot?.model_analysis, props.metric),
);
const observationFresh = computed(
  () =>
    observationValue.value != null &&
    ageHours(props.snapshot?.observation?.source_time) <= 3,
);
const primaryState = computed(() =>
  observationFresh.value
    ? props.snapshot?.observation
    : props.snapshot?.model_analysis,
);
const primaryValue = computed(() =>
  observationFresh.value ? observationValue.value : modelValue.value,
);
const primaryKind = computed(() =>
  observationFresh.value ? "OpenAQ 地面观测" : "CAMS 模式估计",
);
</script>

<template>
  <aside class="readout-ledger" aria-live="polite">
    <div v-if="loading && !snapshot" class="ledger-state">
      <span class="state-rule"></span>
      <p>正在读取城市观测…</p>
    </div>

    <div v-else-if="error && !snapshot" class="ledger-state">
      <span class="state-rule error"></span>
      <p>城市读数加载失败。</p>
      <button type="button" @click="emit('retry')">重试</button>
    </div>

    <template v-else-if="snapshot && primaryState">
      <div class="ledger-heading">
        <div>
          <h2>{{ snapshot.city }}</h2>
          <p class="coords data-mono">
            {{ snapshot.lat.toFixed(3) }} N / {{ snapshot.lon.toFixed(3) }} E
          </p>
        </div>
        <span class="source-label">{{ primaryKind }}</span>
      </div>

      <div class="hero-readout">
        <strong class="data-mono">{{ number(primaryValue) }}</strong>
        <div>
          <b>{{ metricMeta[metric]?.label ?? metric.toUpperCase() }}</b>
          <span>{{ metricMeta[metric]?.unit ?? "" }}</span>
        </div>
      </div>

      <div class="comparison-ledger">
        <div>
          <span>地面观测</span>
          <b class="data-mono">{{ number(observationValue) }}</b>
          <small>
            {{ snapshot.observation?.station_name ?? "未接入" }}
            · {{ time(snapshot.observation?.source_time) }}
          </small>
        </div>
        <div>
          <span>CAMS 模式</span>
          <b class="data-mono">{{ number(modelValue) }}</b>
          <small>{{ time(snapshot.model_analysis?.source_time) }}</small>
        </div>
      </div>

      <dl class="pollutant-grid">
        <div>
          <dt>PM10</dt>
          <dd class="data-mono">{{ number(snapshot.model_analysis?.pm10) }}</dd>
        </div>
        <div>
          <dt>NO₂</dt>
          <dd class="data-mono">{{ number(snapshot.model_analysis?.no2) }}</dd>
        </div>
        <div>
          <dt>O₃</dt>
          <dd class="data-mono">{{ number(snapshot.model_analysis?.o3) }}</dd>
        </div>
        <div>
          <dt>参考 EAQI</dt>
          <dd class="data-mono">{{ number(snapshot.model_analysis?.aqi, 0) }}</dd>
        </div>
      </dl>

      <div class="source-ledger">
        <div>
          <span>当前主源</span>
          <b>{{ primaryState.source }}</b>
        </div>
        <div>
          <span>源时间</span>
          <b class="data-mono">{{ time(primaryState.source_time) }}</b>
        </div>
        <div>
          <span>抓取时间</span>
          <b class="data-mono">{{ time(primaryState.fetched_at) }}</b>
        </div>
        <div>
          <span>质量</span>
          <b>{{ primaryState.quality_flag.toUpperCase() }}</b>
        </div>
      </div>

      <div
        v-if="snapshot.observation && !snapshot.observation.is_authoritative"
        class="observation-note"
      >
        <span>SENSOR OBSERVATION</span>
        <p>
          OpenAQ 提供的是传感器/站点观测，本站未将其标记为官方权威监测。
          CAMS 与观测并列展示，不互相替代。
        </p>
      </div>
      <div v-else-if="!snapshot.observation" class="observation-note">
        <span>GROUND OBSERVATION</span>
        <p>该城市暂无可用地面观测；当前主读数回退为 CAMS 模式估计。</p>
      </div>
    </template>

    <div class="watch-list">
      <div class="watch-heading">
        <span>城市切换</span>
        <span>{{ metricMeta[metric]?.label ?? metric.toUpperCase() }}</span>
      </div>
      <button
        v-for="location in [...locations]
          .sort((a, b) => (b.value ?? -1) - (a.value ?? -1))
          .slice(0, 7)"
        :key="location.location_id"
        type="button"
        class="watch-row"
        :class="{ active: location.location_id === selectedId }"
        :aria-pressed="location.location_id === selectedId"
        @click="emit('select', location.location_id, location.name)"
      >
        <span>{{ location.name }}</span>
        <strong class="data-mono">{{ number(location.value) }}</strong>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.readout-ledger {
  min-width: 0;
  height: 100%;
  background: var(--sheet);
  border-left: 1px solid var(--hairline);
  display: flex;
  flex-direction: column;
  overflow: auto;
}
.ledger-state {
  min-height: 220px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 12px;
  color: var(--muted);
  font-size: 12px;
}
.ledger-state p { margin: 0; }
.ledger-state button {
  min-height: 44px;
  padding: 0 16px;
  border: 1px solid var(--hairline-strong);
  border-radius: var(--radius);
  background: var(--sheet-strong);
  color: var(--ink);
  cursor: pointer;
}
.state-rule { width: 50px; height: 1px; background: var(--accent); }
.state-rule.error { background: var(--error); }
.ledger-heading {
  padding: 18px 20px 14px;
  display: flex;
  justify-content: space-between;
  gap: 14px;
  border-bottom: 1px solid var(--hairline);
}
.ledger-heading h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 620;
  letter-spacing: -.025em;
}
.coords { margin: 5px 0 0; font-size: 10px; color: var(--muted); }
.source-label {
  align-self: start;
  padding: 4px 6px;
  border: 1px solid var(--hairline-strong);
  border-radius: 3px;
  color: var(--muted);
  font-size: 10px;
  white-space: nowrap;
}
.hero-readout {
  padding: 18px 20px 20px;
  display: flex;
  align-items: flex-end;
  gap: 12px;
  border-bottom: 1px solid var(--hairline);
}
.hero-readout strong {
  font-size: 48px;
  line-height: .86;
  font-weight: 520;
  letter-spacing: -.04em;
}
.hero-readout div { display: grid; gap: 2px; }
.hero-readout b { font-size: 13px; }
.hero-readout span { color: var(--muted); font-size: 11px; }

.comparison-ledger {
  display: grid;
  grid-template-columns: 1fr 1fr;
  border-bottom: 1px solid var(--hairline);
}
.comparison-ledger > div {
  min-width: 0;
  padding: 12px 20px;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 4px 8px;
}
.comparison-ledger > div + div { border-left: 1px solid var(--hairline); }
.comparison-ledger span { color: var(--muted); font-size: 10px; }
.comparison-ledger b { font-size: 12px; font-weight: 600; }
.comparison-ledger small {
  grid-column: 1 / -1;
  overflow: hidden;
  color: var(--muted);
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pollutant-grid {
  margin: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  border-bottom: 1px solid var(--hairline);
}
.pollutant-grid div {
  padding: 12px 20px;
  display: flex;
  justify-content: space-between;
  border-right: 1px solid var(--hairline);
  border-bottom: 1px solid var(--hairline);
}
.pollutant-grid div:nth-child(even) { border-right: 0; }
.pollutant-grid div:nth-last-child(-n+2) { border-bottom: 0; }
.pollutant-grid dt { color: var(--muted); font-size: 11px; }
.pollutant-grid dd { margin: 0; font-size: 12px; }

.source-ledger { padding: 10px 20px; border-bottom: 1px solid var(--hairline); }
.source-ledger div {
  min-height: 28px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  font-size: 10px;
}
.source-ledger span { color: var(--muted); }
.source-ledger b {
  max-width: 170px;
  overflow: hidden;
  font-weight: 560;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.observation-note {
  padding: 13px 20px 15px;
  background: #f1f3ef;
  border-bottom: 1px solid var(--hairline);
}
.observation-note span {
  font: 600 9px/1 var(--mono);
  color: var(--warning);
  letter-spacing: .06em;
}
.observation-note p {
  margin: 7px 0 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.55;
}

.watch-list { margin-top: auto; }
.watch-heading,
.watch-row {
  min-height: 44px;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.watch-heading {
  color: var(--muted);
  font-size: 10px;
  border-bottom: 1px solid var(--hairline);
}
.watch-row {
  width: 100%;
  border: 0;
  border-bottom: 1px solid #e2e6e3;
  background: transparent;
  color: var(--ink);
  cursor: pointer;
  font-size: 11px;
  text-align: left;
}
.watch-row:hover { background: #f0f4f1; }
.watch-row:focus-visible { outline: 2px solid var(--accent); outline-offset: -3px; }
.watch-row.active { background: #e4ece9; }
.watch-row strong { font-weight: 560; }

@media (max-width: 520px) {
  .comparison-ledger { grid-template-columns: 1fr; }
  .comparison-ledger > div + div {
    border-left: 0;
    border-top: 1px solid var(--hairline);
  }
}
</style>
