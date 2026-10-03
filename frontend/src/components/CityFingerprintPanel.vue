<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { chartTheme, init, type ECharts } from "../lib/charts";
import { useInView } from "../composables/useInView";

/* Charts stay blank until the reader scrolls to them: the first paint is
   the animated entrance, never a show that already ended. */
const shell = ref<HTMLElement | null>(null);
const inView = useInView(shell);
import { clusterColor, FORECAST_COLOR, MODEL_COLOR, MUTED_DATA_COLOR } from "../lib/palette";

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

/* Deviation from the mean of the provincial representatives is polarity, not
   status: the diverging pair is cool↔warm with a neutral grey midpoint,
   deliberately not the good/bad status green↔red. */
const SIGMA_COOL = MODEL_COLOR;
const SIGMA_WARM = FORECAST_COLOR;
const SIGMA_ZERO = MUTED_DATA_COLOR;

function sigmaColor(z: number) {
  if (z <= -0.05) return SIGMA_COOL;
  if (z >= 0.05) return SIGMA_WARM;
  return SIGMA_ZERO;
}

/** Widest |z| in the whole profile set — one shared scale across groups. */
const sigmaMax = computed(() => {
  let max = 1;
  for (const cluster of props.fingerprint.cluster_profiles) {
    for (const feature of cluster.top_features) {
      max = Math.max(max, Math.abs(feature.zscore));
    }
  }
  return max;
});

const components_ = computed(() => props.fingerprint.explained_variance);

const cityCount = computed(() => {
  const declared = props.fingerprint.meta.city_count;
  return Number.isFinite(declared) && declared > 0 ? declared : props.fingerprint.points.length;
});

const provinceCount = computed(
  () => new Set(props.fingerprint.points.map((point) => point.province || point.city)).size,
);

/* One city per province is the analysis unit; the wording follows the data so a
   multi-city artifact is never described as provincial. */
const onePerProvince = computed(
  () => cityCount.value > 0 && provinceCount.value === cityCount.value,
);

const scatterAria = computed(() =>
  cityCount.value <= 0 ? "无指纹投影" : "城市指纹投影",
);

