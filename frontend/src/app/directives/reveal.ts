import type { Directive } from "vue";

let observer: IntersectionObserver | null = null;

function getObserver(): IntersectionObserver {
  if (observer) return observer;
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer?.unobserve(entry.target);
        }
      }
    },
    { rootMargin: "0px 0px -6% 0px", threshold: 0.08 },
  );
  return observer;
}

/* v-reveal / v-reveal="120" — one-shot scroll entrance. Elements start with
   the .reveal state (hidden + risen) and settle once when they enter the
   viewport; the optional number staggers via --reveal-delay. Reduced motion
   is handled entirely in base.css, which pins .reveal to visible. */
export const vReveal: Directive<HTMLElement, number | undefined> = {
  mounted(el, binding) {
    el.classList.add("reveal");
    if (typeof binding.value === "number") {
      el.style.setProperty("--reveal-delay", `${binding.value}ms`);
    }
    getObserver().observe(el);
  },
  unmounted(el) {
    observer?.unobserve(el);
  },
};
