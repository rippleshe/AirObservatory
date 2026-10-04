<!-- BarChartRace — the province PM2.5 ranking as a race, in the style John
     Burn-Murdoch's D3 original made famous. One fractional frame index drives
     everything: each bar's value lerps between daily keyframes while its row
     chases the rank, so overtakes read as motion, not cuts. Fixed x-scale
     across the whole race keeps lengths honest. -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Pause, Play } from "lucide-vue-next";
import { gsap, prefersReducedMotion } from "../lib/motion";
import { pm25Color } from "../lib/palette";
import { useElementSize } from "../lib/viz";

export type RaceEntry = {
  location_id: number;
  name: string;
  daily: Array<number | null>;
};

const props = withDefaults(
  defineProps<{
    days: string[];
    entries: RaceEntry[];
    topN?: number;
    stepsPerSecond?: number;
    focusId?: number | null;
  }>(),
  { topN: 10, stepsPerSecond: 2.1, focusId: null },
);

const shell = ref<HTMLElement | null>(null);
const size = useElementSize(shell);

/* Same existence guard as the band: a focus outside the race dims nothing. */
const focusActive = computed(
  () => props.focusId != null && props.entries.some((entry) => entry.location_id === props.focusId),
);

const frame = ref(0);
const playing = ref(false);

/* Carry-forward: a province missing one day keeps its last known value so a
   bar never vanishes mid-race. */
const series = computed(() =>
  props.entries.map((entry) => {
    const out: number[] = [];
    let last = 0;
    entry.daily.forEach((value) => {
      if (value != null && Number.isFinite(value)) last = value;
      out.push(last);
    });
    return { ...entry, series: out };
  }),
);

const xMax = computed(() => {
  let max = 10;
  for (const entry of series.value) {
    for (const value of entry.series) max = Math.max(max, value);
  }
  return max * 1.06;
});

const lastStep = computed(() => Math.max(0, props.days.length - 1));

const frameValue = computed(() => {
  const i = Math.max(0, Math.min(lastStep.value - 1, Math.floor(frame.value)));
  const t = Math.min(1, Math.max(0, frame.value - i));
  return { i, t };
});

type Row = {
  id: number;
  name: string;
  value: number;
  rank: number;
  color: string;
};

const rows = computed<Row[]>(() => {
  const { i, t } = frameValue.value;
  const interpolated = series.value.map((entry) => {
    const a = entry.series[i] ?? 0;
    const b = entry.series[Math.min(lastStep.value, i + 1)] ?? a;
    return { id: entry.location_id, name: entry.name, value: a + (b - a) * t };
  });
  interpolated.sort((x, y) => y.value - x.value);
  return interpolated.slice(0, props.topN).map((row, rank) => ({
    ...row,
    rank,
    color: pm25Color(row.value),
  }));
});

/* Full roster keeps every bar a persistent DOM node; the ones outside the
   top-N park below the visible band, ready to slide in on an overtake. */
const allRows = computed(() => {
  const top = rows.value;
  const rankById = new Map(top.map((row) => [row.id, row]));
  const result = series.value.map((entry) => {
    const top_ = rankById.get(entry.location_id);
    return top_ ?? { id: entry.location_id, name: entry.name, value: entry.series[Math.floor(frame.value)] ?? 0, rank: props.topN, color: pm25Color(entry.series[Math.floor(frame.value)] ?? 0) };
  });
  return result;
});

const currentDay = computed(() => {
  const i = Math.min(lastStep.value, Math.round(frame.value));
  return props.days[i] ?? "";
});

const geometry = computed(() => {
  const { w, h } = size.value;
  if (!w || !h) return null;
  const controlsH = 40;
  const innerH = h - controlsH;
  const rowH = Math.min(38, innerH / props.topN);
  return { w, h, innerH, rowH, nameW: 58, controlsH };
});

function fmtDay(day: string) {
  return day.replaceAll("-", "/");
}

function toggle() {
  if (!playing.value && frame.value >= lastStep.value) frame.value = 0;
  playing.value = !playing.value;
}

function seek(event: MouseEvent) {
  const rect = shell.value?.getBoundingClientRect();
  if (!rect) return;
  const track = (event.currentTarget as HTMLElement).getBoundingClientRect();
  const t = Math.min(1, Math.max(0, (event.clientX - track.left) / track.width));
  frame.value = t * lastStep.value;
}

