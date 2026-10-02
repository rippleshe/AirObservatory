/* Air Observatory data colour.
 *
 * Colour follows meaning, never rank. Three jobs, three rules:
 *   status     — AQI severity (HJ 633-2026) and 24h change direction
 *   identity   — Model Analysis / Observation / Forecast; PCA clusters
 *   magnitude  — PM2.5 concentration bands
 *
 * ── Validation (dataviz six-checks, light surface #fcfcfb) ──────────────
 * AQI_LEVEL_COLORS:
 *   [PASS] Chroma floor        all 6 >= 0.1  (no step reads gray)
 *   [PASS] CVD separation      worst adjacent 轻度污染↔良 ΔE 10.2 (deutan)
 *   [WARN] Contrast vs surface 良 #c9a521 at 2.3:1 — relieved by the
 *          mandatory level text (see aqiLevelText) and the table view.
 *   Accepted out-of-scope checks: the categorical lightness band (L .43–.77)
 *   and the normal-vision ΔE 15 floor are gates for *nominal* categories of
 *   equal weight. AQI is an ordered national severity scale — its light end
 *   (良) and dark end (严重污染) are supposed to sit outside that band, and
 *   the only pair whose confusion would misread the story (良 = acceptable vs
 *   轻度污染 = sensitive groups affected) is the pair that was fixed.
 *
 * History: the previous ramp collapsed 良 #b58a22 ↔ 轻度污染 #ce6a2f to
 * ΔE 2.5 (deutan) / 9.0 (normal) — those are the two most common levels on
 * the national map — and 严重污染 #6a2738 sat under the chroma floor (gray).
 * Re-run the validator after any edit:
 *   node scripts/validate_palette.js "<hex,...>" --mode light
 *
 * Colour is never the only channel: every AQI-coloured mark ships its level
 * text, and 24h change ships ↑/↓ plus a state word. DESIGN.md requires it.
 */

/** HJ 633-2026 severity order, best → worst. */
export const AQI_LEVELS = [
  "优",
  "良",
  "轻度污染",
  "中度污染",
  "重度污染",
  "严重污染",
] as const;

export type AqiLevel = (typeof AQI_LEVELS)[number];

export const AQI_LEVEL_COLORS: Record<string, string> = {
  优: "#45a274",
  良: "#c9a521",
  轻度污染: "#c8702b",
  中度污染: "#86251a",
  重度污染: "#703d88",
  严重污染: "#7a2240",
};

/** 24h change: diverging — neutral slate midpoint, saturated poles. */
export const CHANGE_LEVELS = ["明显改善", "改善", "稳定", "上升", "明显上升"] as const;

export const CHANGE_COLORS: Record<string, string> = {
  明显改善: "#047857",
  改善: "#10b981",
  稳定: "#94a3b8",
  上升: "#ea580c",
  明显上升: "#dc2626",
};

/** PM2.5 concentration bands — single-hue family, light → dark. */
export const PM25_BANDS: ReadonlyArray<readonly [string, string]> = [
  ["≤35", "#45a274"],
  ["35–75", "#c9a521"],
  ["75–115", "#c8702b"],
  ["115–150", "#86251a"],
  [">150", "#703d88"],
];

/* Identity colours mirror the --model / --observation / --forecast tokens in
   base.css (single design system, two render targets: CSS and ECharts). The
   former olive/moss trio belonged to a retired palette and read muddy on the
   slate canvas. */
export const MODEL_COLOR = "#0284c7";
export const OBSERVATION_COLOR = "#059669";
export const FORECAST_COLOR = "#d97706";
export const MUTED_DATA_COLOR = "#94a3b8";

/** PCA / exploratory clusters. Always shown with a persistent text legend —
 *  three slots fall under 3:1 contrast and need that relief. */
export const CATEGORY_COLORS = [
  "#2a78d6",
  "#eb6834",
  "#1baf7a",
  "#eda100",
  "#e87ba4",
  "#008300",
  "#4a3aa7",
  "#e34948",
] as const;

export function aqiColor(level: string | null | undefined) {
  return level ? AQI_LEVEL_COLORS[level] ?? MUTED_DATA_COLOR : MUTED_DATA_COLOR;
}

/** HJ 633-2026 level boundaries over IAQI — mirrors backend/analytics/aqi.py
 *  `level_of` so the time-machine projection and the server agree on words. */
export function levelOfAqi(aqi: number | null | undefined): AqiLevel | null {
  if (aqi == null || !Number.isFinite(aqi)) return null;
  if (aqi <= 50) return "优";
  if (aqi <= 100) return "良";
  if (aqi <= 150) return "轻度污染";
  if (aqi <= 200) return "中度污染";
  if (aqi <= 300) return "重度污染";
  return "严重污染";
}

/* ── stage variants ───────────────────────────────────────
   The chart field is the same light world as the cards, so marks keep the
   validated ramp exactly as published. The indirection stays as a single
   hook for any future surface that needs a lifted rendering variant. */
export function stageColor(hex: string | null | undefined) {
  return hex ?? MUTED_DATA_COLOR;
}

/** Redundant channel: the level word always travels with its colour. */
export function aqiLevelText(level: string | null | undefined) {
  return level ?? "暂无";
}

export function changeColor(value: number | null | undefined) {
  if (value == null) return MUTED_DATA_COLOR;
  if (value <= -25) return CHANGE_COLORS["明显改善"];
  if (value <= -8) return CHANGE_COLORS["改善"];
  if (value < 8) return CHANGE_COLORS["稳定"];
  if (value < 25) return CHANGE_COLORS["上升"];
  return CHANGE_COLORS["明显上升"];
}

/** Direction word + arrow. Never render change colour without this. */
export function changeState(value: number | null | undefined): {
  label: string;
  arrow: string;
} {
  if (value == null) return { label: "历史不足", arrow: "" };
  if (value <= -25) return { label: "明显改善", arrow: "↓" };
  if (value <= -8) return { label: "改善", arrow: "↓" };
  if (value < 8) return { label: "稳定", arrow: "→" };
  if (value < 25) return { label: "上升", arrow: "↑" };
  return { label: "明显上升", arrow: "↑" };
}

export function pm25Color(value: number | null | undefined, stage = false) {
  if (value == null) return MUTED_DATA_COLOR;
  let hex: string;
  if (value <= 35) hex = PM25_BANDS[0][1];
  else if (value <= 75) hex = PM25_BANDS[1][1];
  else if (value <= 115) hex = PM25_BANDS[2][1];
  else if (value <= 150) hex = PM25_BANDS[3][1];
  else hex = PM25_BANDS[4][1];
  return stage ? stageColor(hex) : hex;
}

export function clusterColor(cluster: number) {
  return CATEGORY_COLORS[(cluster - 1) % CATEGORY_COLORS.length];
}
