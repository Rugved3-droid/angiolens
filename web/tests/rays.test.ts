import { describe, expect, it } from "vitest";
import { CArm, type Vec3, add, scale } from "../src/geometry";
import type { Edge, GraphNode } from "../src/caseData";
import { nearestEdge, pickInAngio, projectionRays, sampleIndices } from "../src/rays";

const ISO: Vec3 = [0, 0, 0];

function edge(id: number, a: Vec3, b: Vec3, r = 1.5, n = 41, ends: [number, number] = [0, 1]): Edge {
  const pts = [...Array(n).keys()].map((i) => add(a, scale([b[0] - a[0], b[1] - a[1], b[2] - a[2]], i / (n - 1))));
  return { id, tree: "left", a: ends[0], b: ends[1], lengthMm: 0, pts, radius: pts.map(() => r) };
}

const nodes: GraphNode[] = [
  { id: 0, kind: "ostium", tree: "left", pos: [-20, 0, 0] },
  { id: 1, kind: "endpoint", tree: "left", pos: [20, 0, 0] },
  { id: 2, kind: "endpoint", tree: "left", pos: [100, 100, 100] },
  { id: 3, kind: "endpoint", tree: "left", pos: [100, 100, 101] },
];

describe("projection rays", () => {
  const target = edge(0, [-20, 0, 0], [20, 0, 0]);
  it("a vessel behind the target along the AP beam is a culprit", () => {
    // AP: beam along -y -> +y? source is posterior (S = iso - SOD*d = +y side), detector anterior.
    const behind = edge(1, [-20, 30, 0], [20, 30, 0], 1.5, 41, [2, 3]);
    const rays = projectionRays(new CArm(0, 0, ISO), target, [target, behind], nodes);
    expect(rays.length).toBe(15);
    expect(rays.every((r) => r.culprits.includes(1))).toBe(true);
  });
  it("the same vessel does not overlap in a steep cranial view where it projects away", () => {
    const behind = edge(1, [-20, 30, 0], [20, 30, 0], 1.5, 41, [2, 3]);
    const rays = projectionRays(new CArm(0, 40, ISO), target, [target, behind], nodes);
    expect(rays.some((r) => r.culprits.length > 0)).toBe(false);
  });
  it("vessels touching at the target's own bifurcation are excluded", () => {
    const child = edge(2, [20, 0, 0], [20, 2, 0], 1.5, 5, [1, 2]); // within 3 mm of end node 1
    const rays = projectionRays(new CArm(0, 0, ISO), target, [target, child], nodes);
    expect(rays.some((r) => r.culprits.includes(2))).toBe(false);
  });
  it("rays end on the detector plane", () => {
    const c = new CArm(30, -20, ISO);
    for (const r of projectionRays(c, target, [target], nodes)) {
      const off = [0, 1, 2].reduce((s, i) => s + (r.q[i] - c.detectorCenter[i]) * c.d[i], 0);
      expect(off).toBeCloseTo(0, 9);
    }
  });
  it("sample indices include both ends", () => {
    expect(sampleIndices(41, 15)[0]).toBe(0);
    expect(sampleIndices(41, 15).at(-1)).toBe(40);
    expect(sampleIndices(5, 15)).toEqual([0, 1, 2, 3, 4]);
  });
});

describe("picking", () => {
  const a = edge(0, [-20, 0, 0], [20, 0, 0]);
  const b = edge(1, [0, 0, 20], [0, 0, 40]);
  it("click near a projected vessel picks it; empty space picks nothing", () => {
    const c = new CArm(0, 0, ISO);
    expect(pickInAngio(c, 10 * (4 / 3), 0, [a, b])).toBe(0);
    expect(pickInAngio(c, 0, 30 * (4 / 3), [a, b])).toBe(1);
    expect(pickInAngio(c, 60, -60, [a, b])).toBeNull();
  });
  it("nearest edge in 3D", () => {
    expect(nearestEdge([0, 1, 30], [a, b])).toBe(1);
  });
});
