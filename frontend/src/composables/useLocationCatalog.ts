import { watch } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { api } from "../api/client";
import { expectData } from "../api/request";
import { useContextStore } from "../stores/context";

export function useLocationCatalog() {
  const context = useContextStore();
  const locations = useQuery({
    queryKey: ["locations"],
    queryFn: () => expectData(api.GET("/api/locations")),
    staleTime: 30 * 60_000,
  });

  watch(
    () => locations.data.value,
    (items) => {
      if (!items?.length) return;
      const selected = items.find(
        (item) => item.location_id === context.selectedLocationId,
      );
      if (!selected) {
        context.selectLocation(items[0].location_id, items[0].city);
      }
    },
    { immediate: true },
  );

  return { locations };
}
