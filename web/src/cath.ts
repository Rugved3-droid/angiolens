// Scene 5 (D53): catheter + contrast. ILLUSTRATIVE, not physics (the UI says so).
// Geometry comes from preprocess/scripts/build_atlas_cath.py: the route centrelines (right femoral / right radial) from the
// puncture to the top of the ascending aorta, the straight pre-shape down the ascending aorta, and the engaged JL4 (-> LM) and
// JR4 (-> RCA) shapes whose tips sit 3 mm inside the EFFECTIVE OSTIUM, tangent to the coronary's initial direction. The
// catheter is shaped to the anatomy; the coronaries and the aorta are never moved.
// One geometry feeds both views: the same closed tube meshes are drawn in 3D and handed to the X-ray's device channel.
// Contrast: one fill window (mm along the tree from the ostium), shared by the 3D glow and the X-ray (angio.fill).
import * as THREE from "three";
import type { AngioRenderer } from "./angio";

export type Access = "femoral_right" | "radial_right";
export type Target = "left" | "right";
export interface CathData {
  routes: Record<Access, { polyline_to_ascending_top: number[][]; length_mm: number; puncture_LPS: number[] }>;
  shapes: Record<"JL4" | "JR4", { tree: Target; polyline: number[][]; straight_polyline: number[][]; reflux_point_LPS: number[];
    effective_ostium_LPS: number[]; coronary_direction_LPS: number[] }>;
  trees: Record<Target, { max_distance_mm: number }>;
  catheter_outer_radius_mm: number;
}

const V = (p: number[]) => new THREE.Vector3(p[0], p[1], p[2]);

