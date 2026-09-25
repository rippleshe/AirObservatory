import { chromium } from "playwright-core";
import { mkdir } from "node:fs/promises";

const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
});

/* Smoke assertions hang on what the shell promises, never on what the data
   says. The context-bar title is the router's meta.title (全国总览 / 城市详情 /
   数据与方法) and the per-route anchor is a node the view only renders once its
   data has landed. The <h1>s became data-derived conclusions ("武汉 AQI 207
   重度污染 · 11 省需要关注"), so pinning one would pin today's weather. */
/* Screenshots are namespaced check-* on purpose: scripts/shot.mjs writes
   overview.png / city.png / system.png as full-page 2× design captures, and
   two harnesses sharing a filename meant running one silently invalidated the
   other's evidence. */
const routes = [
  ["/overview", "全国总览", ".severity-band", "check-overview.png"],
  ["/city/1", "城市详情", ".hero-title h1", "check-city.png"],
  ["/system", "数据与方法", ".provider-state", "check-system.png"],
];

await mkdir(".review", { recursive: true });
const report = [];

/* The city view re-renders whenever the location catalog or one of its queries
   lands, so a locator-driven scroll can meet its node mid-swap and fail the
   whole run with "element is not attached to the DOM". Waiting for the section
   and then scrolling by id inside the page re-resolves the node at call time,
   and a section that is genuinely gone still throws. */
async function scrollToSection(page, id) {
  await page.locator("#" + id).waitFor({ state: "visible", timeout: 15000 });
  await page.evaluate((section) => {
    const target = document.getElementById(section);
    if (!target) throw new Error("section #" + section + " is not in the DOM");
    target.scrollIntoView({ block: "start" });
  }, id);
}

