<!-- ModelView — the prediction engine as a living pipeline: real 48h input
     series stream into the engine ring, particles ride the feature flow,
     and the actual next-24h forecasts (CAMS + baselines) fan out on the
     right. Everything on the canvas comes from the API; nothing is staged. -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { api } from "../api/client";
import { expectData } from "../api/request";
import { useLocationCatalog } from "../composables/useLocationCatalog";
import { useContextStore } from "../stores/context";
import { prefersReducedMotion } from "../lib/motion";

const context = useContextStore();
const { locations } = useLocationCatalog();

const locationId = computed(
  () => context.selectedLocationId ?? locations.data.value?.[0]?.location_id ?? 1,
);

const city = computed(
  () => locations.data.value?.find((item) => item.location_id === locationId.value)?.city ?? "",
);

const history = useQuery({
  queryKey: computed(() => ["model-history", locationId.value]),
  queryFn: () =>
    expectData(
      api.GET("/api/locations/{location_id}/series", {
        params: {
          path: { location_id: locationId.value },
          query: { variable: "pm25", data_kind: "model_analysis", hours: 48 },
        },
      }),
    ),
  refetchInterval: 60_000,
});

const weather = useQuery({
  queryKey: computed(() => ["model-weather", locationId.value]),
  queryFn: () =>
    expectData(
      api.GET("/api/overview/national/weather", {
        /* weather archives lag ~5 days: a 48h window is empty, so pull the
           full week and keep the latest 48 valid hours per field */
        params: { query: { hours: 720, location_id: locationId.value } },
      }),
    ),
  staleTime: 15 * 60_000,
});

const forecast = useQuery({
  queryKey: computed(() => ["model-forecast", locationId.value]),
  queryFn: () =>
    expectData(
      api.GET("/api/locations/{location_id}/forecast", {
        params: {
          path: { location_id: locationId.value },
          query: { variable: "pm25" },
        },
      }),
    ),
  refetchInterval: 5 * 60_000,
});

const metrics = useQuery({
  queryKey: computed(() => ["model-metrics", locationId.value]),
  queryFn: () =>
    expectData(
      api.GET("/api/models/{location_id}/metrics", {
        params: { path: { location_id: locationId.value } },
      }),
    ),
  staleTime: 10 * 60_000,
});

type SeriesRow = { time: string; value: number | null };

function valuesOf(rows: SeriesRow[] | undefined): number[] {
  return (rows ?? [])
    .map((row) => row.value)
    .filter((v): v is number => v != null && Number.isFinite(v));
}

function numbersOf(values: Array<number | null> | undefined): number[] {
  return (values ?? []).filter((v): v is number => v != null && Number.isFinite(v));
}

const weatherCity = computed(() => weather.data.value?.cities?.[0]);

type InputNode = {
  key: string;
  label: string;
  unit: string;
  color: string;
  series: number[];
  latest: string;
};

const inputNodes = computed<InputNode[]>(() => {
  const tail = (values: Array<number | null> | undefined) => numbersOf(values).slice(-48);
  const pm = valuesOf(history.data.value?.points as SeriesRow[]);
  const speed = tail(weatherCity.value?.wind_speed);
  const dirSin = tail(weatherCity.value?.wind_direction).map(
    (deg) => Math.sin((deg * Math.PI) / 180),
  );
  const temp = tail(weatherCity.value?.temperature);
  const nodes: InputNode[] = [
    {
      key: "pm25",
      label: "PM2.5 历史",
      unit: "µg/m³",
      color: "#f97316",
      series: pm,
      latest: pm.at(-1)?.toFixed(1) ?? "—",
    },
    {
      key: "wind",
      label: "风速",
      unit: "m/s",
      color: "#10b981",
      series: speed,
      latest: speed.at(-1)?.toFixed(1) ?? "—",
    },
    {
      key: "dirsin",
      label: "风向 sin",
      unit: "",
      color: "#0ea5e9",
      series: dirSin,
      latest: dirSin.at(-1)?.toFixed(2) ?? "—",
    },
    {
      key: "temp",
      label: "气温",
      unit: "°C",
      color: "#ec4899",
      series: temp,
      latest: temp.at(-1)?.toFixed(1) ?? "—",
    },
  ];
  return nodes;
});

