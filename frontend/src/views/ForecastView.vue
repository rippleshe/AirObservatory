<script setup lang="ts">
import { computed, ref } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { api } from "../api/client";
import { expectData } from "../api/request";
import { useLocationCatalog } from "../composables/useLocationCatalog";
import ForecastTrajectory from "../components/ForecastTrajectory.vue";
import BacktestAnatomy from "../components/BacktestAnatomy.vue";
import { useContextStore } from "../stores/context";

const context = useContextStore();
const { locations } = useLocationCatalog();
const cityId = computed(() => context.selectedLocationId ?? locations.data.value?.[0]?.location_id ?? 1);
const city = computed(() => locations.data.value?.find((row) => row.location_id === cityId.value)?.city ?? "当前城市");
const forecast = useQuery({
  queryKey: computed(() => ["research-forecast", cityId.value]),
  queryFn: () => expectData(api.GET("/api/locations/{location_id}/forecast", {
    params: { path: { location_id: cityId.value }, query: { variable: "pm25" } },
  })),
  refetchInterval: 5 * 60_000,
});
const history = useQuery({
  queryKey: computed(() => ["research-forecast-history", cityId.value]),
  queryFn: () => expectData(api.GET("/api/locations/{location_id}/series", {
    params: { path: { location_id: cityId.value }, query: { variable: "pm25", data_kind: "model_analysis", hours: 168 } },
  })),
});
const observation = useQuery({
  queryKey: computed(() => ["research-forecast-observation", cityId.value]),
  queryFn: () => expectData(api.GET("/api/locations/{location_id}/series", {
    params: { path: { location_id: cityId.value }, query: { variable: "pm25", data_kind: "observation", hours: 168 } },
  })),
  retry: false,
});
const backtest = useQuery({
  queryKey: computed(() => ["research-backtest", cityId.value]),
  queryFn: () => expectData(api.GET("/api/locations/{location_id}/backtest", {
    params: { path: { location_id: cityId.value } },
  })),
});
const readiness = useQuery({
  queryKey: computed(() => ["research-training-readiness", cityId.value]),
  queryFn: () => expectData(api.GET("/api/models/{location_id}/readiness", {
    params: { path: { location_id: cityId.value } },
  })),
  retry: false,
});
const validation = useQuery({
  queryKey: ["research-model-validation"],
  queryFn: () => expectData(api.GET("/api/models/validation")),
  staleTime: 30 * 60_000,
  retry: false,
});
const chosenModels = ref<string[]>(["CAMS", "LSTM", "Persistence", "Rolling Mean"]);
const latestForecast = computed(() => {
  const data = forecast.data.value;
  if (!data) return undefined;
  const latest = new Map<string, (typeof data.series)[number]>();
  for (const row of data.series) {
    const previous = latest.get(row.model_name);
    if (!previous || +new Date(row.snapshot_at) > +new Date(previous.snapshot_at)) {
      latest.set(row.model_name, row);
    }
  }
  return { ...data, series: [...latest.values()] };
});
const availableModels = computed(() => latestForecast.value?.series.map((row) => row.model_name) ?? []);
const modelRows = computed(() => (latestForecast.value?.series ?? []).filter((row) => chosenModels.value.includes(row.model_name)));
const errorRows = computed(() => {
  return (validation.data.value?.models ?? []).map((model) => ({
    name: model.model_name,
    points: Array.from({ length: 24 }, (_, i) => i < model.mae.length
      ? { mae: model.mae[i]!, rmse: model.rmse[i]!, samples: model.samples }
      : null),
  }));
});
const selectedMetric = ref<"mae" | "rmse">("mae");
const maxError = computed(() => Math.max(1, ...errorRows.value.flatMap((row) => row.points.map((point) => point?.[selectedMetric.value] ?? 0))));
const fmtTime = (time: string) => new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit", hour: "2-digit",
  minute: "2-digit", hour12: false,
}).format(new Date(time));

function toggleModel(name: string) {
  if (chosenModels.value.includes(name)) chosenModels.value = chosenModels.value.filter((row) => row !== name);
  else chosenModels.value = [...chosenModels.value, name];
}
</script>

