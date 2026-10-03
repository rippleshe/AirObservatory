<!-- BumpChart — daily PM2.5 rank race for the heaviest-breathing provinces.
     Each line is one province weaving through the top-N over the window;
     position is rank (worst on top), colour is the province's mean band.
     Hand-written SVG with bezier rank transitions and a draw-in entrance. -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { drawIn } from "../lib/motion";
import { pm25Color } from "../lib/palette";
import { mean, useElementSize } from "../lib/viz";

export type BumpEntry = {
  location_id: number;
  name: string;
  daily: Array<number | null>;
};

const props = withDefaults(
  defineProps<{
    days: string[];
    entries: BumpEntry[];
    topN?: number;
  }>(),
  { topN: 10 },
);

const shell = ref<HTMLElement | null>(null);
const size = useElementSize(shell);
const hoverDay = ref<number | null>(null);
const hoverEntry = ref<number | null>(null);

/* Daily PM2.5 ranks are noisy enough to read as an oscilloscope. A centred
   5-day rolling mean sampled every third day keeps the race legible while
   every real overtake survives. */
const smoothed = computed(() =>
  props.entries.map((entry) => {
    const raw = entry.daily;
    const roll = raw.map((_, i) => {
      const window = raw.slice(Math.max(0, i - 2), i + 3).filter((v): v is number => v != null);
      return window.length >= 3 ? mean(window) : null;
    });
    const daily: Array<number | null> = [];
    for (let i = 0; i < roll.length; i += 3) daily.push(roll[i] ?? null);
    return { location_id: entry.location_id, name: entry.name, daily };
  }),
);

const smoothDays = computed(() =>
  props.days.filter((_, i) => i % 3 === 0),
);

const selected = computed(() =>
  [...smoothed.value]
    .map((entry) => ({ entry, overall: mean(entry.daily.filter((v): v is number => v != null)) }))
    .filter((row) => Number.isFinite(row.overall) && row.overall > 0)
    .sort((a, b) => b.overall - a.overall)
    .slice(0, props.topN),
);

/* rank[dayIndex] = 1..N per selected entry; null = outside the N that day. */
const ranks = computed(() => {
  const result = new Map<number, Array<number | null>>();
  for (const { entry } of selected.value) result.set(entry.location_id, new Array(smoothDays.value.length).fill(null));
  for (let d = 0; d < smoothDays.value.length; d++) {
    const todays = selected.value
      .map(({ entry }, i) => ({ i, id: entry.location_id, value: entry.daily[d] }))
      .filter((row): row is { i: number; id: number; value: number } => row.value != null)
      .sort((a, b) => b.value - a.value);
    todays.forEach((row, rank) => {
      if (rank < props.topN) result.get(row.id)![d] = rank;
    });
  }
  return result;
});

const PAD = { top: 18, right: 74, bottom: 26, left: 40 };

const geometry = computed(() => {
  const { w, h } = size.value;
  if (!w || !h || !smoothDays.value.length || !selected.value.length) return null;
  const innerW = w - PAD.left - PAD.right;
  const innerH = h - PAD.top - PAD.bottom;
  const rows = Math.min(props.topN, selected.value.length);
  const x = (d: number) => PAD.left + (smoothDays.value.length > 1 ? (d / (smoothDays.value.length - 1)) * innerW : innerW / 2);
  const y = (rank: number) => PAD.top + (rank + 0.5) * (innerH / rows);
  return { w, h, x, y, innerW, innerH, rows };
});

/* Bezier through rank waypoints: control points pull horizontally so ranks
   glide instead of zig-zagging. */
function rankPath(points: Array<[number, number]>): string {
  if (points.length < 2) return points.length ? `M${points[0][0]},${points[0][1]}` : "";
  let d = `M${points[0][0]},${points[0][1]}`;
  for (let i = 1; i < points.length; i++) {
    const [x0, y0] = points[i - 1];
    const [x1, y1] = points[i];
    const mx = (x0 + x1) / 2;
    d += ` C${mx},${y0} ${mx},${y1} ${x1},${y1}`;
  }
  return d;
}

const lines = computed(() => {
  const geo = geometry.value;
  if (!geo) return [];
  return selected.value.map(({ entry, overall }, i) => {
    const entryRanks = ranks.value.get(entry.location_id) ?? [];
    const segments: Array<Array<[number, number]>> = [];
    let current: Array<[number, number]> = [];
    entryRanks.forEach((rank, d) => {
      if (rank == null) {
        if (current.length > 1) segments.push(current);
        current = [];
      } else {
        current.push([geo.x(d), geo.y(rank)]);
      }
    });
    if (current.length > 1) segments.push(current);
    return {
      id: entry.location_id,
      name: entry.name,
      color: pm25Color(overall),
      d: segments.map(rankPath),
      rank: entryRanks,
      daily: entry.daily,
      overall,
      order: i,
    };
  });
});

