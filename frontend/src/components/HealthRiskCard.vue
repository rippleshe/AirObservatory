<script setup lang="ts">
import { ShieldAlert } from "lucide-vue-next";
import { aqiColor } from "../lib/palette";

defineProps<{
  city?: string | null;
  level: string | null | undefined;
  healthEffect: string | null | undefined;
  advice: string | null | undefined;
  compact?: boolean;
}>();
</script>

<template>
  <section
    v-if="level && (healthEffect || advice)"
    :class="['health-guidance', { compact }]"
    :style="{ '--risk-tone': aqiColor(level) }"
  >
    <div class="health-heading">
      <span class="risk-dot" aria-hidden="true"></span>
      <div>
        <h3 v-if="compact">{{ city ? `当前最需要关注：${city}` : "当前健康提示" }}</h3>
        <h3 v-else>当前等级下的健康影响与建议</h3>
        <span>{{ level }}</span>
      </div>
      <ShieldAlert :size="compact ? 15 : 17" />
    </div>

    <div class="health-copy">
      <p v-if="healthEffect && !compact">
        <b>可能的影响</b>
        <span>{{ healthEffect }}</span>
      </p>
      <p v-if="advice">
        <b>建议</b>
        <span>{{ advice }}</span>
      </p>
    </div>

    <footer v-if="!compact">
      空气质量等级按 HJ 633-2026 规则由当前模式浓度换算；健康建议来自标准指引。
    </footer>
  </section>
</template>

<style scoped>
.health-guidance {
  overflow: hidden;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--sheet);
}
.health-heading {
  min-height: 58px;
  padding: 0 17px;
  display: grid;
  grid-template-columns: 11px 1fr 20px;
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid var(--hairline-soft);
}
.risk-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--risk-tone);
}
.health-heading h3 {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-body);
  font-weight: var(--fw-strong);
}
.health-heading span {
  display: block;
  margin-top: 2px;
  color: var(--muted);
  font-size: var(--fs-label);
}
.health-heading svg { color: var(--muted); }
.health-copy {
  display: grid;
  grid-template-columns: 1fr 1fr;
}
.health-copy p {
  min-width: 0;
  margin: 0;
  padding: 15px 17px;
  display: grid;
  gap: 5px;
}
.health-copy p + p { border-left: 1px solid var(--hairline-soft); }
.health-copy b {
  color: var(--ink-soft);
  font-size: var(--fs-label);
  font-weight: var(--fw-strong);
}
.health-copy span {
  color: var(--muted);
  font-size: var(--fs-body);
  line-height: 1.6;
}
.health-guidance footer {
  padding: 10px 17px;
  border-top: 1px solid var(--hairline-soft);
  color: var(--muted);
  font-size: var(--fs-label);
  line-height: 1.55;
}
.health-guidance.compact {
  display: grid;
  grid-template-columns: minmax(220px, .75fr) minmax(0, 1.25fr);
}
.health-guidance.compact .health-heading {
  min-height: 62px;
  border-bottom: 0;
  border-right: 1px solid var(--hairline);
}
.health-guidance.compact .health-copy {
  display: block;
}
.health-guidance.compact .health-copy p {
  min-height: 62px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.health-guidance.compact .health-copy p + p { border-left: 0; }
.health-guidance.compact .health-copy b { flex: 0 0 auto; }

@media (max-width: 720px) {
  .health-copy { grid-template-columns: 1fr; }
  .health-copy p + p {
    border-left: 0;
    border-top: 1px solid var(--hairline);
  }
  .health-guidance.compact { grid-template-columns: 1fr; }
  .health-guidance.compact .health-heading {
    border-right: 0;
    border-bottom: 1px solid var(--hairline);
  }
}
</style>