/** Closed tube (indexed, outward winding, both ends capped) along a polyline: for 3D AND for path length. */
export function closedTube(pts: THREE.Vector3[], r: number, sides = 12): THREE.BufferGeometry {
  const n = pts.length;
  const pos: number[] = [], idx: number[] = [];
  const T = pts.map((_, i) => pts[Math.min(i + 1, n - 1)].clone().sub(pts[Math.max(i - 1, 0)]).normalize());
  // parallel-transport frames (no twist flips)
  let N = new THREE.Vector3(0, 0, 1).cross(T[0]);
  if (N.lengthSq() < 1e-6) N = new THREE.Vector3(1, 0, 0).cross(T[0]);
  N.normalize();
  for (let i = 0; i < n; i++) {
    if (i > 0) {
      const ax = T[i - 1].clone().cross(T[i]);
      const s = ax.length();
      if (s > 1e-9) N.applyAxisAngle(ax.normalize(), Math.asin(Math.min(1, s)) * (T[i - 1].dot(T[i]) < 0 ? -1 : 1));
      N.sub(T[i].clone().multiplyScalar(N.dot(T[i]))).normalize();
    }
    const B = T[i].clone().cross(N);
    for (let k = 0; k < sides; k++) {
      const a = (2 * Math.PI * k) / sides;
      const d = N.clone().multiplyScalar(Math.cos(a)).addScaledVector(B, Math.sin(a));
      pos.push(pts[i].x + r * d.x, pts[i].y + r * d.y, pts[i].z + r * d.z);
    }
  }
  for (let i = 0; i < n - 1; i++)
    for (let k = 0; k < sides; k++) {
      const a = i * sides + k, b = i * sides + ((k + 1) % sides), c = a + sides, d = b + sides;
      idx.push(a, b, d, a, d, c);
    }
  const c0 = pos.length / 3, c1 = c0 + 1;
  pos.push(pts[0].x, pts[0].y, pts[0].z, pts[n - 1].x, pts[n - 1].y, pts[n - 1].z);
  for (let k = 0; k < sides; k++) {
    const k2 = (k + 1) % sides;
    idx.push(c0, k2, k);                                         // proximal cap
    idx.push(c1, (n - 1) * sides + k, (n - 1) * sides + k2);    // distal cap
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setIndex(idx);
  g.computeVertexNormals();
  return g;
}

/** A closed tube in a PREALLOCATED, non-indexed buffer, rewritten in place every frame (D60: recreating vertex buffers each
 *  frame stalled the GPU pipeline for hundreds of ms on ANGLE/D3D11). Normals are the outward radial / cap directions, which is
 *  what both the 3D shading and the X-ray's entry/exit test need. One geometry is shared by the 3D mesh and the X-ray. */
export class FlatTube {
  readonly geometry = new THREE.BufferGeometry();
  private readonly pos: Float32Array;
  private readonly nrm: Float32Array;
  constructor(private readonly maxPts: number, private readonly sides: number) {
    const maxVerts = ((maxPts - 1) * sides * 6 + 2 * sides * 3);
    this.pos = new Float32Array(maxVerts * 3);
    this.nrm = new Float32Array(maxVerts * 3);
    const pa = new THREE.BufferAttribute(this.pos, 3).setUsage(THREE.DynamicDrawUsage);
    const na = new THREE.BufferAttribute(this.nrm, 3).setUsage(THREE.DynamicDrawUsage);
    this.geometry.setAttribute("position", pa);
    this.geometry.setAttribute("normal", na);
    this.geometry.setDrawRange(0, 0);
    this.geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1e6);   // never culled; the bounds change every frame
  }
  /** Returns false (and draws nothing) for fewer than two points. */
  update(pts: THREE.Vector3[], r: number): boolean {
    const n = Math.min(pts.length, this.maxPts), S = this.sides;
    if (n < 2) { this.geometry.setDrawRange(0, 0); return false; }
    const ring = new Float32Array(n * S * 3), rn = new Float32Array(n * S * 3);
    const T = new THREE.Vector3(), N = new THREE.Vector3(), B = new THREE.Vector3(), Tp = new THREE.Vector3(), ax = new THREE.Vector3();
    for (let i = 0; i < n; i++) {
      T.copy(pts[Math.min(i + 1, n - 1)]).sub(pts[Math.max(i - 1, 0)]).normalize();
      if (i === 0) {
        N.set(0, 0, 1).cross(T);
        if (N.lengthSq() < 1e-6) N.set(1, 0, 0).cross(T);
        N.normalize();
      } else {
        ax.copy(Tp).cross(T);
        const sn = ax.length();
        if (sn > 1e-9) N.applyAxisAngle(ax.normalize(), Math.asin(Math.min(1, sn)) * (Tp.dot(T) < 0 ? -1 : 1));
        N.addScaledVector(T, -N.dot(T)).normalize();
      }
      Tp.copy(T);
      B.copy(T).cross(N);
      for (let k = 0; k < S; k++) {
        const a = (2 * Math.PI * k) / S, c = Math.cos(a), s = Math.sin(a);
        const dx = N.x * c + B.x * s, dy = N.y * c + B.y * s, dz = N.z * c + B.z * s;
        const o = (i * S + k) * 3;
        ring[o] = pts[i].x + r * dx; ring[o + 1] = pts[i].y + r * dy; ring[o + 2] = pts[i].z + r * dz;
        rn[o] = dx; rn[o + 1] = dy; rn[o + 2] = dz;
      }
    }
    let v = 0;
    const put = (src: Float32Array, nsrc: Float32Array | null, idx: number, nx = 0, ny = 0, nz = 0) => {
      this.pos[v * 3] = src[idx * 3]; this.pos[v * 3 + 1] = src[idx * 3 + 1]; this.pos[v * 3 + 2] = src[idx * 3 + 2];
      if (nsrc) { this.nrm[v * 3] = nsrc[idx * 3]; this.nrm[v * 3 + 1] = nsrc[idx * 3 + 1]; this.nrm[v * 3 + 2] = nsrc[idx * 3 + 2]; }
      else { this.nrm[v * 3] = nx; this.nrm[v * 3 + 1] = ny; this.nrm[v * 3 + 2] = nz; }
      v++;
    };
    for (let i = 0; i < n - 1; i++)
      for (let k = 0; k < S; k++) {
        const a = i * S + k, b = i * S + ((k + 1) % S), c = a + S, d = b + S;
        put(ring, rn, a); put(ring, rn, b); put(ring, rn, d);
        put(ring, rn, a); put(ring, rn, d); put(ring, rn, c);
      }
    // caps: fan around the end points, normals along -T (proximal) and +T (distal)
    const caps: [number, number][] = [[0, -1], [n - 1, 1]];
    const ctr = new Float32Array(3);
    for (const [i, sg] of caps) {
      const t = pts[Math.min(i + 1, n - 1)].clone().sub(pts[Math.max(i - 1, 0)]).normalize().multiplyScalar(sg);
      ctr[0] = pts[i].x; ctr[1] = pts[i].y; ctr[2] = pts[i].z;
      for (let k = 0; k < S; k++) {
        const k2 = (k + 1) % S;
        const [p1, p2] = sg < 0 ? [k2, k] : [k, k2];
        put(ctr, null, 0, t.x, t.y, t.z); put(ring, null, i * S + p1, t.x, t.y, t.z); put(ring, null, i * S + p2, t.x, t.y, t.z);
      }
    }
    this.geometry.setDrawRange(0, v);
    const pa = this.geometry.getAttribute("position") as THREE.BufferAttribute, na = this.geometry.getAttribute("normal") as THREE.BufferAttribute;
    pa.clearUpdateRanges(); pa.addUpdateRange(0, v * 3); pa.needsUpdate = true;
    na.clearUpdateRanges(); na.addUpdateRange(0, v * 3); na.needsUpdate = true;
    return true;
  }
}

