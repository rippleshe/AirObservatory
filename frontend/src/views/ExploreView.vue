<script setup lang="ts">
import { computed, ref } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { BarChart3, Clock3, Database, RotateCw } from "lucide-vue-next";
import { api } from "../api/client";
import { expectData } from "../api/request";
import SeriesCompareChart from "../components/SeriesCompareChart.vue";
import { useContextStore } from "../stores/context";

const context = useContextStore();
const hours = ref(168);

const model = useQuery({
  queryKey: computed(() => [
    "explore-model",
    context.selectedLocationId,
    context.selectedMetric,
    hours.value,
  ]),
  enabled: computed(() => context.selectedLocationId != null),
  queryFn: () =>
    expectData(
      api.GET("/api/locations/{location_id}/series", {
        params: {
          path: { location_id: context.selectedLocationId! },
          query: {
            variable: context.selectedMetric,
            data_kind: "model_analysis",
            hours: hours.value,
          },
        },
      }),
    ),
});

const observation = useQuery({
  queryKey: computed(() => [
    "explore-observation",
    context.selectedLocationId,
    context.selectedMetric,
    hours.value,
  ]),
  enabled: computed(() => context.selectedLocationId != null),
  queryFn: () =>
    expectData(
      api.GET("/api/locations/{location_id}/series", {
        params: {
          path: { location_id: context.selectedLocationId! },
          query: {
            variable: context.selectedMetric,
            data_kind: "observation",
            hours: hours.value,
          },
        },
      }),
    ),
});

const paired = computed(() => {
  const modelByTime = new Map(
    (model.data.value?.points ?? [])
      .filter((point) => point.value != null)
      .map((point) => [new Date(point.time).getTime(), Number(point.value)]),
  );
  return (observation.data.value?.points ?? [])
    .filter((point) => point.value != null)
    .map((point) => {
      const time = new Date(point.time).getTime();
      const modelValue = modelByTime.get(time);
      return modelValue == null
        ? null
        : { observation: Number(point.value), model: modelValue };
    })
    .filter((item): item is { observation: number; model: number } => item != null);
});

const stats = computed(() => {
  const pairs = paired.value;
  if (!pairs.length) {
    return {
      paired: 0,
      bias: null as number | null,
      mae: null as number | null,
      rmse: null as number | null,
    };
  }
  const errors = pairs.map((item) => item.model - item.observation);
  return {
    paired: pairs.length,
    bias: errors.reduce((sum, value) => sum + value, 0) / errors.length,
    mae: errors.reduce((sum, value) => sum + Math.abs(value), 0) / errors.length,
    rmse: Math.sqrt(
      errors.reduce((sum, value) => sum + value * value, 0) / errors.length,
    ),
  };
});

const coverage = computed(() => {
  const modelCount = model.data.value?.points.length ?? 0;
  const observationCount = observation.data.value?.points.length ?? 0;
  return modelCount ? Math.min(1, observationCount / modelCount) : 0;
});

function fmt(value: number | null, digits = 1) {
  return value == null || !Number.isFinite(value) ? "—" : value.toFixed(digits);
}

function retry() {
  void Promise.all([model.refetch(), observation.refetch()]);
}
</script>

