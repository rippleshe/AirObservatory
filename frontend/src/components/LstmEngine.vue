<!-- LstmEngine — the engine page in three acts, every number real.
     ① 输入带: the exact feature vectors the cell consumed (48h).
     ② 单元计算: six activation lanes (forget / input / output / candidate
        gates, cell state, hidden state) recorded from a genuine forward pass
        of the trained numpy LSTM, with a cursor that replays the computation
        timestep by timestep; the schematic cell on the right shows the current
        step's mean gate values modulating the flows (colah's grammar).
     ③ 解码: the trained dense head's 24h forecast plus MAE-vs-horizon against
        the baselines evaluated on the same windows. -->
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

/* ── ① 输入带 ── */
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

function fmtTime(iso: string): string {
  const at = new Date(iso);
  return `${at.getMonth() + 1}/${at.getDate()} ${String(at.getHours()).padStart(2, "0")}:00`;
}

/* ── ② 单元计算 ── */
type LaneKey = "f" | "i" | "o" | "g" | "cell" | "hidden";

const LANES: Array<{ key: LaneKey; label: string; diverging: boolean; hint: string }> = [
  { key: "f", label: "遗忘门", diverging: false, hint: "0→1" },
  { key: "i", label: "输入门", diverging: false, hint: "0→1" },
  { key: "o", label: "输出门", diverging: false, hint: "0→1" },
  { key: "g", label: "候选", diverging: true, hint: "-1↔1" },
  { key: "cell", label: "细胞状态", diverging: true, hint: "记忆" },
  { key: "hidden", label: "隐状态", diverging: true, hint: "输出" },
];

const cursor = ref(0);
const playing = ref(false);
let playTimer: number | null = null;
const LANE_H = 66;
const lanesW = computed(() => Math.max(360, (size.value.w || 900) * 0.58));
const laneCellW = computed(() => lanesW.value / Math.max(1, T.value));
const laneCellH = computed(() => LANE_H / Math.max(1, H.value));

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

function laneValues(key: LaneKey): number[][] {
  return steps.value.map((step) => step[key] as number[]);
}

/* Per-lane normalization for the diverging lanes: the cell state is
   unbounded, so a max-based scale would wash out every ordinary value —
   the colour scale is the replay's own 90th-percentile |value|, clamped. */
const laneExtents = computed(() => {
  const out = {} as Record<LaneKey, number>;
  for (const lane of LANES) {
    if (!lane.diverging) continue;
    const magnitudes: number[] = [];
    for (const row of laneValues(lane.key)) {
      for (const v of row) magnitudes.push(Math.abs(v));
    }
    magnitudes.sort((a, b) => a - b);
    const p90 = magnitudes[Math.floor(magnitudes.length * 0.9)] ?? 1;
    out[lane.key] = Math.max(0.3, p90);
  }
  return out;
});

function cellFill(lane: (typeof LANES)[number], value: number): { color: string; opacity: number } {
  if (!lane.diverging) {
    return { color: ACCENT, opacity: 0.05 + 0.92 * value };
  }
  const max = laneExtents.value[lane.key] ?? 1;
  const magnitude = Math.min(1, Math.abs(value) / max);
  return {
    color: value >= 0 ? WARM : COOL,
    opacity: 0.04 + 0.9 * magnitude,
  };
}

const currentStep = computed(() => steps.value[Math.min(cursor.value, T.value - 1)]);

const meanAt = (row: number[] | undefined) =>
  row && row.length ? row.reduce((sum, v) => sum + v, 0) / row.length : 0;const diagram = computed(() => {
  const step = currentStep.value;
  if (!step) return null;
  const prev = cursor.value > 0 ? steps.value[cursor.value - 1]! : null;
  const cellPrev = prev ? meanAt(prev.cell) : 0;
  return {
    time: fmtTime(step.target_at),
    f: meanAt(step.f),
    i: meanAt(step.i),
    o: meanAt(step.o),
    g: meanAt(step.g),
    cellPrev,
    cell: meanAt(step.cell),
    hidden: meanAt(step.hidden),
    retained: prev ? cellPrev * meanAt(step.f) : 0,
    written: meanAt(step.i) * meanAt(step.g),
  };
});

