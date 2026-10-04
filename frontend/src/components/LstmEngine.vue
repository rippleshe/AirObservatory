<!-- LstmEngine — the engine page as one instrument plus a decode act.
     单元计算: the hero is a large colah-style cell redrawing the current
     timestep of a genuine forward pass of the trained numpy LSTM — each gate
     chip carries its own 48-step mean history with the cursor ticked inside;
     below it, the full-width evidence ribbon (input tape + six 48×16 unit
     activation lanes) shares the same cursor. 解码: the dense head's 24h
     forecast and the MAE-vs-horizon race against the baselines. -->
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
const MEMORY = "#334155";

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

const meanAt = (row: number[] | undefined) =>
  row && row.length ? row.reduce((sum, v) => sum + v, 0) / row.length : 0;

/* ── cursor state, shared by cell chips and ribbon ── */
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

const currentStep = computed(() => steps.value[Math.min(cursor.value, T.value - 1)]);

type LaneKey = "f" | "i" | "o" | "g" | "cell" | "hidden";

const LANES: Array<{ key: LaneKey; label: string; diverging: boolean; hint: string }> = [
  { key: "f", label: "遗忘门", diverging: false, hint: "0→1" },
  { key: "i", label: "输入门", diverging: false, hint: "0→1" },
  { key: "o", label: "输出门", diverging: false, hint: "0→1" },
  { key: "g", label: "候选", diverging: true, hint: "-1↔1" },
  { key: "cell", label: "细胞状态", diverging: true, hint: "记忆" },
  { key: "hidden", label: "隐状态", diverging: true, hint: "输出" },
];

/* per-gate mean history — what the hero chips draw inside themselves */
const gateMeans = computed<Record<LaneKey, number[]>>(() => {
  const out = {} as Record<LaneKey, number[]>;
  for (const lane of LANES) {
    out[lane.key] = steps.value.map((step) => meanAt(step[lane.key] as number[]));
  }
  return out;
});

const laneExtents = computed(() => {
  const out = {} as Record<LaneKey, number>;
  for (const lane of LANES) {
    if (!lane.diverging) continue;
    const magnitudes: number[] = [];
    for (const row of steps.value) {
      for (const v of row[lane.key] as number[]) magnitudes.push(Math.abs(v));
    }
    magnitudes.sort((a, b) => a - b);
    out[lane.key] = Math.max(0.3, magnitudes[Math.floor(magnitudes.length * 0.9)] ?? 1);
  }
  return out;
});

const cellNorm = (v: number) => Math.min(1, Math.abs(v) / (laneExtents.value.cell ?? 1));
const hiddenNorm = (v: number) => Math.min(1, Math.abs(v) / (laneExtents.value.hidden ?? 1));
const flowW = (frac: number) => 1.5 + 9 * Math.min(1, Math.max(0, frac));
const flowO = (v: number) => 0.16 + 0.72 * Math.min(1, Math.max(0.05, v));

const fmt = (v: number) => v.toFixed(2);

function sparkPath(key: LaneKey, x: number, y: number, w: number, h: number): string {
  const series = gateMeans.value[key] ?? [];
  if (series.length < 2) return "";
  const diverging = LANES.find((l) => l.key === key)?.diverging ?? false;
  const max = diverging ? laneExtents.value[key] ?? 1 : 1;
  const lo = diverging ? -max : 0;
  return series
    .map((v, i) => {
      const px = x + (i / (series.length - 1)) * w;
      const py = y + h - ((v - lo) / (max - lo)) * h;
      return `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`;
    })
    .join(" ");
}

function sparkZero(key: LaneKey, y: number, h: number): number {
  const diverging = LANES.find((l) => l.key === key)?.diverging ?? false;
  if (!diverging) return y + h;
  const max = laneExtents.value[key] ?? 1;
  return y + h - (0 - -max) / (max - -max) * h;
}

/* ── the hero cell (viewBox 900×470) ── */
const diagram = computed(() => {
  const step = currentStep.value;
  if (!step) return null;
  const prev = cursor.value > 0 ? steps.value[cursor.value - 1]! : null;
  const cellPrev = prev ? meanAt(prev.cell) : 0;
  const f = meanAt(step.f);
  const i = meanAt(step.i);
  const g = meanAt(step.g);
  return {
    time: fmtTime(step.target_at),
    f,
    i,
    o: meanAt(step.o),
    g,
    cellPrev,
    cell: meanAt(step.cell),
    hidden: meanAt(step.hidden),
    retained: cellPrev * f,
    written: i * g,
  };
});

