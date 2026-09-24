<script setup lang="ts">
import { Minus, Plus, RotateCcw } from "lucide-vue-next";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { components } from "../api/schema";
import { init, registerMap, type ECharts } from "../lib/charts";
import {
  aqiColor,
  changeColor,
  changeState,
  pm25Color,
} from "../lib/palette";

type NationalCity = components["schemas"]["NationalCity"];
type MapMetric = "aqi" | "pm25" | "change";

const props = withDefaults(
  defineProps<{
    cities: NationalCity[];
    metric?: MapMetric;
  }>(),
  { metric: "aqi" },
);
const emit = defineEmits<{ select: [id: number, name: string] }>();

const el = ref<HTMLDivElement | null>(null);
const mapError = ref(false);
const zoom = ref(1.06);
let chart: ECharts | null = null;
let observer: ResizeObserver | null = null;
let mapReady: Promise<void> | null = null;
let mapLoaded = false;

/* DESIGN.md: 重点城市直接标「城市 + 当前指标」，普通用户无需 hover 才能看出热点。
   Ten candidates go in; crowding and hideOverlap settle how many survive. The
   ones that drop out still carry their numbers in the table view. */
const LABEL_LIMIT = 10;

const groundCount = computed(
  () => props.cities.filter((city) => city.has_recent_ground_observation).length,
);

function ensureMap() {
  if (!mapReady) {
    mapReady = fetch("/maps/china.json")
      .then((response) => {
        if (!response.ok) throw new Error("Map asset failed: " + response.status);
        return response.json();
      })
      .then((geoJson) => registerMap("china-national", geoJson));
  }
  return mapReady;
}

function shortProvince(name: string) {
  return name
    .replace("维吾尔自治区", "")
    .replace("壮族自治区", "")
    .replace("回族自治区", "")
    .replace("自治区", "")
    .replace("特别行政区", "")
    .replace("省", "")
    .replace("市", "");
}

function fmtTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function metricValue(city: NationalCity) {
  if (props.metric === "pm25") return city.pm25;
  if (props.metric === "change") return city.pm25_change_24h;
  return city.china_aqi;
}

function cityColor(city: NationalCity) {
  if (props.metric === "pm25") return pm25Color(city.pm25);
  if (props.metric === "change") return changeColor(city.pm25_change_24h);
  return aqiColor(city.china_aqi_level);
}

function rankScore(city: NationalCity) {
  if (props.metric === "change") return Math.abs(city.pm25_change_24h ?? -Infinity);
  return metricValue(city) ?? -Infinity;
}

function metricLabel(city: NationalCity) {
  if (props.metric === "pm25") {
    return city.pm25 == null ? "—" : `${city.pm25.toFixed(0)} µg/m³`;
  }
  if (props.metric === "change") {
    const state = changeState(city.pm25_change_24h);
    if (city.pm25_change_24h == null) return state.label;
    const value = city.pm25_change_24h;
    return `${state.arrow} ${value >= 0 ? "+" : ""}${value.toFixed(1)} µg/m³`;
  }
  return city.china_aqi == null ? "—" : `AQI ${city.china_aqi}`;
}

/* ── label collision ──────────────────────────────────────────────────
   ECharts 6 labelLayout notes, from lib/label/LabelManager.js:
     - the callback receives { dataIndex, text, rect, labelRect, align, ... }
       and NO `data`, so per-datum flags must be looked up by dataIndex;
     - the result honours x/y, dx/dy, rotate, moveOverlap and hideOverlap.
       There is no `hide` key — a label is culled only by `hideOverlap: true`.
   Placement is recomputed from scratch every call (the callback can run more
   than once per datum in a pass) so a repeat call is idempotent. */

type Box = { x: number; y: number; w: number; h: number };
type Geom = { cx: number; cy: number; half: number; w: number; h: number };

const labelInfo = new Map<number, { name: string; subLabel: string }>();
const geom = new Map<number, Geom>();

function textWidth(text: string, size: number) {
  let width = 0;
  for (const ch of text) {
    width += /[⺀-鿿＀-￯]/.test(ch) ? size : size * 0.58;
  }
  return width;
}

function hits(a: Box, b: Box, gap = 6) {
  return !(
    a.x + a.w + gap <= b.x ||
    b.x + b.w + gap <= a.x ||
    a.y + a.h + gap <= b.y ||
    b.y + b.h + gap <= a.y
  );
}

function anchorsFor(g: Geom) {
  const { half, w, h } = g;
  return [
    { dx: half + 8, dy: -h / 2 }, // right
    { dx: -(half + 8 + w), dy: -h / 2 }, // left
    { dx: -w / 2, dy: -(half + 8 + h) }, // top
    { dx: -w / 2, dy: half + 8 }, // bottom
    { dx: half + 18, dy: -h - 8 }, // upper-right
    { dx: -(half + 18 + w), dy: -h - 8 }, // upper-left
    { dx: half + 18, dy: 8 }, // lower-right
    { dx: -(half + 18 + w), dy: 8 }, // lower-left
  ];
}

