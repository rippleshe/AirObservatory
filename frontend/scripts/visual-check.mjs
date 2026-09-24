import { chromium } from "playwright-core";
import { mkdir } from "node:fs/promises";

const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
});

const routes = [
  ["/overview", "全国空气态势", "overview.png"],
  ["/city/1", "过去发生了什么，接下来会怎样？", "city.png"],
  ["/system", "数据从哪里来？", "system.png"],
];

await mkdir(".review", { recursive: true });
const report = [];

for (const [route, expectedText, screenshot] of routes) {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  });
  const errors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(err.message));

  const response = await page.goto(`http://127.0.0.1:5173${route}`, {
    waitUntil: "networkidle",
  });
  await page.getByText(expectedText, { exact: false }).first().waitFor({
    state: "visible",
    timeout: 15000,
  });
  await page.waitForTimeout(700);
  await page.screenshot({
    path: `.review/${screenshot}`,
    fullPage: false,
  });

  report.push({
    route,
    status: response?.status(),
    expectedTextVisible: true,
    bodyHasAirObservatory: (await page.locator("body").innerText()).includes(
      "Air Observatory",
    ),
    consoleErrors: errors,
  });
  await page.close();
}

const drilldown = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
});
const drilldownErrors = [];
drilldown.on("console", (msg) => {
  if (msg.type() === "error") drilldownErrors.push(msg.text());
});
drilldown.on("pageerror", (err) => drilldownErrors.push(err.message));
await drilldown.goto("http://127.0.0.1:5173/overview", { waitUntil: "networkidle" });
await drilldown.locator(".metric-switch").waitFor({
  state: "visible",
  timeout: 10000,
});
await drilldown.waitForTimeout(400);

const mapPaths = drilldown.locator(".national-map svg path");
const pathCount = await mapPaths.count();
let clickedMapCity = false;
for (let index = 0; index < pathCount; index += 1) {
  const box = await mapPaths.nth(index).boundingBox();
  if (
    !box ||
    box.width < 8 ||
    box.height < 8 ||
    box.width > 38 ||
    box.height > 38
  ) {
    continue;
  }
  await mapPaths.nth(index).click({ force: true });
  await drilldown.waitForTimeout(120);
  if (/\/city\/\d+/.test(drilldown.url())) {
    clickedMapCity = true;
    break;
  }
}
if (!clickedMapCity) {
  throw new Error("No city marker on the national map navigated to a city route");
}
await drilldown.locator(".hero-title h1").waitFor({
  state: "visible",
  timeout: 10000,
});
const cityName = (await drilldown.locator(".hero-title h1").innerText()).trim();
report.push({
  route: "overview map→city drilldown",
  status: 200,
  expectedTextVisible: clickedMapCity,
  bodyHasAirObservatory: true,
  consoleErrors: drilldownErrors,
  finalUrl: drilldown.url(),
  cityName,
});
await drilldown.close();

const fingerprint = await browser.newPage({
  viewport: { width: 1440, height: 960 },
  deviceScaleFactor: 1,
});
const fingerprintErrors = [];
fingerprint.on("console", (msg) => {
  if (msg.type() === "error") fingerprintErrors.push(msg.text());
});
fingerprint.on("pageerror", (err) => fingerprintErrors.push(err.message));
await fingerprint.goto("http://127.0.0.1:5173/overview", { waitUntil: "networkidle" });
const deepAnalysis = fingerprint.locator(".deep-analysis");
await deepAnalysis.locator("summary").click();
const fingerprintPanel = fingerprint.locator(".fingerprint-panel");
await fingerprintPanel.scrollIntoViewIfNeeded();
await fingerprintPanel.getByText("60 座城市的长期变化，分成几种模式？", { exact: true }).waitFor({
  state: "visible",
  timeout: 15000,
});
await fingerprint.waitForTimeout(500);
await fingerprintPanel.screenshot({ path: ".review/fingerprint.png" });
report.push({
  route: "/overview fingerprint",
  status: 200,
  expectedTextVisible: true,
  bodyHasAirObservatory: true,
  consoleErrors: fingerprintErrors,
  chartCount: await fingerprintPanel.locator("svg").count(),
  pointTextVisible: (await fingerprintPanel.innerText()).includes("60 城"),
});
await fingerprint.close();

