/* Probe: print what the live page actually renders, so "is the new code live?"
   is answered from the DOM rather than inferred from a screenshot. */
import { chromium } from "playwright-core";

const BASE = process.env.APP_ORIGIN ?? "http://127.0.0.1:5173";
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1560, height: 1000 } });
await page.goto(BASE + (process.argv[2] ?? "/overview"), {
  waitUntil: "networkidle",
  timeout: 45000,
});
await page.waitForTimeout(2500);

const dump = await page.evaluate(() => {
  const pick = (sel) =>
    [...document.querySelectorAll(sel)].map((n) => n.textContent.trim().slice(0, 90));
  return {
    url: location.href,
    h1: pick("h1"),
    h2: pick("h2"),
    h3: pick("h3"),
    hasSeverityBand: !!document.querySelector(".severity-band"),
    hasUnits: document.querySelectorAll(".severity-band .unit").length,
    hasDumbbell: document.querySelectorAll(".dumb-row").length,
    detailsOpen: [...document.querySelectorAll("details")].map((d) => d.open),
    // Any leftover "how to read this chart" captions?
    paragraphs: pick("p").slice(0, 25),
  };
});
console.log(JSON.stringify(dump, null, 2));
await browser.close();
