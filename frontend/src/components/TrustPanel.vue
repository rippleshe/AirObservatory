<script setup lang="ts">
import { computed } from "vue";
import type { components } from "../api/schema";

type CoverageResponse = components["schemas"]["CoverageResponse"];
const props = defineProps<{ coverage: CoverageResponse | undefined }>();

function pct(value: number) {
  return Math.round(value * 100) + "%";
}

function tone(value: number, kind: "obs" | "model" | "weather") {
  const alpha = 0.14 + value * 0.76;
  const rgb = kind === "obs" ? "47,114,95" : kind === "model" ? "53,111,135" : "122,90,66";
  return "rgba(" + rgb + "," + alpha.toFixed(2) + ")";
}

/* The heading carries how many days are complete, the line under it carries
   the gap policy — no paragraph about how to read the colour blocks. */
const coverageHeadline = computed(() => {
  const days = props.coverage?.coverage ?? [];
  if (!days.length) return "覆盖记录尚未生成";
  const full = days.filter((day) => day.observation_coverage >= 0.95).length;
  return `${full} / ${days.length} 天地面实测基本完整`;
});

const coverageSummary = computed(() => {
  const days = props.coverage?.coverage ?? [];
  if (!days.length) return "暂无记录";
  const gap = days.filter((day) => day.observation_coverage < 0.95).length;
  return gap ? `${gap} 天有缺口` : "实测完整";
});

const bindingCopy = computed(() => {
  const bindings = props.coverage?.bindings ?? [];
  if (!bindings.length) return "无站点接入";
  return `接入 ${bindings.length} 站`;
});

const analysisCopy = computed(() => {
  const analyses = props.coverage?.analyses ?? [];
  if (!analyses.length) return "暂无分析";
  return `${analyses.length} 项分析`;
});

const columns = computed(() => {
  const n = props.coverage?.coverage?.length ?? 30;
  return n <= 10 ? 6 : n <= 20 ? 10 : 15;
});
</script>

<template>
  <section class="trust-panel">
    <header class="panel-header">
      <h2 class="display-face">{{ coverageHeadline }}</h2>
      <span class="panel-meta data-mono">{{ coverage?.days ?? 30 }} 天</span>
    </header>

    <div class="coverage-block">
      <div class="coverage-legend">
        <span><i class="obs"></i>地面实测</span>
        <span><i class="model"></i>模式数据</span>
        <span><i class="weather"></i>网格气象</span>
      </div>

      <p class="coverage-summary">{{ coverageSummary }}</p>

      <div
        class="coverage-calendar"
        role="list"
        aria-label="每日数据覆盖率"
        :style="{ gridTemplateColumns: `repeat(${columns}, minmax(24px, 1fr))` }"
      >
        <div
          v-for="day in coverage?.coverage ?? []"
          :key="day.day"
          class="coverage-day"
          role="listitem"
          :title="
            day.day +
            ' · 地面实测 ' +
            pct(day.observation_coverage) +
            ' · 模式 ' +
            pct(day.model_coverage) +
            ' · 气象 ' +
            pct(day.weather_coverage)
          "
        >
          <div :style="{ background: tone(day.observation_coverage, 'obs') }"></div>
          <div :style="{ background: tone(day.model_coverage, 'model') }"></div>
          <div :style="{ background: tone(day.weather_coverage, 'weather') }"></div>
          <small>{{ day.day.slice(5) }}</small>
        </div>
      </div>
    </div>

    <div class="trust-grid">
      <article>
        <h3>{{ bindingCopy }}</h3>
        <div v-if="coverage?.bindings.length" class="binding-list">
          <div v-for="binding in coverage.bindings" :key="binding.external_location_id">
            <span>
              <b>{{ binding.provider }}</b>
              <small>{{ binding.station_name }}</small>
            </span>
            <span class="binding-meta">
              <small>{{ binding.kind }}</small>
              <strong class="data-mono">
                {{ binding.is_authoritative ? "权威源" : "非权威源" }}
              </strong>
            </span>
          </div>
        </div>
        <p v-else class="empty-copy">图上只显示模式数据。</p>
      </article>

      <article>
        <h3>{{ analysisCopy }}</h3>
        <div v-if="coverage?.analyses.length" class="analysis-list">
          <div v-for="item in coverage.analyses" :key="item.run_id">
            <span>
              <b>{{ item.analysis_type }}</b>
              <small>
                {{ item.window_start.slice(0, 10) }} → {{ item.window_end.slice(0, 10) }}
              </small>
            </span>
            <span class="data-mono">{{ item.version }}</span>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.trust-panel {
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
  box-shadow: 0 10px 30px rgba(24, 41, 34, .045);
}
.panel-header {
  min-height: 78px;
  padding: 18px 20px 12px;
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 20px;
  border-bottom: 1px solid var(--hairline-soft);
}
.panel-header h2 {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-sub);
  font-weight: var(--fw-display);
  letter-spacing: var(--track-title);
}
.panel-meta {
  color: var(--muted);
  font-size: var(--fs-label);
  white-space: nowrap;
}

