import { defineStore } from "pinia";

export type Metric = "pm25" | "pm10" | "no2" | "o3" | "aqi" | "reference_aqi";
export type DataKind = "model_analysis" | "observation";

export const useContextStore = defineStore("context", {
  state: () => ({
    selectedLocationId: null as number | null,
    selectedCityName: "全国",
    selectedMetric: "pm25" as Metric,
    selectedDataKind: "model_analysis" as DataKind,
    historyHours: 48,
    /* Pinned city on the national layer: one selection, every chart answers
       (map card, band squares, weave row, chord node, fingerprint dot). */
    focusId: null as number | null,
    focusName: null as string | null,
  }),
  actions: {
    selectLocation(id: number, name: string) {
      this.selectedLocationId = id;
      this.selectedCityName = name;
    },
    setFocus(id: number, name: string | null = null) {
      this.focusId = id;
      this.focusName = name;
    },
    clearFocus() {
      this.focusId = null;
      this.focusName = null;
    },
  },
});
