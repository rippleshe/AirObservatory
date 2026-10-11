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
  await analysis.close();

  console.log(JSON.stringify(report, null, 2));
  const failed = report.some((row) => row.errors?.length || row.overflow || (row.http && row.http !== 200) || (row.navItems && row.navItems !== 4));
  if (failed) process.exitCode = 1;
} finally {
  await browser.close();
}
