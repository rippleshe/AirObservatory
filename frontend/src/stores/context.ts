import { defineStore } from "pinia";

/* The one cross-page channel: which city the top bar is pointing at. Pages
   keep their own focus/hover/toggle state locally, so leaving one page can
   never change what another page shows. */
export const useContextStore = defineStore("context", {
  state: () => ({
    selectedLocationId: null as number | null,
    selectedCityName: "全国",
  }),
  actions: {
    selectLocation(id: number, name: string) {
      this.selectedLocationId = id;
      this.selectedCityName = name;
    },
  },
});
