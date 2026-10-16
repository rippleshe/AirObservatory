<script setup lang="ts">
import { computed, ref } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { api } from "../../api/client";
import { expectData } from "../../api/request";
import { useLocations } from "../../composables/useLocations";
import CityFingerprintPanel from "./components/CityFingerprintPanel.vue";
import PCAStructurePanel from "./components/PCAStructurePanel.vue";
import WindClearance from "../../shared/WindClearance.vue";
import WindRose from "./components/WindRose.vue";
import { useContextStore } from "../../stores/context";

const context = useContextStore();
const { data: locations } = useLocations();
const scope = ref<"national" | "city">("national");
/* Which city the fingerprint panel highlights — page-local, like every other
   page's focus, so nothing outside this page can move it. */
const focusId = ref<number | null>(null);
const cityId = computed(() => context.selectedLocationId ?? locations.value?.[0]?.location_id ?? 1);
const cityName = computed(() => locations.value?.find((row) => row.location_id === cityId.value)?.city ?? "当前城市");

const fingerprint = useQuery({
  queryKey: ["analysis", "fingerprint"],
  queryFn: () => expectData(api.GET("/api/analysis/city-fingerprint")),
  staleTime: 30 * 60_000,
  retry: false,
});
const structure = useQuery({
  queryKey: computed(() => ["analysis", "structure", cityId.value]),
  queryFn: () => expectData(api.GET("/api/locations/{location_id}/structure", {
    params: { path: { location_id: cityId.value } },
  })),
  enabled: computed(() => scope.value === "city"),
  retry: false,
});
const pmSeries = useQuery({
  queryKey: computed(() => ["analysis", "pm25", cityId.value]),
  queryFn: () => expectData(api.GET("/api/locations/{location_id}/series", {
    params: { path: { location_id: cityId.value }, query: { variable: "pm25", data_kind: "model_analysis", hours: 720 } },
  })),
  enabled: computed(() => scope.value === "city"),
});
const weather = useQuery({
  queryKey: computed(() => ["analysis", "weather", cityId.value]),
  queryFn: () => expectData(api.GET("/api/overview/national/weather", {
    params: { query: { hours: 720, location_id: cityId.value } },
  })),
  enabled: computed(() => scope.value === "city"),
});

const matched = computed(() => {
  const row = weather.data.value?.cities[0];
  if (!row) return [];
  const pm = new Map((pmSeries.data.value?.points ?? [])
    .filter((point) => point.value != null)
    .map((point) => [+new Date(point.time), Number(point.value)]));
  return weather.data.value!.times.flatMap((time, i) => {
    const speed = row.wind_speed[i];
    const dir = row.wind_direction[i];
    const pm25 = pm.get(+new Date(time));
    return speed != null && dir != null && pm25 != null
      ? [{ time, wind: speed, speed, dir, pm25 }]
      : [];
  });
});
const matchedWindow = computed(() => {
  const rows = matched.value;
  return rows.length ? `${fmt(rows[0]?.time)} — ${fmt(rows[rows.length - 1]?.time)}` : "—";
});
const fingerprintMeta = computed(() => fingerprint.data.value?.meta);
const structureMeta = computed(() => structure.data.value?.meta);
const fmt = (time: string | undefined) => time ? time.slice(0, 10) : "—";

function focusCity(id: number, name: string) {
  context.selectLocation(id, name);
  focusId.value = id;
  scope.value = "city";
}
</script>

