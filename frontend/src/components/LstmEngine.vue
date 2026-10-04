<!-- LstmEngine — the engine page as one instrument plus a decode act.
     单元计算: the input tape (the exact feature vectors the cell consumed)
     and the six activation lanes (forget / input / output / candidate gates,
     cell state, hidden state — recorded from a genuine forward pass of the
     trained numpy LSTM) share one axis and one cursor; the schematic cell on
     the right redraws the current timestep with colah's grammar, gate values
     modulating flow weight. 解码: the dense head's 24h forecast and the
     MAE-vs-horizon race against the baselines evaluated on the same windows. -->
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useElementSize } from "../lib/viz";
import { gsap, prefersReducedMotion } from "../lib/motion";

export type LstmStepData = {
  target_at: string;
  x: number[];
  f: number[];
  i: number[];
  o: number[];
  g: number[];
  cell: number[];
  hidden: number[];
};

export type LstmMetricRow = {
  model_name: string;
  model_revision: string;
  horizon_hours: number;
  samples: number;
  mae: number;
  rmse: number;
};

export type LstmForecastPointData = {
  target_at: string;
  horizon_hours: number;
  value: number;
};

export type LstmRun = {
  location_id: number;
  city: string;
  unit: string;
  hidden: number;
  window_hours: number;
  replay_hours: number;
  feature_names: string[];
  steps: LstmStepData[];
  forecast: LstmForecastPointData[];
  metrics: LstmMetricRow[];
  meta: {
    version?: string | null;
    trained_at?: string | null;
    eval_basis: string;
    params: number;
    epochs?: number | null;
  };
};

const props = defineProps<{
  run: LstmRun;
  /* CAMS/baseline forecasts for the decode act (optional; the LSTM lane
     comes from the run itself). */
  cams?: Array<{
    name: string;
    points: { target: string; value: number; lower: number | null; upper: number | null }[];
  }>;
}>();

const root = ref<HTMLElement | null>(null);
const fanEl = ref<HTMLElement | null>(null);
const size = useElementSize(root);
const fanSize = useElementSize(fanEl);

const ACCENT = "#0284c7";
const WARM = "#f97316";
const COOL = "#2563eb";
const MUTED = "#94a3b8";

const steps = computed(() => props.run.steps);
const T = computed(() => steps.value.length);
const H = computed(() => props.run.hidden || 16);

function fmtTime(iso: string): string {
  const at = new Date(iso);
  return `${at.getMonth() + 1}/${at.getDate()} ${String(at.getHours()).padStart(2, "0")}:00`;
}

function fmtDay(iso: string): string {
  const at = new Date(iso);
  return `${at.getMonth() + 1}/${at.getDate()}`;
}

/* ── the instrument: input tape + activation lanes on one shared axis ── */
const INPUT_LANES = [
  { index: 0, label: "PM2.5", unit: "µg/m³", color: "#f97316" },
  { index: 1, label: "气温", unit: "°C", color: "#ec4899" },
  { index: 2, label: "湿度", unit: "%", color: "#10b981" },
  { index: 3, label: "风速", unit: "m/s", color: "#0ea5e9" },
  { index: 6, label: "边界层", unit: "m", color: "#8b5cf6" },
];

function laneSeries(lane: (typeof INPUT_LANES)[number]): number[] {
  return steps.value.map((step) => step.x[lane.index] ?? 0);
}

type LaneKey = "f" | "i" | "o" | "g" | "cell" | "hidden";

const LANES: Array<{ key: LaneKey; label: string; diverging: boolean; hint: string }> = [
  { key: "f", label: "遗忘门", diverging: false, hint: "0→1" },
  { key: "i", label: "输入门", diverging: false, hint: "0→1" },
  { key: "o", label: "输出门", diverging: false, hint: "0→1" },
  { key: "g", label: "候选", diverging: true, hint: "-1↔1" },
  { key: "cell", label: "细胞状态", diverging: true, hint: "记忆" },
  { key: "hidden", label: "隐状态", diverging: true, hint: "输出" },
];