/** Display/X-ray resampling (D60): every 3rd point along the route, full detail over the last 70 points (the shaped tip and
 *  the J). The route is a 1 mm polyline, so the tube stays smooth; the per-frame upload is ~3x smaller. */
function thin(P: THREE.Vector3[]): THREE.Vector3[] {
  const keepFrom = Math.max(0, P.length - 70);
  const out: THREE.Vector3[] = [];
  for (let i = 0; i < P.length; i++) if (i % 3 === 0 || i >= keepFrom) out.push(P[i]);
  if (out[out.length - 1] !== P[P.length - 1]) out.push(P[P.length - 1]);
  return out;
}

/** Points of a polyline up to arc length s (interpolated end point). */
function cut(path: THREE.Vector3[], cum: number[], s: number): THREE.Vector3[] {
  if (s <= 0) return [path[0].clone()];
  const out: THREE.Vector3[] = [path[0]];
  for (let i = 1; i < path.length; i++) {
    if (cum[i] >= s) {
      const t = (s - cum[i - 1]) / Math.max(cum[i] - cum[i - 1], 1e-9);
      out.push(path[i - 1].clone().lerp(path[i], t));
      return out;
    }
    out.push(path[i]);
  }
  return out;
}
const cumOf = (p: THREE.Vector3[]) => p.reduce<number[]>((a, q, i) => (a.push(i ? a[i - 1] + q.distanceTo(p[i - 1]) : 0), a), []);

type Phase = "idle" | "advance" | "withdraw" | "shape" | "engaged" | "inject";
const T_ADVANCE = 6.5, T_WITHDRAW = 1.6, T_SHAPE = 2.2, T_FILL = 1.0, T_HOLD = 1.3, T_WASH = 1.6, PUFF_T = 0.9;
const WIRE_LEAD = 30, WIRE_R = 0.45, J_R = 3.0;