/* Forecast fan: primary model carries the band, baselines ride thin. */
const fanModels = computed(() => {
  const series = forecast.data.value?.series ?? [];
  return series
    .map((entry, index) => ({
      name: entry?.model_name ?? `模型 ${index + 1}`,
      primary: index === 0,
      points: (entry?.points ?? []).map((point) => ({
        target: point.target_at,
        value: point.value,
        lower: point.lower_bound,
        upper: point.upper_bound,
      })),
    }))
    .filter((entry) => entry.points.length > 1);
});

const metricRows = computed(() => {
  const rows = metrics.data.value?.metrics ?? [];
  const byModel = new Map<string, { mae: number[]; rmse: number[]; samples: number }>();
  for (const row of rows) {
    const cell = byModel.get(row.model_name) ?? { mae: [], rmse: [], samples: 0 };
    cell.mae.push(row.mae);
    cell.rmse.push(row.rmse);
    cell.samples += row.samples;
    byModel.set(row.model_name, cell);
  }
  const mean = (values: number[]) =>
    values.length ? values.reduce((sum, v) => sum + v, 0) / values.length : 0;
  return [...byModel.entries()].map(([name, cell]) => ({
    name,
    mae: mean(cell.mae),
    rmse: mean(cell.rmse),
    samples: cell.samples,
  }));
});

/* ── canvas stage ── */
const stageEl = ref<HTMLCanvasElement | null>(null);
const wrapEl = ref<HTMLDivElement | null>(null);
let ctx: CanvasRenderingContext2D | null = null;
let running = false;
let raf = 0;
let lastTs = 0;
let stageVisible = true;
let observer: IntersectionObserver | null = null;

type Particle = {
  path: Array<[number, number]>;
  t: number;
  speed: number;
  color: string;
  size: number;
  stage: 0 | 1; // 0 = input→engine, 1 = engine→output
};

const particles: Particle[] = [];
const STAGE_H = 500;

function layout(width: number) {
  const inputX = Math.min(240, width * 0.17);
  const engineX = width * 0.5;
  const outX = width - Math.min(280, width * 0.2);
  const nodeGap = STAGE_H / 4;
  return {
    inputX,
    engineX,
    outX,
    engineY: STAGE_H / 2,
    nodeY: (i: number) => nodeGap * i + nodeGap / 2,
  };
}

function bezier(
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  bend: number,
): Array<[number, number]> {
  const mx = (x0 + x1) / 2;
  return [
    [x0, y0],
    [mx, y0 + bend],
    [mx, y1 - bend],
    [x1, y1],
  ];
}

function cubicAt(path: Array<[number, number]>, t: number): [number, number] {
  const u = 1 - t;
  const [p0, p1, p2, p3] = path;
  const x =
    u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0];
  const y =
    u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1];
  return [x, y];
}

function spawnFromInputs(width: number) {
  const geo = layout(width);
  const nodes = inputNodes.value;
  if (!nodes.length) return;
  const pick = Math.floor(Math.random() * nodes.length);
  const node = nodes[pick]!;
  const y = geo.nodeY(pick);
  particles.push({
    path: bezier(geo.inputX, y, geo.engineX - 86, geo.engineY, (geo.engineY - y) * 0.35),
    t: 0,
    speed: 0.35 + Math.random() * 0.2,
    color: node.color,
    size: 1.8 + Math.random() * 1.4,
    stage: 0,
  });
}

