import { describe, expect, it } from "vitest";
import fixtures from "./fixtures/geometry.json";
import {
  CArm,
  cross,
  detectorDirection,
  dot,
  foreshortening,
  normalize,
  pixelToScreen,
  scale,
  screenAxes,
  screenToPixel,
  sub,
  add,
  type Vec3,
  viewLabel,
} from "../src/geometry";

const ISO: Vec3 = [12, -40, -150];
const close = (a: number[], b: number[], tol = 1e-9) => a.forEach((x, i) => expect(x).toBeCloseTo(b[i], -Math.log10(tol)));

describe("CONVENTIONS.md rules (same as tests/test_geometry.py)", () => {
  it("AP: detector anterior, +x projects screen right", () => {
    close(detectorDirection(0, 0), [0, -1, 0]);
    const { u, v } = screenAxes(detectorDirection(0, 0));
    close(u, [1, 0, 0]);
    close(v, [0, 0, 1]);
    const c = new CArm(0, 0, ISO);
    expect(c.project(add(ISO, [20, 0, 0]))[0]).toBeGreaterThan(0);
  });

  for (const spine of [[0, 90, 0], [-25, 90, 0]] as Vec3[]) {
    it(`RAO 30 spine left, LAO 45 spine right (spine offset ${spine})`, () => {
      const rao = new CArm(-30, 0, ISO);
      expect(rao.project(add(ISO, spine))[0]).toBeLessThan(rao.project(ISO)[0]);
      const lao = new CArm(45, 0, ISO);
      expect(lao.project(add(ISO, spine))[0]).toBeGreaterThan(lao.project(ISO)[0]);
    });
  }

  it("superior stays up over the whole alpha x beta grid", () => {
    for (let a = -90; a <= 90; a += 15)
      for (let b = -45; b <= 45; b += 15) {
        const c = new CArm(a, b, ISO);
        for (const off of [[30, -20, 10], [-60, 40, -50], [0, 0, 0]] as Vec3[]) {
          const p = add(ISO, off);
          expect(c.project(add(p, [0, 0, 30]))[1]).toBeGreaterThan(c.project(p)[1]);
        }
      }
  });

  it("increasing alpha moves the detector toward patient left", () => {
    let prev = -Infinity;
    for (let a = -90; a <= 90; a += 5) {
      const x = new CArm(a, 20, ISO).detectorCenter[0];
      expect(x).toBeGreaterThan(prev);
      prev = x;
    }
  });

  it("foreshortening 0 perpendicular to local ray, 1 along it", () => {
    const c = new CArm(40, -30, ISO);
    const mid = add(ISO, [35, -20, 25]);
    const r = normalize(sub(mid, c.source));
    const t = normalize(cross(r, [0, 0, 1]));
    expect(foreshortening([sub(mid, scale(t, 0.5)), add(mid, scale(t, 0.5))], c.source)).toBeCloseTo(0, 12);
    const along = [0, 5, 10, 20].map((s) => add(mid, scale(r, s)));
    expect(foreshortening(along, c.source)).toBeCloseTo(1, 9);
  });

  it("frame is orthonormal and u x v = d", () => {
    for (let a = -90; a <= 90; a += 10)
      for (let b = -45; b <= 45; b += 9) {
        const d = detectorDirection(a, b);
        const { u, v } = screenAxes(d);
        expect(dot(u, v)).toBeCloseTo(0, 12);
        close(cross(u, v), d, 1e-12);
      }
  });

  it("out-of-range angles throw; labels", () => {
    expect(() => new CArm(91, 0, ISO)).toThrow();
    expect(() => new CArm(0, -46, ISO)).toThrow();
    expect(viewLabel(-30, -20)).toBe("RAO 30 / CAUD 20");
    expect(viewLabel(45, 0)).toBe("LAO 45");
    expect(viewLabel(0, 0)).toBe("AP");
  });
});

describe("matches Python (web/tests/fixtures/geometry.json)", () => {
  const iso = fixtures.isocenter as Vec3;
  const pts = fixtures.points as Vec3[];
  for (const f of fixtures.cases) {
    it(`${f.label}`, () => {
      const c = new CArm(f.alpha, f.beta, iso);
      close(c.d, f.d, 1e-12);
      close(c.u, f.u, 1e-12);
      close(c.v, f.v, 1e-12);
      close(c.source, f.source, 1e-9);
      pts.forEach((p, i) => {
        close(c.project(p), f.screen[i], 1e-9);
        expect(c.magnification(p)).toBeCloseTo(f.magnification[i], 12);
      });
      expect(foreshortening(pts.slice(0, 6), c.source)).toBeCloseTo(f.foreshortening_first6, 12);
      expect(c.label).toBe(f.label);
    });
  }
});

describe("WebGL clip matrix equals point projection", () => {
  it("NDC = screen / (W/2) and depth in (-1,1)", () => {
    const W = 250;
    for (const [a, b] of [[0, 0], [-30, -25], [45, 30], [-90, 45]]) {
      const c = new CArm(a, b, ISO);
      const m = c.clipMatrix(W);
      for (const off of [[10, 20, 30], [-50, 0, 40], [0, 0, 0], [60, -70, -20]] as Vec3[]) {
        const p = add(ISO, off);
        const clip = [0, 1, 2, 3].map((r) => m[r] * p[0] + m[4 + r] * p[1] + m[8 + r] * p[2] + m[12 + r]);
        const [x, y] = c.project(p);
        expect(clip[0] / clip[3]).toBeCloseTo(x / (W / 2), 10);
        expect(clip[1] / clip[3]).toBeCloseTo(y / (W / 2), 10);
        expect(Math.abs(clip[2] / clip[3])).toBeLessThan(1);
      }
    }
  });
});

describe("detector raster", () => {
  it("row 0 is top (+v), col 0 is left (-u), and round-trips", () => {
    const [col, row] = screenToPixel(100, 100, 250, 500);
    expect(col).toBeGreaterThan(250);
    expect(row).toBeLessThan(250);
    for (const [c, r] of [[0, 0], [499, 0], [123, 456]]) {
      const [x, y] = pixelToScreen(c, r, 250, 500);
      close(screenToPixel(x, y, 250, 500), [c, r], 1e-9);
    }
  });
});
