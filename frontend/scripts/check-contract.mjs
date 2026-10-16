/* Contract guard.
 *
 * The roster size is stated in four places — the CSV, the README, the thresholds
 * inside visual-check and the demo generator's station stride — and when it grew
 * from 181 cities to 185 the only symptom was a page quietly describing the wrong
 * set. `pnpm run build` runs this (and CI runs the build), so the numbers have to
 * agree before anything ships.
 *
 * What it checks, all offline and without Python (CI's frontend job has only Node):
 *   - the catalog's own invariants: contiguous ids, unique names, one row per city
 *     in the geography table;
 *   - the province-level unit count, which the national page's headline reads;
 *   - the observing-city count, recomputed from the generator's own stride;
 *   - the numbers README states, so prose drift fails the build too;
 *   - the thresholds the frontend hardcodes (atlas floor, correlation-matrix floor,
 *     AQI level count) against the data and the Python constants they assume.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../../", import.meta.url));
const read = (path) => readFileSync(ROOT + path, "utf8");
const rows = (text) => text.split(/\r?\n/).filter((line) => line.trim());
const quotes = (text) => (text.match(/"/g) ?? []).length / 2;

const problems = [];
const expect = (ok, message) => {
  if (!ok) problems.push(message);
};

// ── the roster ──────────────────────────────────────────────────────────────
const catalogModule = read("backend/city_catalog.py");
const baseEntries = [...catalogModule.matchAll(/^\s{4}CityReference\((\d+), "([^"]+)", "([^"]+)"/gm)];
const baseIds = baseEntries.map((entry) => Number(entry[1]));
const baseNames = baseEntries.map((entry) => entry[2]);
const baseProvinces = baseEntries.map((entry) => entry[3]);

const expanded = rows(read("backend/city_geocoding.csv"))
  .slice(1)
  .map((line) => line.split(","));
const expandedIds = expanded.map((cells) => Number(cells[0]));
const allIds = [...baseIds, ...expandedIds];
const allNames = [...baseNames, ...expanded.map((cells) => cells[1])];
const provinceUnits = new Set([...baseProvinces, ...expanded.map((cells) => cells[2])]);

expect(
  allIds.every((id, index) => id === index + 1),
  `城市 id 不连续：${allIds.length} 行，最后一个 id 是 ${allIds.at(-1)}`,
);
const duplicates = allNames.filter((name, index) => allNames.indexOf(name) !== index);
expect(duplicates.length === 0, `城市名重复：${[...new Set(duplicates)].join(" ")}`);
expect(
  provinceUnits.size === 34,
  `省级单位 ${provinceUnits.size} ≠ 34：全国页的省数与地图的 34 个省级单位要对得上（港澳台各算 1 个）`,
);

const geography = rows(read("backend/city_geography.csv"))
  .slice(1)
  .map((line) => line.split(","));
const geographyCities = new Set(geography.map((cells) => cells[1]));
const missingGeography = allNames.filter((name) => !geographyCities.has(name));
expect(
  missingGeography.length === 0,
  `city_geography.csv 缺 ${missingGeography.length} 个城市：${missingGeography.slice(0, 5).join(" ")}`,
);
const withoutPopulation = geography.filter((cells) => !cells[5].trim());
expect(
  withoutPopulation.length === 0,
  `city_geography.csv 有 ${withoutPopulation.length} 个城市没有人口，指纹 PCA 会整城跳过`,
);

// ── the numbers the prose states ────────────────────────────────────────────
const stride = Number(read("scripts/seed_demo.py").match(/OBSERVED_CITY_STRIDE = (\d+)/)[1]);
const observing = allIds.filter((id) => id % stride !== 0).length;
const readme = read("README.md");
// Each claim is pulled out of the sentence that makes it: matching bare numbers
// would pass while one of several occurrences drifted.
const claims = [
  ["演示库城市数", /演示库（(\d+) 城 ×/, allNames.length],
  ["城市目录城市数", /城市目录是真实坐标（(\d+) 城 \//, allNames.length],
  ["省级单位数", /城市目录是真实坐标（\d+ 城 \/ (\d+) 个省级单位/, provinceUnits.size],
  ["有地面站城市数", /(\d+) 城有地面站/, observing],
  ["只有模式场城市数", /(\d+) 城只有模式场/, allNames.length - observing],
];
for (const [label, pattern, actual] of claims) {
  const claimed = readme.match(pattern)?.[1];
  expect(
    Number(claimed) === actual,
    `README 的${label}是 ${claimed ?? "缺这一句"}，实际 ${actual}`,
  );
}

// ── the thresholds the frontend hardcodes ───────────────────────────────────
const visualCheck = read("frontend/scripts/visual-check.mjs");
const atlasFloor = Number(visualCheck.match(/represented < (\d+)/)[1]);
expect(
  atlasFloor <= allNames.length,
  `visual-check 的城市下限 ${atlasFloor} 超过了城市总数 ${allNames.length}`,
);

const factorBlock = read("backend/analytics/features.py").match(/PCA_FEATURES = \(([\s\S]*?)\n\)/)[1];
const factorCount = quotes(factorBlock);
const correlationFloor = Number(visualCheck.match(/correlation\.count\(\)\) < (\d+)/)[1]);
expect(
  correlationFloor <= factorCount ** 2,
  `visual-check 要求相关矩阵 ${correlationFloor} 格，但 ${factorCount} 个特征只有 ${factorCount ** 2} 格`,
);
expect(
  correlationFloor >= factorCount ** 2 * 0.9,
  `相关矩阵下限 ${correlationFloor} 太松：${factorCount} 个特征有 ${factorCount ** 2} 格，缺几格也该发现`,
);

const paletteLevels = quotes(read("frontend/src/lib/palette.ts").match(/AQI_LEVELS = \[([\s\S]*?)\]/)[1]);
const backendLevels = quotes(read("backend/analytics/aqi.py").match(/LEVELS = \(([\s\S]*?)\n\)/)[1]);
expect(
  paletteLevels === backendLevels,
  `AQI 档位数不一致：palette.ts ${paletteLevels} 档 / aqi.py ${backendLevels} 档`,
);

if (problems.length) {
  console.error("契约漂移检查失败——数据骨架、README 与页面里写死的数字对不上了：\n");
  for (const problem of problems) console.error(`  ✗ ${problem}`);
  console.error("\n改完数据要一起改的地方：README 第 1 节、visual-check 的下限、以及本文件里的期望值。");
  process.exit(1);
}
console.log(
  `契约检查通过：${allNames.length} 城 / ${provinceUnits.size} 个省级单位 / ${observing} 城有地面站，` +
    `README 与前端阈值一致`,
);