.coverage-block {
  padding: 18px 20px 20px;
  border-bottom: 1px solid var(--hairline-soft);
}
.coverage-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  color: var(--muted);
  font-size: var(--fs-label);
}
.coverage-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.coverage-legend i {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}
.coverage-legend .obs { background: rgb(47, 114, 95); }
.coverage-legend .model { background: rgb(53, 111, 135); }
.coverage-legend .weather { background: rgb(122, 90, 66); }

.coverage-summary {
  margin: 12px 0 16px;
  max-width: 82ch;
  color: var(--ink-soft);
  font-size: var(--fs-body);
  line-height: 1.7;
}

.coverage-calendar {
  display: grid;
  gap: 6px;
}
.coverage-day {
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  grid-template-rows: 28px auto;
  gap: 2px;
}
.coverage-day div { min-width: 0; border-radius: 2px; }
.coverage-day small {
  grid-column: 1 / -1;
  margin-top: 4px;
  color: var(--faint);
  font-family: var(--mono);
  font-size: var(--fs-label);
  text-align: center;
}

.trust-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
}
.trust-grid article {
  min-width: 0;
  padding: 18px 20px 20px;
}
.trust-grid article + article {
  border-left: 1px solid var(--hairline-soft);
}
.trust-grid h3 {
  margin: 0 0 14px;
  color: var(--ink);
  font-size: var(--fs-body);
  font-weight: var(--fw-strong);
  letter-spacing: var(--track-title);
}

.binding-list,
.analysis-list {
  display: grid;
}
.binding-list > div,
.analysis-list > div {
  min-height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-top: 1px solid var(--hairline-soft);
}
.binding-list > div:first-child,
.analysis-list > div:first-child {
  border-top: 0;
}
.binding-list span,
.analysis-list span:first-child {
  min-width: 0;
  display: grid;
  gap: 3px;
}
.binding-list b,
.analysis-list b {
  color: var(--ink);
  font-size: var(--fs-label);
  font-weight: var(--fw-strong);
}
.binding-list small,
.analysis-list small {
  color: var(--muted);
  font-size: var(--fs-label);
}
.binding-meta {
  justify-items: end;
}
.binding-meta strong {
  color: var(--ink-soft);
  font-family: var(--mono);
  font-size: var(--fs-label);
  font-weight: 600;
}
.analysis-list > div > span:last-child {
  max-width: 160px;
  overflow: hidden;
  color: var(--muted);
  font-family: var(--mono);
  font-size: var(--fs-label);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.empty-copy {
  margin: 0;
  color: var(--muted);
  font-size: var(--fs-label);
  line-height: 1.6;
}

@media (max-width: 860px) {
  .trust-grid { grid-template-columns: 1fr; }
  .trust-grid article + article {
    border-left: 0;
    border-top: 1px solid var(--hairline-soft);
  }
}
@media (max-width: 560px) {
  .coverage-day { grid-template-rows: 22px auto; }
}
</style>