let tickerFn: ((time: number, deltaTime: number) => void) | null = null;

function startLoop() {
  if (tickerFn) return;
  tickerFn = (_time, deltaMs) => {
    if (!playing.value) return;
    frame.value += (deltaMs / 1000) * props.stepsPerSecond;
    if (frame.value >= lastStep.value) {
      frame.value = lastStep.value;
      playing.value = false;
    }
  };
  gsap.ticker.add(tickerFn);
}

let seen = false;
let raceObserver: IntersectionObserver | null = null;

onMounted(() => {
  startLoop();
  if (prefersReducedMotion() || !shell.value) return;
  raceObserver = new IntersectionObserver(
    (entries) => {
      if (entries[0]?.isIntersecting && !seen) {
        seen = true;
        playing.value = true;
        raceObserver?.disconnect();
      }
    },
    { rootMargin: "40px" },
  );
  raceObserver.observe(shell.value);
});

watch(() => [props.entries, props.days], () => {
  frame.value = 0;
  playing.value = false;
});

onBeforeUnmount(() => {
  if (tickerFn) gsap.ticker.remove(tickerFn);
  raceObserver?.disconnect();
});
</script>

<template>
  <div ref="shell" class="bar-race">
    <div class="race-head">
      <button type="button" class="race-toggle" :aria-label="playing ? '暂停' : '播放'" @click="toggle">
        <Pause v-if="playing" :size="13" />
        <Play v-else :size="13" />
      </button>
      <div
        class="race-progress"
        role="slider"
        aria-label="进度"
        :aria-valuemin="0"
        :aria-valuemax="lastStep"
        :aria-valuenow="Math.round(frame)"
        @click="seek"
      >
        <span class="race-progress-fill" :style="{ width: `${(frame / Math.max(1, lastStep)) * 100}%` }"></span>
      </div>
      <strong class="race-date data-mono">{{ fmtDay(currentDay) }}</strong>
    </div>

    <div v-if="geometry" class="race-field" :style="{ height: geometry.innerH + 'px' }">
      <div
        v-for="row in allRows"
        :key="row.id"
        class="race-row"
        :class="{ focused: focusActive && props.focusId === row.id }"
        :style="{
          transform: `translateY(${Math.min(row.rank, props.topN) * geometry.rowH}px)`,
          opacity:
            row.rank >= props.topN
              ? 0
              : focusActive && row.id !== props.focusId
                ? 0.22
                : 1,
        }"
      >
        <span class="race-name">{{ row.name }}</span>
        <div class="race-track" :style="{ height: geometry.rowH - 10 + 'px' }">
          <div
            class="race-bar"
            :style="{
              width: `${(row.value / xMax) * 100}%`,
              background: row.color,
            }"
          >
            <span v-if="row.value / xMax > 0.28" class="race-value data-mono">{{ row.value.toFixed(1) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bar-race {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 340px;
  display: flex;
  flex-direction: column;
}

.race-head {
  height: 40px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.race-toggle {
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

.race-toggle:hover {
  background: var(--ink);
  color: #ffffff;
}

.race-progress {
  position: relative;
  flex: 1;
  height: 4px;
  border-radius: var(--radius-pill);
  background: var(--hairline);
  cursor: pointer;
}

.race-progress-fill {
  position: absolute;
  inset: 0 auto 0 0;
  border-radius: var(--radius-pill);
  background: var(--ink);
}

.race-date {
  flex: none;
  min-width: 48px;
  text-align: right;
  color: var(--ink);
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.race-field {
  position: relative;
  overflow: hidden;
}

.race-row {
  position: absolute;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  transition: opacity 220ms ease;
  will-change: transform;
}

.race-row.focused .race-name {
  color: var(--ink);
}

.race-row.focused .race-bar {
  box-shadow: 0 0 0 1.5px var(--ink);
}

.race-name {
  flex: none;
  width: 58px;
  text-align: right;
  color: var(--ink-soft);
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.race-track {
  position: relative;
  flex: 1;
  display: flex;
  align-items: center;
}

.race-bar {
  min-width: 3px;
  height: 100%;
  border-radius: 3px 5px 5px 3px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: 7px;
  box-sizing: border-box;
}

.race-value {
  color: rgba(255, 255, 255, 0.96);
  font-size: 10.5px;
  font-weight: 700;
}
</style>
