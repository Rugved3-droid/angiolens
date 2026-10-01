// Phase 2 view metrics. PURELY GEOMETRIC: centerline samples + C-arm pose in, numbers out.
// This module (and anything it imports) must never read a rendered image: guarded by tests/metrics.test.ts.
// Mirrors preprocess/cpt/metrics.py exactly (tested against Python fixtures).
import { ALPHA_RANGE, BETA_RANGE, CArm, type Vec3 } from "./geometry";

export const BIF_EXCLUSION_MM = 3;
export const SELF_ARC_MM = 10;
export const GRID_STEP_DEG = 2;

/** Samples packed as x,y,z,r per sample. */
export type Samples = Float64Array;

export interface ViewMetrics {
  F: number;
  O_inter: number;
  O_self: number;
  O_any: number;
  interMask: Uint8Array;
  selfMask: Uint8Array;
  evaluated: Uint8Array;
}

export function packSamples(pts: Vec3[], radius: number[]): Samples {
  const s = new Float64Array(pts.length * 4);
  pts.forEach((p, i) => s.set([p[0], p[1], p[2], radius[i]], i * 4));
  return s;
}

/** Grid anchored at 0 (zero tilt / AP always sampled) plus the exact range ends. */
export function axis(lo: number, hi: number, step: number): number[] {
  const v = new Set<number>([lo, hi]);
  for (let x = Math.ceil(lo / step) * step; x <= hi + 1e-9; x += step) v.add(Math.round(x * 1e9) / 1e9);
  return [...v].sort((a, b) => a - b);
}
export const angleGrid = (step = GRID_STEP_DEG) => ({ alpha: axis(...ALPHA_RANGE, step), beta: axis(...BETA_RANGE, step) });

interface Pose {
  S: Vec3;
  d: Vec3;
  u: Vec3;
  v: Vec3;
  sid: number;
}
const poseOf = (c: CArm): Pose => ({ S: c.source, d: c.d, u: c.u, v: c.v, sid: c.sid });

/** Project packed samples: out x,y (detector mm) and projected radius (r * local magnification). */
function project(pose: Pose, s: Samples): { x: Float64Array; y: Float64Array; r: Float64Array } {
  const n = s.length / 4;
  const x = new Float64Array(n), y = new Float64Array(n), r = new Float64Array(n);
  const { S, d, u, v, sid } = pose;
  for (let i = 0; i < n; i++) {
    const wx = s[4 * i] - S[0], wy = s[4 * i + 1] - S[1], wz = s[4 * i + 2] - S[2];
    const k = sid / (wx * d[0] + wy * d[1] + wz * d[2]);
    x[i] = k * (wx * u[0] + wy * u[1] + wz * u[2]);
    y[i] = k * (wx * v[0] + wy * v[1] + wz * v[2]);
    r[i] = s[4 * i + 3] * k;
  }
  return { x, y, r };
}

function foreshorteningPose(S: Vec3, s: Samples): number {
  let perp = 0, total = 0;
  for (let i = 1; i < s.length / 4; i++) {
    const dx = s[4 * i] - s[4 * i - 4], dy = s[4 * i + 1] - s[4 * i - 3], dz = s[4 * i + 2] - s[4 * i - 2];
    let rx = 0.5 * (s[4 * i] + s[4 * i - 4]) - S[0], ry = 0.5 * (s[4 * i + 1] + s[4 * i - 3]) - S[1], rz = 0.5 * (s[4 * i + 2] + s[4 * i - 2]) - S[2];
    const rn = Math.hypot(rx, ry, rz);
    rx /= rn; ry /= rn; rz /= rn;
    const dr = dx * rx + dy * ry + dz * rz;
    perp += Math.hypot(dx - dr * rx, dy - dr * ry, dz - dr * rz);
    total += Math.hypot(dx, dy, dz);
  }
  return 1 - perp / total;
}