const GUTTER = 78;
const INPUT_H = 30;
const LANE_H = 62;

const cursor = ref(0);
const playing = ref(false);
let playTimer: number | null = null;

function stopPlay() {
  playing.value = false;
  if (playTimer != null) window.clearInterval(playTimer);
  playTimer = null;
}

function togglePlay() {
  if (playing.value) {
    stopPlay();
    return;
  }
  if (!prefersReducedMotion()) {
    playing.value = true;
    playTimer = window.setInterval(() => {
      cursor.value = cursor.value + 1 >= T.value ? 0 : cursor.value + 1;
    }, 150);
  }
}

watch(() => props.run, stopPlay);
onBeforeUnmount(stopPlay);

const plotW = computed(() => Math.max(360, (size.value.w || 980) * 0.6 - GUTTER));
const cellW = computed(() => plotW.value / Math.max(1, T.value));
const unitH = computed(() => LANE_H / Math.max(1, H.value));

function laneValues(key: LaneKey): number[][] {
  return steps.value.map((step) => step[key] as number[]);
}

const laneExtents = computed(() => {
  const out = {} as Record<LaneKey, number>;
  for (const lane of LANES) {
    if (!lane.diverging) continue;
    const magnitudes: number[] = [];
    for (const row of laneValues(lane.key)) {
      for (const v of row) magnitudes.push(Math.abs(v));
    }
    magnitudes.sort((a, b) => a - b);
    out[lane.key] = Math.max(0.3, magnitudes[Math.floor(magnitudes.length * 0.9)] ?? 1);
  }
  return out;
});

function cellFill(lane: (typeof LANES)[number], value: number): { color: string; opacity: number } {
  if (!lane.diverging) {
    return { color: ACCENT, opacity: 0.05 + 0.92 * value };
  }
  const max = laneExtents.value[lane.key] ?? 1;
  return {
    color: value >= 0 ? WARM : COOL,
    opacity: 0.04 + 0.9 * Math.min(1, Math.abs(value) / max),
  };
}

const axisTicks = computed(() => {
  const n = T.value;
  if (n < 2) return [];
  const picks = [0, Math.round(n / 3), Math.round((n * 2) / 3), n - 1];
  const seen = new Set<number>();
  const out: Array<{ frac: number; label: string; anchor: string }> = [];
  for (const i of picks) {
    if (seen.has(i)) continue;
    seen.add(i);
    out.push({
      frac: i / (n - 1),
      label: fmtDay(steps.value[i]!.target_at),
      anchor: i === 0 ? "start" : i === n - 1 ? "end" : "middle",
    });
  }
  return out;
});

const currentStep = computed(() => steps.value[Math.min(cursor.value, T.value - 1)]);

const meanAt = (row: number[] | undefined) =>
  row && row.length ? row.reduce((sum, v) => sum + v, 0) / row.length : 0;

/* ── the schematic cell: one timestep, colah's grammar ── */
const diagram = computed(() => {
  const step = currentStep.value;
  if (!step) return null;
  const prev = cursor.value > 0 ? steps.value[cursor.value - 1]! : null;
  const cellPrev = prev ? meanAt(prev.cell) : 0;
  const f = meanAt(step.f);
  return {
    time: fmtTime(step.target_at),
    f,
    i: meanAt(step.i),
    o: meanAt(step.o),
    g: meanAt(step.g),
    cellPrev,
    cell: meanAt(step.cell),
    hidden: meanAt(step.hidden),
    retained: (cellPrev * f) / (laneExtents.value.cell ?? 1),
    written: Math.abs(meanAt(step.i) * meanAt(step.g)),
  };
});

const fmt = (v: number) => v.toFixed(2);
const cellNorm = (v: number) => Math.min(1, Math.abs(v) / (laneExtents.value.cell ?? 1));
const hiddenNorm = (v: number) => Math.min(1, Math.abs(v) / (laneExtents.value.hidden ?? 1));
const flowW = (frac: number) => 1 + 6 * Math.min(1, Math.max(0, frac));
const flowO = (v: number) => 0.18 + 0.7 * Math.min(1, Math.max(0.05, v));

