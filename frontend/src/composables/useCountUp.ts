import { onBeforeUnmount, ref, watch, type Ref } from "vue";

/* Eases a displayed number toward its target so hero stats land with weight
   instead of popping. Skips straight to the value under reduced motion. */
export function useCountUp(
  target: Ref<number | null | undefined>,
  duration = 900,
) {
  const display = ref(0);
  let frame = 0;

  function stop() {
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
  }

  function animateTo(value: number) {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      display.value = value;
      return;
    }
    stop();
    const from = display.value;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      display.value = from + (value - from) * eased;
      frame = t < 1 ? requestAnimationFrame(tick) : 0;
    };
    frame = requestAnimationFrame(tick);
  }

  watch(
    target,
    (value) => {
      if (value == null || !Number.isFinite(value)) return;
      animateTo(value);
    },
    { immediate: true },
  );

  onBeforeUnmount(stop);
  return display;
}
