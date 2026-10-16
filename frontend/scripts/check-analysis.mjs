import assert from "node:assert/strict";
import { test } from "node:test";
import { windSpeedBin, stackedWindRadii } from "../src/pages/analysis/windRose.ts";

test("wind speeds use four non-overlapping classes, including boundary values", () => {
  const rows = [
    [-1, -1], [0, -1], [0.499, -1], [0.5, 0],
    [1.999, 0], [2, 1], [3.999, 1], [4, 2],
    [6.999, 2], [7, 3], [15, 3], [Infinity, -1], [NaN, -1],
  ];
  for (const [speed, expected] of rows) assert.equal(windSpeedBin(speed), expected, String(speed));
});

test("directional sectors conserve area and stay inside the reference ring", () => {
  let before = 0;
  let previousOuter = 0;
  const maxCount = 21;
  for (const count of [4, 5, 6, 6]) {
    const { inner, outer } = stackedWindRadii(before, count, maxCount, 100);
    assert.ok(Math.abs(inner - previousOuter) < 1e-10);
    assert.ok(outer <= 94.0000000001);
    assert.ok(Math.abs((outer ** 2 - inner ** 2) / 94 ** 2 - count / maxCount) < 1e-10);
    previousOuter = outer;
    before += count;
  }
  assert.equal(before, maxCount);
});