/* scrubbing + per-cell hover readout */
const hovered = ref<{ t: number; unit: number; label: string; value: number } | null>(null);

function locate(event: PointerEvent): { t: number; unit: number; localY: number } {
  const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
  const t = Math.max(0, Math.min(T.value - 1, Math.floor((event.clientX - box.left - GUTTER) / cellW.value)));
  const localY = event.clientY - box.top;
  const unit = Math.max(0, Math.min(H.value - 1, Math.floor((localY - INPUT_BLOCK_H) / unitH.value)));
  return { t, unit, localY };
}

const INPUT_BLOCK_H = INPUT_LANES.length * (INPUT_H + 5) + 26;

function onScrubDown(event: PointerEvent) {
  stopPlay();
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  cursor.value = locate(event).t;
}

function onScrubMove(event: PointerEvent) {
  const { t, unit, localY } = locate(event);
  const overGates = localY > INPUT_BLOCK_H;
  let label = "";
  let value = 0;
  if (overGates) {
    const laneIndex = Math.floor((localY - INPUT_BLOCK_H) / (LANE_H + 8));
    const lane = LANES[Math.max(0, Math.min(LANES.length - 1, laneIndex))]!;
    label = lane.label;
    value = (steps.value[t]![lane.key] as number[])[unit] ?? 0;
    hovered.value = { t, unit, label, value };
  } else {
    const inputIndex = Math.max(
      0,
      Math.min(INPUT_LANES.length - 1, Math.floor((localY - 22) / (INPUT_H + 5))),
    );
    const lane = INPUT_LANES[inputIndex]!;
    label = lane.label;
    value = steps.value[t]!.x[lane.index] ?? 0;
    hovered.value = { t, unit: 0, label, value };
  }
  if (event.buttons === 1) cursor.value = t;
}

function onScrubLeave() {
  hovered.value = null;
}

const hoverTip = computed(() => {
  if (!hovered.value) return null;
  const step = steps.value[hovered.value.t];
  if (!step) return null;
  const text = `${fmtTime(step.target_at)} · ${hovered.value.label} ${fmt(hovered.value.value)}`;
  return { left: GUTTER + hovered.value.t * cellW.value, text };
});

/* ── 解码 × 对照 ── */
const DECODE_H = 150;
const decodeW = computed(() => Math.max(420, fanSize.value.w || 600));

const decodeModels = computed(() => {
  const models: Array<{ name: string; color: string; width: number; points: { value: number; lower: number | null; upper: number | null }[] }> = [
    {
      name: "LSTM",
      color: ACCENT,
      width: 2.2,
      points: props.run.forecast.map((p) => ({ value: p.value, lower: null, upper: null })),
    },
  ];
  for (const model of props.cams ?? []) {
    if (!model.points.length) continue;
    const isCams = model.name === "CAMS";
    models.push({
      name: model.name,
      color: isCams ? "#d97706" : MUTED,
      width: isCams ? 1.8 : 1.1,
      points: model.points,
    });
  }
  return models.filter((m) => m.points.length > 1);
});

const decodeScale = computed(() => {
  const all = decodeModels.value.flatMap((m) => m.points.map((p) => p.value));
  if (!all.length) return { min: 0, max: 1 };
  const pad = Math.max(1, (Math.max(...all) - Math.min(...all)) * 0.12);
  return { min: Math.min(...all) - pad, max: Math.max(...all) + pad };
});

const METRIC_MODELS = [
  { name: "LSTM", color: ACCENT },
  { name: "Persistence", color: MUTED },
  { name: "Rolling Mean", color: MUTED },
];

const maeScale = computed(() => {
  const all = props.run.metrics.map((row) => row.mae);
  if (!all.length) return { min: 0, max: 1 };
  return { min: 0, max: Math.max(...all) * 1.15 };
});

