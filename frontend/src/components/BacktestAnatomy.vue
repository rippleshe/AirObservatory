<!-- BacktestAnatomy — one figure instead of three chips. The top lane lays the
     forecast against what actually happened (observed / predicted in the site
     identity colours, at the modal horizon so the pair is honest); the strip
     beneath splits every miss into over (warm) and under (cool); the ledger on
     the right carries each model's MAE/RMSE with its horizon decay as a
     sparkline. No chart library. -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { components } from "../api/schema";
import { useElementSize } from "../lib/viz";
import { useInView } from "../composables/useInView";
import { drawIn, gsap, prefersReducedMotion } from "../lib/motion";
import { FORECAST_COLOR, MODEL_COLOR, MUTED_DATA_COLOR, OBSERVATION_COLOR } from "../lib/palette";

type BacktestResponse = components["schemas"]["BacktestResponse"];

const props = defineProps<{ backtest: BacktestResponse | undefined }>();

const shell = ref<HTMLElement | null>(null);
const plotEl = ref<HTMLElement | null>(null);
const size = useElementSize(plotEl);
const inView = useInView(shell);
const hovered = ref<number | null>(null);

/* Drawing curves needs enough realised pairs at enough horizons; below that a
   line invents a trend the records don't support. */
const MIN_SAMPLES = 30;
const MIN_HORIZONS = 3;

const LEDGER_W = 176;
const LANE_A_H = 150;
const LANE_B_H = 62;
const GAP = 30;
const TOP = 12;
const AXIS_H = 20;
const PAD_X = 6;
const TOTAL_H = TOP + LANE_A_H + GAP + LANE_B_H + AXIS_H;

const MODEL_TONES = [MODEL_COLOR, FORECAST_COLOR, OBSERVATION_COLOR, MUTED_DATA_COLOR];
const OVER_COLOR = "#f97316";
const UNDER_COLOR = "#2563eb";

const evidence = computed(() => {
  const samples = props.backtest?.samples ?? [];
  const horizons = [...new Set(samples.map((row) => row.horizon_hours))].sort((a, b) => a - b);
  const models = [...new Set(samples.map((row) => row.model_name))];
  return {
    samples,
    horizons,
    models,
    enough: samples.length >= MIN_SAMPLES && horizons.length >= MIN_HORIZONS,
  };
});

const modalHorizon = computed(() => {
  const counts = new Map<number, number>();
  for (const row of evidence.value.samples) {
    counts.set(row.horizon_hours, (counts.get(row.horizon_hours) ?? 0) + 1);
  }
  let best = 0;
  let bestN = -1;
  counts.forEach((n, h) => {
    if (n > bestN) {
      bestN = n;
      best = h;
    }
  });
  return best;
});

const primaryModel = computed(() => {
  const counts = new Map<string, number>();
  for (const row of evidence.value.samples) {
    counts.set(row.model_name, (counts.get(row.model_name) ?? 0) + 1);
  }
  let best = "";
  let bestN = -1;
  counts.forEach((n, m) => {
    if (n > bestN) {
      bestN = n;
      best = m;
    }
  });
  return best;
});

/* Time-ordered observed/predicted pairs at the modal horizon — the lane the
   eye can verify against the trace above it. */
const pairs = computed(() =>
  evidence.value.samples
    .filter(
      (row) =>
        row.horizon_hours === modalHorizon.value && row.model_name === primaryModel.value,
    )
    .sort((a, b) => +new Date(a.target_at) - +new Date(b.target_at)),
);

const svgW = computed(() => Math.max(320, size.value.w - LEDGER_W - 20));
const plotW = computed(() => svgW.value - PAD_X * 2);

const yMax = computed(() => {
  let peak = 10;
  for (const row of pairs.value) {
    peak = Math.max(peak, row.observed_value, row.predicted_value);
  }
  return peak * 1.12;
});

