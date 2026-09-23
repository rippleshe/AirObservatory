<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { init, registerMap, type ECharts } from "../lib/charts";

type Location = components["schemas"]["OverviewLocation"];

const props = defineProps<{
  locations: Location[];
  selectedId: number | null;
}>();

const emit = defineEmits<{
  select: [id: number, name: string];
}>();

const el = ref<HTMLDivElement | null>(null);
const mapError = ref(false);
let chart: ECharts | null = null;
let observer: ResizeObserver | null = null;
let mapReady: Promise<void> | null = null;
let mapLoaded = false;

function ensureMap() {
  if (!mapReady) {
    mapReady = fetch("/maps/china.json")
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Map asset failed: ${response.status}`);
        }
        return response.json();
      })
      .then((geoJson) => {
        registerMap("china-observatory", geoJson);
      });
  }
  return mapReady;
}

function tone(value: number | null | undefined) {
  if (value == null) return "#98a29e";
  if (value < 20) return "#4d8f82";
  if (value < 40) return "#6e9f7f";
  if (value < 60) return "#b99b50";
  if (value < 90) return "#c17249";
  return "#9d433c";
}

function render() {
  if (!chart || !mapLoaded) return;
  const points = props.locations.map((location) => ({
    name: location.name,
    value: [location.lon, location.lat, location.value ?? null],
    locationId: location.location_id,
    sourceTime: location.source_time,
    source: location.source,
    quality: location.quality_flag,
    itemStyle: { color: tone(location.value) },
    symbolSize: location.location_id === props.selectedId ? 19 : 13,
  }));

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  chart.setOption({
    aria: {
      enabled: true,
      description: "中国重点城市空气质量模式场。城市列表提供等价的键盘操作入口。",
    },
    animation: !reduceMotion,
    animationDurationUpdate: reduceMotion ? 0 : 220,
    animationEasingUpdate: "cubicOut",
    tooltip: {
      trigger: "item",
      borderWidth: 1,
      borderColor: "#c9d1cc",
      backgroundColor: "rgba(249,250,247,.97)",
      textStyle: { color: "#18201e", fontSize: 11 },
      formatter(params: any) {
        if (params.seriesType !== "scatter") return "";
        const raw = params.data;
        const value = raw.value?.[2];
        const time = new Intl.DateTimeFormat("zh-CN", {
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        }).format(new Date(raw.sourceTime));
        return `<strong style="font-size:12px">${raw.name}</strong><br/>
          <span style="color:#6b7571">PM2.5</span>&nbsp;&nbsp;<b style="font-family:monospace">${value == null ? "—" : Number(value).toFixed(1)}</b> µg/m³<br/>
          <span style="color:#6b7571">源时间</span>&nbsp;&nbsp;${time}<br/>
          <span style="color:#6b7571">来源</span>&nbsp;&nbsp;${raw.source}`;
      },
    },
    geo: {
      map: "china-observatory",
      roam: true,
      zoom: 1.06,
      top: 26,
      bottom: 18,
      left: 34,
      right: 34,
      silent: false,
      itemStyle: {
        areaColor: "#dde6e1",
        borderColor: "#9eaba5",
        borderWidth: 0.72,
      },
      emphasis: {
        disabled: true,
      },
      select: {
        disabled: true,
      },
      regions: [
        {
          name: "南海诸岛",
          itemStyle: { opacity: 0.45 },
        },
      ],
    },
    series: [
      {
        type: "scatter",
        coordinateSystem: "geo",
        data: points,
        z: 4,
        symbol: "circle",
        encode: { tooltip: [2] },
        itemStyle: {
          borderColor: "#f8faf7",
          borderWidth: 2,
          shadowColor: "rgba(24,32,30,.16)",
          shadowBlur: 3,
        },
        label: {
          show: true,
          formatter(params: any) {
            const raw = params.data;
            const value = raw.value?.[2];
            return `{name|${raw.name}} {value|${value == null ? "—" : Math.round(value)}}`;
          },
          position: "right",
          distance: 5,
          rich: {
            name: {
              color: "#27302d",
              fontSize: 10,
              fontWeight: 650,
              textBorderColor: "rgba(249,250,247,.92)",
              textBorderWidth: 3,
            },
            value: {
              color: "#4d5955",
              fontSize: 9,
              fontFamily: "Cascadia Code",
              backgroundColor: "rgba(249,250,247,.88)",
              borderColor: "rgba(24,32,30,.10)",
              borderWidth: 1,
              borderRadius: 2,
              padding: [2, 3],
            },
          },
        },
      },
      {
        type: "effectScatter",
        coordinateSystem: "geo",
        data: points.filter((point) => point.locationId === props.selectedId),
        z: 3,
        symbolSize: 25,
        showEffectOn: "render",
        rippleEffect: {
          period: 4,
          scale: 2.1,
          brushType: "stroke",
        },
        itemStyle: {
          color: "#1f6782",
          opacity: 0.22,
        },
        tooltip: { show: false },
        label: { show: false },
      },
    ],
  }, true);
}

function onClick(params: any) {
  if (params.seriesType !== "scatter") return;
  const raw = params.data;
  emit("select", raw.locationId, raw.name);
}

onMounted(async () => {
  if (!el.value) return;
  chart = init(el.value, undefined, { renderer: "canvas" });
  chart.on("click", onClick);
  observer = new ResizeObserver(() => chart?.resize());
  observer.observe(el.value);
  try {
    await ensureMap();
    mapLoaded = true;
    render();
  } catch {
    mapError.value = true;
  }
});

watch(() => [props.locations, props.selectedId], render, { deep: true });

onBeforeUnmount(() => {
  observer?.disconnect();
  chart?.off("click", onClick);
  chart?.dispose();
});
</script>

<template>
  <div class="geo-field-shell">
    <div ref="el" class="geo-field" aria-label="中国重点城市空气质量空间图"></div>
    <p v-if="mapError" class="map-asset-error" role="alert">
      地图底图加载失败；城市数据仍可通过右侧列表访问。
    </p>
  </div>
</template>

<style scoped>
.geo-field-shell,
.geo-field {
  position: absolute;
  inset: 0;
}
.geo-field {
  background:
    linear-gradient(rgba(249, 250, 247, .42), rgba(249, 250, 247, .42)),
    #e9eeea;
}
.map-asset-error {
  position: absolute;
  inset: auto 16px 16px;
  margin: 0;
  padding: 10px 12px;
  border: 1px solid var(--hairline-strong);
  border-radius: var(--radius);
  background: var(--sheet);
  color: var(--error);
  font-size: 11px;
}
</style>
