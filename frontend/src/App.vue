<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { useRoute } from "vue-router";
import { Activity, Database, FlaskConical, Map, Radar } from "lucide-vue-next";
import { api } from "./api/client";
import { expectData } from "./api/request";
import { useLocationCatalog } from "./composables/useLocationCatalog";
import { useContextStore } from "./stores/context";

const route = useRoute();
const context = useContextStore();
const { locations } = useLocationCatalog();
const status = useQuery({
  queryKey: ["app-status"],
  queryFn: () => expectData(api.GET("/api/status")),
  refetchInterval: 30_000,
  staleTime: 15_000,
});
const now = ref(new Date());
let timer = 0;

onMounted(() => {
  timer = window.setInterval(() => (now.value = new Date()), 1000);
});
onBeforeUnmount(() => window.clearInterval(timer));

const title = computed(() => String(route.meta.title ?? "态势"));
const clock = computed(() =>
  new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(now.value),
);
const runtimeState = computed(() => {
  const providers = status.data.value?.providers;
  if (!providers) return "CHECKING";
  const states = Object.values(providers).map((provider) => provider.state);
  if (states.every((state) => state === "healthy")) return "LIVE";
  if (states.some((state) => state === "error")) return "DEGRADED";
  if (states.some((state) => state === "stale")) return "STALE";
  return "ONLINE";
});

function selectGlobalLocation(event: Event) {
  const id = Number((event.target as HTMLSelectElement).value);
  const location = locations.data.value?.find((item) => item.location_id === id);
  if (location) {
    context.selectLocation(location.location_id, location.city);
  }
}

const nav = [
  { to: "/live", label: "态势", icon: Map },
  { to: "/explore", label: "探索", icon: FlaskConical },
  { to: "/forecast", label: "预测", icon: Activity },
  { to: "/system", label: "系统", icon: Database },
];
</script>

<template>
  <div class="app-shell">
    <aside class="app-rail" aria-label="主导航">
      <div class="brand-mark" title="Air Observatory"><Radar :size="22" /></div>
      <nav>
        <RouterLink
          v-for="item in nav"
          :key="item.to"
          :to="item.to"
          class="rail-link"
          :aria-label="item.label"
        >
          <component :is="item.icon" :size="19" stroke-width="1.7" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="rail-live">
        <span
          :class="['live-dot', runtimeState.toLowerCase()]"
          :title="`Runtime status: ${runtimeState}`"
        ></span>
        <span>{{ runtimeState }}</span>
      </div>
    </aside>

    <main class="app-main">
      <header class="context-bar">
        <div class="context-title">
          <span class="product-name">AIR OBSERVATORY</span>
          <strong>{{ title }}</strong>
        </div>
        <div class="context-meta">
          <label class="city-context">
            <span class="sr-only">城市</span>
            <select
              :value="context.selectedLocationId ?? ''"
              @change="selectGlobalLocation"
            >
              <option
                v-for="location in locations.data.value ?? []"
                :key="location.location_id"
                :value="location.location_id"
              >
                {{ location.city }}
              </option>
            </select>
          </label>
          <span>{{ context.selectedMetric.toUpperCase() }}</span>
          <time>{{ clock }}</time>
        </div>
      </header>
      <RouterView />
    </main>
  </div>
</template>