const maeModels = computed(() =>
  METRIC_MODELS.map((model) => {
    const rows = props.run.metrics
      .filter((row) => row.model_name === model.name)
      .sort((a, b) => a.horizon_hours - b.horizon_hours);
    return {
      ...model,
      points: rows.map((row) => ({ h: row.horizon_hours, mae: row.mae })),
      terminal: rows.at(-1)?.mae ?? null,
      samples: rows[0]?.samples ?? 0,
    };
  }).filter((model) => model.points.length > 1),
);

const metaLine = computed(() => {
  const meta = props.run.meta;
  const trained = meta.trained_at ? fmtTime(meta.trained_at) : "—";
  return `H=${props.run.hidden} · 参数 ${meta.params.toLocaleString()} · 训练至 ${trained} · 评估=${meta.eval_basis === "cams_analysis" ? "CAMS 分析场" : meta.eval_basis} · N=${maeModels.value[0]?.samples ?? 0}`;
});

/* entrance: the lanes wipe in once */
let revealed = false;
watch(
  () => props.run.location_id,
  () => {
    revealed = false;
  },
);
watch(
  [size, steps],
  () => {
    if (revealed || !size.value.w || prefersReducedMotion()) return;
    revealed = true;
    requestAnimationFrame(() => {
      const lanes = root.value?.querySelectorAll("[data-lane]");
      if (lanes?.length) {
        gsap.fromTo(
          lanes,
          { autoAlpha: 0, y: 10 },
          { autoAlpha: 1, y: 0, duration: 0.6, stagger: 0.04, ease: "power2.out", clearProps: "transform" },
        );
      }
    });
  },
  { immediate: true },
);
</script>

