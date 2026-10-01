<script setup lang="ts">
import { ShieldCheck } from "lucide-vue-next";
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
  <aside
    v-if="level && (healthEffect || advice)"
    :class="['health-banner', { compact }]"
    :style="{ '--risk-tone': aqiColor(level) }"
    aria-label="健康指引与建议"
  >
    <div class="banner-badge">
      <span class="dot" aria-hidden="true"></span>
      <strong>{{ level }}</strong>
    </div>

    <div class="banner-content">
      <span v-if="healthEffect" class="effect-text">{{ healthEffect }}</span>
      <span v-if="healthEffect && advice" class="separator">·</span>
      <span v-if="advice" class="advice-text">{{ advice }}</span>
    </div>

    <ShieldCheck class="shield-icon" :size="16" />
  </aside>
</template>

<style scoped>
.health-banner {
  display: flex;
  align-items: center;
  gap: 16px;
  min-height: 48px;
  padding: 0 20px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-md);
  background: var(--sheet);
  box-shadow: var(--shadow-sm);
  transition: all var(--duration-fast) ease;
}

.banner-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

.banner-badge .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--risk-tone);
}

.banner-badge strong {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}

.banner-content {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--muted);
}

.effect-text {
  color: var(--ink-soft);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.separator {
  color: var(--faint);
}

.advice-text {
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.shield-icon {
  color: var(--faint);
  flex: none;
}

@media (max-width: 768px) {
  .health-banner {
    flex-wrap: wrap;
    padding: 12px 16px;
    gap: 8px;
  }
  .banner-content {
    flex-basis: 100%;
    flex-direction: column;
    gap: 4px;
  }
  .separator { display: none; }
  .shield-icon { display: none; }
}
</style>