<template>
  <section class="analysis-workspace">
    <header class="workbench-header">
      <div>
        <h1>观测与模式对照</h1>
        <p>
          只比较同一小时的真实观测与 CAMS 模式值；缺测不会被插值成“看起来完整”的曲线。
        </p>
      </div>
      <div class="workbench-controls">
        <label>
          <span>指标</span>
          <select v-model="context.selectedMetric">
            <option value="pm25">PM2.5</option>
            <option value="pm10">PM10</option>
            <option value="no2">NO₂</option>
            <option value="o3">O₃</option>
          </select>
        </label>
        <label>
          <span>窗口</span>
          <select v-model.number="hours">
            <option :value="24">24 小时</option>
            <option :value="48">48 小时</option>
            <option :value="168">7 天</option>
            <option :value="720">30 天</option>
          </select>
        </label>
      </div>
    </header>

    <div v-if="model.isError.value || observation.isError.value" class="workbench-alert">
      <RotateCw :size="16" />
      <span>分析数据加载失败，未用本地假数据替代。</span>
      <button type="button" @click="retry">重试</button>
    </div>

    <div class="analysis-grid">
      <section class="analysis-chart-panel">
        <div class="section-heading">
          <div>
            <span>TIME SERIES</span>
            <h2>{{ context.selectedCityName }} · {{ context.selectedMetric.toUpperCase() }}</h2>
          </div>
          <div class="source-key">
            <span><i class="obs"></i>OpenAQ</span>
            <span><i class="model"></i>CAMS</span>
          </div>
        </div>
        <SeriesCompareChart
          :model="model.data.value"
          :observation="observation.data.value"
        />
      </section>

      <aside class="analysis-ledger">
        <div class="ledger-row">
          <BarChart3 :size="15" />
          <span>同小时配对</span>
          <strong class="data-mono">{{ stats.paired }}</strong>
        </div>
        <div class="ledger-row">
          <Clock3 :size="15" />
          <span>观测覆盖</span>
          <strong class="data-mono">{{ (coverage * 100).toFixed(0) }}%</strong>
        </div>
        <div class="metric-block">
          <span>平均偏差 · CAMS − OpenAQ</span>
          <strong class="data-mono">{{ fmt(stats.bias) }}</strong>
          <small>正值表示模式值整体偏高</small>
        </div>
        <div class="metric-block">
          <span>MAE</span>
          <strong class="data-mono">{{ fmt(stats.mae) }}</strong>
          <small>同小时绝对误差均值</small>
        </div>
        <div class="metric-block">
          <span>RMSE</span>
          <strong class="data-mono">{{ fmt(stats.rmse) }}</strong>
          <small>对较大误差更敏感</small>
        </div>
        <div class="provenance-note">
          <Database :size="14" />
          <p>
            分析直接读取后端序列。OpenAQ 站点来源、时间与质量标记均保留；
            CAMS 仍作为模式场单独展示。
          </p>
        </div>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.analysis-workspace {
  min-height: calc(100vh - 54px);
  padding: 28px;
  background: var(--canvas);
}
.workbench-header {
  display: flex;
  justify-content: space-between;
  gap: 28px;
  margin-bottom: 20px;
}
.workbench-header h1 {
  margin: 0;
  font-size: clamp(26px, 3vw, 42px);
  font-weight: 560;
  letter-spacing: -.03em;
}
.workbench-header p {
  max-width: 720px;
  margin: 10px 0 0;
  color: var(--muted);
  line-height: 1.65;
  font-size: 13px;
}
.workbench-controls { display: flex; align-items: end; gap: 10px; }
.workbench-controls label { display: grid; gap: 5px; color: var(--muted); font-size: 10px; }
.workbench-controls select {
  min-width: 112px;
  min-height: 40px;
  border: 1px solid var(--hairline-strong);
  border-radius: var(--radius);
  background: var(--sheet);
  color: var(--ink);
  padding: 0 10px;
}
.workbench-alert {
  min-height: 46px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 14px;
  border: 1px solid #d8b7b2;
  background: #f6ece9;
  color: var(--error);
  font-size: 12px;
}
.workbench-alert button {
  margin-left: auto;
  min-height: 34px;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-weight: 650;
}
.analysis-grid {
  min-height: 590px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 290px;
  border: 1px solid var(--hairline);
  background: var(--sheet);
}
.analysis-chart-panel { min-width: 0; padding: 18px; }
.section-heading {
  min-height: 52px;
  display: flex;
  justify-content: space-between;
  align-items: start;
  gap: 20px;
}
.section-heading span { color: var(--muted); font: 600 9px/1 var(--mono); letter-spacing: .08em; }
.section-heading h2 { margin: 6px 0 0; font-size: 15px; font-weight: 620; }
.source-key { display: flex; gap: 14px; padding-top: 4px; }
.source-key span { display: flex; align-items: center; gap: 6px; font-family: inherit; letter-spacing: 0; }
.source-key i { width: 18px; border-top: 2px solid var(--model); }
.source-key i.obs { border-top-color: var(--ok); }
.analysis-ledger { border-left: 1px solid var(--hairline); }
.ledger-row {
  min-height: 48px;
  display: grid;
  grid-template-columns: 22px 1fr auto;
  align-items: center;
  gap: 8px;
  padding: 0 16px;
  border-bottom: 1px solid var(--hairline);
  color: var(--muted);
  font-size: 11px;
}
.ledger-row strong { color: var(--ink); font-weight: 600; }
.metric-block {
  padding: 18px 16px;
  display: grid;
  gap: 5px;
  border-bottom: 1px solid var(--hairline);
}
.metric-block span { color: var(--muted); font-size: 10px; }
.metric-block strong { font-size: 28px; font-weight: 520; letter-spacing: -.03em; }
.metric-block small { color: var(--muted); font-size: 9px; }
.provenance-note {
  display: flex;
  gap: 9px;
  padding: 16px;
  color: var(--muted);
}
.provenance-note p { margin: 0; font-size: 10px; line-height: 1.55; }
@media (max-width: 980px) {
  .analysis-grid { grid-template-columns: 1fr; }
  .analysis-ledger { border-left: 0; border-top: 1px solid var(--hairline); }
}
@media (max-width: 700px) {
  .analysis-workspace { padding: 18px 12px; }
  .workbench-header { display: grid; }
  .workbench-controls { align-items: stretch; }
}
</style>