<template>
  <div ref="root" class="lstm-engine">
    <p class="group-label">单元计算</p>

    <div class="compute-row">
      <!-- the instrument: tape + gates on one axis, one cursor -->
      <div class="instrument">
        <header class="tape-head">
          <button
            type="button"
            class="play"
            :aria-label="playing ? '暂停回放' : '回放计算'"
            @click="togglePlay"
          >
            <svg v-if="playing" viewBox="0 0 16 16" aria-hidden="true"><rect x="3" y="2.5" width="3.4" height="11" rx="1" /><rect x="9.6" y="2.5" width="3.4" height="11" rx="1" /></svg>
            <svg v-else viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2.6 L13.2 8 L4 13.4 Z" /></svg>
          </button>
          <span class="cursor-time data-mono">{{ diagram?.time }}</span>
          <span class="tape-hint">{{ T }} 步 × {{ H }} 单元 · 真实前向 · 拖拽游标</span>
        </header>

        <div class="tape-block" @pointerdown="onScrubDown" @pointermove="onScrubMove" @pointerleave="onScrubLeave">
          <span
            v-for="(tick, i) in axisTicks"
            :key="`tick-${i}`"
            class="tape-tick data-mono"
            :style="{
              left: `${GUTTER + tick.frac * plotW}px`,
              transform: tick.anchor === 'start' ? 'none' : tick.anchor === 'end' ? 'translateX(-100%)' : 'translateX(-50%)',
            }"
          >{{ tick.label }}</span>

          <!-- input tape -->
          <div
            v-for="lane in INPUT_LANES"
            :key="`in-${lane.label}`"
            data-lane
            class="input-lane"
            :style="{ height: `${INPUT_H}px` }"
          >
            <span class="lane-label">{{ lane.label }}</span>
            <svg class="lane-svg" :viewBox="`0 0 ${T} 30`" preserveAspectRatio="none">
              <polyline
                :points="laneSeries(lane)
                  .map((v, i, arr) => {
                    const min = Math.min(...arr);
                    const max = Math.max(...arr);
                    const y = 28 - ((v - min) / Math.max(0.5, max - min)) * 26;
                    return `${i},${y.toFixed(1)}`;
                  })
                  .join(' ')"
                :fill="lane.color"
                fill-opacity="0.08"
                :stroke="lane.color"
                stroke-width="0.5"
                vector-effect="non-scaling-stroke"
              />
            </svg>
          </div>

          <div class="tape-divider" aria-hidden="true"></div>

          <!-- activation lanes -->
          <div
            v-for="lane in LANES"
            :key="lane.key"
            data-lane
            class="heat-lane"
            :style="{ height: `${LANE_H}px` }"
          >
            <span class="lane-label">{{ lane.label }}<small>{{ lane.hint }}</small></span>
            <svg
              class="lane-svg heat-svg"
              :height="LANE_H"
              :viewBox="`0 0 ${T * 10} ${LANE_H}`"
              preserveAspectRatio="none"
            >
              <template v-for="(row, t) in laneValues(lane.key)" :key="`${lane.key}-c${t}`">
                <rect
                  v-for="(v, u) in row"
                  :key="u"
                  :x="t * 10"
                  :y="u * (LANE_H / H)"
                  :width="10.7"
                  :height="LANE_H / H + 0.6"
                  :fill="cellFill(lane, v).color"
                  :fill-opacity="cellFill(lane, v).opacity"
                />
              </template>
            </svg>
          </div>

          <!-- the one cursor -->
          <div
            class="tape-cursor"
            :style="{ left: `${GUTTER + cursor * cellW}px` }"
            aria-hidden="true"
          ></div>

          <div v-if="hoverTip" class="tape-tip data-mono" :style="{ left: `${Math.min(hoverTip.left + 10, GUTTER + plotW - 170)}px` }">
            {{ hoverTip.text }}
          </div>
        </div>
      </div>

      <!-- the schematic cell -->
      <aside class="cell-side">
        <svg class="cell-svg" viewBox="0 0 460 310">
          <rect x="14" y="18" width="432" height="272" rx="14" class="cell-boundary" />

          <!-- memory lane -->
          <text x="34" y="102" class="d-label">c₋₁</text>
          <text x="34" y="120" class="d-value data-mono">{{ fmt(diagram?.cellPrev ?? 0) }}</text>
          <line x1="62" y1="115" x2="112" y2="115" class="flow memory" :stroke-width="flowW(cellNorm(diagram?.cellPrev ?? 0))" :stroke-opacity="flowO(cellNorm(diagram?.cellPrev ?? 0))" />

          <circle cx="126" cy="115" r="12" class="node" />
          <text x="126" y="120" text-anchor="middle" class="d-op">×</text>
          <rect x="95" y="158" width="62" height="26" rx="8" class="pill" :class="{ hot: (diagram?.f ?? 0) > 0.5 }" />
          <text x="126" y="175" text-anchor="middle" class="pill-text">遗忘 <tspan class="d-value data-mono">{{ fmt(diagram?.f ?? 0) }}</tspan></text>
          <line x1="126" y1="157" x2="126" y2="128" class="flow accent" :stroke-width="flowW(diagram?.f ?? 0)" :stroke-opacity="flowO(diagram?.f ?? 0)" />

          <line x1="138" y1="115" x2="233" y2="115" class="flow memory" :stroke-width="flowW(Math.abs(diagram?.retained ?? 0))" :stroke-opacity="flowO(Math.abs(diagram?.retained ?? 0))" />

          <circle cx="246" cy="115" r="12" class="node" />
          <text x="246" y="121" text-anchor="middle" class="d-op">+</text>

          <text x="272" y="132" class="d-label">c</text>
          <text x="272" y="148" class="d-value data-mono">{{ fmt(diagram?.cell ?? 0) }}</text>
          <line x1="258" y1="115" x2="304" y2="115" class="flow memory" :stroke-width="flowW(cellNorm(diagram?.cell ?? 0))" :stroke-opacity="flowO(cellNorm(diagram?.cell ?? 0))" />

          <rect x="304" y="100" width="54" height="30" rx="8" class="tanh-box" />
          <text x="331" y="120" text-anchor="middle" class="d-op">tanh</text>
          <line x1="331" y1="99" x2="331" y2="82" class="flow" stroke-width="1.6" stroke-opacity="0.7" />

          <circle cx="331" cy="70" r="12" class="node" />
          <text x="331" y="75" text-anchor="middle" class="d-op">×</text>
          <rect x="365" y="40" width="62" height="26" rx="8" class="pill" :class="{ hot: (diagram?.o ?? 0) > 0.5 }" />
          <text x="396" y="57" text-anchor="middle" class="pill-text">输出 <tspan class="d-value data-mono">{{ fmt(diagram?.o ?? 0) }}</tspan></text>
          <line x1="365" y1="53" x2="343" y2="62" class="flow accent" :stroke-width="flowW(diagram?.o ?? 0)" :stroke-opacity="flowO(diagram?.o ?? 0)" />
          <line x1="343" y1="70" x2="414" y2="70" class="flow accent" :stroke-width="flowW(hiddenNorm(diagram?.hidden ?? 0) + 0.25)" :stroke-opacity="flowO(hiddenNorm(diagram?.hidden ?? 0))" />
          <text x="420" y="74" class="d-label">h</text>
          <text x="420" y="90" class="d-value data-mono">{{ fmt(diagram?.hidden ?? 0) }}</text>

          <!-- bottom branch: input gate ⊗ candidate, then up into the merge -->
          <text x="34" y="249" class="d-label">xₜ</text>
          <line x1="52" y1="244" x2="70" y2="244" class="flow" stroke-width="1.6" stroke-opacity="0.6" />
          <path d="M70 244 L70 229 L91 229" class="flow thin" fill="none" />
          <path d="M70 244 L70 265 L91 265" class="flow thin" fill="none" />
          <rect x="92" y="216" width="62" height="26" rx="8" class="pill" :class="{ hot: (diagram?.i ?? 0) > 0.5 }" />
          <text x="123" y="233" text-anchor="middle" class="pill-text">输入 <tspan class="d-value data-mono">{{ fmt(diagram?.i ?? 0) }}</tspan></text>
          <rect x="92" y="252" width="62" height="26" rx="8" class="pill" />
          <text x="123" y="269" text-anchor="middle" class="pill-text">候选 <tspan class="d-value data-mono">{{ fmt(diagram?.g ?? 0) }}</tspan></text>
          <line x1="154" y1="229" x2="238" y2="238" class="flow accent" :stroke-width="flowW(diagram?.i ?? 0)" :stroke-opacity="flowO(diagram?.i ?? 0)" />
          <line x1="154" y1="265" x2="238" y2="250" class="flow accent" :stroke-width="flowW(Math.abs(diagram?.g ?? 0))" :stroke-opacity="flowO(Math.abs(diagram?.g ?? 0))" />
          <circle cx="246" cy="244" r="11" class="node" />
          <text x="246" y="249" text-anchor="middle" class="d-op">×</text>
          <path d="M246 232 L246 128" class="flow accent" fill="none" :stroke-width="flowW(diagram?.written ?? 0)" :stroke-opacity="flowO(diagram?.written ?? 0)" />
        </svg>
        <p class="equation data-mono">c = f·c₋₁ + i·g &nbsp;·&nbsp; h = o·tanh(c) &nbsp;·&nbsp; 16 单元均值</p>
      </aside>
    </div>

    <!-- 解码 × 对照 -->
    <p class="group-label">解码 × 对照</p>
    <div class="decode-row">
      <div ref="fanEl" class="decode-fan">
        <svg :width="decodeW" :height="DECODE_H + 24" :viewBox="`0 0 ${decodeW} ${DECODE_H + 24}`">
          <template v-for="model in decodeModels" :key="model.name">
            <template v-if="model.points[0]?.lower != null">
              <polygon
                :points="[
                  ...model.points.map((p, i) => `${(i / (model.points.length - 1)) * decodeW},${(DECODE_H - ((p.lower ?? p.value) - decodeScale.min) / (decodeScale.max - decodeScale.min) * DECODE_H).toFixed(1)}`),
                  ...[...model.points].reverse().map((p, i) => `${decodeW - (i / (model.points.length - 1)) * decodeW},${(DECODE_H - ((p.upper ?? p.value) - decodeScale.min) / (decodeScale.max - decodeScale.min) * DECODE_H).toFixed(1)}`),
                ].join(' ')"
                :fill="model.color"
                fill-opacity="0.1"
              />
            </template>
            <polyline
              :points="model.points
                .map((p, i) => `${(i / (model.points.length - 1)) * decodeW},${(DECODE_H - ((p.value - decodeScale.min) / (decodeScale.max - decodeScale.min)) * DECODE_H).toFixed(1)}`)
                .join(' ')"
              fill="none"
              :stroke="model.color"
              :stroke-width="model.width"
              stroke-linejoin="round"
              stroke-linecap="round"
            />
            <text
              :x="decodeW - 3"
              :y="(DECODE_H - ((model.points.at(-1)!.value - decodeScale.min) / (decodeScale.max - decodeScale.min)) * DECODE_H - 5).toFixed(1)"
              text-anchor="end"
              :fill="model.color === MUTED ? 'var(--muted)' : model.color"
              class="decode-name"
            >{{ model.name }}</text>
          </template>
          <text x="0" :y="DECODE_H + 18" class="decode-axis data-mono">+1h</text>
          <text :x="decodeW" :y="DECODE_H + 18" text-anchor="end" class="decode-axis data-mono">+24h</text>
        </svg>
      </div>

      <div class="mae-ledger">
        <svg viewBox="0 0 240 130" class="mae-svg">
          <template v-for="(model, mi) in maeModels" :key="model.name">
            <polyline
              :points="model.points
                .map((p) => `${((p.h - 1) / 23) * 200 + 8},${118 - ((p.mae - maeScale.min) / (maeScale.max - maeScale.min)) * 100}`)
                .join(' ')"
              fill="none"
              :stroke="model.color"
              :stroke-width="model.name === 'LSTM' ? 2 : 1.1"
              :stroke-dasharray="model.name === 'LSTM' ? undefined : '3 3'"
              stroke-linecap="round"
            />
            <text
              x="212"
              :y="118 - (((model.terminal ?? 0) - maeScale.min) / (maeScale.max - maeScale.min)) * 100 + 3 + (mi - 1) * 11"
              :fill="model.name === 'LSTM' ? ACCENT : 'var(--muted)'"
              class="decode-name data-mono"
            >{{ model.terminal?.toFixed(1) }}</text>
          </template>
        </svg>
        <p class="mae-caption">MAE (µg/m³) 随时效 1→24h · 终值标注</p>
      </div>
    </div>

    <p class="engine-meta data-mono">{{ metaLine }}</p>
  </div>
