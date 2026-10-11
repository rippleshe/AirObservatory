<script setup lang="ts">
import { computed, ref } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { api } from "../api/client";
import { expectData } from "../api/request";
import { useLocationCatalog } from "../composables/useLocationCatalog";
import CityFingerprintPanel from "../components/CityFingerprintPanel.vue";
import PCAStructurePanel from "../components/PCAStructurePanel.vue";
import WindClearance from "../components/WindClearance.vue";
import WindRose from "../components/WindRose.vue";
import { useContextStore } from "../stores/context";

const context = useContextStore();
const { locations } = useLocationCatalog();
const scope = ref<"national" | "city">("national");
const cityId = computed(() => context.selectedLocationId ?? locations.data.value?.[0]?.location_id ?? 1);
const cityName = computed(() => locations.data.value?.find((row) => row.location_id === cityId.value)?.city ?? "当前城市");

const fingerprint = useQuery({
  queryKey: ["research-fingerprint"],
  queryFn: () => expectData(api.GET("/api/analysis/city-fingerprint")),
  staleTime: 30 * 60_000,
  retry: false,
});
const structure = useQuery({
  queryKey: computed(() => ["research-city-structure", cityId.value]),
  queryFn: () => expectData(api.GET("/api/locations/{location_id}/structure", {
    params: { path: { location_id: cityId.value } },
  })),
  enabled: computed(() => scope.value === "city"),
  retry: false,
});
const pmSeries = useQuery({
  queryKey: computed(() => ["research-pm25", cityId.value]),
  queryFn: () => expectData(api.GET("/api/locations/{location_id}/series", {
    params: { path: { location_id: cityId.value }, query: { variable: "pm25", data_kind: "model_analysis", hours: 720 } },
  })),
  enabled: computed(() => scope.value === "city"),
});
const weather = useQuery({
  queryKey: computed(() => ["research-weather", cityId.value]),
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
      ? [{ wind: speed, speed, dir, pm25 }]
      : [];
  });
});
const fingerprintMeta = computed(() => fingerprint.data.value?.meta);
const structureMeta = computed(() => structure.data.value?.meta);
const fmt = (time: string | undefined) => time ? time.slice(0, 10) : "—";

function focusCity(id: number, name: string) {
  context.selectLocation(id, name);
  context.setFocus(id, name);
  scope.value = "city";
}
</script>

<template>
  <section class="research-view analysis-workspace">
    <header class="research-head">
      <div>
        <h1>多变量关联分析</h1>
        <p>城市特征结构与污染—气象统计关系</p>
      </div>
      <div class="research-tabs" role="group" aria-label="分析尺度">
        <button type="button" :class="{ active: scope === 'national' }" :aria-pressed="scope === 'national'" @click="scope = 'national'">全国城市结构</button>
        <button type="button" :class="{ active: scope === 'city' }" :aria-pressed="scope === 'city'" @click="scope = 'city'">单城市关联</button>
      </div>
    </header>

    <template v-if="scope === 'national'">
      <div v-if="fingerprintMeta" class="research-evidence">
        <span><strong>{{ fingerprintMeta.city_count }}</strong> 城市</span>
        <span><strong>{{ fingerprintMeta.sample_hours_min }}–{{ fingerprintMeta.sample_hours_max }}</strong> 小时/城市</span>
        <span>分析窗口 <strong>{{ fmt(fingerprintMeta.window_start) }} — {{ fmt(fingerprintMeta.window_end) }}</strong></span>
        <span>聚类轮廓系数 <strong>{{ fingerprintMeta.silhouette?.toFixed(2) ?? "—" }}</strong></span>
      </div>
      <section class="research-section">
        <div class="research-section-head">
          <h2>全国城市多变量结构</h2>
          <span>主成分分析 · 特征标准化 · 聚类探索</span>
        </div>
        <CityFingerprintPanel
          v-if="fingerprint.data.value"
          :fingerprint="fingerprint.data.value"
          :focus-id="context.focusId"
          @select="focusCity"
        />
        <div v-else class="research-panel research-empty" role="status">
          <strong>{{ fingerprint.isPending.value ? "正在读取分析结果" : "当前缺少有效的全国统计结果" }}</strong>
          <small>统计图只使用已经完成计算的特征矩阵，不补造数据。</small>
        </div>
      </section>
      <footer class="research-evidence">
        <span>聚类用于发现特征相似的城市，不代表环境质量类型或因果分类。</span>
        <span>来源：CAMS 模式分析场与 Open-Meteo 气象再分析</span>
      </footer>
    </template>

    <template v-else>
      <div class="research-evidence">
        <span>分析城市 <strong>{{ cityName }}</strong></span>
        <span v-if="structureMeta">配对有效样本 <strong>{{ structureMeta.sample_count }}</strong></span>
        <span v-if="structureMeta">缺失比例 <strong>{{ (structureMeta.missing_fraction * 100).toFixed(1) }}%</strong></span>
        <span v-if="structureMeta">窗口 <strong>{{ fmt(structureMeta.window_start) }} — {{ fmt(structureMeta.window_end) }}</strong></span>
      </div>
      <section class="research-section">
        <div class="research-section-head">
          <h2>{{ cityName }} · 主成分与相关结构</h2>
          <span>PCA 解释方差、载荷、得分及相关矩阵</span>
        </div>
        <PCAStructurePanel v-if="structure.data.value" :structure="structure.data.value" />
        <div v-else class="research-panel research-empty" role="status">
          <strong>{{ structure.isPending.value ? "正在读取城市结构" : "该城市尚无可用的统计分析产物" }}</strong>
          <small>请在右上角切换城市；未完成分析的城市不显示推测结果。</small>
        </div>
      </section>
      <section class="research-section">
        <div class="research-section-head">
          <h2>PM2.5 与风速的配对关系</h2>
          <span>相同时间戳配对 · {{ matched.length }} 个有效小时</span>
        </div>
        <div v-if="matched.length >= 16" class="research-split">
          <div class="research-panel research-panel-pad relationship-plot">
            <WindClearance :points="matched" />
          </div>
          <div class="research-panel research-panel-pad relationship-plot">
            <WindRose :samples="matched" />
          </div>
        </div>
        <div v-else class="research-panel research-empty" role="status">
          <strong>配对气象样本不足</strong>
          <small>只有同一时刻的污染物和气象记录都有效时才参与统计。</small>
        </div>
      </section>
      <footer class="research-evidence">
        <span>关联结构仅反映样本内的统计关系，不作为污染成因的因果证明。</span>
        <span v-if="structureMeta">标准化：{{ structureMeta.standardization }}</span>
      </footer>
    </template>
  </section>
</template>

<style scoped>
.analysis-workspace { padding-bottom: 88px; }
.relationship-plot { min-height: 350px; }
.relationship-plot :deep(.wind-clearance),
.relationship-plot :deep(.wind-rose) { min-height: 300px; }
</style>
