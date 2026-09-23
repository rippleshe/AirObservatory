import { computed, watch } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { api } from "../api/client";
import { expectData } from "../api/request";
import { useContextStore } from "../stores/context";

export function useLiveField() {
  const context = useContextStore();
  const selectedId = computed(() => context.selectedLocationId);

  const status = useQuery({
    queryKey: ["status"],
    queryFn: () => expectData(api.GET("/api/status")),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const overview = useQuery({
    queryKey: computed(() => [
      "overview",
      context.selectedMetric,
      "model_analysis",
    ]),
    queryFn: () =>
      expectData(
        api.GET("/api/overview", {
          params: {
            query: {
              metric: context.selectedMetric,
              data_kind: "model_analysis",
            },
          },
        }),
      ),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  watch(
    () => overview.data.value?.locations,
    (locations) => {
      if (!locations?.length) return;
      const current = locations.find(
        (location) => location.location_id === context.selectedLocationId,
      );
      if (!current) {
        context.selectLocation(locations[0].location_id, locations[0].name);
      }
    },
    { immediate: true },
  );

  const snapshot = useQuery({
    queryKey: computed(() => ["snapshot", selectedId.value]),
    enabled: computed(() => selectedId.value != null),
    queryFn: () =>
      expectData(
        api.GET("/api/locations/{location_id}/snapshot", {
          params: { path: { location_id: selectedId.value! } },
        }),
      ),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const modelHistory = useQuery({
    queryKey: computed(() => [
      "series",
      selectedId.value,
      context.selectedMetric,
      "model_analysis",
      context.historyHours,
    ]),
    enabled: computed(() => selectedId.value != null),
    queryFn: () =>
      expectData(
        api.GET("/api/locations/{location_id}/series", {
          params: {
            path: { location_id: selectedId.value! },
            query: {
              variable: context.selectedMetric,
              data_kind: "model_analysis",
              hours: context.historyHours,
            },
          },
        }),
      ),
    refetchInterval: 5 * 60_000,
    staleTime: 60_000,
  });

  const observationHistory = useQuery({
    queryKey: computed(() => [
      "series",
      selectedId.value,
      context.selectedMetric,
      "observation",
      context.historyHours,
    ]),
    enabled: computed(() => selectedId.value != null),
    queryFn: () =>
      expectData(
        api.GET("/api/locations/{location_id}/series", {
          params: {
            path: { location_id: selectedId.value! },
            query: {
              variable: context.selectedMetric,
              data_kind: "observation",
              hours: context.historyHours,
            },
          },
        }),
      ),
    refetchInterval: 5 * 60_000,
    staleTime: 60_000,
  });

  const forecast = useQuery({
    queryKey: computed(() => [
      "forecast",
      selectedId.value,
      context.selectedMetric,
    ]),
    enabled: computed(() => selectedId.value != null),
    queryFn: () =>
      expectData(
        api.GET("/api/locations/{location_id}/forecast", {
          params: {
            path: { location_id: selectedId.value! },
            query: { variable: context.selectedMetric },
          },
        }),
      ),
    refetchInterval: 5 * 60_000,
    staleTime: 60_000,
  });

  function retryPrimary() {
    void Promise.all([
      status.refetch(),
      overview.refetch(),
      snapshot.refetch(),
      modelHistory.refetch(),
      observationHistory.refetch(),
      forecast.refetch(),
    ]);
  }

  return {
    context,
    selectedId,
    status,
    overview,
    snapshot,
    modelHistory,
    observationHistory,
    forecast,
    retryPrimary,
  };
}