/** Capsule a->b with radius ra->rb covers q? (radius linearly interpolated, t clamped). */
function covers(qx: number, qy: number, ax: number, ay: number, bx: number, by: number, ra: number, rb: number): boolean {
  const abx = bx - ax, aby = by - ay;
  const L2 = Math.max(abx * abx + aby * aby, 1e-12);
  const t = Math.min(1, Math.max(0, ((qx - ax) * abx + (qy - ay) * aby) / L2));
  return Math.hypot(qx - (ax + t * abx), qy - (ay + t * aby)) <= ra + t * (rb - ra);
}

/** Uniform 2D grid over capsules so each query checks only nearby capsules. */
class CapsuleGrid {
  private cells = new Map<number, number[]>();
  constructor(private cap: { ax: Float64Array; ay: Float64Array; bx: Float64Array; by: Float64Array; ra: Float64Array; rb: Float64Array }, private h = 4) {
    for (let i = 0; i < cap.ax.length; i++) {
      const rr = Math.max(cap.ra[i], cap.rb[i]);
      const x0 = Math.floor((Math.min(cap.ax[i], cap.bx[i]) - rr) / h), x1 = Math.floor((Math.max(cap.ax[i], cap.bx[i]) + rr) / h);
      const y0 = Math.floor((Math.min(cap.ay[i], cap.by[i]) - rr) / h), y1 = Math.floor((Math.max(cap.ay[i], cap.by[i]) + rr) / h);
      for (let cx = x0; cx <= x1; cx++)
        for (let cy = y0; cy <= y1; cy++) {
          const key = cx * 1048576 + cy;
          const list = this.cells.get(key);
          if (list) list.push(i);
          else this.cells.set(key, [i]);
        }
    }
  }
  any(qx: number, qy: number, accept?: (i: number) => boolean): boolean {
    const list = this.cells.get(Math.floor(qx / this.h) * 1048576 + Math.floor(qy / this.h));
    if (!list) return false;
    const c = this.cap;
    for (const i of list) {
      if (accept && !accept(i)) continue;
      if (covers(qx, qy, c.ax[i], c.ay[i], c.bx[i], c.by[i], c.ra[i], c.rb[i])) return true;
    }
    return false;
  }
}

function capsulesOf(projs: { x: Float64Array; y: Float64Array; r: Float64Array }[]) {
  const n = projs.reduce((s, p) => s + Math.max(p.x.length - 1, 0), 0);
  const ax = new Float64Array(n), ay = new Float64Array(n), bx = new Float64Array(n), by = new Float64Array(n);
  const ra = new Float64Array(n), rb = new Float64Array(n);
  let k = 0;
  for (const p of projs)
    for (let i = 0; i + 1 < p.x.length; i++, k++) {
      ax[k] = p.x[i]; ay[k] = p.y[i]; bx[k] = p.x[i + 1]; by[k] = p.y[i + 1]; ra[k] = p.r[i]; rb[k] = p.r[i + 1];
    }
  return { ax, ay, bx, by, ra, rb };
}

/** Which target samples are evaluated for INTER (not within 3 mm of the target's own bifurcations). Pose-independent. */
export function evaluatedMask(target: Samples, bif: Vec3[]): Uint8Array {
  const n = target.length / 4;
  const ev = new Uint8Array(n).fill(1);
  for (let i = 0; i < n; i++)
    for (const b of bif)
      if (Math.hypot(target[4 * i] - b[0], target[4 * i + 1] - b[1], target[4 * i + 2] - b[2]) <= BIF_EXCLUSION_MM) ev[i] = 0;
  return ev;
}

export function arcLengths(target: Samples): Float64Array {
  const n = target.length / 4;
  const arc = new Float64Array(n);
  for (let i = 1; i < n; i++)
    arc[i] = arc[i - 1] + Math.hypot(target[4 * i] - target[4 * i - 4], target[4 * i + 1] - target[4 * i - 3], target[4 * i + 2] - target[4 * i - 2]);
  return arc;
}