/* ── the evidence ribbon (full width) ── */
const INPUT_LANES = [
  { index: 0, label: "PM2.5", color: "#f97316" },
  { index: 1, label: "气温", color: "#ec4899" },
  { index: 2, label: "湿度", color: "#10b981" },
  { index: 3, label: "风速", color: "#0ea5e9" },
  { index: 6, label: "边界层", color: "#8b5cf6" },
];

function laneSeries(lane: (typeof INPUT_LANES)[number]): number[] {
  return steps.value.map((step) => step.x[lane.index] ?? 0);
}

const GUTTER = 92;
const INPUT_H = 16;
const LANE_H = 50;
const INPUT_BLOCK_H = INPUT_LANES.length * (INPUT_H + 4) + 30;
const ribbonW = computed(() => Math.max(480, (size.value.w || 980) - GUTTER));
const cellW = computed(() => ribbonW.value / Math.max(1, T.value));
const unitH = computed(() => LANE_H / Math.max(1, H.value));

function laneValues(key: LaneKey): number[][] {
  return steps.value.map((step) => step[key] as number[]);
}

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

const hovered = ref<{ left: number; text: string } | null>(null);

function locate(event: PointerEvent): { t: number; localY: number } {
  const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
  const t = Math.max(0, Math.min(T.value - 1, Math.floor((event.clientX - box.left - GUTTER) / cellW.value)));
  return { t, localY: event.clientY - box.top };
}

function onScrubDown(event: PointerEvent) {
  stopPlay();
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  cursor.value = locate(event).t;
}

function onScrubMove(event: PointerEvent) {
  const { t, localY } = locate(event);
  if (localY > INPUT_BLOCK_H) {
    const laneIndex = Math.max(0, Math.min(LANES.length - 1, Math.floor((localY - INPUT_BLOCK_H) / (LANE_H + 6))));
    const lane = LANES[laneIndex]!;
    const unit = Math.max(0, Math.min(H.value - 1, Math.floor((localY - INPUT_BLOCK_H - laneIndex * (LANE_H + 6)) / unitH.value)));
    const value = (steps.value[t]![lane.key] as number[])[unit] ?? 0;
    hovered.value = { left: GUTTER + t * cellW.value, text: `${fmtTime(steps.value[t]!.target_at)} · ${lane.label} · 单元 ${unit + 1} · ${fmt(value)}` };
  } else if (localY > 20) {
    const inputIndex = Math.max(0, Math.min(INPUT_LANES.length - 1, Math.floor((localY - 22) / (INPUT_H + 4))));
    const lane = INPUT_LANES[inputIndex]!;
    const value = steps.value[t]!.x[lane.index] ?? 0;
    hovered.value = { left: GUTTER + t * cellW.value, text: `${fmtTime(steps.value[t]!.target_at)} · ${lane.label} ${fmt(value)}` };
  }
  if (event.buttons === 1) cursor.value = t;
}

