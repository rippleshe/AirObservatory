import { useQuery } from "@tanstack/vue-query";
import { api } from "../api/client";
import { expectData } from "../api/request";

/* The city catalog, read-only for every page. Filling in a default selection
   is the app shell's job (App.vue) — doing it here made four watchers race to
   write the same global field. */
export function useLocations() {
  return useQuery({
    queryKey: ["locations"],
    queryFn: () => expectData(api.GET("/api/locations")),
    staleTime: 30 * 60_000,
  });
}
