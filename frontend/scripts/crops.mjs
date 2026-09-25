/* Region crops for design review. Element screenshots, not page clips:
   page-level clip coordinates fight the viewport scroll and fail on tall pages. */
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const OUT = fileURLToPath(new URL("../.review/", import.meta.url));
const BASE = process.env.APP_ORIGIN ?? "http://127.0.0.1:5173";
const tag = process.argv[2] ?? String(Date.now());

const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({
  viewport: { width: 1560, height: 1000 },
  deviceScaleFactor: 2,
  locale: "zh-CN",
  reducedMotion: "reduce",
});
const page = await context.newPage();
await page.goto(BASE + (process.env.PAGE ?? "/overview"), {
  waitUntil: "networkidle",
  timeout: 45000,
});
await page.waitForTimeout(2600);

const targets = [
  [".severity-band", "band"],
  [".ruler", "ruler"],
  [".map-stage", "map"],
  [".mover-card", "mover"],
  [".matrix-card", "matrix"],
];

await page.evaluate(() => {
  document.querySelector("details.deep-analysis")?.setAttribute("open", "");
});
await page.waitForTimeout(1600);
targets.push([".fingerprint-panel", "fp"]);
targets.push([".sigma-list", "sigma"]);

for (const [selector, name] of targets) {
  const el = page.locator(selector).first();
  try {
    await el.scrollIntoViewIfNeeded();
    await page.waitForTimeout(250);
    await el.screenshot({ path: `${OUT}q-${name}-${tag}.png` });
    console.log(`ok  ${name}`);
  } catch (error) {
    console.log(`FAIL ${name}: ${String(error).slice(0, 140)}`);
  }
}

await browser.close();
console.log("tag=" + tag);
