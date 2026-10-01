// Projection rays for a selected segment, overlap culprits along each ray, and picking in the angiogram.
import { add, type CArm, dot, norm, scale, sub, type Vec3 } from "./geometry";
import type { Edge, GraphNode } from "./caseData";

export const BIFURCATION_EXCLUSION_MM = 3;

export interface Ray {
  p: Vec3; // sample on the target vessel
  q: Vec3; // hit on the detector
  culprits: number[]; // DIAGNOSTIC ONLY: other edges whose 3D lumen this ray passes through (not displayed)
  sampleIndex?: number; // index into the target's samples (for colouring from the 2D capsule metric)
  overlap?: "inter" | "self" | null; // from the capsule metric: the ONLY overlap shown to the user
}

/** Rays source -> sample -> detector for evenly spaced target samples (no overlap test). */
export function samplesRays(carm: CArm, pts: Vec3[], nRays = 15): Ray[] {
  return sampleIndices(pts.length, nRays).map((i) => ({ p: pts[i], q: carm.detectorHit(pts[i]), culprits: [], sampleIndex: i }));
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
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const ends = [target.a, target.b].map((id) => byId.get(id)).filter((n) => n).map((n) => n!.pos);
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

export interface Pick {
  id: number; // edge
  idx: number; // sample index on that edge
}

/** Nearest edge sample to a detector point (screen mm), within `tolMm` beyond its projected radius. */
export function pickSampleInAngio(carm: CArm, x: number, y: number, edges: Edge[], tolMm = 2): Pick | null {
  let best: (Pick & { d: number }) | null = null;
  for (const e of edges) {
    for (let i = 0; i < e.pts.length; i++) {
      const [sx, sy] = carm.project(e.pts[i]);
      const d = Math.hypot(sx - x, sy - y) - e.radius[i] * carm.magnification(e.pts[i]);
      if (d < tolMm && (!best || d < best.d)) best = { id: e.id, idx: i, d };
    }
  }
  return best ? { id: best.id, idx: best.idx } : null;
}

export function pickInAngio(carm: CArm, x: number, y: number, edges: Edge[], tolMm = 2): number | null {
  return pickSampleInAngio(carm, x, y, edges, tolMm)?.id ?? null;
}

/** Nearest edge sample to a 3D point, e.g. a raycast hit on the lumen surface. */
export function nearestSample(p: Vec3, edges: Edge[]): Pick | null {
  let best: (Pick & { d: number }) | null = null;
  for (const e of edges)
    e.pts.forEach((s, i) => {
      const d = norm(sub(s, p));
      if (!best || d < best.d) best = { id: e.id, idx: i, d };
    });
  return best ? { id: (best as Pick).id, idx: (best as Pick).idx } : null;
}

export function nearestEdge(p: Vec3, edges: Edge[]): number | null {
  return nearestSample(p, edges)?.id ?? null;
}
