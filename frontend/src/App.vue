<script setup lang="ts">
import { computed } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { Cpu, Database, MapPinned, Radar } from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";
import { api } from "./api/client";
import { expectData } from "./api/request";
import { useLocationCatalog } from "./composables/useLocationCatalog";
import { useContextStore } from "./stores/context";

const route = useRoute();
const router = useRouter();
const context = useContextStore();
const { locations } = useLocationCatalog();
const status = useQuery({
  queryKey: ["app-status"],
  queryFn: () => expectData(api.GET("/api/status")),
  refetchInterval: 30_000,
  staleTime: 15_000,
});

const title = computed(() => String(route.meta.title ?? "空气质量"));
const cityTo = computed(() => `/city/${context.selectedLocationId ?? 1}`);
const runtimeState = computed(() => {
  const providers = status.data.value?.providers;
  if (!providers) return "正在连接";
  const states = Object.values(providers).map((provider) => provider.state);
  if (states.every((state) => state === "healthy")) return "数据已连接";
  if (states.some((state) => state === "error")) return "部分数据异常";
  if (states.some((state) => state === "stale")) return "等待新数据";
  return "数据在线";
});

function selectGlobalLocation(event: Event) {
  const id = Number((event.target as HTMLSelectElement).value);
  const location = locations.data.value?.find((item) => item.location_id === id);
  if (!location) return;
  context.selectLocation(location.location_id, location.city);
  /* Switching must actually move the page: the city view derives everything
     from the route param, not the store. */
  if (route.name !== "city" || Number(route.params.locationId) !== location.location_id) {
    void router.push({ name: "city", params: { locationId: location.location_id } });
  }
}
</script>

<template>
  <div class="app-shell">
    <aside class="app-rail" aria-label="主导航">
      <RouterLink to="/overview" class="brand-mark" aria-label="Air Observatory 全国总览">
        <span class="radar-glow" aria-hidden="true"></span>
        <Radar :size="24" stroke-width="2" />
      </RouterLink>

      <nav>
        <RouterLink to="/overview" class="rail-link">
          <MapPinned :size="20" stroke-width="1.9" />
          <span>全国</span>
        </RouterLink>
        <RouterLink :to="cityTo" class="rail-link">
          <Radar :size="20" stroke-width="1.9" />
          <span>城市</span>
        </RouterLink>
        <RouterLink to="/model" class="rail-link">
          <Cpu :size="20" stroke-width="1.9" />
          <span>引擎</span>
        </RouterLink>
      </nav>

      <RouterLink to="/system" class="rail-method">
        <Database :size="18" stroke-width="1.8" />
        <span>数据</span>
      </RouterLink>
    </aside>

    <main class="app-main">
      <header class="context-bar">
        <div class="context-inner">
          <div class="context-title">
            <span class="product-name">Air Observatory</span>
            <strong>{{ title }}</strong>
          </div>
          <div class="context-meta">
            <div class="runtime-indicator" :title="runtimeState">
              <span class="runtime-pulse" aria-hidden="true"></span>
              <span>{{ runtimeState }}</span>
            </div>
            <label class="city-context">
              <span class="sr-only">选择城市</span>
              <select
                :value="route.name === 'city' ? Number(route.params.locationId) : context.selectedLocationId ?? ''"
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
          </div>
        </div>
      </header>
      <div class="page-body">
        <RouterView v-slot="{ Component }">
          <Transition name="route" mode="out-in">
            <component :is="Component" />
          </Transition>
        </RouterView>
      </div>
    </main>
  </div>
</template>
