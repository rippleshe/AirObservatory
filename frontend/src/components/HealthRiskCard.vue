<script setup lang="ts">
import { ShieldCheck } from "lucide-vue-next";
import { aqiColor } from "../lib/palette";

/* One line, zero sentences: the level word travels with its colour and the
   icon; the prose lives in the data, not on the page. */
defineProps<{
  level: string | null | undefined;
}>();
</script>

<template>
  <aside
    v-if="level"
    :class="['health-banner']"
    :style="{ '--risk-tone': aqiColor(level) }"
    aria-label="空气质量等级"
  >
    <span class="dot" aria-hidden="true"></span>
    <strong>{{ level }}</strong>
    <ShieldCheck class="shield-icon" :size="15" />
  </aside>
</template>

<style scoped>
.health-banner {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  min-height: 34px;
  padding: 0 14px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-pill);
  background: var(--sheet);
  box-shadow: var(--shadow-sm);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--risk-tone);
}

strong {
  font-size: 13px;
  font-weight: var(--fw-strong);
  color: var(--ink);
}

.shield-icon {
  color: var(--faint);
}
</style>
