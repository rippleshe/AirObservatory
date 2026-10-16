/* Per-pollutant band definitions for the national loom.
 *
 * This belongs to the overview page, not to the shared palette: the keys of
 * VARIABLE_BANDS drive that page's variable buttons, so adding a pollutant
 * here must never change another page. Colours still come from the shared
 * palette tokens.
 *
 * Thresholds follow HJ 633-2026 IAQI grade boundaries (1-hour averages;
 * CO in mg/m³). AQI keeps the six-word level ramp — it IS the severity
 * scale, not a magnitude.
 */
import { AQI_LEVEL_COLORS, AQI_LEVELS, PM25_BANDS } from "../../lib/palette";

export type VariableBand = {
  label: string;
  unit: string;
  bands: ReadonlyArray<readonly [string, string]>;
  /** 警戒阈值 — exceed-hour counts and warnings read off this. */
  exceed: number;
  /** visualMap ceiling hint before data adaptation. */
  max: number;
};

/* One ramp rules every magnitude variable: the validated five-hue severity
   ramp, only the thresholds move. Worse always reads redder, whichever
   pollutant the loom is weaving — no new colour pairs to validate. */
const SEVERITY_RAMP = PM25_BANDS.map(([, color]) => color);

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