<template>
  <section class="research-view analysis-workspace">
    <header class="research-head">
      <div>
        <h1>多变量关联分析</h1>
        <p>城市特征、污染物与气象条件的统计关系</p>
      </div>
      <div class="research-tabs" role="group" aria-label="分析尺度">
        <button type="button" :class="{ active: scope === 'national' }" :aria-pressed="scope === 'national'" @click="scope = 'national'">全国城市结构</button>
        <button type="button" :class="{ active: scope === 'city' }" :aria-pressed="scope === 'city'" @click="scope = 'city'">单城市关联</button>
      </div>
    </header>

    <template v-if="scope === 'national'">
      <div v-if="fingerprintMeta" class="research-evidence">
        <span><strong>{{ fingerprintMeta.city_count }}</strong> 纳入城市 / <strong>{{ fingerprintMeta.eligible_city_count }}</strong> 合格城市</span>
        <span><strong>{{ fingerprintMeta.sample_hours_min }}–{{ fingerprintMeta.sample_hours_max }}</strong> 小时/城市</span>
        <span>历史分析窗口 <strong>{{ fmt(fingerprintMeta.window_start) }} — {{ fmt(fingerprintMeta.window_end) }}</strong></span>
        <span>聚类轮廓系数 <strong>{{ fingerprintMeta.silhouette?.toFixed(2) ?? "—" }}</strong></span>
      </div>
      <section class="research-section">
        <div class="research-section-head">
          <h2>城市特征空间与分群</h2>
          <span>主成分分析 · 特征标准化 · 聚类探索</span>
        </div>
        <CityFingerprintPanel
          v-if="fingerprint.data.value"
          :fingerprint="fingerprint.data.value"
          :focus-id="focusId"
          @select="focusCity"
        />
        <div v-else class="research-panel research-empty" role="status">
          <strong>{{ fingerprint.isPending.value ? "正在读取分析结果" : fingerprint.isError.value ? "全国统计结果加载失败" : "当前缺少有效的全国统计结果" }}</strong>
        </div>
      </section>
    </template>

    <template v-else>
      <div class="research-evidence">
        <span>分析城市 <strong>{{ cityName }}</strong></span>
        <span v-if="structureMeta">PCA 完整样本 <strong>{{ structureMeta.sample_count }}</strong></span>
        <span v-if="structureMeta">缺失比例 <strong>{{ (structureMeta.missing_fraction * 100).toFixed(1) }}%</strong></span>
        <span v-if="structureMeta">窗口 <strong>{{ fmt(structureMeta.window_start) }} — {{ fmt(structureMeta.window_end) }}</strong></span>
        <span v-if="structureMeta">标准化：{{ structureMeta.standardization }}</span>
      </div>
      <section class="research-section">
        <div class="research-section-head">
          <h2>{{ cityName }} · 主成分与相关结构</h2>
          <span>PCA 解释方差、主成分权重、得分及相关矩阵</span>
        </div>
        <PCAStructurePanel v-if="structure.data.value" :structure="structure.data.value" />
        <div v-else class="research-panel research-empty" role="status">
          <strong>{{ structure.isPending.value ? "正在读取城市结构" : structure.isError.value ? "城市结构分析加载失败" : "该城市尚无可用的统计分析产物" }}</strong>
          <small>请在右上角切换城市；未完成分析的城市不显示推测结果。</small>
        </div>
      </section>
      <section class="research-section">
        <div class="research-section-head">
          <h2>PM2.5 与风速的配对关系</h2>
          <span>相同时间戳配对 · {{ matched.length }} 个有效小时 · {{ matchedWindow }}</span>
        </div>
        <div v-if="matched.length >= 16" class="research-split">
          <div class="research-panel research-panel-pad relationship-plot">
            <h3>风速与 PM2.5 浓度</h3>
            <WindClearance :points="matched" :height="360" />
            <p class="plot-method">风速分箱中位数与四分位带；每箱至少 8 个有效样本。</p>
          </div>
          <div class="research-panel research-panel-pad relationship-plot">
            <h3>风向分布与条件浓度</h3>
            <WindRose :samples="matched" />
            <p class="plot-method">扇瓣面积表示频数，颜色表示条件 PM2.5 均值；低于 0.5 m/s 的风不计入方向扇区。</p>
          </div>
        </div>
        <div v-else class="research-panel research-empty" role="status">
          <strong>配对气象样本不足</strong>
          <small>请在右上角切换城市。</small>
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.analysis-workspace { padding-bottom: 88px; }
.relationship-plot { min-height: 350px; }
.relationship-plot h3 { color: var(--ink); font-size: 14px; font-weight: 650; margin: 0 0 12px; }
.relationship-plot :deep(.wind-rose) { height: 360px; min-height: 0; }
.plot-method { color: var(--ink-secondary); font-size: var(--fs-label); line-height: 1.55; margin: 10px 0 0; }
.research-split {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(280px, 1fr);
  align-items: start;
  gap: 20px;
}
@media (max-width: 1050px) {
  .research-split { grid-template-columns: minmax(0, 1fr); }
}
</style>
