<!-- SignalStrip — data-derived conclusions, zero prose: the cities worsening
     fastest over the next 24h (clickable → page-wide focus), the national
     peak window, how many cities improve. Basis: each city's latest CAMS
     snapshot against its current analysis reading. -->
<script setup lang="ts">
import type { components } from "../api/schema";

type Signals = components["schemas"]["OverviewSignalsResponse"];

defineProps<{ signals: Signals }>();
const emit = defineEmits<{ focus: [id: number, name: string] }>();

function fmtAt(iso: string): string {
  const at = new Date(iso);
  return `${at.getMonth() + 1}/${at.getDate()} ${String(at.getHours()).padStart(2, "0")}:00`;
}
</script>

<template>
  <div class="signal-strip">
    <div class="signal-group is-main">
      <span class="signal-k">恶化最快</span>
      <div class="signal-cities">
        <button
          v-for="signal in signals.worsening ?? []"
          :key="signal.location_id"
          type="button"
          class="signal-city"
          :title="`${signal.name} · 峰值 ${signal.peak} · ${fmtAt(signal.peak_at)}`"
          @click="emit('focus', signal.location_id, signal.name)"
        >
          <b>{{ signal.name }}</b>
          <span class="delta data-mono">+{{ signal.delta.toFixed(0) }}</span>
          <small class="data-mono">{{ fmtAt(signal.peak_at) }} · {{ signal.peak.toFixed(0) }}</small>
        </button>
        <span v-if="!signals.worsening?.length" class="signal-none">无显著恶化</span>
      </div>
    </div>

    <div class="signal-group">
      <span class="signal-k">全国峰值</span>
      <div class="signal-value">
        <b class="data-mono">{{ signals.peak?.value ?? "—" }}</b>
        <small v-if="signals.peak" class="data-mono">{{ fmtAt(signals.peak.target_at) }} · +{{ signals.peak.lead_hours }}h</small>
      </div>
    </div>

    <div class="signal-group">
      <span class="signal-k">转好</span>
      <div class="signal-value">
        <b class="data-mono ok">{{ signals.improving_count }} 城</b>
        <small class="data-mono">未来 24h</small>
      </div>
    </div>
  </div>
</template>

<style scoped>
.signal-strip {
  display: flex;
  align-items: stretch;
  gap: 0;
  flex-wrap: wrap;
}

.signal-group {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 6px 26px;
  border-left: 1px solid var(--hairline-soft);
}

.signal-group:first-child {
  padding-left: 0;
  border-left: 0;
}

.signal-k {
  color: var(--muted);
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
}

.signal-cities {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.signal-city {
  display: inline-flex;
  align-items: baseline;
  gap: 7px;
  padding: 6px 13px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-pill);
  background: var(--sheet);
  cursor: pointer;
  transition: all var(--duration-fast) ease;
}

.signal-city:hover {
  border-color: var(--ink);
  background: var(--ink);
}

.signal-city b {
  color: var(--ink);
  font-size: 12.5px;
  font-weight: 600;
}

.signal-city:hover b {
  color: #ffffff;
}

.signal-city .delta {
  color: #ea580c;
  font-size: 12px;
  font-weight: 700;
}

.signal-city:hover .delta {
  color: #fdba74;
}

.signal-city small {
  color: var(--faint);
  font-size: 10.5px;
}

.signal-city:hover small {
  color: rgba(255, 255, 255, 0.72);
}

.signal-none {
  color: var(--faint);
  font-size: 12px;
}

.signal-value {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.signal-value b {
  color: var(--ink);
  font-size: 16px;
  font-weight: 700;
}

.signal-value b.ok {
  color: #059669;
}

.signal-value small {
  color: var(--faint);
  font-size: 10.5px;
}
</style>
