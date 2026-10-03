import type { Directive } from "vue";
import { gsap, riseOnScroll, ScrollTrigger } from "../../lib/motion";

/* v-reveal / v-reveal="120" — one-shot scroll entrance backed by GSAP
   (lib/motion.ts). The optional number staggers the element by milliseconds.
   Elements must start visually consistent with the pre-animation state;
   riseOnScroll handles the from-state itself, and reduced motion collapses
   to instantly visible. */
export const vReveal: Directive<HTMLElement, number | undefined> = {
  mounted(el, binding) {
    riseOnScroll(el, typeof binding.value === "number" ? binding.value / 1000 : 0);
  },
  unmounted(el) {
    ScrollTrigger.getAll().forEach((trigger) => {
      if (trigger.trigger === el) trigger.kill();
    });
    gsap.killTweensOf(el);
  },
};