</template>

<style scoped>
.lstm-engine {
  display: grid;
  gap: 26px;
  min-width: 0;
}

.group-label {
  margin: 0;
  text-align: center;
  color: var(--muted);
  font-size: 11.5px;
  font-weight: var(--fw-strong);
  letter-spacing: 0.2em;
}

/* ── the instrument ── */
.compute-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 470px);
  gap: 34px;
  align-items: center;
}

.instrument {
  min-width: 0;
}

.tape-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.play {
  width: 30px;
  height: 30px;
  flex: none;
  display: grid;
  place-items: center;
  border: 1px solid var(--hairline);
  border-radius: 50%;
  background: var(--sheet);
  color: var(--ink);
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: all var(--duration-fast) ease;
}

.play:hover {
  background: var(--ink);
  color: #ffffff;
}

.play svg {
  width: 12px;
  height: 12px;
  fill: currentColor;
}

.cursor-time {
  color: var(--ink);
  font-size: 13.5px;
  font-weight: 700;
}

.tape-hint {
  margin-left: auto;
  color: var(--faint);
  font-size: 10.5px;
}

.tape-block {
  position: relative;
  cursor: ew-resize;
  touch-action: none;
  user-select: none;
}

.tape-tick {
  position: absolute;
  bottom: -16px;
  color: var(--faint);
  font-size: 10px;
}