function placeAll() {
  const placed: Box[] = [];
  const result = new Map<number, { dx: number; dy: number } | null>();
  for (const index of [...geom.keys()].sort((a, b) => a - b)) {
    const g = geom.get(index)!;
    let slot: { dx: number; dy: number } | null = null;
    for (const anchor of anchorsFor(g)) {
      const box: Box = { x: g.cx + anchor.dx, y: g.cy + anchor.dy, w: g.w, h: g.h };
      if (!placed.some((other) => hits(box, other))) {
        placed.push(box);
        slot = anchor;
        break;
      }
    }
    result.set(index, slot);
  }
  return result;
}

function labelLayout(params: any) {
  const info = labelInfo.get(params.dataIndex);
  if (!info) return { hideOverlap: true };

  const rect = params.rect ?? {};
  const labelRect = params.labelRect ?? {};
  const half = (rect.width ?? 20) / 2;
  geom.set(params.dataIndex, {
    cx: (rect.x ?? 0) + half,
    cy: (rect.y ?? 0) + (rect.height ?? 20) / 2,
    half,
    // Prefer the measured label box; fall back to an estimate before the
    // label has been laid out.
    w: labelRect.width || Math.max(textWidth(info.name, 13), textWidth(info.subLabel, 12)) + 18,
    h: labelRect.height || 34,
  });

  // The first pass meets labels one at a time, so an early label would be
  // placed without knowing its neighbours. Hold them at the default anchor
  // until the full geometry is in, then place the whole set at once —
  // relayoutLabels() forces that second pass. During roam the map is already
  // complete, so labels track it immediately.
  const slot = geom.size < labelInfo.size ? null : placeAll().get(params.dataIndex);

  // moveOverlap nudges before hideOverlap culls, so a crowded cluster keeps
  // more names. hideOverlap is also the only way to drop a label at all —
  // ECharts 6's labelLayout has no `hide` key.
  const settled = { moveOverlap: "shiftY" as const, hideOverlap: true };
  if (!slot) return { dx: 0, dy: 0, ...settled };

  // dx/dy are offsets from the position:"right" anchor, whose origin sits at
  // (symbol right edge, symbol centre) with align:left / verticalAlign:middle.
  return {
    dx: slot.dx - half,
    dy: slot.dy + (labelRect.height || 34) / 2,
    ...settled,
  };
}

