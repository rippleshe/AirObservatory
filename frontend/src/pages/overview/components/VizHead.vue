<!-- VizHead — the one shared section head: a 2–4 字 functional label,
     centred and hairline-quiet; optional meta hugs the right edge. -->
<script setup lang="ts">
defineProps<{ label: string; meta?: string }>();
</script>

<template>
  <header class="viz-head">
    <h2 class="viz-label">{{ label }}</h2>
    <span v-if="meta" class="viz-meta data-mono">{{ meta }}</span>
  </header>
</template>

<style scoped>
.viz-head {
  position: relative;
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 24px;
}

.viz-label {
  margin: 0;
  color: var(--muted);
  font-size: 11.5px;
  font-weight: var(--fw-strong);
  letter-spacing: 0.2em;
}

.viz-meta {
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  color: var(--faint);
  font-size: 11.5px;
  white-space: nowrap;
}
</style>
