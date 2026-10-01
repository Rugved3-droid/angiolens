// Projection rays for a selected segment, overlap culprits along each ray, and picking in the angiogram.
import { add, type CArm, dot, norm, scale, sub, type Vec3 } from "./geometry";
import type { Edge, GraphNode } from "./caseData";

export const BIFURCATION_EXCLUSION_MM = 3;

export interface Ray {
  p: Vec3; // sample on the target vessel
  q: Vec3; // hit on the detector
  culprits: number[]; // other edges whose lumen this ray passes through
}

function distPointSegment(c: Vec3, a: Vec3, b: Vec3): number {
  const ab = sub(b, a);
  const t = Math.min(1, Math.max(0, dot(sub(c, a), ab) / dot(ab, ab)));
  return norm(sub(c, add(a, scale(ab, t))));
}

/** Evenly spaced sample indices along an edge (always including both ends). */
export function sampleIndices(n: number, k: number): number[] {
  if (n <= k) return [...Array(n).keys()];
  return [...Array(k).keys()].map((i) => Math.round((i * (n - 1)) / (k - 1)));
}

/**
 * Rays source -> target samples -> detector. A ray is an overlap if it passes within the lumen
 * radius of another edge of the injected tree. Samples of other edges within
 * BIFURCATION_EXCLUSION_MM of the target's own end nodes are ignored (vessels touch there by definition).
 */
export function projectionRays(carm: CArm, target: Edge, injected: Edge[], nodes: GraphNode[], nRays = 15): Ray[] {
  const ends = [nodes[target.a].pos, nodes[target.b].pos];
  const others = injected
    .filter((e) => e.id !== target.id)
    .map((e) => ({
      id: e.id,
      samples: e.pts
        .map((p, i) => ({ p, r: e.radius[i] }))
        .filter(({ p }) => ends.every((n) => norm(sub(p, n)) > BIFURCATION_EXCLUSION_MM)),
    }));
  const S = carm.source;
  return sampleIndices(target.pts.length, nRays).map((i) => {
    const p = target.pts[i];
    const q = carm.detectorHit(p);
    const culprits = others.filter((o) => o.samples.some(({ p: c, r }) => distPointSegment(c, S, q) < r)).map((o) => o.id);
    return { p, q, culprits };
  });
}

/** Nearest edge to a detector point (screen mm), within `tolMm` beyond its projected radius. */
export function pickInAngio(carm: CArm, x: number, y: number, edges: Edge[], tolMm = 2): number | null {
  let best: { id: number; d: number } | null = null;
  for (const e of edges) {
    for (let i = 0; i < e.pts.length; i++) {
      const [sx, sy] = carm.project(e.pts[i]);
      const d = Math.hypot(sx - x, sy - y) - e.radius[i] * carm.magnification(e.pts[i]);
      if (d < tolMm && (!best || d < best.d)) best = { id: e.id, d };
    }
  }
  return best ? best.id : null;
}

/** Nearest edge (within `trees`) to a 3D point, e.g. a raycast hit on the lumen surface. */
export function nearestEdge(p: Vec3, edges: Edge[]): number | null {
  let best: { id: number; d: number } | null = null;
  for (const e of edges)
    for (const s of e.pts) {
      const d = norm(sub(s, p));
      if (!best || d < best.d) best = { id: e.id, d };
    }
  return best ? best.id : null;
}