function labelAnchorY(line: (typeof lines.value)[number], side: "first" | "last") {
  const geo = geometry.value;
  if (!geo) return null;
  const ranksList = line.rank;
  if (side === "first") {
    const first = ranksList.findIndex((r) => r != null);
    return first === -1 ? null : { y: geo.y(first), rank: (first + 1).toString() };
  }
  let last = -1;
  for (let d = ranksList.length - 1; d >= 0; d--) if (ranksList[d] != null) { last = d; break; }
  return last === -1 ? null : { y: geo.y(last), rank: (last + 1).toString() };
}

function onMove(event: MouseEvent) {
  const geo = geometry.value;
  const rect = shell.value?.getBoundingClientRect();
  if (!geo || !rect) return;
  const d = Math.round(((event.clientX - rect.left - PAD.left) / Math.max(1, geo.innerW)) * (smoothDays.value.length - 1));
  hoverDay.value = Math.min(smoothDays.value.length - 1, Math.max(0, d));
}

const hoverTip = computed(() => {
  if (hoverDay.value == null || hoverEntry.value == null) return null;
  const line = lines.value.find((l) => l.id === hoverEntry.value);
  const day = hoverDay.value;
  if (!line) return null;
  return {
    name: line.name,
    rank: line.rank[day],
    value: line.daily?.[day],
    day: smoothDays.value[day],
  };
});

let played = false;
watch(lines, (next) => {
  if (!next.length || played) return;
  played = true;
  requestAnimationFrame(() => {
    drawIn(shell.value?.querySelectorAll(".rank-path") ?? [], {
      duration: 1.4,
      stagger: 0.06,
    });
  });
});
</script>

<template>
  <div ref="shell" class="bump-chart" @mousemove="onMove" @mouseleave="hoverDay = null; hoverEntry = null">
    <svg :width="geometry?.w" :height="geometry?.h" v-if="geometry">
      <g class="rank-grid">
        <g v-for="rank in geometry.rows" :key="rank">
          <line :x1="PAD.left" :x2="PAD.left + geometry.innerW" :y1="geometry.y(rank - 1)" :y2="geometry.y(rank - 1)" />
          <text :x="PAD.left - 10" :y="geometry.y(rank - 1)">{{ rank }}</text>
        </g>
      </g>

      <line
        v-if="hoverDay != null"
        class="cursor"
        :x1="geometry.x(hoverDay)" :x2="geometry.x(hoverDay)"
        :y1="PAD.top" :y2="PAD.top + geometry.innerH"
      />

      <g
        v-for="line in lines"
        :key="line.id"
        class="bump-line"
        :class="{ dim: hoverEntry != null && hoverEntry !== line.id }"
        @mouseenter="hoverEntry = line.id"
      >
        <path
          v-for="(d, si) in line.d"
          :key="si"
          class="rank-path"
          :d="d"
          :stroke="line.color"
          :stroke-width="hoverEntry === line.id ? 3 : 2.1"
        />
        <circle
          v-for="(rank, d) in line.rank"
          :key="d"
          v-show="rank != null && (hoverDay === d || hoverEntry === line.id)"
          :cx="geometry.x(d)"
          :cy="geometry.y(rank ?? 0)"
          r="3.4"
          :fill="line.color"
        />
        <text
          v-if="labelAnchorY(line, 'last')"
          class="name-label"
          :x="PAD.left + geometry.innerW + 8"
          :y="labelAnchorY(line, 'last')!.y"
          :fill="line.color"
        >{{ line.name }}</text>
      </g>
    </svg>

    <div v-if="hoverTip" class="bump-tip" :class="{ pinned: true }">
      <strong>{{ hoverTip.name }}</strong>
      <span v-if="hoverTip.rank != null" class="data-mono">NO.{{ hoverTip.rank + 1 }} · {{ hoverTip.value?.toFixed(1) }} µg/m³</span>
    </div>
  </div>
</template>

<style scoped>
.bump-chart {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 300px;
}

.rank-grid line {
  stroke: var(--hairline);
  stroke-dasharray: 2 4;
}

.rank-grid text {
  fill: var(--faint);
  font-family: var(--font-display);
  font-size: 10.5px;
  text-anchor: end;
  dominant-baseline: central;
}

.cursor {
  stroke: var(--ink);
  stroke-opacity: 0.22;
  pointer-events: none;
}

.bump-line {
  cursor: pointer;
  transition: opacity 200ms ease;
}

.bump-line.dim {
  opacity: 0.15;
}

.rank-path {
  fill: none;
  stroke-linecap: round;
}

.name-label {
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 600;
  dominant-baseline: central;
}

.bump-tip {
  position: absolute;
  top: 8px;
  right: 84px;
  display: grid;
  gap: 2px;
  padding: 8px 12px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: var(--shadow-sm);
  font-size: 12px;
  color: var(--ink-soft);
  pointer-events: none;
}

.bump-tip strong {
  color: var(--ink);
}
</style>
