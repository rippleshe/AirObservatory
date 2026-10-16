/* Ownership guard.
 *
 * Four people develop four pages in parallel, one folder each. The one mistake
 * that costs the whole team is a page reaching into another page's files, so
 * the rule from README/.agents/skills is enforced here instead of by memory:
 * `pnpm run build` runs this, and CI runs `pnpm run build`.
 *
 * Allowed, by design:
 *   - pages/<a>/…  ->  src/lib, src/api, src/composables, src/stores, src/styles, src/shared
 *   - src/app/router.ts -> pages/<x>/<X>Page.vue   (the route table is the entry point)
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const RETIRED = ["components", "views"];
const SPECIFIER = /(?:\bfrom\s*|\bimport\s*\(?\s*)["']([^"']+)["']/g;
const EXTENSIONS = [".ts", ".vue", ".js", ".mjs"];

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = resolve(dir, name);
    if (statSync(full).isDirectory()) return walk(full);
    return EXTENSIONS.some((ext) => full.endsWith(ext)) ? [full] : [];
  });
}

function pageOf(absolute) {
  const parts = relative(SRC, absolute).split(sep);
  return parts[0] === "pages" && parts.length > 2 ? parts[1] : null;
}

const problems = [];
let scanned = 0;

for (const file of walk(SRC)) {
  scanned += 1;
  const rel = relative(SRC, file).split(sep).join("/");
  if (RETIRED.includes(rel.split("/")[0])) {
    problems.push(`${rel}: 这是重构前的旧目录，页面文件应该放在 src/pages/<页>/ 里`);
    continue;
  }
  const own = pageOf(file);
  const body = readFileSync(file, "utf8");
  for (const match of body.matchAll(SPECIFIER)) {
    const spec = match[1];
    if (!spec.startsWith(".")) continue;
    const target = resolve(dirname(file), spec);
    const targetPage = pageOf(target);
    if (targetPage && own && targetPage !== own) {
      problems.push(`${rel}: 引用了「${targetPage}」页的文件（${spec}）`);
    }
    if (targetPage && !own && rel !== "app/router.ts") {
      problems.push(`${rel}: 只有 app/router.ts 可以引用页面（${spec}）`);
    }
  }
}

if (problems.length) {
  console.error("页面边界检查失败——每个页面只能改自己 src/pages/<页>/ 里的东西：\n");
  for (const problem of problems) console.error(`  ✗ ${problem}`);
  console.error("\n需要共用时：把组件放进 src/shared/，或开单独的 PR 说明理由。");
  process.exit(1);
}
console.log(`页面边界检查通过：${scanned} 个文件，0 处跨页引用`);
