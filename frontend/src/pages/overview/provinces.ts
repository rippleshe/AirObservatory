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

import type { components } from "../../api/schema";

export type NationalCity = components["schemas"]["NationalCity"];

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
