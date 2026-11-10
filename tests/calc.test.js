// R·수량 계산 단위 테스트 — 실행: node tests/calc.test.js
"use strict";
const path = require("path");
const { calc } = require(path.join(__dirname, "..", "docs", "calc.js"));
const { cases } = require(path.join(__dirname, "sizing_cases.json"));

function near(a, b) {
  return Math.abs(a - b) <= Math.max(1e-6, 1e-9 * Math.abs(b));
}
function same(actual, expected, where, fails) {
  if (expected === null || typeof expected !== "object") {
    const ok = typeof expected === "number" ? typeof actual === "number" && near(actual, expected) : actual === expected;
    if (!ok) fails.push(`${where}: 기대 ${JSON.stringify(expected)}, 실제 ${JSON.stringify(actual)}`);
    return;
  }
  if (Array.isArray(expected) && (where.endsWith(".errors") || where.endsWith(".warnings"))) {
    const a = [...new Set(actual || [])].sort(), e = [...new Set(expected)].sort();
    if (JSON.stringify(a) !== JSON.stringify(e)) fails.push(`${where}: 기대 ${JSON.stringify(e)}, 실제 ${JSON.stringify(a)}`);
    return;
  }
  if (actual === null || typeof actual !== "object") { fails.push(`${where}: 기대 객체, 실제 ${JSON.stringify(actual)}`); return; }
  if (Array.isArray(expected) && actual.length !== expected.length) fails.push(`${where}: 길이 기대 ${expected.length}, 실제 ${actual.length}`);
  for (const k of Object.keys(expected)) same(actual[k], expected[k], `${where}.${k}`, fails);
}

let failed = 0;
for (const c of cases) {
  const fails = [];
  same(calc(c.input), c.expect, "결과", fails);
  if (fails.length) { failed++; console.log(`✗ ${c.name}\n   ${fails.join("\n   ")}`); }
  else console.log(`✓ ${c.name}`);
}
console.log(`\n${cases.length - failed}/${cases.length} 통과`);
process.exit(failed ? 1 : 0);