const mobile = await browser.newPage({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 1,
});
const mobileErrors = [];
mobile.on("console", (msg) => {
  if (msg.type() === "error") mobileErrors.push(msg.text());
});
mobile.on("pageerror", (err) => mobileErrors.push(err.message));
await mobile.goto("http://127.0.0.1:5173/overview", { waitUntil: "networkidle" });
await mobile.getByText("全国空气态势", { exact: true }).first().waitFor({ state: "visible" });
await mobile.screenshot({ path: ".review/overview-mobile.png", fullPage: false });
report.push({
  route: "/overview mobile",
  status: 200,
  expectedTextVisible: true,
  bodyHasAirObservatory: true,
  consoleErrors: mobileErrors,
  horizontalOverflow:
    (await mobile.evaluate(() => document.documentElement.scrollWidth)) >
    (await mobile.evaluate(() => document.documentElement.clientWidth)),
});
await mobile.close();

const cityMobile = await browser.newPage({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 1,
});
const cityMobileErrors = [];
cityMobile.on("console", (msg) => {
  if (msg.type() === "error") cityMobileErrors.push(msg.text());
});
cityMobile.on("pageerror", (err) => cityMobileErrors.push(err.message));
await cityMobile.goto("http://127.0.0.1:5173/city/1", { waitUntil: "networkidle" });
await cityMobile.locator(".hero-title h1").filter({ hasText: "北京" }).waitFor({
  state: "visible",
  timeout: 15000,
});
await cityMobile.screenshot({ path: ".review/city-mobile.png", fullPage: false });
report.push({
  route: "/city/1 mobile",
  status: 200,
  expectedTextVisible: true,
  bodyHasAirObservatory: true,
  consoleErrors: cityMobileErrors,
  horizontalOverflow:
    (await cityMobile.evaluate(() => document.documentElement.scrollWidth)) >
    (await cityMobile.evaluate(() => document.documentElement.clientWidth)),
  sectionCount: await cityMobile.locator(".detail-section").count(),
});
await cityMobile.close();

const overviewSections = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
});
await overviewSections.goto("http://127.0.0.1:5173/overview", { waitUntil: "networkidle" });
const insightDeck = overviewSections.locator(".insight-deck");
await insightDeck.scrollIntoViewIfNeeded();
await overviewSections.waitForTimeout(400);
await insightDeck.screenshot({ path: ".review/overview-insights.png" });
await overviewSections.close();

const citySections = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
});
await citySections.goto("http://127.0.0.1:5173/city/1", { waitUntil: "networkidle" });
for (const section of ["trend", "pollutants", "rhythm", "structure"]) {
  const target = citySections.locator("#" + section);
  await target.scrollIntoViewIfNeeded();
  if (section === "pollutants") {
    await citySections.locator(".pollutant-grid article").first().waitFor({
      state: "visible",
      timeout: 15000,
    });
  }
  if (section === "trend") {
    await citySections.locator(".trace-chart svg").waitFor({
      state: "visible",
      timeout: 15000,
    });
  }
  await citySections.waitForTimeout(550);
  await citySections.screenshot({ path: `.review/city-${section}.png`, fullPage: false });
}
await citySections.close();

// ── Design gates ────────────────────────────────────────────────────────
// These are the acceptance body of the visual-language pass, not a smoke test.

const gates = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
});
const gateErrors = [];
gates.on("console", (msg) => {
  if (msg.type() === "error") gateErrors.push(msg.text());
});
gates.on("pageerror", (err) => gateErrors.push(err.message));

async function measureFonts(page) {
  // Information-carrying text must clear 12px at projector distance
  // (DESIGN.md). Collect anything smaller that actually carries words.
  return page.evaluate(() => {
    const offenders = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const seen = new Set();
    let node;
    while ((node = walker.nextNode())) {
      const text = (node.textContent || "").trim();
      if (!text) continue;
      const el = node.parentElement;
      if (!el || seen.has(el)) continue;
      seen.add(el);
      const style = getComputedStyle(el);
      if (style.visibility === "hidden" || style.display === "none") continue;
      if (el.closest(".sr-only")) continue;
      const size = parseFloat(style.fontSize);
      if (size < 12) {
        offenders.push({ size, text: text.slice(0, 24), tag: el.className || el.tagName });
      }
    }
    return offenders;
  });
}

// Gate 1 — font floor on the national view and the city view.
await gates.goto("http://127.0.0.1:5173/overview", { waitUntil: "networkidle" });
await gates.locator(".metric-switch").waitFor({ state: "visible", timeout: 15000 });
await gates.waitForTimeout(500);
const overviewFonts = await measureFonts(gates);

await gates.goto("http://127.0.0.1:5173/city/1", { waitUntil: "networkidle" });
await gates.locator(".hero-title h1").waitFor({ state: "visible", timeout: 15000 });
for (const section of ["trend", "pollutants", "rhythm", "structure", "trust"]) {
  await gates.locator("#" + section).scrollIntoViewIfNeeded();
  await gates.waitForTimeout(250);
}
const cityFonts = await measureFonts(gates);

