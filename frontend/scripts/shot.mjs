/* Visual review harness: renders the live app in real Chromium at 2× and
   writes PNGs to .review/. Not a test — it exists so the design can be looked
   at rather than reasoned about (dataviz procedure step 7). */
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const BASE = process.env.APP_ORIGIN ?? "http://127.0.0.1:5173";
// fileURLToPath, not URL.pathname — pathname percent-encodes the CJK in
// "桌面" and silently writes the PNGs to a directory that is never reviewed.
const OUT = fileURLToPath(new URL("../.review/", import.meta.url));
const ONLY = process.argv[2] ?? "all";

const SHOTS = [
  { name: "overview", path: "/overview", viewport: { width: 1560, height: 1000 }, full: true },
  { name: "overview-fold", path: "/overview", viewport: { width: 1560, height: 1000 }, full: false },
  { name: "city", path: "/city/7", viewport: { width: 1560, height: 1000 }, full: true },
  { name: "city-fold", path: "/city/7", viewport: { width: 1560, height: 1000 }, full: false },
  { name: "system", path: "/system", viewport: { width: 1560, height: 1000 }, full: true },
  { name: "overview-narrow", path: "/overview", viewport: { width: 820, height: 1000 }, full: true },
];

await mkdir(OUT, { recursive: true });

const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
});

let failed = 0;
for (const shot of SHOTS) {
  if (ONLY !== "all" && shot.name !== ONLY) continue;
  const context = await browser.newContext({
    viewport: shot.viewport,
    deviceScaleFactor: 2,
    locale: "zh-CN",
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  try {
    await page.goto(BASE + shot.path, { waitUntil: "networkidle", timeout: 45000 });
    // ECharts paints after the data lands; a settle beat beats a fixed sleep.
    await page.waitForTimeout(2200);
    await page.screenshot({
      path: `${OUT}${shot.name}.png`,
      fullPage: shot.full,
    });
    console.log(`ok  ${shot.name}${errors.length ? `  [${errors.length} console error(s)]` : ""}`);
    for (const error of errors.slice(0, 4)) console.log(`    ! ${error.slice(0, 180)}`);
    if (errors.length) failed += 1;
  } catch (error) {
    failed += 1;
    console.log(`FAIL ${shot.name}: ${String(error).slice(0, 200)}`);
  }
  await context.close();
}

await browser.close();
process.exit(failed ? 1 : 0);
