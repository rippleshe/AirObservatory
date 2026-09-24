<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { init, type ECharts } from "../lib/charts";
import { clusterColor } from "../lib/palette";

type Fingerprint = components["schemas"]["CityFingerprintResponse"];

const props = defineProps<{ fingerprint: Fingerprint }>();
const emit = defineEmits<{
  select: [locationId: number, city: string];
}>();

const scatterEl = ref<HTMLDivElement | null>(null);
const varianceEl = ref<HTMLDivElement | null>(null);
let scatter: ECharts | null = null;
let variance: ECharts | null = null;
let observer: ResizeObserver | null = null;

const FEATURE_LABELS: Record<string, string> = {
  pm25_mean: "PM2.5 均值",
  pm25_p90: "PM2.5 高值",
  pm25_std: "PM2.5 波动",
  pm10_mean: "PM10 均值",
  pm10_p90: "PM10 高值",
  no2_mean: "NO₂ 均值",
  no2_p90: "NO₂ 高值",
  o3_mean: "O₃ 均值",
  o3_p90: "O₃ 高值",
  o3_std: "O₃ 波动",
  so2_mean: "SO₂ 均值",
  co_mean: "CO 均值",
  temperature_mean: "平均气温",
  humidity_mean: "平均湿度",
  wind_speed_mean: "平均风速",
  boundary_layer_height_mean: "平均边界层高度",
  precipitation_hour_fraction: "降水小时占比",
  pm25_diurnal_amplitude: "PM2.5 日内起伏",
  corr_pm25_wind: "PM2.5 与风速",
  corr_pm25_boundary_layer: "PM2.5 与边界层",
  corr_o3_temperature: "O₃ 与气温",
};

function featureLabel(name: string) {
  return FEATURE_LABELS[name] ?? name;
}

const retainedShare = () => {
  const ev = props.fingerprint.explained_variance;
  const pick = ev[1]?.cumulative_ratio ?? ev[0]?.cumulative_ratio ?? 0;
  return (pick * 100).toFixed(1);
};

function render() {
  if (!scatter || !variance) return;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const clusters = Array.from(
    new Set(props.fingerprint.points.map((point) => point.cluster)),
  ).sort((a, b) => a - b);
  const axisInk = "#5b6d64";
  const axisSize = 12;

  scatter.setOption(
    {
      animation: !reducedMotion,
      aria: {
        enabled: true,
        description:
          "60 城共同时间窗的城市结构指纹二维图。每个点是一座城市，颜色表示探索性分组。",
      },
      grid: { left: 60, right: 24, top: 34, bottom: 52 },
      tooltip: {
        backgroundColor: "rgba(255,255,255,.985)",
        borderColor: "#c5d1cb",
        borderWidth: 1,
        padding: [11, 13],
        textStyle: { color: "#17231e", fontSize: 13, lineHeight: 21 },
        extraCssText: "box-shadow:0 12px 32px rgba(21,36,30,.12);border-radius:10px;",
        formatter(params: any) {
          const row = params.data;
          return [
            `<b>${row.city}</b> · ${row.region}`,
            `第 ${row.cluster} 组`,
            `变化方向 1 <b>${Number(row.value[0]).toFixed(2)}</b>`,
            `变化方向 2 <b>${Number(row.value[1]).toFixed(2)}</b>`,
            `样本 ${row.sampleHours} 小时 · 点击进入城市`,
          ].join("<br/>");
        },
      },
      legend: {
        top: 0,
        right: 0,
        itemWidth: 10,
        itemHeight: 10,
        itemGap: 14,
        textStyle: { color: axisInk, fontSize: axisSize },
      },
      xAxis: {
        type: "value",
        name: "变化方向 1 →",
        nameLocation: "middle",
        nameGap: 32,
        nameTextStyle: { color: axisInk, fontSize: axisSize },
        axisLabel: { color: axisInk, fontSize: axisSize },
        axisLine: { lineStyle: { color: "#c9d3cd" } },
        splitLine: { lineStyle: { color: "#dde4e0" } },
      },
      yAxis: {
        type: "value",
        name: "变化方向 2 ↑",
        nameTextStyle: { color: axisInk, fontSize: axisSize, padding: [0, 0, 8, 0] },
        axisLabel: { color: axisInk, fontSize: axisSize },
        axisLine: { lineStyle: { color: "#c9d3cd" } },
        splitLine: { lineStyle: { color: "#dde4e0" } },
      },
      series: clusters.map((cluster) => ({
        name: "第 " + cluster + " 组",
        type: "scatter",
        symbolSize: 11,
        data: props.fingerprint.points
          .filter((point) => point.cluster === cluster)
          .map((point) => ({
            value: [point.values.PC1 ?? 0, point.values.PC2 ?? 0],
            locationId: point.location_id,
            city: point.city,
            region: point.region,
            cluster: point.cluster,
            sampleHours: point.sample_hours,
          })),
        itemStyle: {
          color: clusterColor(cluster),
          opacity: 0.85,
          borderColor: "#ffffff",
          borderWidth: 2,
        },
        emphasis: {
          scale: 1.5,
          label: {
            show: true,
            formatter: (params: any) => params.data.city,
            position: "top",
            color: "#10221a",
            fontSize: 13,
            fontWeight: 700,
            backgroundColor: "rgba(255,255,255,.96)",
            borderColor: "#c5d1cb",
            borderWidth: 1,
            borderRadius: 6,
            padding: [5, 8],
          },
        },
      })),
    },
    true,
  );

  scatter.off("click");
  scatter.on("click", (params: any) => {
    const data = params.data;
    if (data?.locationId && data?.city) {
      emit("select", Number(data.locationId), String(data.city));
    }
  });

  variance.setOption(
    {
      animation: !reducedMotion,
      aria: { enabled: true, description: "各变化方向解释比例与累计解释比例。" },
      grid: { left: 44, right: 14, top: 30, bottom: 34 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(255,255,255,.985)",
        borderColor: "#c5d1cb",
        borderWidth: 1,
        textStyle: { color: "#17231e", fontSize: 13 },
        extraCssText: "box-shadow:0 12px 32px rgba(21,36,30,.12);border-radius:10px;",
      },
      legend: {
        top: 0,
        right: 0,
        itemWidth: 12,
        itemHeight: 8,
        textStyle: { color: axisInk, fontSize: axisSize },
      },
      xAxis: {
        type: "category",
        data: props.fingerprint.explained_variance.map((item) => item.component),
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "#c9d3cd" } },
        axisLabel: { color: axisInk, fontSize: axisSize },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 1,
        axisLabel: {
          color: axisInk,
          fontSize: axisSize,
          formatter: (value: number) => Math.round(value * 100) + "%",
        },
        splitLine: { lineStyle: { color: "#dde4e0" } },
      },
      series: [
        {
          name: "单独解释",
          type: "bar",
          barMaxWidth: 24,
          data: props.fingerprint.explained_variance.map((item) => item.variance_ratio),
          itemStyle: { color: "#356f87", borderRadius: [4, 4, 0, 0] },
        },
        {
          name: "累计解释",
          type: "line",
          data: props.fingerprint.explained_variance.map((item) => item.cumulative_ratio),
          showSymbol: true,
          symbolSize: 6,
          lineStyle: { color: "#a06a34", width: 2 },
          itemStyle: { color: "#a06a34", borderColor: "#fff", borderWidth: 2 },
        },
      ],
    },
    true,
  );
}