function onScrubLeave() {
  hovered.value = null;
}

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
          { autoAlpha: 0, y: 8 },
          { autoAlpha: 1, y: 0, duration: 0.5, stagger: 0.035, ease: "power2.out", clearProps: "transform" },
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

    <!-- the hero cell -->
    <div class="hero-wrap">
      <header class="hero-head">
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
        <span class="hero-hint">{{ T }} 步 × {{ H }} 单元 · 真实前向</span>
      </header>

      <svg class="cell-svg" viewBox="0 0 900 446">
        <defs>
          <marker id="arrow-ink" markerUnits="userSpaceOnUse" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">
            <path d="M0.5,0.5 L8,4.5 L0.5,8.5 Z" fill="#334155" />
          </marker>
          <marker id="arrow-accent" markerUnits="userSpaceOnUse" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">
            <path d="M0.5,0.5 L8,4.5 L0.5,8.5 Z" fill="#0284c7" />
          </marker>
          <marker id="arrow-soft" markerUnits="userSpaceOnUse" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
            <path d="M0.5,0.5 L7,4 L0.5,7.5 Z" fill="#94a3b8" />
          </marker>
        </defs>
        <rect x="8" y="8" width="884" height="414" rx="18" class="cell-boundary" />

        <!-- memory lane -->
        <text x="46" y="152" class="d-label">c₋₁</text>
        <text x="46" y="174" class="d-value data-mono">{{ fmt(diagram?.cellPrev ?? 0) }}</text>
        <line x1="88" y1="180" x2="150" y2="180" class="flow memory" :stroke-width="flowW(cellNorm(diagram?.cellPrev ?? 0))" :stroke-opacity="flowO(cellNorm(diagram?.cellPrev ?? 0))" marker-end="url(#arrow-ink)" />

        <circle cx="170" cy="180" r="15" class="node" />
        <text x="170" y="186" text-anchor="middle" class="d-op">×</text>
        <text x="144" y="163" text-anchor="end" class="role-word">保留</text>
        <rect x="108" y="238" width="124" height="54" rx="10" class="chip" :class="{ hot: (diagram?.f ?? 0) > 0.5 }" />
        <text x="118" y="258" class="chip-name">遗忘门</text>
        <text x="222" y="260" text-anchor="end" class="chip-value data-mono">{{ fmt(diagram?.f ?? 0) }}</text>
        <path :d="sparkPath('f', 118, 266, 104, 18)" class="chip-spark" :stroke="ACCENT" fill="none" />
        <line x1="170" y1="237" x2="170" y2="200" class="flow accent" :stroke-width="flowW(diagram?.f ?? 0)" :stroke-opacity="flowO(diagram?.f ?? 0)" marker-end="url(#arrow-accent)" />

        <line x1="185" y1="180" x2="370" y2="180" class="flow memory" :stroke-width="flowW(cellNorm(diagram?.retained ?? 0))" :stroke-opacity="flowO(cellNorm(diagram?.retained ?? 0))" marker-end="url(#arrow-ink)" />

        <circle cx="390" cy="180" r="15" class="node" />
        <text x="390" y="186" text-anchor="middle" class="d-op">+</text>
        <text x="364" y="163" text-anchor="end" class="role-word">写入</text>

        <text x="428" y="146" class="d-label">c</text>
        <text x="428" y="168" class="d-value data-mono">{{ fmt(diagram?.cell ?? 0) }}</text>
        <line x1="405" y1="180" x2="448" y2="180" class="flow memory" :stroke-width="flowW(cellNorm(diagram?.cell ?? 0))" :stroke-opacity="flowO(cellNorm(diagram?.cell ?? 0))" marker-end="url(#arrow-ink)" />

        <rect x="456" y="162" width="64" height="36" rx="9" class="tanh-box" />
        <text x="488" y="185" text-anchor="middle" class="d-op">tanh</text>
        <line x1="488" y1="161" x2="488" y2="106" class="flow" stroke-width="2" stroke-opacity="0.7" marker-end="url(#arrow-soft)" />

        <circle cx="488" cy="86" r="15" class="node" />
        <text x="488" y="92" text-anchor="middle" class="d-op">×</text>
        <text x="462" y="69" text-anchor="end" class="role-word">读出</text>
        <rect x="560" y="20" width="124" height="54" rx="10" class="chip" :class="{ hot: (diagram?.o ?? 0) > 0.5 }" />
        <text x="570" y="40" class="chip-name">输出门</text>
        <text x="674" y="42" text-anchor="end" class="chip-value data-mono">{{ fmt(diagram?.o ?? 0) }}</text>
        <path :d="sparkPath('o', 570, 48, 104, 18)" class="chip-spark" :stroke="ACCENT" fill="none" />
        <line x1="574" y1="74" x2="499" y2="92" class="flow accent" :stroke-width="flowW(diagram?.o ?? 0)" :stroke-opacity="flowO(diagram?.o ?? 0)" />
        <line x1="503" y1="86" x2="666" y2="86" class="flow accent" :stroke-width="flowW(hiddenNorm(diagram?.hidden ?? 0) + 0.3)" :stroke-opacity="flowO(hiddenNorm(diagram?.hidden ?? 0))" marker-end="url(#arrow-accent)" />
        <text x="680" y="80" class="d-label">h</text>
        <text x="680" y="100" class="d-value data-mono">{{ fmt(diagram?.hidden ?? 0) }}</text>
        <text x="726" y="90" class="decode-tag">→ 24h 解码</text>
        <text x="580" y="296" class="cell-note"><tspan fill="#64748b">c = </tspan><tspan fill="#334155">f·c₋₁</tspan><tspan fill="#64748b"> + </tspan><tspan fill="#0284c7">i·g</tspan></text>
        <text x="580" y="322" class="cell-note"><tspan fill="#64748b">h = </tspan><tspan fill="#0284c7">o·tanh(c)</tspan></text>
        <text x="580" y="348" class="cell-note faint">芯片曲线 = 16 单元均值 × 48 步</text>

        <!-- bottom branch -->
        <text x="46" y="336" class="d-label">xₜ</text>
        <line x1="66" y1="331" x2="82" y2="331" class="flow" stroke-width="2" stroke-opacity="0.55" marker-end="url(#arrow-soft)" />
        <path d="M86 331 L86 317 L108 317" class="flow thin" fill="none" marker-end="url(#arrow-soft)" />
        <path d="M86 331 L86 383 L108 383" class="flow thin" fill="none" marker-end="url(#arrow-soft)" />
        <rect x="116" y="290" width="124" height="54" rx="10" class="chip" :class="{ hot: (diagram?.i ?? 0) > 0.5 }" />
        <text x="126" y="310" class="chip-name">输入门</text>
        <text x="230" y="312" text-anchor="end" class="chip-value data-mono">{{ fmt(diagram?.i ?? 0) }}</text>
        <path :d="sparkPath('i', 126, 318, 104, 18)" class="chip-spark" :stroke="ACCENT" fill="none" />
        <rect x="116" y="356" width="124" height="54" rx="10" class="chip" />
        <text x="126" y="376" class="chip-name">候选</text>
        <text x="230" y="378" text-anchor="end" class="chip-value data-mono">{{ fmt(diagram?.g ?? 0) }}</text>
        <path :d="sparkPath('g', 126, 384, 104, 18)" class="chip-spark" :stroke="ACCENT" fill="none" />
        <line x1="240" y1="317" x2="316" y2="352" class="flow accent" :stroke-width="flowW(diagram?.i ?? 0)" :stroke-opacity="flowO(diagram?.i ?? 0)" marker-end="url(#arrow-accent)" />
        <line x1="240" y1="383" x2="316" y2="370" class="flow accent" :stroke-width="flowW(Math.abs(diagram?.g ?? 0))" :stroke-opacity="flowO(Math.abs(diagram?.g ?? 0))" marker-end="url(#arrow-accent)" />
        <circle cx="336" cy="362" r="13" class="node" />
        <text x="336" y="367" text-anchor="middle" class="d-op">×</text>
        <path d="M336 349 L336 240 L386 240 L386 200" class="flow accent" fill="none" :stroke-width="flowW(diagram?.written ?? 0)" :stroke-opacity="flowO(diagram?.written ?? 0)" marker-end="url(#arrow-accent)" />
      </svg>
    </div>

    <!-- the evidence ribbon -->
    <div class="ribbon-block" @pointerdown="onScrubDown" @pointermove="onScrubMove" @pointerleave="onScrubLeave">
      <div class="ribbon-caption">
        <span>输入 xₜ</span>
        <span class="ribbon-caption-right">单元级激活 · 拖拽游标</span>
      </div>

      <div
        v-for="lane in INPUT_LANES"
        :key="`in-${lane.label}`"
        data-lane
        class="ribbon-input"
        :style="{ height: `${INPUT_H}px` }"
      >
        <span class="lane-label">{{ lane.label }}</span>
        <svg class="lane-svg" :height="INPUT_H" :viewBox="`0 0 ${T} ${INPUT_H}`" preserveAspectRatio="none">
          <polyline
            :points="laneSeries(lane)
              .map((v, i, arr) => {
                const min = Math.min(...arr);
                const max = Math.max(...arr);
                const y = INPUT_H - 2 - ((v - min) / Math.max(0.5, max - min)) * (INPUT_H - 4);
                return `${i},${y.toFixed(1)}`;
              })
              .join(' ')"
            :fill="lane.color"
            fill-opacity="0.07"
            :stroke="lane.color"
            stroke-width="0.5"
            vector-effect="non-scaling-stroke"
          />
        </svg>
      </div>

      <div class="ribbon-divider" aria-hidden="true"></div>

      <div
        v-for="lane in LANES"
        :key="lane.key"
        data-lane
        class="ribbon-lane"
        :style="{ height: `${LANE_H}px` }"
      >
        <span class="lane-label">{{ lane.label }}<small>{{ lane.hint }}</small></span>
        <svg
          class="lane-svg"
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

      <span
        v-for="(tick, i) in axisTicks"
        :key="`tick-${i}`"
        class="ribbon-tick data-mono"
        :style="{
          left: `${GUTTER + tick.frac * ribbonW}px`,
          transform: tick.anchor === 'start' ? 'none' : tick.anchor === 'end' ? 'translateX(-100%)' : 'translateX(-50%)',
        }"
      >{{ tick.label }}</span>

      <div
        class="ribbon-cursor"
        :style="{ left: `${GUTTER + cursor * cellW}px` }"
        aria-hidden="true"
      ></div>

      <div v-if="hovered" class="ribbon-tip data-mono" :style="{ left: `${Math.min(hovered.left + 12, GUTTER + ribbonW - 190)}px` }">
        {{ hovered.text }}
      </div>
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
  gap: 24px;
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

