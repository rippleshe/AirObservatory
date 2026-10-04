<!-- ModelView — the prediction engine page: a thin shell around LstmEngine,
     which renders the trained hand-written numpy LSTM's real computation —
     input band, gate-activation replay, 24h decode and baseline comparison.
     Until the worker's first (nightly) training lands, the page says so. -->
<script setup lang="ts">
import { computed } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { api } from "../api/client";
import { expectData } from "../api/request";
import { useLocationCatalog } from "../composables/useLocationCatalog";
import { useContextStore } from "../stores/context";
import LstmEngine from "../components/LstmEngine.vue";

const context = useContextStore();
const { locations } = useLocationCatalog();

const locationId = computed(
  () => context.selectedLocationId ?? locations.data.value?.[0]?.location_id ?? 1,
);

const city = computed(
  () => locations.data.value?.find((item) => item.location_id === locationId.value)?.city ?? "",
);

const run = useQuery({
  queryKey: computed(() => ["model-lstm", locationId.value]),
  queryFn: () =>
    expectData(
      api.GET("/api/models/{location_id}/lstm", {
        params: { path: { location_id: locationId.value } },
      }),
    ),
  staleTime: 5 * 60_000,
  refetchInterval: 10 * 60_000,
  retry: 0,
});

/* CAMS + baselines ride the decode act alongside the LSTM line. */
const forecast = useQuery({
  queryKey: computed(() => ["model-forecast", locationId.value]),
  queryFn: () =>
    expectData(
      api.GET("/api/locations/{location_id}/forecast", {
        params: {
          path: { location_id: locationId.value },
          query: { variable: "pm25" },
        },
      }),
    ),
  refetchInterval: 5 * 60_000,
});

const cams = computed(() =>
  (forecast.data.value?.series ?? [])
    .filter((series) => series.model_name !== "LSTM")
    .map((series) => ({
      name: series.model_name,
      points: series.points.map((point) => ({
        target: point.target_at,
        value: point.value,
        lower: point.lower_bound ?? null,
        upper: point.upper_bound ?? null,
      })),
    })),
);
</script>

<template>
  <section class="model-view">
    <header class="model-head">
      <h1 class="page-title">预测引擎</h1>
      <span class="head-meta data-mono">{{ city }} · 手写 numpy LSTM · CAMS + 基线</span>
    </header>

    <div v-if="run.data.value" v-reveal class="engine-wrap">
      <LstmEngine :run="run.data.value" :cams="cams" />
    </div>

    <div v-else-if="run.isPending.value" class="engine-state">
      <div class="skeleton engine-skeleton" role="status"></div>
    </div>

    <div v-else class="engine-state">
      <span class="state-word">训练中</span>
      <span class="state-hint data-mono">worker 每晚重训 · 就绪后自动点亮</span>
    </div>
  </section>
</template>

<style scoped>
.model-view {
  min-height: calc(100vh - 64px);
  padding: 28px var(--page-pad) 56px;
  display: grid;
  gap: 26px;
  align-content: start;
  background: var(--canvas);
}

.model-head {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 18px;
}

.page-title {
  margin: 0;
  color: var(--muted);
  font-size: 11.5px;
  font-weight: var(--fw-strong);
  letter-spacing: 0.2em;
}

.head-meta {
  color: var(--faint);
  font-size: 11px;
}

.engine-wrap {
  min-width: 0;
}

.engine-state {
  min-height: 320px;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 10px;
}

.state-word {
  color: var(--muted);
  font-size: var(--fs-body);
}

.state-hint {
  color: var(--faint);
  font-size: 11px;
}

.engine-skeleton {
  width: min(100%, 980px);
  height: 320px;
  border-radius: var(--radius-lg);
}
</style>