const fmt = (v: number) => v.toFixed(2);
const flowWidth = (v: number) => 1 + 6 * Math.min(1, Math.max(0, v));
const flowOpacity = (v: number) => 0.2 + 0.7 * Math.min(1, Math.max(0.04, Math.abs(v)));

/* hover readout on the heat lanes */
const hovered = ref<{ t: number; unit: number; lane: LaneKey } | null>(null);
const hoverTip = computed(() => {
  if (!hovered.value) return null;
  const step = steps.value[hovered.value.t];
  if (!step) return null;
  const lane = LANES.find((l) => l.key === hovered.value!.lane)!;
  const value = (step[hovered.value.lane] as number[])[hovered.value.unit] ?? 0;
  return {
    x: hovered.value.t * laneCellW.value,
    text: `${fmtTime(step.target_at)} · 单元 ${hovered.value.unit + 1} · ${lane.label} ${fmt(value)}`,
  };
});

function onLanesPointer(event: PointerEvent) {
  const target = event.currentTarget as HTMLElement;
  const box = target.getBoundingClientRect();
  const t = Math.floor((event.clientX - box.left) / laneCellW.value);
  if (t >= 0 && t < T.value) cursor.value = t;
  const unit = Math.floor((event.clientY - box.top) / laneCellH.value);
  return { t: Math.max(0, Math.min(T.value - 1, t)), unit: Math.max(0, Math.min(H.value - 1, unit)) };
}

function onLanesMove(event: PointerEvent) {
  const pos = onLanesPointer(event);
  const laneEl = (event.target as HTMLElement).closest("[data-lane]") as HTMLElement | null;
  if (!laneEl) return;
  hovered.value = { t: pos.t, unit: pos.unit, lane: laneEl.dataset.lane as LaneKey };
}

function onLanesLeave() {
  hovered.value = null;
}

/* ── ③ 解码 × 对照 ── */
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
      overall: rows.length
        ? rows.reduce((sum, row) => sum + row.mae, 0) / rows.length
        : null,
      samples: rows[0]?.samples ?? 0,
    };
  }).filter((model) => model.points.length > 1),
);

const metaLine = computed(() => {
  const meta = props.run.meta;
  const trained = meta.trained_at ? fmtTime(meta.trained_at) : "—";
  return `H=${props.run.hidden} · 参数 ${meta.params.toLocaleString()} · 训练至 ${trained} · 评估=${meta.eval_basis === "cams_analysis" ? "CAMS 分析场" : meta.eval_basis} · N=${maeModels.value[0]?.samples ?? 0}`;
});

/* entrance: the gate lanes wipe in once */
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
          { autoAlpha: 1, y: 0, duration: 0.6, stagger: 0.05, ease: "power2.out", clearProps: "transform" },
        );
      }
    });
  },
  { immediate: true },
);
</script>