onMounted(() => {
  if (scatterEl.value) scatter = init(scatterEl.value, undefined, { renderer: "svg" });
  if (varianceEl.value) variance = init(varianceEl.value, undefined, { renderer: "svg" });
  observer = new ResizeObserver(() => {
    scatter?.resize();
    variance?.resize();
  });
  if (scatterEl.value) observer.observe(scatterEl.value);
  if (varianceEl.value) observer.observe(varianceEl.value);
  render();
});

watch(() => props.fingerprint, render, { deep: true });

onBeforeUnmount(() => {
  observer?.disconnect();
  scatter?.dispose();
  variance?.dispose();
});
</script>

<template>
  <section class="fingerprint-panel">
    <header class="panel-header">
      <div>
        <h2>60 座城市的长期变化，分成几种模式？</h2>
        <p>
          同一段 {{ fingerprint.meta.sample_hours_min }} 小时时间窗，21 项污染与气象摘要特征。
          在这张图上靠得越近的城市，长期变化方式越像。
        </p>
      </div>
      <div class="panel-meta data-mono">
        <b>{{ fingerprint.meta.city_count }} 城</b>
        <span>{{ fingerprint.meta.cluster_count }} 组</span>
      </div>
    </header>

    <div class="fingerprint-layout">
      <article class="scatter-cell">
        <div class="chart-heading">
          <h3>哪些城市的长期变化更像？</h3>
          <p>每个点是一座城市，颜色只是探索性分组，不代表城市有固定类别。点击城市继续看它的具体变化。</p>
          <span class="retained data-mono">{{ retainedShare() }}% 信息保留</span>
        </div>
        <div ref="scatterEl" class="scatter-chart"></div>
      </article>

      <aside class="fingerprint-ledger">
        <section>
          <div class="chart-heading">
            <h3>二维图保留了多少信息？</h3>
            <p>柱子是每个方向单独解释的变化，折线是累计。</p>
          </div>
          <div ref="varianceEl" class="variance-chart"></div>
        </section>

        <section class="cluster-section">
          <div class="chart-heading">
            <h3>每一组城市最突出的特征是什么？</h3>
            <p>用来理解它们为什么会聚在一起。σ 表示相对全国 60 城的偏离程度。</p>
          </div>
          <div class="cluster-list">
            <div
              v-for="cluster in fingerprint.cluster_profiles"
              :key="cluster.cluster"
              class="cluster-row"
            >
              <div class="cluster-title">
                <i :style="{ background: clusterColor(cluster.cluster) }"></i>
                <b>第 {{ cluster.cluster }} 组</b>
                <span>{{ cluster.city_count }} 城</span>
              </div>
              <div class="feature-list">
                <span v-for="feature in cluster.top_features" :key="feature.feature">
                  {{ featureLabel(feature.feature) }}
                  <b class="data-mono">
                    {{ feature.zscore > 0 ? "+" : "" }}{{ feature.zscore.toFixed(2) }}σ
                  </b>
                </span>
              </div>
            </div>
          </div>
        </section>
      </aside>
    </div>

    <footer class="panel-footer">
      <span class="data-mono">
        {{ fingerprint.meta.window_start.slice(0, 10) }} → {{ fingerprint.meta.window_end.slice(0, 10) }}
      </span>
      <span>统一标准化后比较</span>
      <span>分组只用于探索，不是给城市定性</span>
    </footer>
  </section>