for (const [route, expectedTitle, viewContent, screenshot] of routes) {
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
  const contextTitle = page.locator(".context-title strong");
  await contextTitle.filter({ hasText: expectedTitle }).first().waitFor({
    state: "visible",
    timeout: 15000,
  });
  await page.locator(viewContent).first().waitFor({ state: "visible", timeout: 15000 });
  await page.waitForTimeout(700);
  await page.screenshot({
    path: `.review/${screenshot}`,
    fullPage: false,
  });

  const titleText = (await contextTitle.innerText()).trim();
  report.push({
    route,
    status: response?.status(),
    expectedTitle,
    titleText,
    expectedTextVisible: titleText === expectedTitle,
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
/* The panel headline is computed from the data ("31 个省各取一城的长期变化
   分成 3 种模式"), so the wait is structural: its h2, then the group ledger
   that only exists once the fingerprint has landed. */
await fingerprintPanel.locator(".panel-header h2").waitFor({
  state: "visible",
  timeout: 15000,
});
await fingerprintPanel.locator(".cluster-row").first().waitFor({
  state: "visible",
  timeout: 15000,
});
await fingerprint.waitForTimeout(500);
await fingerprintPanel.screenshot({ path: ".review/fingerprint.png" });

const fingerprintHeading = (
  await fingerprintPanel.locator(".panel-header h2").innerText()
).trim();
const fingerprintMeta = await fingerprintPanel.locator(".panel-meta").innerText();
const clusterSizes = (await fingerprintPanel.locator(".cluster-title").allInnerTexts())
  .map((row) => Number(/(\d+)\s*城/.exec(row)?.[1]))
  .filter((count) => Number.isFinite(count));
/* "60 城" stopped being the unit when the national layer converged to one city
   per province. What still has to hold is that the panel states the size of
   the set it grouped and that its groups add up to exactly that set — a
   partial ledger would misreport the scale of the pattern split. How many
   patterns that split has is the data's business, not this gate's. */
const statedUnits = Number(/^(\d+)\s*城$/m.exec(fingerprintMeta)?.[1]);
report.push({
  route: "/overview fingerprint",
  status: 200,
  expectedTextVisible: fingerprintHeading.length > 0 && clusterSizes.length >= 1,
  bodyHasAirObservatory: true,
  consoleErrors: fingerprintErrors,
  chartCount: await fingerprintPanel.locator("svg").count(),
  heading: fingerprintHeading,
  statedUnits,
  clusterSizes,
  pointTextVisible:
    fingerprintHeading.length > 0 &&
    Number.isFinite(statedUnits) &&
    statedUnits > 0 &&
    clusterSizes.length >= 1 &&
    clusterSizes.reduce((sum, count) => sum + count, 0) === statedUnits,
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
await mobile.locator(".context-title strong").filter({ hasText: "全国总览" }).waitFor({
  state: "visible",
  timeout: 15000,
});
await mobile.locator(".severity-band").waitFor({ state: "visible", timeout: 15000 });
await mobile.screenshot({ path: ".review/overview-mobile.png", fullPage: false });
const mobileTitle = (await mobile.locator(".context-title strong").innerText()).trim();
report.push({
  route: "/overview mobile",
  status: 200,
  expectedTitle: "全国总览",
  titleText: mobileTitle,
  expectedTextVisible: mobileTitle === "全国总览",
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
  await scrollToSection(citySections, section);
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
for (const section of ["trend", "pollutants", "rhythm", "structure", "trust"]) {
  await scrollToSection(gates, section);
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

// Gate 2 — the table twin: every value on the deck is reachable without hover.
await gates.goto("http://127.0.0.1:5173/overview", { waitUntil: "networkidle" });
await gates.locator(".table-toggle").scrollIntoViewIfNeeded();
await gates.locator(".table-toggle").click();
const table = gates.locator(".matrix-table");
await table.waitFor({ state: "visible", timeout: 15000 });
const tableRows = await table.locator("tbody tr").count();
const tableText = await table.innerText();
/* The caption declares both scopes: the roster the table carries and the
   provincial set the charts plot. A twin that drops rows, or that covers less
   than the deck plots, is not a twin — checked against the declaration instead
   of a row-count constant, which only ever tracked one data vintage. */
const tableCaption = (await gates.locator(".matrix-card caption").textContent()) ?? "";
const declaredRoster = Number(/全部\s*(\d+)\s*城/.exec(tableCaption)?.[1]);
const declaredPlotted = Number(/(\d+)\s*省代表城市/.exec(tableCaption)?.[1]);
await table.screenshot({ path: ".review/overview-table.png" });
report.push({
  route: "design gate · 表格孪生",
  status: 200,
  expectedTextVisible:
    tableRows === declaredRoster &&
    declaredRoster >= declaredPlotted &&
    tableText.includes("轻度污染"),
  bodyHasAirObservatory: true,
  consoleErrors: [],
  tableRows,
  declaredRoster,
  declaredPlotted,
  hasLevelWord: tableText.includes("轻度污染") || tableText.includes("优"),
});

// Gate 3 — the map names its cities without hover, and the names do not collide.
/* One representative per province is plotted (31 today). The floor says most
   of that layer is named on the map itself; it leaves room for the crowded
   east to cull a few, and it is far above the 6 the gate used to accept. */
const DIRECT_LABEL_FLOOR = 24;
await gates.goto("http://127.0.0.1:5173/overview", { waitUntil: "networkidle" });
await gates.locator(".metric-switch").waitFor({ state: "visible", timeout: 15000 });
await gates.waitForTimeout(700);
const mapLabels = await gates.evaluate(() => {
  const svg = document.querySelector(".national-map svg");
  if (!svg) {
    return {
      count: 0,
      overlapping: 0,
      collided: [],
      minGap: null,
      readings: 0,
      unmatchedReadings: 1,
      provinceCollisions: 0,
      names: [],
    };
  }
  /* Filter by layer, never by "does the text carry a digit". A quiet province's
     city label is the bare name — the reading line only appears where there is
     something to read — so a digit test now catches readings and misses names,
     which is the opposite of what this gate measures. City labels are set in
     --ink (name) and --ink-soft (reading); province names are --map-name. */
  const tokenRgb = (name) => {
    const probe = document.createElement("span");
    probe.style.color = `var(${name})`;
    document.body.appendChild(probe);
    const value = getComputedStyle(probe).color;
    probe.remove();
    return value;
  };
  const CITY_NAME = tokenRgb("--ink");
  const CITY_READING = tokenRgb("--ink-soft");
  const PROVINCE_NAME = tokenRgb("--map-name");

  /* Rich text splits one label into one node per line; leaves only, so a label
     is never counted twice. */
  const lines = [];
  for (const node of svg.querySelectorAll("text, tspan")) {
    if (node.querySelector("text, tspan")) continue;
    const text = (node.textContent || "").trim();
    const rect = node.getBoundingClientRect();
    if (!text || rect.width <= 4 || rect.height <= 0) continue;
    lines.push({
      text,
      fill: getComputedStyle(node).fill,
      x: rect.x,
      y: rect.y,
      w: rect.width,
      h: rect.height,
    });
  }

  /* One annotation = a city name plus the reading line the map stacks directly
     under it. Pairing the two lines by their own geometry keeps a label's
     second row from reading as a collision without excusing a collision
     between two cities. */
  const annotations = lines
    .filter((line) => line.fill === CITY_NAME)
    .map((line) => ({ name: line.text, x: line.x, y: line.y, w: line.w, h: line.h }));
  const readings = lines.filter((line) => line.fill === CITY_READING);
  let unmatchedReadings = 0;
  for (const reading of readings) {
    const host = annotations
      .filter(
        (box) =>
          Math.abs(box.x - reading.x) <= 1.5 && Math.abs(box.y + box.h - reading.y) <= 1.5,
      )
      .sort((a, b) => Math.abs(a.y + a.h - reading.y) - Math.abs(b.y + b.h - reading.y))[0];
    if (!host) {
      unmatchedReadings += 1;
      continue;
    }
    host.w = Math.max(host.w, reading.w);
    host.h = Math.max(host.h, reading.y + reading.h - host.y);
  }

  let overlapping = 0;
  let minGap = Infinity;
  const collided = [];
  for (let i = 0; i < annotations.length; i += 1) {
    for (let j = i + 1; j < annotations.length; j += 1) {
      const a = annotations[i];
      const b = annotations[j];
      const dx = Math.max(a.x - (b.x + b.w), b.x - (a.x + a.w));
      const dy = Math.max(a.y - (b.y + b.h), b.y - (a.y + a.h));
      minGap = Math.min(minGap, Math.max(dx, dy));
      if (dx < 0 && dy < 0) {
        overlapping += 1;
        collided.push(a.name + " × " + b.name);
      }
    }
  }

  /* Province names are the layer underneath, not a colliding peer: a city name
     printed over one is context replaced, not a read that cannot be made. */
  const provinces = lines.filter((line) => line.fill === PROVINCE_NAME);
  let provinceCollisions = 0;
  for (const box of annotations) {
    for (const province of provinces) {
      if (
        box.x < province.x + province.w &&
        province.x < box.x + box.w &&
        box.y < province.y + province.h &&
        province.y < box.y + box.h
      ) {
        provinceCollisions += 1;
      }
    }
  }

  return {
    count: annotations.length,
    overlapping,
    collided,
    minGap: Number.isFinite(minGap) ? Number(minGap.toFixed(2)) : null,
    readings: readings.length,
    unmatchedReadings,
    provinceCollisions,
    names: annotations.map((box) => box.name),
  };
});
await gates.screenshot({ path: ".review/overview-map-labels.png", fullPage: false });
report.push({
  route: "design gate · 地图直接标注",
  // Crowding decides how many of the plotted provinces keep a label; the gate
  // is that the national layer is named on the map itself, and that no two of
  // those names are printed over each other. An unpaired reading line would sit
  // outside the collision set, so it is a failure rather than a silent gap.
  status: 200,
  expectedTextVisible:
    mapLabels.count >= DIRECT_LABEL_FLOOR &&
    mapLabels.overlapping === 0 &&
    mapLabels.unmatchedReadings === 0,
  bodyHasAirObservatory: true,
  consoleErrors: [],
  labelledCities: mapLabels.count,
  overlappingLabels: mapLabels.overlapping,
  overlappingPairs: mapLabels.collided,
  closestLabelGap: mapLabels.minGap,
  readingLines: mapLabels.readings,
  unmatchedReadingLines: mapLabels.unmatchedReadings,
  provinceNameCollisions: mapLabels.provinceCollisions,
  labels: mapLabels.names,
});

// Gate 4 — with N this small the backtest must state its evidence and must not
// draw error-vs-horizon curves.
await gates.goto("http://127.0.0.1:5173/city/1", { waitUntil: "networkidle" });
await scrollToSection(gates, "trust");
await gates.locator("summary", { hasText: "查看预测回测与误差" }).first().click();
await gates.waitForTimeout(600);
const backtestPanel = gates.locator(".backtest-panel");
const backtestText = await backtestPanel.innerText();
const curvesDrawn = (await backtestPanel.locator(".metric-chart svg").count()) > 0;
/* The refusal now reads as a reading: the headline carries how many prediction
   /observation pairs were aligned, the body still says that is too few to
   conclude from. Both halves are required — a panel that draws a curve from
   too few points fails on curvesDrawn, and a panel that admits the shortage
   without ever stating the sample size fails on the count. */
const statesAlignedCount = /已对齐\s*\d+\s*组/.test(backtestText);
const statesInsufficiency = /还不够|不足以|数据不足|样本太少|不给结论|暂不给/.test(backtestText);
const alignedSamples = Number(/已对齐\s*(\d+)\s*组/.exec(backtestText)?.[1]);
const declaredSampleSize = Number(/N=(\d+)/.exec(await backtestPanel.locator(".panel-meta").innerText())?.[1]);
report.push({
  route: "design gate · 回测诚实陈述",
  status: 200,
  expectedTextVisible: statesAlignedCount && statesInsufficiency && !curvesDrawn,
  bodyHasAirObservatory: true,
  consoleErrors: [],
  curvesDrawn,
  statesAlignedCount,
  statesInsufficiency,
  emptyStateRendered: (await backtestPanel.locator(".not-enough").count()) === 1,
  alignedSamples,
  declaredSampleSize,
  countsAgree: Number.isFinite(alignedSamples) && alignedSamples === declaredSampleSize,
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