export class CathSim {
  readonly group = new THREE.Group();
  access: Access = "femoral_right";
  target: Target = "left";
  phase: Phase = "idle";
  /** true while the injection runs: the caller turns the heartbeat on in 3D and in the X-ray (cine) */
  cine = false;
  private t = 0;
  private readonly cathMesh: THREE.Mesh;
  private readonly wireMesh: THREE.Mesh;
  private readonly puff3d: THREE.Mesh;
  private readonly cathTube = new FlatTube(1400, 12);
  private readonly wireTube = new FlatTube(1400, 8);
  onPhase: (p: Phase) => void = () => {};
  /** the catheter as drawn now (puncture -> tip), for the cross-section */
  visiblePath: THREE.Vector3[] | null = null;
  get engaged() { return this.phase === "engaged" || this.phase === "inject"; }
  /** where the engaged tip ends (3 mm inside the effective ostium) */
  tipPoint() { const p = this.data.shapes[this.shapeName].polyline; return V(p[p.length - 1]); }

  constructor(private readonly data: CathData, private readonly angio: AngioRenderer,
    cathMat: THREE.Material, wireMat: THREE.Material, puffMat: THREE.Material) {
    this.cathMesh = new THREE.Mesh(this.cathTube.geometry, cathMat);
    this.wireMesh = new THREE.Mesh(this.wireTube.geometry, wireMat);
    this.cathMesh.frustumCulled = this.wireMesh.frustumCulled = false;
    angio.setDeviceGeometries([{ geometry: this.cathTube.geometry, weight: 1 }, { geometry: this.wireTube.geometry, weight: 5 }]);
    this.puff3d = new THREE.Mesh(new THREE.IcosahedronGeometry(1, 3), puffMat);
    this.puff3d.visible = false;
    this.cathMesh.renderOrder = 3; this.wireMesh.renderOrder = 3; this.puff3d.renderOrder = 4;
    this.group.add(this.cathMesh, this.wireMesh, this.puff3d);
    this.reset();
  }

  get shapeName(): "JL4" | "JR4" { return this.target === "left" ? "JL4" : "JR4"; }

  private routePts() { return this.data.routes[this.access].polyline_to_ascending_top.map(V); }
  private seg(m: number) {
    const sh = this.data.shapes[this.shapeName];
    return sh.straight_polyline.map((p, i) => V(p).lerp(V(sh.polyline[i]), m));
  }
  /** Whole catheter path (puncture -> tip) for a morph m (0 = straight in the ascending aorta, 1 = engaged shape). */
  private path(m: number) {
    const r = this.routePts();
    return [...r, ...this.seg(m).slice(1)];
  }

  reset() {
    this.phase = "idle"; this.t = 0; this.cine = false;
    this.angio.fill.value.set(-1e9, -1e9);                      // no contrast
    this.angio.setPuff(null, 0);
    this.puff3d.visible = false;
    this.setGeometry(0, 0, -1);
  }

  /** Start the whole sequence: wire + catheter advance, wire out, shape and engage. */
  run() { this.reset(); this.phase = "advance"; this.onPhase("advance"); }

  /** Contrast injection (only when engaged). */
  inject() {
    if (this.phase !== "engaged" && this.phase !== "inject") return;
    this.phase = "inject"; this.t = 0; this.cine = true; this.onPhase("inject");
  }

  /** Engage directly (no animation): for screenshots and the root close-up. */
  engageNow() { this.phase = "engaged"; this.t = 0; this.setGeometry(1, Infinity, -1); this.onPhase("engaged"); }