<template>
  <div ref="root" class="lstm-engine">
    <!-- ① 输入带 -->
    <p class="group-label">输入</p>
    <div class="input-band" aria-label="输入特征带">
      <div v-for="lane in INPUT_LANES" :key="lane.label" class="input-lane">
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
        <span class="lane-latest data-mono">{{ laneSeries(lane).at(-1)?.toFixed(1) }}<small>{{ lane.unit }}</small></span>
      </div>
    </div>

    <!-- ② 单元计算 -->
    <p class="group-label">单元计算</p>
    <div class="compute-row">
      <div class="lanes-wrap">
        <header class="lanes-head">
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
          <span class="lanes-hint">{{ T }} 步 × {{ H }} 单元 · 真实前向</span>
        </header>

        <div
          class="heat-lanes"
          @pointermove="onLanesMove"
          @pointerleave="onLanesLeave"
          @pointerdown="onLanesPointer"
        >
          <div
            v-for="lane in LANES"
            :key="lane.key"
            :data-lane="lane.key"
            class="heat-lane"
            :style="{ height: `${LANE_H}px` }"
          >
            <span class="lane-label">{{ lane.label }}<small>{{ lane.hint }}</small></span>
            <svg
              class="heat-svg"
              :width="lanesW"
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
        </div>
      </div>

      <!-- schematic cell -->
      <aside class="cell-diagram">
        <svg viewBox="0 0 430 250" class="cell-svg">
          <!-- incoming memory -->
          <text x="8" y="72" class="d-label">c₋₁</text>
          <text x="8" y="86" class="d-value data-mono">{{ fmt(diagram?.cellPrev ?? 0) }}</text>
          <line x1="34" y1="90" x2="99" y2="90" class="flow" :stroke-width="flowWidth(Math.abs(diagram?.cellPrev ?? 0))" :stroke-opacity="flowOpacity(Math.abs(diagram?.cellPrev ?? 0))" />

          <!-- forget gate multiplier -->
          <circle cx="110" cy="90" r="12" class="node" />
          <text x="110" y="96" text-anchor="middle" class="d-op">×</text>
          <text x="110" y="62" text-anchor="middle" class="d-label">遗忘</text>
          <text x="110" y="48" text-anchor="middle" class="d-value data-mono">{{ fmt(diagram?.f ?? 0) }}</text>
          <line x1="110" y1="66" x2="110" y2="77" class="flow accent" :stroke-width="flowWidth(diagram?.f ?? 0)" :stroke-opacity="flowOpacity(diagram?.f ?? 0)" />

          <line x1="122" y1="90" x2="196" y2="90" class="flow" :stroke-width="flowWidth(Math.abs(diagram?.cell ?? 0) + 0.4)" stroke-opacity="0.75" />

          <!-- add node -->
          <circle cx="208" cy="90" r="12" class="node" />
          <text x="208" y="97" text-anchor="middle" class="d-op">+</text>

          <!-- input gate × candidate from below -->
          <rect x="128" y="182" width="54" height="26" rx="7" class="pill" />
          <text x="155" y="199" text-anchor="middle" class="d-label">候选</text>
          <text x="155" y="222" text-anchor="middle" class="d-value data-mono">{{ fmt(diagram?.g ?? 0) }}</text>
          <rect x="38" y="182" width="54" height="26" rx="7" class="pill" />
          <text x="65" y="199" text-anchor="middle" class="d-label">输入</text>
          <text x="65" y="222" text-anchor="middle" class="d-value data-mono">{{ fmt(diagram?.i ?? 0) }}</text>
          <line x1="92" y1="195" x2="99" y2="195" class="flow accent" :stroke-width="flowWidth(diagram?.i ?? 0)" :stroke-opacity="flowOpacity(diagram?.i ?? 0)" />
          <circle cx="110" cy="195" r="9" class="node" />
          <text x="110" y="199" text-anchor="middle" class="d-op">×</text>
          <line x1="119" y1="195" x2="127" y2="195" class="flow accent" :stroke-width="flowWidth(diagram?.i ?? 0)" :stroke-opacity="flowOpacity(diagram?.i ?? 0)" />
          <line x1="155" y1="181" x2="155" y2="140" class="flow accent" :stroke-width="flowWidth(diagram?.i ?? 0)" :stroke-opacity="flowOpacity(diagram?.i ?? 0)" />
          <line x1="155" y1="140" x2="204" y2="103" class="flow accent" :stroke-width="flowWidth(diagram?.i ?? 0)" :stroke-opacity="flowOpacity(diagram?.i ?? 0)" />

          <!-- cell out -->
          <text x="234" y="72" class="d-label">c</text>
          <text x="234" y="86" class="d-value data-mono">{{ fmt(diagram?.cell ?? 0) }}</text>
          <line x1="220" y1="90" x2="298" y2="90" class="flow" :stroke-width="flowWidth(Math.abs(diagram?.cell ?? 0))" :stroke-opacity="flowOpacity(Math.abs(diagram?.cell ?? 0))" />

          <!-- output path -->
          <circle cx="310" cy="90" r="13" class="node soft" />
          <text x="310" y="95" text-anchor="middle" class="d-op">tanh</text>
          <line x1="310" y1="77" x2="310" y2="46" class="flow" stroke-opacity="0.6" stroke-width="1.4" />
          <circle cx="310" cy="34" r="11" class="node" />
          <text x="310" y="39" text-anchor="middle" class="d-op">×</text>
          <text x="352" y="66" text-anchor="middle" class="d-label">输出</text>
          <text x="352" y="52" text-anchor="middle" class="d-value data-mono">{{ fmt(diagram?.o ?? 0) }}</text>
          <line x1="352" y1="70" x2="317" y2="40" class="flow accent" :stroke-width="flowWidth(diagram?.o ?? 0)" :stroke-opacity="flowOpacity(diagram?.o ?? 0)" />
          <line x1="321" y1="34" x2="392" y2="34" class="flow accent" :stroke-width="flowWidth(Math.abs(diagram?.hidden ?? 0) + 0.3)" :stroke-opacity="flowOpacity(Math.abs(diagram?.hidden ?? 0))" />
          <text x="398" y="38" class="d-label">h</text>
          <text x="398" y="52" class="d-value data-mono">{{ fmt(diagram?.hidden ?? 0) }}</text>
        </svg>
        <p class="equation data-mono">c = f·c₋₁ + i·g &nbsp;→&nbsp; h = o·tanh(c)</p>
      </aside>

      <div v-if="hoverTip" class="heat-tip data-mono" :style="{ left: `${86 + Math.min(hoverTip.x, lanesW - 180)}px` }">
        {{ hoverTip.text }}
      </div>
    </div>

    <!-- ③ 解码 × 对照 -->
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

