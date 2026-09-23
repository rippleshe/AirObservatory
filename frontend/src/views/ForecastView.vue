<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { Activity, CheckCircle2, Database, TriangleAlert } from "lucide-vue-next";
import { api } from "../api/client";
import { expectData } from "../api/request";
import ForecastComparisonChart from "../components/ForecastComparisonChart.vue";
import { useContextStore } from "../stores/context";

const context = useContextStore();

onMounted(() => {
  context.selectedMetric = "pm25";
});

const forecast = useQuery({
  queryKey: computed(() => ["forecast-workbench", context.selectedLocationId]),
  enabled: computed(() => context.selectedLocationId != null),
  queryFn: () =>
    expectData(
      api.GET("/api/locations/{location_id}/forecast", {
        params: {
          path: { location_id: context.selectedLocationId! },
          query: { variable: "pm25" },
        },
      }),
    ),
});

const observations = useQuery({
  queryKey: computed(() => ["forecast-observations", context.selectedLocationId]),
  enabled: computed(() => context.selectedLocationId != null),
  queryFn: () =>
    expectData(
      api.GET("/api/locations/{location_id}/series", {
        params: {
          path: { location_id: context.selectedLocationId! },
          query: {
            variable: "pm25",
            data_kind: "observation",
            hours: 48,
          },
        },
      }),
    ),
});

const readiness = useQuery({
  queryKey: computed(() => ["readiness", context.selectedLocationId]),
  enabled: computed(() => context.selectedLocationId != null),
  queryFn: () =>
    expectData(
      api.GET("/api/models/{location_id}/readiness", {
        params: { path: { location_id: context.selectedLocationId! } },
      }),
    ),
});

const metrics = useQuery({
  queryKey: computed(() => ["model-metrics", context.selectedLocationId]),
  enabled: computed(() => context.selectedLocationId != null),
  queryFn: () =>
    expectData(
      api.GET("/api/models/{location_id}/metrics", {
        params: { path: { location_id: context.selectedLocationId! } },
      }),
    ),
});