const errMax = computed(() => {
  let peak = 1;
  for (const row of pairs.value) peak = Math.max(peak, Math.abs(row.error));
  return peak * 1.1;
});

function xAt(i: number) {
  const n = Math.max(1, pairs.value.length - 1);
  return PAD_X + (i / n) * plotW.value;
}

function yObs(v: number) {
  return TOP + LANE_A_H - (v / yMax.value) * LANE_A_H;
}

const laneAPaths = computed(() => {
  let obs = "";
  let pred = "";
  pairs.value.forEach((row, i) => {
    const x = xAt(i);
    obs += `${i ? " L" : "M"}${x.toFixed(1)},${yObs(row.observed_value).toFixed(1)}`;
    pred += `${i ? " L" : "M"}${x.toFixed(1)},${yObs(row.predicted_value).toFixed(1)}`;
  });
  return { obs, pred };
});

const errBars = computed(() => {
  const zero = TOP + LANE_A_H + GAP + LANE_B_H / 2;
  const unit = (LANE_B_H / 2 - 3) / errMax.value;
  const w = Math.max(1.4, Math.min(4, (plotW.value / Math.max(1, pairs.value.length)) * 0.45));
  return pairs.value.map((row, i) => ({
    x: xAt(i) - w / 2,
    y: row.error >= 0 ? zero - row.error * unit : zero,
    h: Math.max(0.8, Math.abs(row.error) * unit),
    w,
    color: row.error >= 0 ? OVER_COLOR : UNDER_COLOR,
  }));
});

const zeroY = computed(() => TOP + LANE_A_H + GAP + LANE_B_H / 2);

const axisMarks = computed(() => {
  const n = pairs.value.length;
  if (n < 2) return [];
  const picks = [0, Math.round(n / 2), n - 1];
  const seen = new Set<number>();
  const out: { x: number; label: string; anchor: string }[] = [];
  for (const i of picks) {
    if (seen.has(i)) continue;
    seen.add(i);
    out.push({
      x: xAt(i),
      label: new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(
        new Date(pairs.value[i]!.target_at),
      ),
      anchor: i === 0 ? "start" : i === n - 1 ? "end" : "middle",
    });
  }
  return out;
});

