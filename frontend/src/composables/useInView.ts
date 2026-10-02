import { onBeforeUnmount, onMounted, ref, type Ref } from "vue";

/* True once the element has entered the viewport (one-shot). Charts gate
   their first paint on it, so every figure "grows in" exactly when the
   reader arrives instead of animating unseen at mount. */
export function useInView(target: Ref<HTMLElement | null>, rootMargin = "0px 0px -8% 0px") {
  const inView = ref(false);
  let observer: IntersectionObserver | null = null;

  onMounted(() => {
    if (!target.value || typeof IntersectionObserver === "undefined") {
      inView.value = true;
      return;
    }
    observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          inView.value = true;
          observer?.disconnect();
          observer = null;
        }
      },
      { rootMargin },
    );
    observer.observe(target.value);
  });

  onBeforeUnmount(() => observer?.disconnect());
  return inView;
}
