/* Shared low-level helpers for the hand-written SVG charts. No framework
   imports: every function here is pure geometry or time formatting so chart
   components stay focused on what they draw. */
import { onBeforeUnmount, onMounted, ref, type Ref } from "vue";

export function useElementSize(el: Ref<HTMLElement | null>) {
  const size = ref({ w: 0, h: 0 });
  let observer: ResizeObserver | null = null;
  onMounted(() => {
    if (!el.value) return;
    observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) size.value = { w: width, h: height };
    });
    observer.observe(el.value);
  });
  onBeforeUnmount(() => observer?.disconnect());
  return size;
}

/* Catmull-Rom → cubic bezier: smooth through every point without overshoot
   control from the caller. Points are [x, y]; returns a path string that
   starts with M (caller appends area closing segments as needed). */
export function smoothPath(points: Array<[number, number]>, tension = 0.5): string {
  if (points.length === 0) return "";
  if (points.length === 1) return `M${points[0][0]},${points[0][1]}`;
  let d = `M${points[0][0]},${points[0][1]}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(0, i - 1)];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[Math.min(points.length - 1, i + 2)];
    const c1x = p1[0] + ((p2[0] - p0[0]) / 6) * tension * 2;
    const c1y = p1[1] + ((p2[1] - p0[1]) / 6) * tension * 2;
    const c2x = p2[0] - ((p3[0] - p1[0]) / 6) * tension * 2;
    const c2y = p2[1] - ((p3[1] - p1[1]) / 6) * tension * 2;
    d += ` C${c1x.toFixed(2)},${c1y.toFixed(2)} ${c2x.toFixed(2)},${c2y.toFixed(2)} ${p2[0].toFixed(2)},${p2[1].toFixed(2)}`;
  }
  return d;
}

/* Forward-fill short holes in an hourly series so stream layers stay
   continuous; long leading holes stay 0 and long trailing holes stay null
   (the pattern is not invented where the field genuinely ends). */
export function filled(values: Array<number | null>): number[] {
  const out: number[] = [];
  let last = 0;
  for (const value of values) {
    if (value != null && Number.isFinite(value)) last = value;
    out.push(last);
  }
  return out;
}

export function mean(values: number[]): number {
  if (!values.length) return 0;
  let sum = 0;
  for (const value of values) sum += value;
  return sum / values.length;
}

/* day-key helper for daily bucketing (local calendar days). */
export function dayKey(iso: string): string {
  return new Date(iso).toISOString().slice(0, 10);
}

/* Sparse x-axis ticks: ~1 tick every `span` days, formatted M/D. */
export function dayTicks(times: string[], spanDays = 7): Array<{ index: number; label: string }> {
  const ticks: Array<{ index: number; label: string }> = [];
  let lastDay = -1;
  times.forEach((time, index) => {
    const date = new Date(time);
    const day = Math.floor(date.getTime() / 86_400_000);
    if (day === lastDay) return;
    lastDay = day;
    const dayIndex = Math.floor(index / 24);
    if (dayIndex % spanDays === 0) {
      ticks.push({ index, label: `${date.getMonth() + 1}/${date.getDate()}` });
    }
  });
  return ticks;
}