.input-lane,
.heat-lane {
  display: grid;
  grid-template-columns: var(--gutter, 78px) 1fr;
  gap: 0;
  align-items: center;
  min-width: 0;
}

.input-lane {
  margin-bottom: 5px;
}

.lane-label {
  padding-right: 10px;
  color: var(--ink-soft);
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
}

.lane-label small {
  margin-left: 4px;
  color: var(--faint);
  font-size: 10px;
  font-weight: 400;
}

.lane-svg {
  display: block;
  width: 100%;
}

.input-lane .lane-svg {
  height: 30px;
}

.tape-divider {
  height: 1px;
  margin: 12px 0 14px;
  background: var(--hairline-soft);
}

.heat-lane {
  margin-bottom: 8px;
}

.tape-cursor {
  position: absolute;
  top: 6px;
  bottom: 2px;
  width: 2px;
  border-radius: 1px;
  background: var(--ink);
  pointer-events: none;
  transition: left 90ms linear;
}

.tape-cursor::after {
  content: "";
  position: absolute;
  bottom: -5px;
  left: 50%;
  width: 8px;
  height: 8px;
  transform: translateX(-50%);
  border-radius: 50%;
  background: var(--ink);
}

.tape-tip {
  position: absolute;
  top: -14px;
  z-index: 3;
  padding: 4px 9px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.96);
  box-shadow: var(--shadow-sm);
  color: var(--ink);
  font-size: 11px;
  pointer-events: none;
  white-space: nowrap;
}