report.push({
  route: "design gate · font floor",
  status: 200,
  expectedTextVisible: overviewFonts.length + cityFonts.length === 0,
  bodyHasAirObservatory: true,
  consoleErrors: gateErrors,
  belowTwelvePx: [...overviewFonts, ...cityFonts],
});

// Gate 2 — the 60-city table twin: every value reachable without hover.
await gates.goto("http://127.0.0.1:5173/overview", { waitUntil: "networkidle" });
await gates.locator(".table-toggle").scrollIntoViewIfNeeded();
await gates.locator(".table-toggle").click();
const table = gates.locator(".matrix-table");
await table.waitFor({ state: "visible", timeout: 15000 });
const tableRows = await table.locator("tbody tr").count();
const tableText = await table.innerText();
await table.screenshot({ path: ".review/overview-table.png" });
report.push({
  route: "design gate · 60 城表格孪生",
  status: 200,
  expectedTextVisible: tableRows >= 50 && tableText.includes("轻度污染"),
  bodyHasAirObservatory: true,
  consoleErrors: [],
  tableRows,
  hasLevelWord: tableText.includes("轻度污染") || tableText.includes("优"),
});

// Gate 3 — the map names its hotspots without hover, and does not collide.
await gates.goto("http://127.0.0.1:5173/overview", { waitUntil: "networkidle" });
await gates.locator(".metric-switch").waitFor({ state: "visible", timeout: 15000 });
await gates.waitForTimeout(700);
const mapLabels = await gates.evaluate(() => {
  const svg = document.querySelector(".national-map svg");
  if (!svg) return { count: 0, overlapping: 0, names: [] };
  // City value labels ("轻度污染 · AQI 128") always carry a digit; province
  // names never do. Measure collisions between city labels only.
  const boxes = [...svg.querySelectorAll("text, tspan")]
    .map((t) => {
      const r = t.getBoundingClientRect();
      return { text: (t.textContent || "").trim(), x: r.x, y: r.y, w: r.width, h: r.height };
    })
    .filter((b) => b.text && b.w > 4 && /\d/.test(b.text));
  let overlapping = 0;
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      const a = boxes[i];
      const b = boxes[j];
      const hit =
        a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
      if (hit) overlapping += 1;
    }
  }
  return {
    count: boxes.length,
    overlapping,
    names: boxes.map((b) => b.text),
  };
});
await gates.screenshot({ path: ".review/overview-map-labels.png", fullPage: false });
report.push({
  route: "design gate · 地图直接标注",
  // Ten candidates are offered; crowding decides how many survive. The gate
  // is that the hotspots are named and nothing is printed over anything else.
  status: 200,
  expectedTextVisible: mapLabels.count >= 6 && mapLabels.overlapping === 0,
  bodyHasAirObservatory: true,
  consoleErrors: [],
  labelledTexts: mapLabels.count,
  overlappingLabels: mapLabels.overlapping,
  labels: mapLabels.names,
});

// Gate 4 — with N this small the backtest must not draw error-vs-horizon curves.
await gates.goto("http://127.0.0.1:5173/city/1", { waitUntil: "networkidle" });
await gates.locator("#trust").scrollIntoViewIfNeeded();
await gates.locator("summary", { hasText: "查看预测回测与误差" }).first().click();
await gates.waitForTimeout(600);
const backtestText = await gates.locator(".backtest-panel").innerText();
const curvesDrawn = (await gates.locator(".backtest-panel .metric-chart svg").count()) > 0;
report.push({
  route: "design gate · 回测诚实陈述",
  status: 200,
  expectedTextVisible: backtestText.includes("样本还不够") && !curvesDrawn,
  bodyHasAirObservatory: true,
  consoleErrors: [],
  curvesDrawn,
  statesSampleSize: /已对齐样本/.test(backtestText),
});
await gates.screenshot({ path: ".review/city-trust.png", fullPage: false });
await gates.close();

console.log(JSON.stringify(report, null, 2));
await browser.close();

if (
  report.some(
    (item) =>
      item.status !== 200 ||
      !item.expectedTextVisible ||
      !item.bodyHasAirObservatory ||
      item.consoleErrors.length ||
      item.horizontalOverflow === true ||
      (item.route === "/overview fingerprint" &&
        (item.chartCount < 2 || item.pointTextVisible !== true)),
  )
) {
  process.exitCode = 1;
}
