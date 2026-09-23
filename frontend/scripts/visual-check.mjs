import { chromium } from "playwright-core";
import { mkdir } from "node:fs/promises";

const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
});

const routes = [
  ["/live", "中国重点城市", "live.png"],
  ["/explore", "观测与模式对照", "explore.png"],
  ["/forecast", "预测与基线", "forecast.png"],
  ["/system", "系统与数据管线", "system.png"],
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
  await page.waitForTimeout(800);
  await page.screenshot({
    path: `.review/${screenshot}`,
    fullPage: false,
  });

  report.push({
    route,
    status: response?.status(),
    expectedTextVisible: true,
    bodyHasAirObservatory: (await page.locator("body").innerText()).includes(
      "AIR OBSERVATORY",
    ),
    consoleErrors: errors,
  });
  await page.close();
}

console.log(JSON.stringify(report, null, 2));
await browser.close();

if (
  report.some(
    (item) =>
      item.status !== 200 ||
      !item.expectedTextVisible ||
      !item.bodyHasAirObservatory ||
      item.consoleErrors.length,
  )
) {
  process.exitCode = 1;
}