function render() {
  if (!chart || !mapLoaded) return;

  labelInfo.clear();
  geom.clear();

  const ranked = [...props.cities]
    .filter((city) => metricValue(city) != null)
    .sort((a, b) => rankScore(b) - rankScore(a));
  const labelledCities = ranked.slice(0, LABEL_LIMIT);
  const labelled = new Set(labelledCities.map((city) => city.location_id));

  const data = props.cities.map((city, index) => {
    const state = changeState(city.pm25_change_24h);
    const isFocus = labelled.has(city.location_id);
    // Level word travels with the colour — never colour alone.
    const subLabel =
      props.metric === "change"
        ? `${state.label} · ${metricLabel(city)}`
        : `${city.china_aqi_level ?? "暂无"} · ${metricLabel(city)}`;
    if (isFocus) labelInfo.set(index, { name: city.name, subLabel });
    return {
      name: city.name,
      value: [
        city.lon,
        city.lat,
        metricValue(city),
        city.china_aqi ?? null,
        city.pm25 ?? null,
        city.pm25_change_24h ?? null,
      ],
      locationId: city.location_id,
      level: city.china_aqi_level,
      ground: city.has_recent_ground_observation,
      sourceTime: city.source_time,
      primary: city.primary_pollutants,
      metricText: metricLabel(city),
      subLabel,
      isFocus,
      symbolSize: isFocus ? 20 : 16,
      itemStyle: { color: cityColor(city) },
      label: { show: isFocus },
    };
  });

  const groundData = data
    .filter((item) => item.ground)
    .map((item) => ({
      ...item,
      symbolSize: Number(item.symbolSize) + 8,
      itemStyle: {
        color: "rgba(0,0,0,0)",
        borderColor: "#183f38",
        borderWidth: 2,
      },
      label: { show: false },
    }));

  /* The catch layer must be truly invisible. Building it from a spread would
     carry each datum's own itemStyle across and paint 32px discs on the map. */
  const hitData = props.cities.map((city) => ({
    name: city.name,
    value: [city.lon, city.lat],
    locationId: city.location_id,
    level: city.china_aqi_level,
    ground: city.has_recent_ground_observation,
    sourceTime: city.source_time,
    primary: city.primary_pollutants,
    metricText: metricLabel(city),
    symbolSize: 32,
    itemStyle: {
      color: "rgba(0,0,0,0)",
      borderColor: "rgba(0,0,0,0)",
      borderWidth: 0,
      opacity: 0,
    },
  }));

  chart.setOption(
    {
      aria: {
        enabled: true,
        description:
          "全国六十个城市空气质量地图。可切换 AQI、PM2.5 和过去24小时变化，点击城市进入详情。",
      },
      animation: !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
      animationDurationUpdate: 220,
      tooltip: {
        trigger: "item",
        confine: true,
        padding: [14, 15],
        backgroundColor: "rgba(255,255,255,.985)",
        borderColor: "#b9c4bf",
        borderWidth: 1,
        textStyle: { color: "#15211d", fontSize: 13, lineHeight: 23 },
        extraCssText: "box-shadow:0 16px 40px rgba(19,31,27,.14);border-radius:12px;",
        formatter(params: any) {
          if (params.seriesName !== "城市" && params.seriesName !== "点击区") return "";
          const raw = params.data;
          const aqi = raw.value?.[3];
          const pm = raw.value?.[4];
          const change = raw.value?.[5];
          const primary = raw.primary?.length > 0 ? raw.primary.join(" / ") : "暂无";
          const state = changeState(change as number | null);
          const changeText =
            change == null
              ? "历史不足"
              : `${state.arrow} ${state.label} ${Math.abs(Number(change)).toFixed(1)} µg/m³`;
          return [
            '<div style="min-width:250px">',
            '<div style="display:flex;align-items:baseline;justify-content:space-between;gap:18px">',
            '<strong style="font-size:17px">' + raw.name + "</strong>",
            '<span style="font-size:12px;color:#69756f">点击查看城市</span>',
            "</div>",
            '<div style="margin-top:9px;font-size:15px;font-weight:700">' + raw.metricText + "</div>",
            '<div style="margin-top:5px;color:#2a3d34"><b>' + (raw.level ?? "暂无") + "</b> · AQI " + (aqi ?? "—") + "</div>",
            '<div style="color:#5c6963">PM2.5 ' + (pm == null ? "—" : Number(pm).toFixed(1)) + " µg/m³ · 24h " + changeText + "</div>",
            '<div style="color:#5c6963">主要污染物 ' + primary + "</div>",
            '<div style="margin-top:6px;color:#88928e;font-size:12px">更新 ' + fmtTime(raw.sourceTime) + (raw.ground ? " · 有近期地面观测" : "") + "</div>",
            "</div>",
          ].join("");
        },
      },
      geo: {
        map: "china-national",
        roam: true,
        zoom: zoom.value,
        scaleLimit: { min: 0.92, max: 4.5 },
        top: 24,
        bottom: 22,
        left: 20,
        right: 20,
        label: {
          show: window.innerWidth >= 700,
          // Province names recede in colour, not in size: projector legibility
          // is a floor, hierarchy comes from tone and weight.
          color: "#93a19a",
          fontSize: 12,
          formatter: (params: any) => shortProvince(params.name),
          // Drop a province name rather than print it over a neighbour.
          labelLayout: { hideOverlap: true },
        },
        itemStyle: {
          areaColor: "#e8efed",
          borderColor: "#91a29a",
          borderWidth: 1,
        },
        emphasis: {
          itemStyle: {
            areaColor: "#dce7e3",
            borderColor: "#52665d",
            borderWidth: 1.35,
          },
          label: {
            color: "#26352f",
            fontSize: 12,
            fontWeight: 700,
          },
        },
        select: { disabled: true },
      },
      series: [
        {
          // Invisible, oversized target under the marks: a 32px catch area so
          // a city can be clicked without landing on the dead centre.
          name: "点击区",
          type: "scatter",
          coordinateSystem: "geo",
          data: hitData,
          z: 3,
          cursor: "pointer",
          // No emphasis/blur here: this layer is a hit target only. Emphasising
          // it would push every city mark into the blur state and dim the map.
          emphasis: { disabled: true },
          tooltip: { show: true },
        },
        {
          name: "地面观测外环",
          type: "scatter",
          coordinateSystem: "geo",
          data: groundData,
          silent: true,
          z: 4,
        },
        {
          name: "城市",
          type: "scatter",
          coordinateSystem: "geo",
          data,
          z: 5,
          cursor: "pointer",
          emphasis: {
            scale: 1.35,
            itemStyle: {
              borderColor: "#10231c",
              borderWidth: 2.4,
              opacity: 1,
            },
            label: {
              show: true,
              color: "#10231c",
              fontSize: 13,
              fontWeight: 750,
              backgroundColor: "rgba(255,255,255,.98)",
              borderColor: "#b9c5bf",
              borderWidth: 1,
              borderRadius: 6,
              padding: [5, 8],
            },
          },
          itemStyle: {
            borderColor: "#ffffff",
            borderWidth: 2,
            opacity: 0.98,
          },
          label: {
            show: true,
            position: "right",
            distance: 0,
            align: "left",
            verticalAlign: "middle",
            formatter(params: any) {
              const line2 = params.data.subLabel ?? "";
              return `{city|${params.data.name}}\n{value|${line2}}`;
            },
            textBorderColor: "#f7f9f7",
            textBorderWidth: 4,
            rich: {
              city: {
                color: "#10221a",
                fontSize: 13,
                fontWeight: 750,
                lineHeight: 18,
              },
              value: {
                color: "#3f5149",
                fontSize: 12,
                fontWeight: 600,
                lineHeight: 16,
              },
            },
          },
          labelLayout,
        },
      ],
    },
    true,
  );

  relayoutLabels();
}