  /** wireTipS: arc length of the guidewire tip (< 0 = no wire). */
  private setGeometry(m: number, tipS: number, wireTipS: number) {
    const P = this.path(m);
    const cum = cumOf(P);
    const L = cum[cum.length - 1];
    const cath = cut(P, cum, Math.min(tipS, L));
    this.visiblePath = cath.length > 1 ? cath : null;
    const cOn = this.cathTube.update(thin(cath), this.data.catheter_outer_radius_mm);
    this.cathMesh.visible = cOn;
    let wOn = false;
    if (wireTipS > 0) {
      // the wire runs inside the catheter and leads it; its last few mm curl into a J (soft, atraumatic tip)
      const W = cut(P, cum, Math.min(wireTipS, L));
      const end = W[W.length - 1], prev = W[Math.max(W.length - 2, 0)];
      const t = end.clone().sub(prev).normalize();
      let n = new THREE.Vector3(1, 0, 0).cross(t);
      if (n.lengthSq() < 1e-6) n = new THREE.Vector3(0, 1, 0).cross(t);
      n.normalize();
      for (let k = 1; k <= 14; k++) {
        const th = (k / 14) * Math.PI * 1.1;
        W.push(end.clone().addScaledVector(t, J_R * Math.sin(th)).addScaledVector(n, J_R * (1 - Math.cos(th))));
      }
      wOn = this.wireTube.update(thin(W), WIRE_R);                     // metal: weight 5, far denser than the catheter wall
    } else this.wireTube.update([], WIRE_R);
    this.wireMesh.visible = wOn;
    this.angio.setDeviceVisible([cOn, wOn]);
  }

  /** Advance the timeline; returns true while something moves (the caller re-renders the X-ray). */
  update(dt: number): boolean {
    if (this.phase === "idle" || this.phase === "engaged") return false;
    this.t += dt;
    const ease = (x: number) => (x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2);
    const Lroute = cumOf(this.routePts()).at(-1)!;
    const Lstraight = cumOf(this.seg(0)).at(-1)!;
    if (this.phase === "advance") {
      const e = ease(Math.min(1, this.t / T_ADVANCE));
      const tip = e * (Lroute + Lstraight * 0.85);
      this.setGeometry(0, tip, tip + WIRE_LEAD);
      if (this.t >= T_ADVANCE) { this.phase = "withdraw"; this.t = 0; this.onPhase("withdraw"); }
    } else if (this.phase === "withdraw") {
      const tip = Lroute + Lstraight * 0.85;
      const e = Math.min(1, this.t / T_WITHDRAW);
      this.setGeometry(0, tip, tip + WIRE_LEAD - e * (WIRE_LEAD + 120));
      if (this.t >= T_WITHDRAW) { this.phase = "shape"; this.t = 0; this.onPhase("shape"); }
    } else if (this.phase === "shape") {
      const m = ease(Math.min(1, this.t / T_SHAPE));
      // the catheter is pushed the last few mm while it takes its shape, so the tip ends 3 mm inside the ostium
      this.setGeometry(m, Infinity, -1);
      if (this.t >= T_SHAPE) { this.phase = "engaged"; this.t = 0; this.onPhase("engaged"); }
    } else if (this.phase === "inject") {
      const max = this.data.trees[this.target].max_distance_mm + 5;
      const t = this.t;
      const front = t < T_FILL ? -8 + (max + 8) * ease(t / T_FILL) : max;
      const back = t < T_FILL + T_HOLD ? -1e9 : -8 + (max + 8) * ease(Math.min(1, (t - T_FILL - T_HOLD) / T_WASH));
      this.angio.fill.value.set(front, back);
      const sh = this.data.shapes[this.shapeName];
      const pr = t < PUFF_T ? 4.0 * Math.sin((Math.PI * t) / PUFF_T) : 0;
      this.angio.setPuff(pr > 0 ? V(sh.reflux_point_LPS) : null, pr);
      this.puff3d.visible = pr > 0.05;
      if (pr > 0.05) { this.puff3d.position.copy(V(sh.reflux_point_LPS)); this.puff3d.scale.setScalar(pr); }
      if (t >= T_FILL + T_HOLD + T_WASH) {
        this.angio.fill.value.set(-1e9, -1e9);
        this.phase = "engaged"; this.t = 0; this.cine = false; this.onPhase("engaged");
      }
    }
    return true;
  }
}