function drawSparkline(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  series: number[],
  color: string,
) {
  if (series.length < 2) return;
  const min = Math.min(...series);
  const max = Math.max(...series);
  const span = Math.max(0.5, max - min);
  ctx.beginPath();
  series.forEach((value, i) => {
    const px = x + (i / (series.length - 1)) * w;
    const py = y + h - ((value - min) / span) * h;
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.6;
  ctx.stroke();
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

const FONT = '500 12px "Inter Tight", "PingFang SC", "Microsoft YaHei", sans-serif';
const FONT_BOLD = '700 13px "Inter Tight", "PingFang SC", "Microsoft YaHei", sans-serif';

function draw(ts: number) {
  if (!running) return;
  raf = requestAnimationFrame(draw);
  const canvas = stageEl.value;
  const ctxRef = canvas?.getContext("2d");
  if (!canvas || !ctxRef || document.hidden || !stageVisible) return;
  ctx = ctxRef;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const cssW = canvas.clientWidth;
  const cssH = canvas.clientHeight;
  if (canvas.width !== Math.round(cssW * dpr) || canvas.height !== Math.round(cssH * dpr)) {
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);
  const dt = Math.min(0.05, (ts - lastTs) / 1000 || 0.016);
  lastTs = ts;

  const geo = layout(cssW);
  const nodes = inputNodes.value;
  const reduced = prefersReducedMotion();

  /* input node cards */
  nodes.forEach((node, i) => {
    const y = geo.nodeY(i);
    const x = 24;
    const w = geo.inputX - 24;
    const h = 74;
    ctx!.fillStyle = "rgba(255,255,255,0.9)";
    ctx!.strokeStyle = "rgba(15,23,42,0.1)";
    roundRect(ctx!, x, y - h / 2, w, h, 10);
    ctx!.fill();
    ctx!.stroke();
    ctx!.fillStyle = "#0f172a";
    ctx!.font = FONT_BOLD;
    ctx!.textAlign = "left";
    ctx!.fillText(node.label, x + 14, y - h / 2 + 20);
    ctx!.font = FONT;
    ctx!.fillStyle = "#64748b";
    ctx!.fillText(`最新 ${node.latest} ${node.unit}`, x + 14, y - h / 2 + 37);
    drawSparkline(ctx!, x + 14, y + 2, w - 28, 22, node.series, node.color);
    /* node port */
    ctx!.fillStyle = node.color;
    ctx!.beginPath();
    ctx!.arc(x + w, y, 3.4, 0, Math.PI * 2);
    ctx!.fill();
  });

  /* flow paths (faint rails) */
  nodes.forEach((_, i) => {
    const y = geo.nodeY(i);
    const path = bezier(geo.inputX, y, geo.engineX - 86, geo.engineY, (geo.engineY - y) * 0.35);
    ctx!.beginPath();
    ctx!.moveTo(path[0]![0], path[0]![1]);
    ctx!.bezierCurveTo(path[1]![0], path[1]![1], path[2]![0], path[2]![1], path[3]![0], path[3]![1]);
    ctx!.strokeStyle = "rgba(15,23,42,0.07)";
    ctx!.lineWidth = 1.2;
    ctx!.stroke();
  });

  /* engine ring */
  ctx!.save();
  ctx!.translate(geo.engineX, geo.engineY);
  ctx!.rotate(ts / 4200);
  ctx!.setLineDash([10, 8]);
  ctx!.lineWidth = 1.6;
  ctx!.strokeStyle = "rgba(15,23,42,0.35)";
  ctx!.beginPath();
  ctx!.arc(0, 0, 86, 0, Math.PI * 2);
  ctx!.stroke();
  ctx!.restore();
  ctx!.setLineDash([]);
  ctx!.beginPath();
  ctx!.arc(geo.engineX, geo.engineY, 62, 0, Math.PI * 2);
  ctx!.fillStyle = "rgba(255,255,255,0.95)";
  ctx!.fill();
  ctx!.strokeStyle = "rgba(15,23,42,0.12)";
  ctx!.stroke();
  ctx!.fillStyle = "#0f172a";
  ctx!.font = FONT_BOLD;
  ctx!.textAlign = "center";
  ctx!.fillText(city.value || "—", geo.engineX, geo.engineY - 8);
  ctx!.font = FONT;
  ctx!.fillStyle = "#64748b";
  ctx!.fillText("特征工程", geo.engineX, geo.engineY + 12);
  ctx!.fillText("CAMS · 基线", geo.engineX, geo.engineY + 28);

  /* output fan */
  const fanW = Math.min(250, cssW - geo.outX - 20);
  const fanH = 300;
  const fanY = (STAGE_H - fanH) / 2;
  const fan = { x: geo.outX, y: fanY, w: fanW, h: fanH };
  const models = fanModels.value;
  if (models.length && fanW > 120) {
    const primary = models[0]!;
    const horizon = primary.points.length;
    const all = models.flatMap((m) => m.points.map((p) => p.value));
    const vMin = Math.min(0, ...all) * 0.9;
    const vMax = Math.max(...all) * 1.1;
    const px = (i: number) => geo.outX + (i / (horizon - 1)) * fanW;
    const py = (v: number) => fanY + fanH - ((v - vMin) / (vMax - vMin)) * fanH;
    const lower = primary.points.map((p, i) => [px(i), py(p.lower ?? p.value)] as [number, number]);
    const upper = primary.points.map((p, i) => [px(i), py(p.upper ?? p.value)] as [number, number]);
    ctx!.beginPath();
    lower.forEach(([x, y], i) => (i === 0 ? ctx!.moveTo(x, y) : ctx!.lineTo(x, y)));
    for (let i = upper.length - 1; i >= 0; i--) ctx!.lineTo(upper[i]![0], upper[i]![1]);
    ctx!.closePath();
    ctx!.fillStyle = "rgba(217, 119, 6, 0.13)";
    ctx!.fill();
    primary.points.forEach((point, i) => {
      if (i === 0) return;
      ctx!.beginPath();
      ctx!.moveTo(px(i - 1), py(primary.points[i - 1]!.value));
      ctx!.lineTo(px(i), py(point.value));
      ctx!.strokeStyle = "#d97706";
      ctx!.lineWidth = 2;
      ctx!.stroke();
    });
    models.slice(1).forEach((model) => {
      ctx!.beginPath();
      model.points.forEach((point, i) => {
        const x = geo.outX + (i / (model.points.length - 1)) * fanW;
        const y = py(point.value);
        if (i === 0) ctx!.moveTo(x, y);
        else ctx!.lineTo(x, y);
      });
      ctx!.strokeStyle = "rgba(100, 116, 139, 0.5)";
      ctx!.lineWidth = 1.2;
      ctx!.stroke();
    });
    ctx!.fillStyle = "#64748b";
    ctx!.font = FONT;
    ctx!.textAlign = "left";
    ctx!.fillText("未来 24h", geo.outX, fanY - 10);
    /* output rail for stage-1 particles */
    ctx!.beginPath();
    ctx!.moveTo(geo.engineX + 86, geo.engineY);
    ctx!.bezierCurveTo(
      (geo.engineX + geo.outX) / 2,
      geo.engineY,
      (geo.engineX + geo.outX) / 2,
      fanY + fanH / 2,
      geo.outX,
      fanY + fanH / 2,
    );
    ctx!.strokeStyle = "rgba(15,23,42,0.07)";
    ctx!.lineWidth = 1.2;
    ctx!.stroke();
  }

  /* particles */
  if (!reduced) {
    if (Math.random() < 0.5 && particles.length < 240) spawnFromInputs(cssW);
    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i]!;
      p.t += p.speed * dt;
      if (p.t >= 1) {
        if (p.stage === 0) {
          /* absorbed by the engine, re-emitted toward the output fan */
          const y0 = geo.engineY + (Math.random() - 0.5) * 40;
          particles.splice(i, 1);
          particles.push({
            path: bezier(
              geo.engineX + 86,
              y0,
              fan.x + 8,
              fan.y + fan.h / 2 + (Math.random() - 0.5) * fan.h * 0.5,
              0,
            ),
            t: 0,
            speed: 0.3 + Math.random() * 0.2,
            color: "#d97706",
            size: p.size,
            stage: 1,
          });
        } else {
          particles.splice(i, 1);
        }
        continue;
      }
      const [x, y] = cubicAt(p.path, p.t);
      ctx!.beginPath();
      ctx!.arc(x, y, p.size, 0, Math.PI * 2);
      ctx!.fillStyle = p.color;
      ctx!.globalAlpha = p.stage === 0 ? 0.55 + p.t * 0.35 : 0.9 - p.t * 0.4;
      ctx!.fill();
      ctx!.globalAlpha = 1;
    }
  }
}

function start() {
  if (running) return;
  running = true;
  lastTs = performance.now();
  raf = requestAnimationFrame(draw);
}

function stop() {
  running = false;
  cancelAnimationFrame(raf);
}

onMounted(() => {
  if (!stageEl.value) return;
  observer = new IntersectionObserver(
    (entries) => {
      stageVisible = entries[0]?.isIntersecting ?? true;
      if (stageVisible) start();
      else stop();
    },
    { rootMargin: "80px" },
  );
  observer.observe(stageEl.value);
  start();
});

onBeforeUnmount(() => {
  observer?.disconnect();
  stop();
});

watch([locationId], () => {
  particles.length = 0;
});
</script>

<template>
  <section class="model-view">
    <header class="model-head">
      <h1 class="page-title">预测引擎</h1>
      <span class="head-meta data-mono">{{ city }} · CAMS + 基线 · 实时管线</span>
    </header>

    <div ref="wrapEl" class="stage-wrap">
      <canvas ref="stageEl" class="stage"></canvas>
    </div>

    <section class="metric-strip">
      <span class="mini-label">模型对照</span>
      <div class="metric-rows">
        <div v-for="row in metricRows" :key="row.name" class="metric-row">
          <b>{{ row.name }}</b>
          <span class="data-mono">MAE {{ row.mae.toFixed(2) }}</span>
          <span class="data-mono">RMSE {{ row.rmse.toFixed(2) }}</span>
          <span class="data-mono faint">N {{ row.samples }}</span>
        </div>
        <div v-if="!metricRows.length" class="metric-empty">样本积累中</div>
      </div>
    </section>
  </section>
</template>

<style scoped>
.model-view {
  min-height: calc(100vh - 64px);
  padding: 28px var(--page-pad) 56px;
  display: grid;
  gap: 22px;
  align-content: start;
  background: var(--canvas);
}

.model-head {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 18px;
}

.page-title {
  margin: 0;
  color: var(--muted);
  font-size: 11.5px;
  font-weight: var(--fw-strong);
  letter-spacing: 0.2em;
}

.head-meta {
  color: var(--faint);
  font-size: 11px;
}

.stage-wrap {
  position: relative;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-xl);
  background: radial-gradient(130% 100% at 50% 0%, #eef3f9 0%, #e8eef5 55%, #e2eaf2 100%);
  overflow: hidden;
}

.stage {
  display: block;
  width: 100%;
  height: 500px;
}

.metric-strip {
  display: grid;
  gap: 10px;
  justify-items: center;
}

.mini-label {
  color: var(--muted);
  font-size: 11px;
  font-weight: var(--fw-strong);
  letter-spacing: 0.18em;
}

.metric-rows {
  display: grid;
  gap: 6px;
  min-width: min(520px, 100%);
}

.metric-row {
  display: grid;
  grid-template-columns: 9em 1fr 1fr 4em;
  gap: 18px;
  padding: 9px 16px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: var(--sheet);
  align-items: center;
}

.metric-row b {
  color: var(--ink);
  font-size: 12.5px;
  font-weight: var(--fw-strong);
}

.metric-row span {
  color: var(--ink-soft);
  font-size: 12px;
}

.metric-row .faint {
  color: var(--faint);
}

.metric-empty {
  color: var(--muted);
  font-size: 12px;
  padding: 8px 0;
}
</style>