function onClick(params: any) {
  if (params.seriesName !== "城市" && params.seriesName !== "点击区") return;
  emit("select", Number(params.data.locationId), String(params.data.name));
}

/* The first layout pass meets the labels one at a time, so early ones are
   placed without knowing their neighbours. One forced re-layout afterwards
   re-runs placement with the full geometry map filled in. */
function relayoutLabels() {
  requestAnimationFrame(() => chart?.resize());
}

function setZoom(next: number) {
  zoom.value = Math.min(4.5, Math.max(0.92, next));
  chart?.setOption({ geo: { zoom: zoom.value } });
}

function resetView() {
  zoom.value = 1.06;
  chart?.setOption({ geo: { zoom: zoom.value } });
}

onMounted(async () => {
  if (!el.value) return;
  chart = init(el.value, undefined, { renderer: "svg" });
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

watch(() => [props.cities, props.metric], render, { deep: true });

onBeforeUnmount(() => {
  observer?.disconnect();
  chart?.off("click", onClick);
  chart?.dispose();
});
</script>

<template>
  <div class="national-map-shell">
    <div ref="el" class="national-map" aria-label="全国空气质量地图"></div>

    <div class="map-actions" aria-label="地图缩放控制">
      <button type="button" aria-label="放大地图" @click="setZoom(zoom + 0.22)">
        <Plus :size="17" />
      </button>
      <button type="button" aria-label="缩小地图" @click="setZoom(zoom - 0.22)">
        <Minus :size="17" />
      </button>
      <button type="button" aria-label="复位地图" @click="resetView">
        <RotateCcw :size="16" />
      </button>
    </div>

    <div v-if="groundCount" class="ground-key">
      <i></i>
      <span>{{ groundCount }} 城有近期地面观测</span>
    </div>

    <p v-if="mapError" class="map-error" role="alert">
      地图底图加载失败，请刷新后重试。
    </p>
  </div>
</template>

<style scoped>
.national-map-shell,
.national-map {
  position: absolute;
  inset: 0;
}
.national-map {
  background:
    radial-gradient(circle at 74% 25%, rgba(205, 221, 216, .34), transparent 32%),
    linear-gradient(180deg, #f4f8f7 0%, #edf3f1 100%);
}
.map-actions {
  position: absolute;
  z-index: 8;
  right: 18px;
  bottom: 18px;
  display: grid;
  overflow: hidden;
  border: 1px solid var(--hairline-strong);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, .96);
  box-shadow: 0 8px 24px rgba(21, 37, 31, .08);
}
.map-actions button {
  width: 42px;
  height: 40px;
  display: grid;
  place-items: center;
  border: 0;
  border-bottom: 1px solid var(--hairline-soft);
  background: transparent;
  color: var(--ink-soft);
  cursor: pointer;
}
.map-actions button:last-child { border-bottom: 0; }
.map-actions button:hover {
  background: var(--soft);
  color: var(--ink);
}
.ground-key {
  position: absolute;
  z-index: 7;
  right: 72px;
  bottom: 18px;
  min-height: 40px;
  padding: 0 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, .96);
  box-shadow: 0 8px 24px rgba(21, 37, 31, .06);
  color: var(--ink-soft);
  font-size: var(--fs-label);
}
.ground-key i {
  width: 12px;
  height: 12px;
  border: 2px solid #183f38;
  border-radius: 50%;
}
.map-error {
  position: absolute;
  left: 18px;
  bottom: 18px;
  margin: 0;
  padding: 11px 14px;
  border: 1px solid #d2aaa5;
  border-radius: var(--radius-sm);
  background: #fff8f7;
  color: var(--error);
  font-size: var(--fs-label);
}
@media (max-width: 700px) {
  .ground-key {
    left: 12px;
    right: auto;
    bottom: 12px;
    max-width: calc(100% - 70px);
  }
  .map-actions {
    right: 12px;
    bottom: 12px;
  }
}
</style>