/* ── hero cell ── */
.hero-wrap {
  min-width: 0;
  display: grid;
  gap: 10px;
}

.hero-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.play {
  width: 32px;
  height: 32px;
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
  width: 13px;
  height: 13px;
  fill: currentColor;
}

.cursor-time {
  color: var(--ink);
  font-size: 14px;
  font-weight: 700;
}

.hero-hint {
  margin-left: auto;
  color: var(--faint);
  font-size: 10.5px;
}

.cell-svg {
  display: block;
  width: 100%;
  max-width: 1060px;
  margin: 0 auto;
  height: auto;
}

.cell-boundary {
  fill: rgba(255, 255, 255, 0.8);
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
  stroke-width: 1.4;
  stroke-opacity: 0.6;
}

.node {
  fill: #ffffff;
  stroke: #cbd5e1;
  stroke-width: 1.4;
}

.tanh-box {
  fill: #ffffff;
  stroke: #cbd5e1;
  stroke-width: 1.4;
}

.chip {
  fill: #ffffff;
  stroke: var(--hairline-strong, #cbd5e1);
  stroke-width: 1.2;
  transition: stroke var(--duration-fast) ease;
}

.chip.hot {
  stroke: #0284c7;
}

.chip-name {
  fill: var(--muted);
  font-size: 12px;
  font-weight: 600;
}

.chip-value {
  fill: var(--ink);
  font-size: 15px;
  font-weight: 700;
}

.chip-spark {
  stroke-width: 1.5;
  stroke-linejoin: round;
  stroke-linecap: round;
}

.d-label {
  fill: var(--muted);
  font-size: 12.5px;
  font-weight: 600;
}

.d-value {
  fill: var(--ink);
  font-size: 14px;
  font-weight: 700;
}

.d-op {
  fill: #475569;
  font-size: 13px;
  font-weight: 700;
}

.role-word {
  fill: var(--faint);
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
}

.decode-tag {
  fill: var(--faint);
  font-size: 11px;
  font-weight: 500;
}

.cell-note {
  fill: var(--ink-soft, #475569);
  font-size: 13px;
  font-weight: 600;
}

.cell-note.faint {
  fill: var(--faint);
  font-size: 11px;
  font-weight: 500;
}

/* ── evidence ribbon ── */
.ribbon-block {
  position: relative;
  cursor: ew-resize;
  touch-action: none;
  user-select: none;
  padding-top: 22px;
}

.ribbon-caption {
  position: absolute;
  top: 0;
  left: 92px;
  right: 0;
  display: flex;
  justify-content: space-between;
  color: var(--muted);
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
}

.ribbon-caption-right {
  color: var(--faint);
  font-weight: 400;
  letter-spacing: 0;
}

.ribbon-input,
.ribbon-lane {
  display: grid;
  grid-template-columns: 92px 1fr;
  align-items: center;
  min-width: 0;
}

.ribbon-input {
  margin-bottom: 4px;
}

.lane-label {
  padding-right: 12px;
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

.ribbon-divider {
  height: 1px;
  margin: 12px 0 14px;
  background: var(--hairline-soft);
}

.ribbon-lane {
  margin-bottom: 6px;
}

.ribbon-tick {
  position: absolute;
  bottom: -16px;
  color: var(--faint);
  font-size: 10px;
}

.ribbon-cursor {
  position: absolute;
  top: 18px;
  bottom: 2px;
  width: 2px;
  border-radius: 1px;
  background: var(--ink);
  pointer-events: none;
  transition: left 90ms linear;
}

.ribbon-cursor::after {
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

.ribbon-tip {
  position: absolute;
  top: 0;
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
  .decode-row {
    grid-template-columns: 1fr;
    gap: 24px;
  }
}
</style>
