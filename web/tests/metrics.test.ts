import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import fx from "./fixtures/metrics.json";
import { CArm, type Vec3 } from "../src/geometry";
import { angleGrid, angleMaps, argminCost, viewMetrics } from "../src/metrics";

const pack = (rows: number[][]) => Float64Array.from(rows.flat());
const target = pack(fx.target);
const others = fx.others.map(pack);
const bif = fx.bif as Vec3[];
const iso = fx.isocenter as Vec3;

describe("metrics match Python (web/tests/fixtures/metrics.json)", () => {
  for (const c of fx.cases) {
    it(`pose ${c.alpha},${c.beta}`, () => {
      for (const brute of [false, true]) {
        const m = viewMetrics(new CArm(c.alpha, c.beta, iso), target, bif, others, brute);
        expect(m.F).toBeCloseTo(c.F, 10);
        expect(m.O_inter).toBeCloseTo(c.O_inter, 10);
        expect(m.O_self).toBeCloseTo(c.O_self, 10);
        expect(m.O_any).toBeCloseTo(c.O_any, 10);
        expect(Array.from(m.interMask)).toEqual(c.inter_mask);
        expect(Array.from(m.selfMask)).toEqual(c.self_mask);
      }
    });
  }

  it("angle maps (10 degree grid) equal Python", () => {
    const m = angleMaps(iso, target, bif, others, 10);
    expect(m.alpha).toEqual(fx.maps10.alpha);
    expect(m.beta).toEqual(fx.maps10.beta);
    for (const key of ["F", "O_inter", "O_self", "O_any"] as const) {
      const exp = (fx.maps10 as any)[key].flat() as number[];
      exp.forEach((v, k) => expect(m[key][k]).toBeCloseTo(v, 5));
    }
  });

  it("2 degree grid is anchored at 0 and spans the full ranges", () => {
    const g = angleGrid(2);
    expect(g.alpha[0]).toBe(-90);
    expect(g.alpha.at(-1)).toBe(90);
    expect(g.beta[0]).toBe(-45);
    expect(g.beta.at(-1)).toBe(45);
    expect(g.alpha).toContain(0);
    expect(g.beta).toContain(0);
  });

  it("argmin picks the lowest combined cost", () => {
    const m = angleMaps(iso, target, bif, others, 10);
    const best = argminCost(m, 1, 1);
    let min = Infinity;
    for (let k = 0; k < m.F.length; k++) min = Math.min(min, m.F[k] + m.O_any[k]);
    expect(best.cost).toBeCloseTo(min, 10);
  });
});

// ---------------- guard: metrics never read rendered pixels ----------------
const SRC = resolve(dirname(fileURLToPath(import.meta.url)), "../src");
const FORBIDDEN_MODULES = ["three", "./angio", "./scene3d", "./main", "./caseData"];
const FORBIDDEN_TOKENS = ["readPixels", "readRenderTargetPixels", "getContext", "WebGL", "texture", "canvas", "ImageData"];

function importsOf(file: string): string[] {
  const src = readFileSync(resolve(SRC, file), "utf8");
  return [...src.matchAll(/^\s*import[^"']*["']([^"']+)["']/gm)].map((m) => m[1]);
}

describe("guard: metrics are purely geometric", () => {
  for (const entry of ["metrics.ts", "metricsWorker.ts"]) {
    it(`${entry} and its imports never touch rendering or pixels`, () => {
      const seen = new Set<string>();
      const visit = (file: string) => {
        if (seen.has(file)) return;
        seen.add(file);
        // code only: strip block and line comments before scanning
        const src = readFileSync(resolve(SRC, file), "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
        for (const tok of FORBIDDEN_TOKENS) expect(src.includes(tok), `${file} contains "${tok}"`).toBe(false);
        for (const imp of importsOf(file)) {
          expect(FORBIDDEN_MODULES.some((f) => imp === f || imp.startsWith(f + "/") || imp.startsWith("three/")),
            `${file} imports ${imp}`).toBe(false);
          if (imp.startsWith("./")) visit(imp.slice(2).replace(/\.ts$/, "") + ".ts");
        }
      };
      visit(entry);
      expect(seen.has("geometry.ts")).toBe(true);
    });
  }
});
