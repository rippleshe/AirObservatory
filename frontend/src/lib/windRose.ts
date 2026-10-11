/* Wind rose bins and stacked radial geometry, shared with numeric checks. */
export const WIND_SPEED_EDGES = [0.5, 2, 4, 7, Infinity] as const;

export function windSpeedBin(speed: number): number {
  for (let i = 0; i < WIND_SPEED_EDGES.length - 1; i++) {
    if (speed >= WIND_SPEED_EDGES[i]! && speed < WIND_SPEED_EDGES[i + 1]!) return i;
  }
  return -1;
}

/* Radial ring area is proportional to accumulated sample frequency. */
export function stackedWindRadii(before: number, count: number, maximum: number, radius: number) {
  const scale = (radius * 0.94) / Math.sqrt(Math.max(1, maximum));
  return {
    inner: Math.sqrt(before) * scale,
    outer: Math.sqrt(before + count) * scale,
  };
}
