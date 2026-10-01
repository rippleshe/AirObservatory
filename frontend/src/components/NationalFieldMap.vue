<script setup lang="ts">
import { Minus, Plus, RotateCcw } from "lucide-vue-next";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { init, registerMap, token, type ECharts } from "../lib/charts";
import {
  aqiColor,
  changeColor,
  changeState,
  pm25Color,
} from "../lib/palette";
import type { NationalCity } from "../lib/provinces";

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
const zoom = ref(1.04);
/* Province names are a 12px layer under the city labels; below this width
   they crowd the pins, so they drop out. Tracked as state because a window
   resize must re-render, not keep the value read at mount. */
const wide = ref(true);
let chart: ECharts | null = null;
let observer: ResizeObserver | null = null;
let mapReady: Promise<void> | null = null;
let mapLoaded = false;

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

function metricLabel(city: NationalCity) {
  if (props.metric === "pm25") {
    return city.pm25 == null ? "—" : `${city.pm25.toFixed(0)}`;
  }
  if (props.metric === "change") {
    const state = changeState(city.pm25_change_24h);
    if (city.pm25_change_24h == null) return state.label;
    const value = city.pm25_change_24h;
    return `${state.arrow}${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
  }
  return city.china_aqi == null ? "—" : `${city.china_aqi}`;
}

/* The reading line is a second row on the label, and it doubles the label's
   collision area. It appears only where there is something to read — a
   province that is genuinely polluted, or genuinely moving — so the crowded
   east carries names while the story-carrying provinces carry numbers. */
function hasReading(city: NationalCity) {
  if (props.metric === "pm25") return (city.pm25 ?? 0) > 75;
  if (props.metric === "change") return Math.abs(city.pm25_change_24h ?? 0) >= 25;
  return (city.china_aqi ?? 0) > 100;
}

/* Every province the page plots already carries its city's name, and the two
   label systems — geo regions and scatter series — cannot see each other, so
   printing both put two labels on the same square centimetre (福州 over 福建,
   昆明 over 云南). The province outline still draws the geography and the
   tooltip names the province; the region name is kept only where nothing else
   labels that ground. */
const namedProvinces = computed(
  () => new Set(props.cities.map((city) => shortProvince(city.province || city.name))),
);

/* Mark area tracks the metric so the eye reads magnitude before colour.
   Sizes stay compact — big discs pile up in the eastern cluster and read as
   bubblegum; a thin surface ring separates neighbours by whitespace. */
function markSize(city: NationalCity) {
  const raw = metricValue(city);
  if (raw == null || !Number.isFinite(raw)) return 11;
  const scale = props.metric === "change" ? 40 : props.metric === "pm25" ? 120 : 160;
  return Math.max(11, Math.min(24, 11 + 13 * Math.min(1, Math.abs(raw) / scale)));
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

const labelInfo = new Map<number, { name: string; subLabel: string; h: number }>();
const labelRank = new Map<number, number>();
const geom = new Map<number, Geom>();

function textWidth(text: string, size: number) {
  let width = 0;
  for (const ch of text) {
    width += /[⺀-鿿＀-￯]/.test(ch) ? size : size * 0.56;
  }
  return width;
}

function hits(a: Box, b: Box, gap = 7) {
  return !(
    a.x + a.w + gap <= b.x ||
    b.x + b.w + gap <= a.x ||
    a.y + a.h + gap <= b.y ||
    b.y + b.h + gap <= a.y
  );
}

function ringAnchors(g: Geom, gap: number, lift: number) {
  const { half, w, h } = g;
  const diag = half + gap + 11;
  return [
    { dx: half + gap, dy: -h / 2 }, // right
    { dx: -(half + gap + w), dy: -h / 2 }, // left
    { dx: -w / 2, dy: -(half + gap + h) }, // top
    { dx: -w / 2, dy: half + gap }, // bottom
    { dx: diag, dy: -h - lift }, // upper-right
    { dx: -(diag + w), dy: -h - lift }, // upper-left
    { dx: diag, dy: lift }, // lower-right
    { dx: -(diag + w), dy: lift }, // lower-left
  ];
}

/* Two rings, nearest first. One ring leaves a province unnamed whenever all
   eight positions beside its mark are taken, and in the crowded east that cost
   three of thirty-one names. The outer ring is the escape hatch: a name drifts
   further from its dot rather than disappearing, which is the lesser cost on a
   map whose whole job is naming where to look. */
function anchorsFor(g: Geom) {
  return [...ringAnchors(g, 9, 7), ...ringAnchors(g, 26, 21), ...ringAnchors(g, 46, 40)];
}

/* Severity order, worst first. A label placed early owns its anchor for the
   whole pass, so the provinces the page is about must claim the readable
   positions before the quiet ones take them. */
function placeAll() {
  const placed: Box[] = [];
  const result = new Map<number, { dx: number; dy: number } | null>();
  const order = [...geom.keys()].sort(
    (a, b) => (labelRank.get(a) ?? 0) - (labelRank.get(b) ?? 0),
  );
  for (const index of order) {
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
  const half = (rect.width ?? 24) / 2;
  const boxH = labelRect.height || info.h;
  geom.set(params.dataIndex, {
    cx: (rect.x ?? 0) + half,
    cy: (rect.y ?? 0) + (rect.height ?? 16) / 2,
    half,
    w: labelRect.width || Math.max(textWidth(info.name, 13), textWidth(info.subLabel, 12)) + 16,
    h: boxH,
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

  return { dx: slot.dx - half, dy: slot.dy + boxH / 2, ...settled };
}

function render() {
  if (!chart || !mapLoaded) return;

  labelInfo.clear();
  labelRank.clear();
  geom.clear();

  const cities = props.cities;

  const ranked = cities
    .map((city, index) => ({ index, value: metricValue(city) }))
    .sort((a, b) => (b.value ?? -Infinity) - (a.value ?? -Infinity));
  ranked.forEach((entry, rank) => labelRank.set(entry.index, rank));

  const data = cities.map((city, index) => {
    const state = changeState(city.pm25_change_24h);
    // Level word travels with the colour — never colour alone.
    const reading = hasReading(city);
    const subLabel = !reading
      ? ""
      : props.metric === "change"
        ? `${state.label} ${metricLabel(city)}`
        : `${city.china_aqi_level ?? "暂无"} ${metricLabel(city)}`;
    labelInfo.set(index, { name: city.name, subLabel, h: reading ? 33 : 18 });
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
      province: city.province,
      level: city.china_aqi_level,
      ground: city.has_recent_ground_observation,
      sourceTime: city.source_time,
      primary: city.primary_pollutants,
      metricText: metricLabel(city),
      subLabel,
      symbolSize: markSize(city),
      itemStyle: { color: cityColor(city) },
    };
  });

  const groundData = data
    .filter((item) => item.ground)
    .map((item) => ({
      ...item,
      symbolSize: Number(item.symbolSize) + 7,
      itemStyle: {
        color: "rgba(0,0,0,0)",
        borderColor: token("--ink"),
        borderWidth: 2,
      },
    }));

  /* The catch layer must be truly invisible. Building it from a spread would
     carry each datum's own itemStyle across and paint oversized discs. */
  const hitData = cities.map((city) => ({
    name: city.name,
    value: [city.lon, city.lat],
    locationId: city.location_id,
    level: city.china_aqi_level,
    ground: city.has_recent_ground_observation,
    sourceTime: city.source_time,
    primary: city.primary_pollutants,
    metricText: metricLabel(city),
    symbolSize: Math.max(38, markSize(city) + 10),
    itemStyle: {
      color: "rgba(0,0,0,0)",
      borderColor: "rgba(0,0,0,0)",
      borderWidth: 0,
      opacity: 0,
    },
  }));

  /* Swiss modern luminous chart world: clean, pristine white land, airy sea, slate typography */
  const ink = token("--ink");
  const land = token("--map-land");
  const border = token("--map-border");
  const provinceName = token("--map-name");
  const muted = token("--muted");
  const ring = "#ffffff";
  const labelHalo = "#ffffff";
  const panelBg = "rgba(255, 255, 255, 0.96)";
  const panelEdge = token("--hairline");
  const hoverGround = "#f1f5f9";

  chart.setOption(
    {
      aria: {
        enabled: true,
        description:
          "全国省级空气质量地图，一省一点，取该省当前 AQI 最高的城市。可切换 AQI、PM2.5 与 24 小时变化，点击进入城市详情。",
      },
      animation: !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
      animationDurationUpdate: 320,
      animationEasingUpdate: "cubicOut",
      tooltip: {
        trigger: "item",
        confine: true,
        padding: [14, 15],
        backgroundColor: panelBg,
        borderColor: panelEdge,
        borderWidth: 1,
        textStyle: { color: ink, fontSize: 13, lineHeight: 23 },
        extraCssText: "box-shadow:0 16px 40px rgba(11,21,18,.16);border-radius:10px;",
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
            '<span style="font-size:12px;color:' + muted + '">' + (raw.province ?? "") + "</span>",
            "</div>",
            '<div style="margin-top:9px;font-size:15px;font-weight:700">' + raw.metricText + "</div>",
            '<div style="margin-top:5px;color:' + ink + '"><b>' + (raw.level ?? "暂无") + "</b> · AQI " + (aqi ?? "—") + "</div>",
            '<div style="color:' + muted + '">PM2.5 ' + (pm == null ? "—" : Number(pm).toFixed(1)) + " µg/m³ · 24h " + changeText + "</div>",
            '<div style="color:' + muted + '">主要污染物 ' + primary + "</div>",
            '<div style="margin-top:6px;color:' + muted + ';font-size:12px">更新 ' + fmtTime(raw.sourceTime) + (raw.ground ? " · 有近期地面观测" : "") + "</div>",
            "</div>",
          ].join("");
        },
      },
      geo: {
        map: "china-national",
        roam: true,
        zoom: zoom.value,
        scaleLimit: { min: 0.9, max: 4.5 },
        top: 22,
        bottom: 22,
        left: 18,
        right: 18,
        label: {
          show: wide.value,
          // Province names are the third layer: below the pins, below the
          // readings, printed in ink on paper rather than in gray on mint.
          color: provinceName,
          fontSize: 12,
          formatter: (params: any) => {
            const name = shortProvince(params.name);
            return namedProvinces.value.has(name) ? "" : name;
          },
          // Drop a province name rather than print it over a neighbour.
          labelLayout: { hideOverlap: true },
        },
        /* Cartographic inversion: the stage is the sea, the provinces are
           paper. Pale-on-pale geography is what made the map read as muddy
           low-resolution rendering rather than a drawn chart. */
        itemStyle: {
          areaColor: land,
          borderColor: border,
          borderWidth: 1,
        },
        emphasis: {
          itemStyle: {
            areaColor: hoverGround,
            borderColor: ink,
            borderWidth: 1.6,
          },
          label: {
            color: ink,
            fontSize: 12,
            fontWeight: 700,
          },
        },
        select: { disabled: true },
      },
      series: [
        {
          // Invisible, oversized target under the marks: a catch area so a
          // city can be clicked without landing on the dead centre.
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
            scale: 1.2,
            itemStyle: {
              borderColor: ink,
              borderWidth: 2.5,
              opacity: 1,
            },
            label: {
              show: true,
              color: ink,
              fontSize: 14,
              fontWeight: 700,
              backgroundColor: panelBg,
              borderColor: panelEdge,
              borderWidth: 1,
              borderRadius: 6,
              padding: [5, 8],
            },
          },
          itemStyle: {
            borderColor: ring,
            borderWidth: 2,
            opacity: 1,
          },
          label: {
            show: true,
            position: "right",
            distance: 0,
            align: "left",
            verticalAlign: "middle",
            formatter(params: any) {
              const line2 = params.data.subLabel ?? "";
              return line2
                ? `{city|${params.data.name}}\n{value|${line2}}`
                : `{city|${params.data.name}}`;
            },
            // A ground-coloured halo, not a white glow: letters stay legible
            // over the sea without the sticker outline.
            textBorderColor: labelHalo,
            textBorderWidth: 3,
            rich: {
              city: {
                color: ink,
                fontSize: 13,
                fontWeight: 650,
                lineHeight: 17,
              },
              value: {
                color: token("--ink-soft"),
                fontSize: 12,
                fontWeight: 500,
                lineHeight: 15,
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
  zoom.value = Math.min(4.5, Math.max(0.9, next));
  chart?.setOption({ geo: { zoom: zoom.value } });
}

function resetView() {
  zoom.value = 1.04;
  chart?.setOption({ geo: { zoom: zoom.value } });
}

function syncWidth() {
  const next = (el.value?.clientWidth ?? window.innerWidth) >= 700;
  if (next === wide.value) return;
  wide.value = next;
  render();
}

onMounted(async () => {
  if (!el.value) return;
  chart = init(el.value, undefined, { renderer: "svg" });
  chart.on("click", onClick);
  observer = new ResizeObserver(() => {
    chart?.resize();
    syncWidth();
  });
  observer.observe(el.value);
  syncWidth();
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
    <div
      ref="el"
      class="national-map"
      aria-label="全国省级空气质量地图"
    ></div>

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
/* Flat sea tone, no decorative wash — the stage is a printed chart field. */
.national-map {
  background: var(--map-sea);
}
.map-actions {
  position: absolute;
  z-index: 8;
  right: 22px;
  bottom: 22px;
  display: grid;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.7);
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--shadow-sm);
}
.map-actions button {
  width: 40px;
  height: 38px;
  display: grid;
  place-items: center;
  border: 0;
  border-bottom: 1px solid var(--hairline-soft);
  background: transparent;
  color: var(--ink-soft);
  cursor: pointer;
  transition: all var(--duration-fast) ease;
}
.map-actions button:last-child { border-bottom: 0; }
.map-actions button:hover {
  background: var(--sheet-soft);
  color: var(--ink);
}
.ground-key {
  position: absolute;
  z-index: 7;
  right: 76px;
  bottom: 22px;
  min-height: 38px;
  padding: 0 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid rgba(255, 255, 255, 0.7);
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  color: var(--ink-soft);
  font-size: var(--fs-label);
  box-shadow: var(--shadow-sm);
}
.ground-key i {
  width: 12px;
  height: 12px;
  border: 2px solid var(--ink);
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