const ledgerRows = computed(() => {
  const metrics = props.backtest?.metrics ?? [];
  return evidence.value.models.slice(0, 3).map((model, index) => {
    const rows = metrics
      .filter((row) => row.model_name === model)
      .sort((a, b) => a.horizon_hours - b.horizon_hours);
    const mean = (pick: "mae" | "rmse") =>
      rows.length ? rows.reduce((sum, row) => sum + row[pick], 0) / rows.length : 0;
    const peak = Math.max(0.001, ...rows.map((row) => row.mae));
    const spark = rows
      .map((row, i) => {
        const x = rows.length > 1 ? (i / (rows.length - 1)) * 116 + 2 : 60;
        const y = 24 - (row.mae / peak) * 20;
        return `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
    return {
      model,
      color: MODEL_TONES[index % MODEL_TONES.length]!,
      mae: mean("mae"),
      rmse: mean("rmse"),
      spark,
    };
  });
});

const tip = computed(() => {
  if (hovered.value == null) return null;
  const row = pairs.value[hovered.value];
  if (!row) return null;
  return {
    x: xAt(hovered.value),
    lines: [
      new Intl.DateTimeFormat("zh-CN", {
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        hour12: false,
      }).format(new Date(row.target_at)),
      `实测 ${row.observed_value.toFixed(1)} · 预测 ${row.predicted_value.toFixed(1)}`,
      `误差 ${row.error > 0 ? "+" : ""}${row.error.toFixed(1)} ${props.backtest?.unit ?? ""}`,
    ],
  };
});

function onMove(event: PointerEvent) {
  const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
  const ratio = (event.clientX - box.left) / Math.max(1, box.width);
  const i = Math.round(Math.min(1, Math.max(0, ratio)) * (pairs.value.length - 1));
  hovered.value = i;
}

let drawn = false;
watch([inView, pairs], ([ready]) => {
  if (!ready || !evidence.value.enough || drawn || prefersReducedMotion()) return;
  drawn = true;
  requestAnimationFrame(() => {
    const lines = shell.value?.querySelectorAll(".lane-line");
    if (lines) drawIn(lines, { duration: 1.2 });
    const bars = shell.value?.querySelectorAll(".err-bar");
    if (bars?.length) {
      gsap.fromTo(
        bars,
        { opacity: 0 },
        { opacity: 1, duration: 0.5, stagger: 0.004, delay: 0.5 },
      );
    }
  });
});
</script>

<template>
  <section ref="shell" class="anatomy">
    <template v-if="evidence.enough && pairs.length > 1">
      <header class="anatomy-meta">
        <span class="data-mono">N={{ evidence.samples.length }}</span>
        <span class="meta-sep"></span>
        <span>时效 {{ evidence.horizons[0] }}–{{ evidence.horizons[evidence.horizons.length - 1] }}h · 对照 {{ modalHorizon }}h</span>
      </header>

      <div ref="plotEl" class="anatomy-plot">
        <svg
          :width="svgW"
          :height="TOTAL_H"
          role="img"
          aria-label="预测对实测与误差分解"
          @pointermove="onMove"
          @pointerleave="hovered = null"
        >
          <!-- lane A: observed vs predicted -->
          <g>
            <line class="grid-rule" :x1="PAD_X" :x2="svgW - PAD_X" :y1="yObs(yMax / 2)" :y2="yObs(yMax / 2)" />
            <text class="lane-tick data-mono" :x="PAD_X" :y="yObs(yMax / 2) - 4">{{ Math.round(yMax / 2) }}</text>
            <text class="lane-tick data-mono" :x="PAD_X" :y="TOP + 10">{{ Math.round(yMax) }}</text>
            <path class="lane-line lane-obs" :d="laneAPaths.obs" />
            <path class="lane-line lane-pred" :d="laneAPaths.pred" />
            <text
              class="lane-name"
              :x="svgW - PAD_X"
              :y="Math.min(TOP + LANE_A_H - 4, yObs(pairs[pairs.length - 1]!.predicted_value) - 6)"
            >预测</text>
            <text
              class="lane-name obs"
              :x="svgW - PAD_X"
              :y="Math.max(TOP + 12, yObs(pairs[pairs.length - 1]!.observed_value) + 12)"
            >实测</text>
          </g>

          <!-- lane B: per-sample error, over warm / under cool -->
          <g>
            <line class="zero-rule" :x1="PAD_X" :x2="svgW - PAD_X" :y1="zeroY" :y2="zeroY" />
            <text class="lane-tick data-mono" :x="PAD_X" :y="TOP + LANE_A_H + GAP - 5">+{{ errMax.toFixed(0) }}</text>
            <text class="lane-tick data-mono" :x="PAD_X" :y="zeroY + LANE_B_H / 2 + 10">-{{ errMax.toFixed(0) }}</text>
            <rect
              v-for="(bar, i) in errBars"
              :key="i"
              class="err-bar"
              :x="bar.x"
              :y="bar.y"
              :width="bar.w"
              :height="bar.h"
              :fill="bar.color"
              opacity=".72"
            />
          </g>

          <!-- shared time axis -->
          <g>
            <text
              v-for="mark in axisMarks"
              :key="mark.label"
              class="lane-tick data-mono"
              :x="Math.min(Math.max(mark.x, 18), svgW - 18)"
              :y="TOTAL_H - 5"
              :text-anchor="mark.anchor"
            >
              {{ mark.label }}
            </text>
          </g>

          <!-- crosshair -->
          <g v-if="hovered != null">
            <line
              class="crosshair"
              :x1="xAt(hovered)"
              :x2="xAt(hovered)"
              :y1="TOP"
              :y2="zeroY + LANE_B_H / 2"
            />
          </g>
        </svg>

        <aside class="ledger">
          <div v-for="row in ledgerRows" :key="row.model" class="ledger-row">
            <header>
              <i :style="{ background: row.color }"></i>
              <span>{{ row.model }}</span>
            </header>
            <svg class="ledger-spark" viewBox="0 0 120 26" aria-hidden="true">
              <path :d="row.spark" fill="none" :stroke="row.color" stroke-width="1.6" stroke-linecap="round" />
            </svg>
            <div class="ledger-nums">
              <span><em>MAE</em><b class="data-mono">{{ row.mae.toFixed(1) }}</b></span>
              <span><em>RMSE</em><b class="data-mono">{{ row.rmse.toFixed(1) }}</b></span>
            </div>
          </div>
        </aside>

        <div v-if="tip" class="anatomy-tip data-mono" :style="{ left: `${Math.min(tip.x + 12, svgW - 150)}px` }">
          <b>{{ tip.lines[0] }}</b>
          <span>{{ tip.lines[1] }}</span>
          <span>{{ tip.lines[2] }}</span>
        </div>
      </div>
    </template>
    <div v-else class="anatomy-state">样本不足</div>
  </section>
</template>

<style scoped>
.anatomy {
  min-width: 0;
}

.anatomy-meta {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 10px;
  color: var(--muted);
  font-size: var(--fs-label);
}

.meta-sep {
  width: 1px;
  height: 10px;
  background: var(--hairline-strong);
}

.anatomy-plot {
  position: relative;
  display: flex;
  gap: 20px;
  align-items: stretch;
}

.anatomy-plot svg {
  flex: none;
  touch-action: none;
}

.grid-rule {
  stroke: var(--hairline-soft);
  stroke-width: 1;
}

.zero-rule {
  stroke: var(--hairline-strong);
  stroke-width: 1;
}

.lane-tick {
  fill: var(--faint);
  font-size: 10px;
}

.lane-line {
  fill: none;
  stroke-width: 1.8;
  stroke-linejoin: round;
  stroke-linecap: round;
}

.lane-obs {
  stroke: var(--stage-ink, #0f172a);
}

.lane-pred {
  stroke: var(--accent, #0284c7);
}

.lane-name {
  fill: var(--accent, #0284c7);
  font-size: 10.5px;
  font-weight: 600;
  text-anchor: end;
}

.lane-name.obs {
  fill: var(--muted);
}

.crosshair {
  stroke: var(--muted);
  stroke-opacity: 0.45;
  stroke-width: 1;
}

.ledger {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 12px;
  align-content: start;
  padding-top: 2px;
}

.ledger-row {
  display: grid;
  gap: 5px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--hairline-soft);
}

.ledger-row:last-child {
  border-bottom: 0;
}

.ledger-row header {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--ink-soft);
  font-size: 11.5px;
  font-weight: 600;
}

.ledger-row header i {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}

.ledger-spark {
  width: 120px;
  height: 26px;
}

.ledger-nums {
  display: flex;
  gap: 18px;
}

.ledger-nums span {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.ledger-nums em {
  font-style: normal;
  color: var(--faint);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.ledger-nums b {
  color: var(--ink);
  font-size: 14px;
  font-weight: 700;
}

.anatomy-tip {
  position: absolute;
  top: 6px;
  z-index: 2;
  display: grid;
  gap: 2px;
  padding: 8px 11px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.96);
  box-shadow: var(--shadow-sm);
  font-size: 11.5px;
  color: var(--ink-soft);
  pointer-events: none;
  white-space: nowrap;
}

.anatomy-tip b {
  color: var(--ink);
  font-size: 12px;
}

.anatomy-state {
  min-height: 120px;
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: var(--fs-body);
}
</style>