/* ① 输入带 */
.input-band {
  display: grid;
  gap: 4px;
}

.input-lane {
  display: grid;
  grid-template-columns: 64px 1fr 72px;
  align-items: center;
  gap: 12px;
}

.lane-label {
  color: var(--muted);
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
}

.lane-label small {
  margin-left: 4px;
  color: var(--faint);
  font-size: 10px;
}

.lane-svg {
  width: 100%;
  height: 30px;
  display: block;
}

.lane-latest {
  text-align: right;
  color: var(--ink);
  font-size: 12.5px;
  font-weight: 600;
  white-space: nowrap;
}

.lane-latest small {
  margin-left: 3px;
  color: var(--faint);
  font-size: 10px;
  font-weight: 400;
}

/* ② 单元计算 */
.compute-row {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(340px, 430px);
  gap: 30px;
  align-items: start;
}

.lanes-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
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
  font-size: 13px;
  font-weight: 700;
}

.lanes-hint {
  margin-left: auto;
  color: var(--faint);
  font-size: 10.5px;
}

.heat-lanes {
  position: relative;
  display: grid;
  gap: 8px;
}

.heat-lane {
  display: grid;
  grid-template-columns: 76px 1fr;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.heat-svg {
  display: block;
  width: 100%;
}

.heat-tip {
  position: absolute;
  top: -26px;
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

.cell-diagram {
  min-width: 0;
}

.cell-svg {
  width: 100%;
  height: auto;
  display: block;
}

.flow {
  stroke: var(--ink-soft, #475569);
  stroke-linecap: round;
}

.flow.accent {
  stroke: #0284c7;
}

.node {
  fill: #ffffff;
  stroke: var(--hairline-strong);
  stroke-width: 1;
}

.node.soft {
  stroke: var(--hairline);
}

.pill {
  fill: #ffffff;
  stroke: var(--hairline);
}

.d-label {
  fill: var(--muted);
  font-size: 11px;
  font-weight: 600;
}

.d-value {
  fill: var(--ink);
  font-size: 11px;
  font-weight: 600;
}

.d-op {
  fill: var(--ink-soft, #475569);
  font-size: 11px;
  font-weight: 700;
}

.equation {
  margin: 8px 0 0;
  text-align: center;
  color: var(--faint);
  font-size: 11px;
}

/* ③ 解码 */
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
