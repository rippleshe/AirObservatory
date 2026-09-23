<script setup lang="ts">
import { useQuery } from "@tanstack/vue-query";
import { Database, HardDrive, Radio, RefreshCw } from "lucide-vue-next";
import { api } from "../api/client";
import { expectData } from "../api/request";

const status = useQuery({
  queryKey: ["system-status"],
  queryFn: () => expectData(api.GET("/api/status")),
  refetchInterval: 30_000,
});

const system = useQuery({
  queryKey: ["system-state"],
  queryFn: () =>
    expectData(
      api.GET("/api/system", {
        params: { query: { limit: 30 } },
      }),
    ),
  refetchInterval: 60_000,
});

function time(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function retry() {
  void Promise.all([status.refetch(), system.refetch()]);
}
</script>

<template>
  <section class="system-workspace">
    <header class="system-header">
      <div>
        <h1>系统与数据管线</h1>
        <p>
          这里展示的是实际 provider 状态、采集运行记录和城市站点绑定，不是静态状态牌。
        </p>
      </div>
      <button type="button" class="refresh-button" @click="retry">
        <RefreshCw :size="14" />
        刷新
      </button>
    </header>

    <div class="system-summary">
      <section class="provider-strip">
        <div
          v-for="(provider, name) in status.data.value?.providers ?? {}"
          :key="name"
          class="provider-state"
        >
          <Radio :size="15" />
          <div>
            <span>{{ name.toUpperCase() }}</span>
            <b :class="provider.state">{{ provider.state.toUpperCase() }}</b>
          </div>
          <time class="data-mono">{{ time(provider.latest_source_time) }}</time>
        </div>
      </section>

      <section class="storage-state">
        <HardDrive :size="17" />
        <div>
          <span>STORAGE</span>
          <b>{{ status.data.value?.storage ?? "—" }}</b>
        </div>
        <dl>
          <div>
            <dt>OBS</dt>
            <dd class="data-mono">{{ status.data.value?.counts.air_observations ?? 0 }}</dd>
          </div>
          <div>
            <dt>MODEL</dt>
            <dd class="data-mono">{{ status.data.value?.counts.air_model_analysis ?? 0 }}</dd>
          </div>
          <div>
            <dt>FCST</dt>
            <dd class="data-mono">{{ status.data.value?.counts.forecasts ?? 0 }}</dd>
          </div>
        </dl>
      </section>
    </div>

    <section class="system-panel">
      <header>
        <Database :size="15" />
        <div>
          <h2>Provider bindings</h2>
          <p>每个城市当前绑定的外部观测站点。</p>
        </div>
      </header>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>城市</th>
              <th>Provider</th>
              <th>站点</th>
              <th>External ID</th>
              <th>最新观测</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="binding in system.data.value?.bindings ?? []" :key="binding.location_id">
              <td>{{ binding.city }}</td>
              <td>{{ binding.provider }}</td>
              <td>{{ binding.station_name }}</td>
              <td class="data-mono">{{ binding.external_location_id }}</td>
              <td class="data-mono">{{ time(binding.last_at) }}</td>
              <td>
                <span :class="['binding-state', { active: binding.active }]">
                  {{ binding.active ? "ACTIVE" : "INACTIVE" }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="system-panel">
      <header>
        <RefreshCw :size="15" />
        <div>
          <h2>Ingestion runs</h2>
          <p>最近的采集任务、延迟与错误状态。</p>
        </div>
      </header>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Provider</th>
              <th>Dataset</th>
              <th>状态</th>
              <th>最新源时间</th>
              <th>耗时</th>
              <th>错误</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="run in system.data.value?.ingestions ?? []"
              :key="`${run.provider}-${run.dataset}-${run.started_at}`"
            >
              <td>{{ run.provider }}</td>
              <td>{{ run.dataset }}</td>
              <td><b :class="['run-state', run.status]">{{ run.status.toUpperCase() }}</b></td>
              <td class="data-mono">{{ time(run.latest_source_time) }}</td>
              <td class="data-mono">
                {{ run.latency_seconds == null ? "—" : run.latency_seconds.toFixed(2) + " s" }}
              </td>
              <td class="data-mono">{{ run.error_count }}</td>
              <td class="message-cell">{{ run.message ?? "—" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>

<style scoped>
.system-workspace {
  min-height: calc(100vh - 54px);
  padding: 28px;
  background: var(--canvas);
}
.system-header {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 20px;
}
.system-header h1 {
  margin: 0;
  font-size: clamp(26px, 3vw, 42px);
  font-weight: 560;
  letter-spacing: -.03em;
}
.system-header p {
  max-width: 700px;
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.65;
}
.refresh-button {
  min-height: 40px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 12px;
  border: 1px solid var(--hairline-strong);
  border-radius: var(--radius);
  background: var(--sheet);
  color: var(--ink);
  cursor: pointer;
}
.system-summary {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 16px;
  margin-bottom: 16px;
}
.provider-strip {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  border: 1px solid var(--hairline);
  background: var(--sheet);
}
.provider-state {
  min-height: 92px;
  display: grid;
  grid-template-columns: 24px 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 0 18px;
}
.provider-state + .provider-state { border-left: 1px solid var(--hairline); }
.provider-state div { display: grid; gap: 4px; }
.provider-state span { color: var(--muted); font: 600 9px/1 var(--mono); letter-spacing: .08em; }
.provider-state b { font-size: 12px; }
.provider-state b.healthy { color: var(--ok); }
.provider-state b.stale,
.provider-state b.error { color: var(--warning); }
.provider-state time { color: var(--muted); font-size: 9px; }
.storage-state {
  min-height: 92px;
  display: grid;
  grid-template-columns: 24px 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 0 18px;
  border: 1px solid var(--hairline);
  background: var(--sheet);
}
.storage-state > div { display: grid; gap: 4px; }
.storage-state span { color: var(--muted); font: 600 9px/1 var(--mono); letter-spacing: .08em; }
.storage-state b { font-size: 12px; }
.storage-state dl { display: flex; gap: 16px; margin: 0; }
.storage-state dl div { display: grid; gap: 4px; text-align: right; }
.storage-state dt { color: var(--muted); font-size: 8px; }
.storage-state dd { margin: 0; font-size: 11px; }
.system-panel {
  margin-top: 16px;
  border: 1px solid var(--hairline);
  background: var(--sheet);
}
.system-panel > header {
  min-height: 62px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  border-bottom: 1px solid var(--hairline);
}
.system-panel h2 { margin: 0; font-size: 13px; font-weight: 620; }
.system-panel p { margin: 3px 0 0; color: var(--muted); font-size: 10px; }
.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 10px; }
th, td { padding: 11px 14px; border-bottom: 1px solid var(--hairline); text-align: left; vertical-align: top; }
th { color: var(--muted); font-size: 9px; font-weight: 600; }
.binding-state,
.run-state {
  font: 600 9px/1 var(--mono);
  color: var(--muted);
}
.binding-state.active,
.run-state.success { color: var(--ok); }
.run-state.partial { color: var(--warning); }
.run-state.error { color: var(--error); }
.message-cell { min-width: 300px; max-width: 560px; color: var(--muted); line-height: 1.45; }
@media (max-width: 980px) {
  .system-summary { grid-template-columns: 1fr; }
}
@media (max-width: 700px) {
  .system-workspace { padding: 18px 12px; }
  .provider-strip { grid-template-columns: 1fr; }
  .provider-state + .provider-state { border-left: 0; border-top: 1px solid var(--hairline); }
}
</style>
