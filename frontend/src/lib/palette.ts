/* Air Observatory data colour.
 *
 * Colour follows meaning, never rank. Three jobs, three rules:
 *   status     — AQI severity (HJ 633-2026) and 24h change direction
 *   identity   — Model Analysis / Observation / Forecast; PCA clusters
 *   magnitude  — PM2.5 concentration bands
 *
 * ── Validation (re-derived 2026-10-03, light surface #ffffff) ───────────
 * AQI_LEVEL_COLORS (clean luminous set — the previous olive-gold 良 and
 * plum 重度 read muddy on white, a standing user complaint):
 *   normal-vision adjacent ΔE ≥ 34.6 (floor 15)
 *   deutan min adjacent ΔE 21.1, protan 21.5 (floor 10)
 *   良 #eab308 sits at 1.92:1 vs white — relieved by the mandatory level
 *   text that ships with every AQI-coloured mark (aqiLevelText).
 *
 * Colour is never the only channel: every AQI-coloured mark ships its level
 * text, and 24h change ships ↑/↓ plus a state word.
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
  优: "#10b981",
  良: "#eab308",
  轻度污染: "#f97316",
  中度污染: "#ef4444",
  重度污染: "#8b5cf6",
  严重污染: "#9f1239",
};

/** 24h change: diverging — neutral slate midpoint, saturated poles. */
export const CHANGE_LEVELS = ["明显改善", "改善", "稳定", "上升", "明显上升"] as const;

export const CHANGE_COLORS: Record<string, string> = {
  明显改善: "#047857",
  改善: "#10b981",
  稳定: "#94a3b8",
  上升: "#f97316",
  明显上升: "#ef4444",
};

/** PM2.5 concentration bands — single-hue family, light → dark. */
export const PM25_BANDS: ReadonlyArray<readonly [string, string]> = [
  ["≤35", "#10b981"],
  ["35–75", "#eab308"],
  ["75–115", "#f97316"],
  ["115–150", "#ef4444"],
  [">150", "#8b5cf6"],
];

/* One ramp rules every magnitude variable: the validated five-hue severity
   ramp above, only the thresholds move. Worse always reads redder, whichever
   pollutant the loom is weaving — no new colour pairs to validate. */
const SEVERITY_RAMP = PM25_BANDS.map(([, color]) => color);

export type VariableBand = {
  label: string;
  unit: string;
  bands: ReadonlyArray<readonly [string, string]>;
  /** 警戒阈值 — exceed-hour counts and warnings read off this. */
  exceed: number;
  /** visualMap ceiling hint before data adaptation. */
  max: number;
};

/* Thresholds follow HJ 633-2026 IAQI grade boundaries (1-hour averages;
   CO in mg/m³). AQI keeps the six-word level ramp — it IS the severity
   scale, not a magnitude. */
export const VARIABLE_BANDS: Record<string, VariableBand> = {
  aqi: {
    label: "AQI",
    unit: "",
    bands: AQI_LEVELS.map((level) => [level, AQI_LEVEL_COLORS[level]] as const),
    exceed: 100,
    max: 300,
  },
  pm25: { label: "PM2.5", unit: "µg/m³", bands: PM25_BANDS, exceed: 75, max: 160 },
  pm10: {
    label: "PM10",
    unit: "µg/m³",
    bands: [
      ["≤50", SEVERITY_RAMP[0]],
      ["50–150", SEVERITY_RAMP[1]],
      ["150–250", SEVERITY_RAMP[2]],
      ["250–350", SEVERITY_RAMP[3]],
      [">350", SEVERITY_RAMP[4]],
    ],
    exceed: 150,
    max: 400,
  },
  o3: {
    label: "O₃",
    unit: "µg/m³",
    bands: [
      ["≤160", SEVERITY_RAMP[0]],
      ["160–200", SEVERITY_RAMP[1]],
      ["200–300", SEVERITY_RAMP[2]],
      ["300–400", SEVERITY_RAMP[3]],
      [">400", SEVERITY_RAMP[4]],
    ],
    exceed: 200,
    max: 450,
  },
  no2: {
    label: "NO₂",
    unit: "µg/m³",
    bands: [
      ["≤100", SEVERITY_RAMP[0]],
      ["100–200", SEVERITY_RAMP[1]],
      ["200–700", SEVERITY_RAMP[2]],
      ["700–1200", SEVERITY_RAMP[3]],
      [">1200", SEVERITY_RAMP[4]],
    ],
    exceed: 200,
    max: 300,
  },
  so2: {
    label: "SO₂",
    unit: "µg/m³",
    bands: [
      ["≤150", SEVERITY_RAMP[0]],
      ["150–500", SEVERITY_RAMP[1]],
      ["500–650", SEVERITY_RAMP[2]],
      ["650–800", SEVERITY_RAMP[3]],
      [">800", SEVERITY_RAMP[4]],
    ],
    exceed: 500,
    max: 650,
  },
  co: {
    label: "CO",
    unit: "mg/m³",
    bands: [
      ["≤5", SEVERITY_RAMP[0]],
      ["5–10", SEVERITY_RAMP[1]],
      ["10–35", SEVERITY_RAMP[2]],
      ["35–60", SEVERITY_RAMP[3]],
      [">60", SEVERITY_RAMP[4]],
    ],
    exceed: 10,
    max: 14,
  },
};

/* Identity colours mirror the --model / --observation / --forecast tokens in
   base.css (single design system, two render targets: CSS and ECharts). The
   former olive/moss trio belonged to a retired palette and read muddy on the
   slate canvas. */
export const MODEL_COLOR = "#0284c7";
export const OBSERVATION_COLOR = "#059669";
export const FORECAST_COLOR = "#d97706";
export const MUTED_DATA_COLOR = "#94a3b8";

/** PCA / exploratory clusters + nominal series (stream layers). Clean,
 *  luminous hues; always shown with a persistent text legend. */
export const CATEGORY_COLORS = [
  "#2563eb",
  "#f97316",
  "#10b981",
  "#eab308",
  "#ec4899",
  "#8b5cf6",
  "#06b6d4",
  "#ef4444",
] as const;

/** Six-pollutant identity for horizon/stream layers (nominal, not severity). */
export const POLLUTANT_COLORS: Record<string, string> = {
  pm25: "#f97316",
  pm10: "#eab308",
  no2: "#10b981",
  o3: "#2563eb",
  so2: "#ec4899",
  co: "#8b5cf6",
};

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