<template>
  <section class="research-view forecast-workspace">
    <header class="research-head">
      <div>
        <h1>短期预测与模型评估</h1>
        <p>{{ city }} · PM2.5 · 历史分析、未来 24h 预测与回测验证</p>
      </div>
      <div class="research-side">
        <span>预测模型 <b>{{ availableModels.length }}</b></span>
        <span>验证样本 <b>{{ validation.data.value?.models[0]?.samples ?? "—" }}</b></span>
      </div>
    </header>

    <section class="research-section">
      <div class="research-section-head">
        <h2>历史演变与多模型预测</h2>
        <span>模型起报时刻与目标时间以原始记录为准</span>
      </div>
      <div class="research-panel">
        <div class="forecast-model-controls" role="group" aria-label="显示预测模型">
          <button v-for="name in availableModels" :key="name" type="button"
            :class="{ active: chosenModels.includes(name) }"
            :aria-pressed="chosenModels.includes(name)" @click="toggleModel(name)">
            <span class="model-dot" aria-hidden="true"></span>{{ name }}
          </button>
        </div>
        <ForecastTrajectory :history="history.data.value" :observation="observation.data.value"
          :forecast="latestForecast" :active-models="chosenModels" />
        <div v-if="modelRows.length" class="forecast-issues">
          <span v-for="row in modelRows" :key="row.model_name" class="data-mono">
            <strong>{{ row.model_name }}</strong>
            {{ fmtTime(row.snapshot_at) }} 起报 · {{ row.points.length }}h · {{ row.model_revision }}
          </span>
        </div>
      </div>
      <div class="research-evidence">
        <span>历史分析：CAMS 模式分析场</span>
        <span>地面观测：OpenAQ（缺失处不连接曲线）</span>
        <span>LSTM 监督目标：CAMS 分析场，不能等同于地面实测预测精度</span>
      </div>
    </section>

    <section class="research-section">
      <div class="research-section-head">
        <h2>CAMS 验证集上的预测误差</h2>
        <div class="research-tabs" role="group" aria-label="误差指标">
          <button :class="{ active: selectedMetric === 'mae' }" :aria-pressed="selectedMetric === 'mae'" @click="selectedMetric = 'mae'">MAE</button>
          <button :class="{ active: selectedMetric === 'rmse' }" :aria-pressed="selectedMetric === 'rmse'" @click="selectedMetric = 'rmse'">RMSE</button>
        </div>
      </div>
      <div v-if="validation.data.value" class="research-evidence">
        <span>同一验证集 <strong>{{ validation.data.value.models[0]?.samples ?? 0 }}</strong> 个窗口</span>
        <span>验证时段 <strong>{{ fmtTime(validation.data.value.validation_start) }} — {{ fmtTime(validation.data.value.validation_end) }}</strong></span>
        <span>模型版本 <strong>{{ validation.data.value.model_version }}</strong></span>
      </div>
      <div v-if="errorRows.length" class="research-panel research-panel-pad">
        <div class="error-grid" role="table" :aria-label="selectedMetric.toUpperCase() + ' 预测时效误差矩阵'">
          <div class="error-label axis-label">模型 / 时效</div>
          <div v-for="h in 24" :key="'axis'+h" class="error-hour data-mono">{{ h % 3 === 0 || h === 1 ? h : '' }}</div>
          <template v-for="row in errorRows" :key="row.name">
            <div class="error-label">{{ row.name }}</div>
            <div v-for="(point, index) in row.points" :key="row.name + index" class="error-cell"
              :class="{ missing: !point }"
              :style="point ? { '--heat': Math.round(Math.min(90, (point[selectedMetric] / maxError) * 77 + 9)) + '%' } : undefined"
              :title="point ? row.name + ' · +' + (index + 1) + 'h · ' + selectedMetric.toUpperCase() + ' ' + point[selectedMetric].toFixed(2) + ' µg/m³ · N=' + point.samples : row.name + ' · +' + (index + 1) + 'h · 暂无回测'"
            ></div>
          </template>
        </div>
        <div class="error-scale"><span>低误差</span><i></i><span>高误差</span><span>空白：无核验样本</span></div>
        <div class="research-table-scroll">
          <table class="research-data-table">
            <thead><tr><th>模型</th><th class="num">+24h MAE</th><th class="num">+24h RMSE</th><th class="num">有效样本</th></tr></thead>
            <tbody>
              <tr v-for="row in errorRows" :key="row.name">
                <td>{{ row.name }}</td>
                <td class="num">{{ row.points[23]?.mae.toFixed(2) ?? "—" }}</td>
                <td class="num">{{ row.points[23]?.rmse.toFixed(2) ?? "—" }}</td>
                <td class="num">{{ row.points[23]?.samples ?? "—" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div v-else class="research-panel research-empty" role="status">
        <strong>尚无足够的历史核验记录</strong>
        <small>模型验证集结果尚未入库，不能推测 LSTM 与基线的误差大小。</small>
      </div>
    </section>

    <section class="research-section">
      <div class="research-section-head">
        <h2>上线预测的后验回测</h2>
        <span>当前 {{ backtest.data.value?.samples.length ?? 0 }} 条核验样本 · 与上方 CAMS 验证集不同</span>
      </div>
      <div v-if="(backtest.data.value?.samples.length ?? 0) >= 30" class="research-panel research-panel-pad">
        <BacktestAnatomy :backtest="backtest.data.value" />
      </div>
      <div v-else class="research-evidence">
        <span>运行中的预测需要等待目标时刻到达，且完成有效数据核验；样本不足时不绘制误差趋势。</span>
      </div>
      <div class="research-evidence">
        <span>地面观测训练条件：<strong>{{ readiness.data.value?.ready ? "满足" : "未满足或待核验" }}</strong></span>
        <span v-if="readiness.data.value">有效观测行数 <strong>{{ readiness.data.value.observation_rows }}</strong></span>
        <span>只有相同验证目标、时间窗和样本集合上的指标才适合直接排名。</span>
      </div>
    </section>
  </section>
</template>

<style scoped>
.forecast-model-controls { display: flex; flex-wrap: wrap; gap: 8px; padding: 18px 24px 0; }
.forecast-model-controls button {
  display: inline-flex; gap: 9px; align-items: center;
  border: 1px solid var(--hairline); border-radius: var(--radius-sm);
  background: var(--sheet); color: var(--ink-secondary); padding: 8px 12px;
  font-size: 12px; font-weight: 600; cursor: pointer;
}
.forecast-model-controls button.active { background: var(--canvas-subtle); border-color: var(--hairline-strong); color: var(--ink); }
.model-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--faint); }
.forecast-model-controls button.active .model-dot { background: var(--accent); }
.forecast-issues { display: flex; flex-wrap: wrap; gap: 10px 26px; padding: 13px 24px 18px; border-top: 1px solid var(--hairline-soft); color: var(--muted); font-size: 11px; overflow-wrap: anywhere; }
.forecast-issues strong { color: var(--ink-soft); margin-right: 5px; }
.error-grid { display: grid; grid-template-columns: 114px repeat(24,minmax(0,1fr)); gap: 4px; align-items: center; min-width: 630px; }
.error-label { white-space: nowrap; font-size: 12px; font-weight: 650; color: var(--ink-secondary); padding-right: 7px; }
.error-hour { color: var(--muted); font-size: 10px; text-align: center; }
.error-cell { height: 29px; background: color-mix(in srgb, var(--accent) var(--heat, 0%), var(--sheet)); border-radius: 3px; }
.error-cell.missing { background: var(--canvas-subtle); }
.error-scale { display: flex; gap: 12px; align-items: center; color: var(--muted); font-size: 11px; padding: 16px 0 22px; }
.error-scale i { width: 112px; height: 7px; border-radius: 3px; background: linear-gradient(to right,var(--sheet),var(--accent)); border: 1px solid var(--hairline); }
.error-scale span:last-child { margin-left: auto; }
.research-panel-pad { overflow-x: auto; }
@media(max-width: 850px) {
  .error-grid { min-width: 630px; }
  .forecast-model-controls { padding: 14px 12px 0; }
  .forecast-issues { padding: 12px; }
}
</style>