function time(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function retry() {
  void Promise.all([
    forecast.refetch(),
    observations.refetch(),
    readiness.refetch(),
    metrics.refetch(),
  ]);
}
</script>

<template>
  <section class="forecast-workspace">
    <header class="forecast-header">
      <div>
        <h1>预测与基线</h1>
        <p>
          CAMS 外部预测与基于真实观测生成的 Persistence、Rolling Mean 基线同屏展示。
          没有足够历史样本时，不会伪装成“训练完成”。
        </p>
      </div>
      <div
        v-if="readiness.data.value"
        :class="['readiness-chip', { ready: readiness.data.value.ready }]"
      >
        <CheckCircle2 v-if="readiness.data.value.ready" :size="15" />
        <TriangleAlert v-else :size="15" />
        <span>
          {{ readiness.data.value.ready ? "训练数据就绪" : "训练数据不足" }}
        </span>
      </div>
    </header>

    <div
      v-if="forecast.isError.value || readiness.isError.value || metrics.isError.value"
      class="forecast-error"
    >
      <span>预测工作台数据加载失败。</span>
      <button type="button" @click="retry">重试</button>
    </div>

    <div class="forecast-layout">
      <section class="forecast-chart-panel">
        <div class="panel-title">
          <div>
            <span>PM2.5 · {{ context.selectedCityName }}</span>
            <h2>48 小时观测 + 最新预测快照</h2>
          </div>
          <Activity :size="18" />
        </div>
        <ForecastComparisonChart
          :forecast="forecast.data.value"
          :observations="observations.data.value"
        />
      </section>

      <aside class="forecast-side">
        <section class="readiness-panel" v-if="readiness.data.value">
          <div class="mini-title">DATA READINESS</div>
          <strong class="data-mono">
            {{ (readiness.data.value.completeness * 100).toFixed(1) }}%
          </strong>
          <p>
            {{ readiness.data.value.observation_rows }} 条 PM2.5 观测 ·
            {{ (readiness.data.value.span_hours / 24).toFixed(1) }} 天跨度
          </p>
          <ul v-if="readiness.data.value.reasons.length">
            <li v-for="reason in readiness.data.value.reasons" :key="reason">
              {{ reason }}
            </li>
          </ul>
        </section>

        <section class="model-snapshots">
          <div class="mini-title">ACTIVE SNAPSHOTS</div>
          <div
            v-for="series in forecast.data.value?.series ?? []"
            :key="`${series.model_name}-${series.snapshot_at}`"
            class="snapshot-row"
          >
            <div>
              <b>{{ series.model_name }}</b>
              <span>{{ series.source }}</span>
            </div>
            <time class="data-mono">{{ time(series.snapshot_at) }}</time>
          </div>
          <div v-if="!(forecast.data.value?.series.length)" class="empty-copy">
            暂无可用预测快照。
          </div>
        </section>
      </aside>
    </div>

    <section class="metrics-panel">
      <div class="metrics-heading">
        <div>
          <Database :size="15" />
          <div>
            <h2>已实现预测误差</h2>
            <p>只统计已有真实观测能够对齐的历史预测点。</p>
          </div>
        </div>
      </div>
      <div class="metrics-table-wrap">
        <table class="metrics-table">
          <thead>
            <tr>
              <th>模型</th>
              <th>预测步长</th>
              <th>样本</th>
              <th>MAE</th>
              <th>RMSE</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in metrics.data.value?.metrics ?? []"
              :key="`${row.model_name}-${row.horizon_hours}`"
            >
              <td>{{ row.model_name }}</td>
              <td class="data-mono">{{ row.horizon_hours }} h</td>
              <td class="data-mono">{{ row.samples }}</td>
              <td class="data-mono">{{ row.mae.toFixed(2) }}</td>
              <td class="data-mono">{{ row.rmse.toFixed(2) }}</td>
            </tr>
            <tr v-if="!(metrics.data.value?.metrics.length)">
              <td colspan="5" class="empty-cell">
                预测尚未到达足够的验证时间点，暂不输出误差结论。
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>

<style scoped>
.forecast-workspace {
  min-height: calc(100vh - 54px);
  padding: 28px;
  background: var(--canvas);
}
.forecast-header {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 20px;
}
.forecast-header h1 {
  margin: 0;
  font-size: clamp(26px, 3vw, 42px);
  font-weight: 560;
  letter-spacing: -.03em;
}
.forecast-header p {
  max-width: 760px;
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.65;
}
.readiness-chip {
  min-height: 38px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 11px;
  border: 1px solid #d7b789;
  background: #f5eee4;
  color: var(--warning);
  font-size: 11px;
  white-space: nowrap;
}
.readiness-chip.ready {
  border-color: #b8d1c7;
  background: #eaf2ee;
  color: var(--ok);
}
.forecast-error {
  min-height: 44px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 14px;
  border: 1px solid #d8b7b2;
  background: #f6ece9;
  color: var(--error);
  font-size: 12px;
}
.forecast-error button {
  margin-left: auto;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-weight: 650;
}
.forecast-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 310px;
  border: 1px solid var(--hairline);
  background: var(--sheet);
}
.forecast-chart-panel { min-width: 0; padding: 18px; }
.panel-title {
  min-height: 54px;
  display: flex;
  justify-content: space-between;
  align-items: start;
  color: var(--muted);
}
.panel-title span { font-size: 10px; }
.panel-title h2 { margin: 5px 0 0; color: var(--ink); font-size: 15px; font-weight: 620; }
.forecast-side { border-left: 1px solid var(--hairline); }
.readiness-panel,
.model-snapshots { padding: 18px; border-bottom: 1px solid var(--hairline); }
.mini-title {
  margin-bottom: 12px;
  color: var(--muted);
  font: 600 9px/1 var(--mono);
  letter-spacing: .08em;
}
.readiness-panel strong {
  display: block;
  font-size: 34px;
  font-weight: 520;
  letter-spacing: -.04em;
}
.readiness-panel p {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 10px;
  line-height: 1.5;
}
.readiness-panel ul {
  margin: 12px 0 0;
  padding-left: 16px;
  color: var(--warning);
  font-size: 10px;
  line-height: 1.5;
}
.snapshot-row {
  min-height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-top: 1px solid var(--hairline);
}
.snapshot-row div { display: grid; gap: 3px; }
.snapshot-row b { font-size: 11px; }
.snapshot-row span,
.snapshot-row time { color: var(--muted); font-size: 9px; }
.empty-copy { color: var(--muted); font-size: 11px; line-height: 1.5; }
.metrics-panel {
  margin-top: 18px;
  border: 1px solid var(--hairline);
  background: var(--sheet);
}
.metrics-heading {
  min-height: 60px;
  padding: 0 16px;
  display: flex;
  align-items: center;
  border-bottom: 1px solid var(--hairline);
}
.metrics-heading > div { display: flex; align-items: center; gap: 10px; }
.metrics-heading h2 { margin: 0; font-size: 13px; font-weight: 620; }
.metrics-heading p { margin: 3px 0 0; color: var(--muted); font-size: 10px; }
.metrics-table-wrap { overflow-x: auto; }
.metrics-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.metrics-table th,
.metrics-table td {
  padding: 12px 16px;
  border-bottom: 1px solid var(--hairline);
  text-align: left;
}
.metrics-table th { color: var(--muted); font-size: 9px; font-weight: 600; }
.empty-cell { color: var(--muted); text-align: center !important; padding: 22px !important; }
@media (max-width: 980px) {
  .forecast-layout { grid-template-columns: 1fr; }
  .forecast-side { border-left: 0; border-top: 1px solid var(--hairline); }
}
@media (max-width: 700px) {
  .forecast-workspace { padding: 18px 12px; }
  .forecast-header { display: grid; }
}
</style>