function metricsAtPose(pose: Pose, target: Samples, ev: Uint8Array, arc: Float64Array, others: Samples[], brute: boolean): ViewMetrics {
  const n = target.length / 4;
  const pt = project(pose, target);
  const F = foreshorteningPose(pose.S, target);
  const otherCaps = capsulesOf(others.map((o) => project(pose, o)));
  const selfCaps = capsulesOf([pt]);
  const midArc = new Float64Array(Math.max(n - 1, 0));
  for (let j = 0; j + 1 < n; j++) midArc[j] = 0.5 * (arc[j] + arc[j + 1]);
  const og = brute ? null : new CapsuleGrid(otherCaps);
  const sg = brute ? null : new CapsuleGrid(selfCaps);
  const interMask = new Uint8Array(n), selfMask = new Uint8Array(n);
  let nEval = 0, nInter = 0, nSelf = 0, nAny = 0;
  for (let i = 0; i < n; i++) {
    const qx = pt.x[i], qy = pt.y[i];
    const far = (j: number) => Math.abs(midArc[j] - arc[i]) > SELF_ARC_MM;
    let inter = false, self = false;
    if (ev[i]) {
      if (og) inter = og.any(qx, qy);
      else for (let j = 0; j < otherCaps.ax.length && !inter; j++)
        inter = covers(qx, qy, otherCaps.ax[j], otherCaps.ay[j], otherCaps.bx[j], otherCaps.by[j], otherCaps.ra[j], otherCaps.rb[j]);
    }
    if (sg) self = sg.any(qx, qy, far);
    else for (let j = 0; j < selfCaps.ax.length && !self; j++)
      self = far(j) && covers(qx, qy, selfCaps.ax[j], selfCaps.ay[j], selfCaps.bx[j], selfCaps.by[j], selfCaps.ra[j], selfCaps.rb[j]);
    interMask[i] = inter ? 1 : 0;
    selfMask[i] = self ? 1 : 0;
    nEval += ev[i];
    nInter += inter ? 1 : 0;
    nSelf += self ? 1 : 0;
    nAny += ev[i] && (inter || self) ? 1 : 0;
  }
  const ne = Math.max(nEval, 1);
  return { F, O_inter: nInter / ne, O_self: nSelf / n, O_any: nAny / ne, interMask, selfMask, evaluated: ev };
}

export function viewMetrics(carm: CArm, target: Samples, bif: Vec3[], others: Samples[], brute = false): ViewMetrics {
  return metricsAtPose(poseOf(carm), target, evaluatedMask(target, bif), arcLengths(target), others, brute);
}

export const combinedCost = (F: number, O_any: number, wF = 1, wO = 1) => wF * F + wO * O_any;

export interface AngleMaps {
  alpha: number[];
  beta: number[];
  /** row-major [beta][alpha] */
  F: Float32Array;
  O_inter: Float32Array;
  O_self: Float32Array;
  O_any: Float32Array;
}

export function angleMaps(iso: Vec3, target: Samples, bif: Vec3[], others: Samples[], step = GRID_STEP_DEG,
                          onRow?: (done: number, total: number) => void): AngleMaps {
  const { alpha, beta } = angleGrid(step);
  const N = alpha.length * beta.length;
  const out: AngleMaps = { alpha, beta, F: new Float32Array(N), O_inter: new Float32Array(N), O_self: new Float32Array(N), O_any: new Float32Array(N) };
  const ev = evaluatedMask(target, bif);
  const arc = arcLengths(target);
  beta.forEach((b, j) => {
    alpha.forEach((a, i) => {
      const m = metricsAtPose(poseOf(new CArm(a, b, iso)), target, ev, arc, others, false);
      const k = j * alpha.length + i;
      out.F[k] = m.F; out.O_inter[k] = m.O_inter; out.O_self[k] = m.O_self; out.O_any[k] = m.O_any;
    });
    onRow?.(j + 1, beta.length);
  });
  return out;
}

/** Index of the minimum combined cost (ties -> first in row-major order). */
export function argminCost(m: AngleMaps, wF: number, wO: number): { alpha: number; beta: number; cost: number } {
  let best = 0, bestCost = Infinity;
  for (let k = 0; k < m.F.length; k++) {
    const c = combinedCost(m.F[k], m.O_any[k], wF, wO);
    if (c < bestCost) { bestCost = c; best = k; }
  }
  return { alpha: m.alpha[best % m.alpha.length], beta: m.beta[Math.floor(best / m.alpha.length)], cost: bestCost };
}
