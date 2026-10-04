/* Single motion authority. Every entrance, scrub and draw-in in the app goes
   through here so timing, easing and reduced-motion behave identically —
   GSAP 3.13+ ships ScrollTrigger and DrawSVG free, so nothing here is
   feature-gated. Views import { gsap, ScrollTrigger } from this module, never
   from "gsap" directly, or ScrollTrigger registration would fork. */
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export { gsap, ScrollTrigger };

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

/* Shared entrance vocabulary. `rise` is the section-level settle, `pop` the
   small-element accent; both accept a delay in seconds so callers can
   orchestrate beats without building timelines for one-shots. */
export function rise(el: gsap.TweenTarget, delay = 0) {
  if (prefersReducedMotion()) return gsap.set(el, { autoAlpha: 1 });
  return gsap.fromTo(
    el,
    { autoAlpha: 0, y: 18 },
    {
      autoAlpha: 1,
      y: 0,
      duration: 0.7,
      delay,
      ease: "power2.out",
      overwrite: "auto",
    },
  );
}

/* Scroll-gated variant: element stays hidden until it crosses the viewport,
   then plays once. Replaces the old IntersectionObserver+CSS reveal while
   keeping the same visual contract. */
export function riseOnScroll(el: HTMLElement, delay = 0) {
  if (prefersReducedMotion()) {
    gsap.set(el, { autoAlpha: 1 });
    return;
  }
  gsap.fromTo(
    el,
    { autoAlpha: 0, y: 18 },
    {
      autoAlpha: 1,
      y: 0,
      duration: 0.7,
      delay,
      ease: "power2.out",
      scrollTrigger: { trigger: el, start: "top 90%", once: true },
    },
  );
}

/* Stroke draw-in for SVG paths/lines: measures each path and sweeps its
   dash offset, so charts "hand-draw" instead of fading in. Call after the
   path is in the DOM; safe to call on non-SVG targets (no-op). */
export function drawIn(
  targets: gsap.TweenTarget,
  options: { duration?: number; delay?: number; stagger?: number } = {},
) {
  if (prefersReducedMotion()) return;
  const { duration = 1.1, delay = 0, stagger = 0.08 } = options;
  const paths = gsap.utils
    .toArray(targets)
    .filter((el): el is SVGGeometryElement => el instanceof SVGGeometryElement);
  paths.forEach((path, index) => {
    const length = path.getTotalLength?.() ?? 0;
    if (!length) return;
    gsap.set(path, { strokeDasharray: length, strokeDashoffset: length });
    gsap.to(path, {
      strokeDashoffset: 0,
      duration,
      delay: delay + index * stagger,
      ease: "power1.inOut",
    });
  });
}

/* FLIP re-order for keyed flex/grid children: measure each element's slot,
   let `apply()` produce the new order (it must await the DOM update), then
   play every element from its old slot to its new one. Works on rows and
   columns alike — the delta is taken per axis. */
export function flipReorder(
  items: HTMLElement[],
  apply: () => Promise<void> | void,
  options: { duration?: number } = {},
) {
  const { duration = 0.55 } = options;
  if (prefersReducedMotion()) {
    void apply();
    return;
  }
  const first = new Map(items.map((el) => [el, el.getBoundingClientRect()]));
  Promise.resolve(apply()).then(() => {
    requestAnimationFrame(() => {
      for (const el of items) {
        const before = first.get(el);
        if (!before) continue;
        const after = el.getBoundingClientRect();
        const dx = before.left - after.left;
        const dy = before.top - after.top;
        if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) continue;
        gsap.fromTo(
          el,
          { x: dx, y: dy },
          { x: 0, y: 0, duration, ease: "power3.out", clearProps: "x,y" },
        );
      }
    });
  });
}

/* Clip-path wipe used by area/ridge/stream sections: the band rises out of
   its baseline instead of popping. `from` is a CSS clip-path inset value. */
export function wipeUp(el: gsap.TweenTarget, delay = 0) {
  if (prefersReducedMotion()) return gsap.set(el, { autoAlpha: 1 });
  return gsap.fromTo(
    el,
    { autoAlpha: 0, clipPath: "inset(100% 0% 0% 0%)" },
    {
      autoAlpha: 1,
      clipPath: "inset(0% 0% 0% 0%)",
      duration: 1.0,
      delay,
      ease: "power3.out",
    },
  );
}
