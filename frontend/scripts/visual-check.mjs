import { chromium } from "playwright-core";
import { mkdir } from "node:fs/promises";

const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
});
const routes = [
  ["/overview", "全国时空", ".china-map-shell"],
  ["/city/1", "污染过程", ".trace-chart"],
  ["/analysis", "多变量关联", ".fingerprint-panel"],
  ["/forecast", "预测评估", ".forecast-trajectory"],
  ["/system", "数据与方法", ".provider-state"],
];
const report = [];
await mkdir(".review", { recursive: true });

async function visit(route, title, selector, width, height) {
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (err) => errors.push(err.message));
  page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });
  try {
    const response = await page.goto("http://127.0.0.1:5173" + route, { waitUntil: "networkidle" });
    await page.locator(selector).first().waitFor({ state: "visible", timeout: 18000 });
    await page.locator(".context-title strong").filter({ hasText: title }).waitFor({ state: "visible" });
    await page.screenshot({ path: `.review/${route.replaceAll("/", "-")}-${width}.png` });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    report.push({ route, width, http: response?.status(), errors, overflow, navItems: await page.locator(".app-rail nav a").count() });
  } finally {
    await page.close();
  }
}

try {
  for (const [route, title, selector] of routes) await visit(route, title, selector, 1440, 900);
  for (const [route, title, selector] of routes.slice(0, 4)) await visit(route, title, selector, 390, 844);

  const map = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await map.goto("http://127.0.0.1:5173/overview", { waitUntil: "networkidle" });
  const beforeMapZoom = await map.evaluate(() => {
    const singles = document.querySelectorAll(".china-map-shell .marks circle.mark").length;
    const clusters = [...document.querySelectorAll(".china-map-shell .map-cluster text")]
      .reduce((total, text) => total + Number(text.textContent), 0);
    const label = document.querySelector(".china-map-shell .label-name");
    return { represented: singles + clusters, font: label ? getComputedStyle(label).fontSize : null };
  });
  if (beforeMapZoom.represented < 120) throw new Error("The expanded city atlas is missing visible or clustered cities");
  await map.getByRole("button", { name: "放大地图" }).click();
  await map.waitForTimeout(450);
  const afterMapZoom = await map.evaluate(() => {
    const singles = document.querySelectorAll(".china-map-shell .marks circle.mark").length;
    const clusters = [...document.querySelectorAll(".china-map-shell .map-cluster text")]
      .reduce((total, text) => total + Number(text.textContent), 0);
    const label = document.querySelector(".china-map-shell .label-name");
    return { represented: singles + clusters, font: label ? getComputedStyle(label).fontSize : null };
  });
  if (afterMapZoom.represented !== beforeMapZoom.represented || afterMapZoom.font !== beforeMapZoom.font) {
    throw new Error("Map zoom lost city marks or scaled labels");
  }
  await map.getByRole("button", { name: "复位地图" }).click();
  await map.waitForTimeout(450);
  report.push({ interaction: "expanded atlas zoom preserves city count and font size", cities: beforeMapZoom.represented });
  await map.locator(".marks circle.mark").first().click({ force: true });
  await map.locator(".city-card .card-open").waitFor({ state: "visible" });
  await map.locator(".city-card .card-open").click();
  await map.waitForURL(/\/city\/\d+/);
  report.push({ interaction: "map→city", destination: new URL(map.url()).pathname });
  await map.close();

  const analysis = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await analysis.goto("http://127.0.0.1:5173/analysis", { waitUntil: "networkidle" });
  await analysis.getByRole("button", { name: "单城市关联" }).click();
  await analysis.locator(".structure-panel").waitFor({ state: "visible", timeout: 18000 });
  report.push({ interaction: "national PCA→city PCA", ok: true });
  const loadings = analysis.locator(".structure-grid article:nth-child(2) svg");
  const loadHeight = Number((await loadings.getAttribute("viewBox")).split(" ")[3]);
  const lastLabel = Number(await analysis.locator(".structure-grid article:nth-child(2) .row-label").last().getAttribute("y"));
  if (!(lastLabel < loadHeight - 12)) throw new Error("PCA loadings rows are clipped");
  const correlation = analysis.locator(".correlation-svg rect[role=button]");
  if ((await correlation.count()) < 190) throw new Error("Correlation matrix is incomplete");
  await correlation.first().click();
  if (!(await analysis.locator(".corr-reading .reading-value").textContent()).includes("1.000")) {
    throw new Error("Selecting a correlation cell did not update its reading");
  }
  const scoreSvg = analysis.locator(".structure-grid article:nth-child(3) svg").first();
  await scoreSvg.scrollIntoViewIfNeeded();
  const position = await scoreSvg.evaluate((svg) => {
    const dot = svg.querySelector("circle");
    const bounds = svg.getBoundingClientRect();
    const frame = svg.viewBox.baseVal;
    return {
      x: bounds.left + ((dot.cx.baseVal.value - frame.x) / frame.width) * bounds.width,
      y: bounds.top + ((dot.cy.baseVal.value - frame.y) / frame.height) * bounds.height,
    };
  });
  await analysis.mouse.move(position.x, position.y);
  if (!(await analysis.locator(".quad-tip").isVisible())) throw new Error("PCA score hover failed");
  await analysis.locator(".wind-rose").waitFor({ state: "visible", timeout: 18000 });
  for (const chart of [".wind-clearance", ".wind-rose"]) {
    const bounds = await analysis.locator(chart).boundingBox();
    if (!bounds || bounds.height < 320 || bounds.height > 400) {
      throw new Error(`${chart} did not keep its bounded research-panel height`);
    }
  }
  report.push({ interaction: "PCA loadings, correlation choice and score hover", ok: true });
  await analysis.close();

  const mobileAnalysis = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await mobileAnalysis.goto("http://127.0.0.1:5173/analysis", { waitUntil: "networkidle" });
  await mobileAnalysis.getByRole("button", { name: "单城市关联" }).click();
  await mobileAnalysis.locator(".structure-panel").waitFor({ state: "visible", timeout: 18000 });
  const mobileOverflow = await mobileAnalysis.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  report.push({ route: "/analysis/city", width: 390, overflow: mobileOverflow });
  await mobileAnalysis.close();

  console.log(JSON.stringify(report, null, 2));
  const failed = report.some((row) => row.errors?.length || row.overflow || (row.http && row.http !== 200) || (row.navItems && row.navItems !== 4));
  if (failed) process.exitCode = 1;
} finally {
  await browser.close();
}
