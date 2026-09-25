/* Provincial resolution for the national layer.
 *
 * The national layer answers "where in the country should I look", and that
 * question does not need sixty marks. Every province contributes exactly one
 * city, so the unit of comparison is the province and the count in the
 * headline, the band, the matrix and the region bars all describe the same
 * set. Sixty marks on the eastern seaboard collided into noise; the full
 * sixty-city roster stays available in the table twin, so no city becomes
 * unreachable.
 *
 * Which city represents a province: the one with the highest current AQI.
 * Not a fixed provincial capital — a fixed roster would let the national
 * headline name a city that is not the country's worst (河北's worst hour is
 * usually 保定, not 石家庄), and a headline that misnames the worst place is
 * a factual error, not a simplification. Ties fall through to PM2.5 and then
 * to the lower location_id, so the set is deterministic.
 */

import type { components } from "../api/schema";
import { AQI_LEVELS } from "./palette";

export type NationalCity = components["schemas"]["NationalCity"];
export type RegionRow = components["schemas"]["NationalRegion"];

function higher(a: NationalCity, b: NationalCity): NationalCity {
  if (a.china_aqi != null || b.china_aqi != null) {
    if (a.china_aqi == null) return b;
    if (b.china_aqi == null) return a;
    if (a.china_aqi !== b.china_aqi) return a.china_aqi > b.china_aqi ? a : b;
  }
  if (a.pm25 != null || b.pm25 != null) {
    if (a.pm25 == null) return b;
    if (b.pm25 == null) return a;
    if (a.pm25 !== b.pm25) return a.pm25 > b.pm25 ? a : b;
  }
  return a.location_id <= b.location_id ? a : b;
}

/** One city per province, in catalog order. */
export function provinceRepresentatives(cities: NationalCity[]): NationalCity[] {
  const best = new Map<string, NationalCity>();
  for (const city of cities) {
    const key = city.province || city.name;
    const held = best.get(key);
    best.set(key, held ? higher(held, city) : city);
  }
  return [...best.values()];
}

export function levelCounts(cities: NationalCity[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const level of AQI_LEVELS) counts[level] = 0;
  for (const city of cities) {
    const level = city.china_aqi_level;
    if (level && level in counts) counts[level] += 1;
  }
  return counts;
}

/** 优 + 良 — the two HJ 633-2026 levels that need no health caution. */
export function goodCount(cities: NationalCity[]): number {
  return cities.filter(
    (city) => city.china_aqi_level === "优" || city.china_aqi_level === "良",
  ).length;
}

/** Levels above 良, i.e. the provinces the headline asks the reader to watch. */
export function concernCount(cities: NationalCity[]): number {
  return cities.filter(
    (city) =>
      city.china_aqi_level != null &&
      city.china_aqi_level !== "优" &&
      city.china_aqi_level !== "良",
  ).length;
}

function mean(values: number[]): number | null {
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

/** Region aggregates recomputed over the displayed set, so bars and headline agree. */
export function regionSummary(cities: NationalCity[]): RegionRow[] {
  const groups = new Map<string, NationalCity[]>();
  for (const city of cities) {
    const key = city.region || "未分组";
    const held = groups.get(key);
    if (held) held.push(city);
    else groups.set(key, [city]);
  }
  return [...groups.entries()].map(([region, rows]) => ({
    region,
    city_count: rows.length,
    mean_pm25: mean(
      rows.map((row) => row.pm25).filter((value): value is number => value != null),
    ),
    mean_china_aqi: mean(
      rows.map((row) => row.china_aqi).filter((value): value is number => value != null),
    ),
  }));
}