</template>

<style scoped>
.fingerprint-panel {
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
  box-shadow: 0 10px 30px rgba(24, 41, 34, .045);
}
.panel-header {
  min-height: 86px;
  padding: 18px 20px 12px;
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 20px;
  border-bottom: 1px solid var(--hairline-soft);
}
.panel-header h2 {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-title);
  font-weight: var(--fw-display);
  letter-spacing: var(--track-display);
}
.panel-header p {
  max-width: 76ch;
  margin: 8px 0 0;
  color: var(--muted);
  font-size: var(--fs-body);
  line-height: 1.65;
}
.panel-meta {
  display: flex;
  gap: 14px;
  color: var(--muted);
  font-size: var(--fs-label);
  white-space: nowrap;
}
.panel-meta b {
  color: var(--ink);
  font-weight: var(--fw-strong);
}

.fingerprint-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.65fr) minmax(320px, .85fr);
}
.scatter-cell {
  min-width: 0;
  padding: 18px 20px;
  border-right: 1px solid var(--hairline-soft);
}
.chart-heading {
  position: relative;
  margin-bottom: 10px;
}
.chart-heading h3 {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-body);
  font-weight: var(--fw-strong);
  letter-spacing: var(--track-title);
}
.chart-heading p {
  max-width: 62ch;
  margin: 5px 0 0;
  color: var(--muted);
  font-size: var(--fs-label);
  line-height: 1.55;
}
.retained {
  display: inline-block;
  margin-top: 7px;
  padding: 4px 9px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-pill);
  background: var(--sheet-soft);
  color: var(--ink-soft);
  font-family: var(--mono);
  font-size: var(--fs-label);
}
.scatter-chart {
  width: 100%;
  height: 480px;
}

.fingerprint-ledger {
  min-width: 0;
}
.fingerprint-ledger > section {
  padding: 18px 20px;
}
.fingerprint-ledger > section + section {
  border-top: 1px solid var(--hairline-soft);
}
.variance-chart {
  width: 100%;
  height: 200px;
}

.cluster-list {
  display: grid;
}
.cluster-row {
  padding: 12px 0;
  border-top: 1px solid var(--hairline-soft);
}
.cluster-row:first-child {
  border-top: 0;
  padding-top: 2px;
}
.cluster-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cluster-title i {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.cluster-title b {
  color: var(--ink);
  font-size: var(--fs-label);
  font-weight: var(--fw-strong);
}
.cluster-title span {
  margin-left: auto;
  color: var(--muted);
  font-size: var(--fs-label);
}
.feature-list {
  margin-top: 8px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 12px;
}
.feature-list span {
  min-width: 0;
  display: flex;
  justify-content: space-between;
  gap: 6px;
  color: var(--muted);
  font-size: var(--fs-label);
}
.feature-list b {
  color: var(--ink);
  font-family: var(--mono);
  font-size: var(--fs-label);
  white-space: nowrap;
}

.panel-footer {
  min-height: 48px;
  padding: 12px 20px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 18px;
  color: var(--muted);
  font-size: var(--fs-label);
  line-height: 1.4;
}

@media (max-width: 980px) {
  .fingerprint-layout { grid-template-columns: 1fr; }
  .scatter-cell {
    border-right: 0;
    border-bottom: 1px solid var(--hairline-soft);
  }
}
@media (max-width: 680px) {
  .panel-header { display: grid; }
  .panel-meta { justify-content: start; }
  .scatter-chart { height: 400px; }
  .feature-list { grid-template-columns: 1fr; }
}
</style>
