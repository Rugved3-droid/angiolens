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
  private cathGeo: THREE.BufferGeometry | null = null;
  private wireGeo: THREE.BufferGeometry | null = null;
  onPhase: (p: Phase) => void = () => {};

  constructor(private readonly data: CathData, private readonly angio: AngioRenderer,
    cathMat: THREE.Material, wireMat: THREE.Material, puffMat: THREE.Material) {
    this.cathMesh = new THREE.Mesh(new THREE.BufferGeometry(), cathMat);
    this.wireMesh = new THREE.Mesh(new THREE.BufferGeometry(), wireMat);
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
    this.cathGeo?.dispose();
    this.cathGeo = cath.length > 1 ? closedTube(cath, this.data.catheter_outer_radius_mm, 12) : new THREE.BufferGeometry();
    this.cathMesh.geometry = this.cathGeo;
    this.cathMesh.visible = cath.length > 1;
    const devices: { geometry: THREE.BufferGeometry; weight: number }[] = [];
    if (cath.length > 1) devices.push({ geometry: this.cathGeo, weight: 1 });
    this.wireGeo?.dispose();
    this.wireGeo = null;
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
      this.wireGeo = closedTube(W, WIRE_R, 8);
      devices.push({ geometry: this.wireGeo, weight: 5 });     // metal: far denser than the catheter wall
    }
    this.wireMesh.geometry = this.wireGeo ?? new THREE.BufferGeometry();
    this.wireMesh.visible = !!this.wireGeo;
    this.angio.setDevices(devices);
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