/* ── the schematic cell ── */
.cell-side {
  min-width: 0;
}

.cell-svg {
  display: block;
  width: 100%;
  height: auto;
}

.cell-boundary {
  fill: rgba(255, 255, 255, 0.72);
  stroke: var(--hairline);
}

.flow {
  stroke: #64748b;
  stroke-linecap: round;
}

.flow.memory {
  stroke: #334155;
}

.flow.accent {
  stroke: #0284c7;
}

.flow.thin {
  stroke: #94a3b8;
  stroke-width: 1.2;
  stroke-opacity: 0.6;
}

.node {
  fill: #ffffff;
  stroke: var(--hairline-strong);
  stroke-width: 1;
}

.tanh-box {
  fill: #ffffff;
  stroke: var(--hairline-strong);
}

.pill {
  fill: #f1f5f9;
  stroke: var(--hairline);
  transition: stroke var(--duration-fast) ease;
}

.pill.hot {
  stroke: #0284c7;
}

.pill-text {
  fill: var(--muted);
  font-size: 11px;
  font-weight: 500;
}

.pill-text .d-value {
  fill: var(--ink);
  font-weight: 700;
}

.d-label {
  fill: var(--muted);
  font-size: 11px;
  font-weight: 600;
}

.d-value {
  fill: var(--ink);
  font-size: 11px;
  font-weight: 700;
}

.d-op {
  fill: var(--ink-soft, #475569);
  font-size: 11px;
  font-weight: 700;
}

.equation {
  margin: 6px 0 0;
  text-align: center;
  color: var(--faint);
  font-size: 10.5px;
}

/* ── 解码 × 对照 ── */
.decode-row {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(260px, 1fr);
  gap: 40px;
  align-items: start;
}

.decode-fan svg {
  display: block;
  width: 100%;
  height: auto;
}

.decode-name {
  font-size: 10.5px;
  font-weight: 600;
}

.decode-axis {
  fill: var(--faint);
  font-size: 10px;
}

.mae-svg {
  width: 100%;
  max-width: 320px;
  height: auto;
  display: block;
}

.mae-caption {
  margin: 4px 0 0;
  color: var(--faint);
  font-size: 10.5px;
}

.engine-meta {
  margin: 0;
  color: var(--muted);
  font-size: 11px;
}

@media (max-width: 1100px) {
  .compute-row {
    grid-template-columns: 1fr;
  }

  .decode-row {
    grid-template-columns: 1fr;
    gap: 24px;
  }
}
</style>