function render() {
  if (!inView.value) return;
  if (!scatter || !variance) return;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const clusters = Array.from(
    new Set(props.fingerprint.points.map((point) => point.cluster)),
  ).sort((a, b) => a - b);
  const axisInk = chartTheme().axisInk;
  const axisSize = 12;
  const ev = components_.value;

  scatter.setOption(
    {
      animation: !reducedMotion,
      aria: {
        enabled: true,
        description: scatterAria.value,
      },
      grid: { left: 58, right: 66, top: 26, bottom: 54 },
      tooltip: {
        backgroundColor: "rgba(255,255,255,.985)",
        borderColor: chartTheme().tooltipBorder,
        borderWidth: 1,
        padding: [11, 13],
        textStyle: { color: chartTheme().ink, fontSize: 13, lineHeight: 21 },
        extraCssText: "box-shadow:0 12px 32px rgba(15,23,42,.14);border-radius:8px;",
        formatter(params: any) {
          const row = params.data;
          return [
            `<b>${row.city}</b> · ${row.region}`,
            `第 ${row.cluster} 组`,
            `主成分 1 <b>${Number(row.value[0]).toFixed(2)}</b>`,
            `主成分 2 <b>${Number(row.value[1]).toFixed(2)}</b>`,
            `样本 ${row.sampleHours} 小时`,
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
        name: `主成分 1 · ${Math.round((ev[0]?.variance_ratio ?? 0) * 100)}%`,
        nameLocation: "middle",
        nameGap: 32,
        nameTextStyle: { color: chartTheme().inkSoft, fontSize: axisSize, fontWeight: 650 },
        axisLabel: { color: axisInk, fontSize: axisSize },
        axisLine: { lineStyle: { color: chartTheme().axisLine } },
        splitLine: { lineStyle: { color: chartTheme().splitLine } },
      },
      yAxis: {
        type: "value",
        name: `主成分 2 · ${Math.round((ev[1]?.variance_ratio ?? 0) * 100)}%`,
        nameTextStyle: {
          color: chartTheme().inkSoft,
          fontSize: axisSize,
          fontWeight: 650,
          padding: [0, 0, 8, 0],
        },
        axisLabel: { color: axisInk, fontSize: axisSize },
        axisLine: { lineStyle: { color: chartTheme().axisLine } },
        splitLine: { lineStyle: { color: chartTheme().splitLine } },
      },
      series: clusters.map((cluster, clusterIndex) => {
        const rows = props.fingerprint.points
          .filter((point) => point.cluster === cluster)
          .map((point) => ({
            value: [point.values.PC1 ?? 0, point.values.PC2 ?? 0],
            locationId: point.location_id,
            city: point.city,
            region: point.region,
            cluster: point.cluster,
            sampleHours: point.sample_hours,
          }));
        return {
          name: "第 " + cluster + " 组",
          type: "scatter",
          symbolSize: 15,
          data: rows,
          animationDuration: 720,
          animationDelay: (idx: number) => clusterIndex * 200 + idx * 26,
          itemStyle: {
            color: clusterColor(cluster),
            opacity: 0.95,
            borderColor: chartTheme().surface,
            borderWidth: 2,
          },
          // Names on as many points as the canvas can seat; the resolver culls
          // the rest rather than printing them over each other.
          label: {
            show: true,
            formatter: (params: any) => params.data.city,
            position: "right",
            distance: 4,
            color: chartTheme().inkSoft,
            fontSize: 12,
            fontWeight: 650,
            textBorderColor: chartTheme().surface,
            textBorderWidth: 3,
          },
          labelLayout: { moveOverlap: "shiftY", hideOverlap: true },
          emphasis: {
            scale: 1.5,
            focus: "series",
            itemStyle: { borderColor: chartTheme().ink, borderWidth: 2 },
            label: {
              show: true,
              formatter: (params: any) => params.data.city,
              position: "top",
              color: chartTheme().ink,
              fontSize: 13,
              fontWeight: 700,
              backgroundColor: "rgba(255,255,255,.96)",
              borderColor: chartTheme().tooltipBorder,
              borderWidth: 1,
              borderRadius: 5,
              padding: [5, 8],
              textBorderWidth: 0,
            },
          },
        };
      }),
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
      aria: { enabled: false },
      grid: { left: 44, right: 14, top: 30, bottom: 34 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(255,255,255,.985)",
        borderColor: chartTheme().tooltipBorder,
        borderWidth: 1,
        textStyle: { color: chartTheme().ink, fontSize: 13 },
        extraCssText: "box-shadow:0 12px 32px rgba(15,23,42,.14);border-radius:8px;",
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
        data: ev.map((item) => item.component),
        axisTick: { show: false },
        axisLine: { lineStyle: { color: chartTheme().axisLine } },
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
        splitLine: { lineStyle: { color: chartTheme().splitLine } },
      },
      series: [
        {
          name: "单独解释",
          type: "bar",
          barMaxWidth: 24,
          data: ev.map((item) => item.variance_ratio),
          animationDuration: 760,
          animationDelay: (idx: number) => idx * 90,
          itemStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: MODEL_COLOR },
                { offset: 1, color: "#7dd3fc" },
              ],
            },
            borderRadius: [3, 3, 0, 0],
          },
          label: {
            show: true,
            position: "top",
            color: chartTheme().inkSoft,
            fontSize: 12,
            fontWeight: 650,
            formatter: (params: any) =>
              Math.round(Number(params.value) * 100) + "%",
          },
        },
        {
          name: "累计解释",
          type: "line",
          data: ev.map((item) => item.cumulative_ratio),
          showSymbol: true,
          symbolSize: 6,
          animationDuration: 1100,
          animationDelay: 420,
          lineStyle: { color: FORECAST_COLOR, width: 2 },
          itemStyle: { color: FORECAST_COLOR, borderColor: chartTheme().surface, borderWidth: 2 },
          endLabel: {
            show: true,
            formatter: (params: any) => Math.round(Number(params.value) * 100) + "%",
            color: FORECAST_COLOR,
            fontSize: 12,
            fontWeight: 700,
            distance: 4,
          },
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
watch(inView, () => render());

onBeforeUnmount(() => {
  observer?.disconnect();
  scatter?.dispose();
  variance?.dispose();
});
</script>

<template>
  <section ref="shell" class="fingerprint-panel">
    <div class="fingerprint-layout">
      <article class="scatter-cell">
        <div ref="scatterEl" class="scatter-chart"></div>
      </article>

      <aside class="fingerprint-ledger">
        <section>
          <div ref="varianceEl" class="variance-chart"></div>
        </section>

        <section class="cluster-section">
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

              <div class="sigma-list">
                <div
                  v-for="feature in cluster.top_features"
                  :key="feature.feature"
                  class="sigma-row"
                >
                  <span class="sigma-name">{{ featureLabel(feature.feature) }}</span>
                  <div class="sigma-track">
                    <i class="sigma-zero"></i>
                    <i
                      class="sigma-bar"
                      :style="{
                        background: sigmaColor(feature.zscore),
                        left: feature.zscore >= 0 ? '50%' : undefined,
                        right: feature.zscore < 0 ? '50%' : undefined,
                        width: (Math.abs(feature.zscore) / sigmaMax) * 50 + '%',
                      }"
                    ></i>
                  </div>
                  <b class="sigma-value data-mono" :style="{ color: sigmaColor(feature.zscore) }">
                    {{ feature.zscore > 0 ? "+" : "" }}{{ feature.zscore.toFixed(1) }}σ
                  </b>
                </div>
              </div>
            </div>
          </div>
        </section>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.fingerprint-panel {
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
}
.panel-header {
  min-height: 62px;
  padding: 16px 20px 12px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 20px;
  border-bottom: 1px solid var(--hairline-soft);
}
.panel-header h2 {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-sub);
  letter-spacing: var(--track-title);
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
  grid-template-columns: minmax(0, 1.6fr) minmax(320px, .85fr);
}
.scatter-cell {
  min-width: 0;
  padding: 18px 20px;
  border-right: 1px solid var(--hairline-soft);
}
.chart-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 10px;
}
.chart-heading h3 {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-body);
  letter-spacing: var(--track-title);
}
.scatter-chart {
  width: 100%;
  height: 470px;
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
  padding: 14px 0;
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

/* σ as a diverging bar on a shared scale — polarity read off position,
   value read off the number. Replaces a table of ±σ digits. */
.sigma-list {
  margin-top: 10px;
  display: grid;
  gap: 7px;
}
.sigma-row {
  display: grid;
  grid-template-columns: 8.5em minmax(0, 1fr) 3.6em;
  align-items: center;
  gap: 10px;
}
.sigma-name {
  color: var(--muted);
  font-size: var(--fs-label);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sigma-track {
  position: relative;
  height: 12px;
  border-radius: 2px;
  background: var(--sheet-sunken);
}
.sigma-zero {
  position: absolute;
  top: -2px;
  bottom: -2px;
  left: 50%;
  width: 1px;
  background: var(--hairline-strong);
}
.sigma-bar {
  position: absolute;
  top: 2px;
  bottom: 2px;
  border-radius: 2px;
}
.sigma-value {
  color: var(--ink);
  font-size: var(--fs-label);
  text-align: right;
  white-space: nowrap;
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
  .scatter-chart { height: 400px; }
  .sigma-row { grid-template-columns: 7em minmax(0, 1fr) 3.4em; }
}
</style>
