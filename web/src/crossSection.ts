// Scene 6 (D56): a coronary cross-section. ILLUSTRATIVE (the panel says so).
// The slice sits on a coronary centreline sample (build_atlas_cath.py: every spline's points, authored radius, and fill distance
// s along the tree from the effective ostium), perpendicular to the centreline. It shows the lumen at the atlas's own radius, an
// illustrative three-layer wall (intima, media, adventitia, ~0.8 mm in all) and epicardial fat as a soft ring. The lumen fills
// with contrast from the SAME fill window as the 3D glow and the X-ray (angio.fill); the catheter tip appears where the engaged
// catheter crosses the slice plane. A ring marks the slice on the 3D vessel; the caller puts the X-ray dot at
// CArm.project(point()) (the validated engine).
import * as THREE from "three";
import type { Target } from "./cath";

export interface Line { points: number[][]; radius_mm: number[]; s_mm: number[] }
type Lines = Record<Target, Record<string, Line>>;

const WALL = [{ name: "Intima", t: 0.12, c: "#f1d9cf" }, { name: "Media", t: 0.3, c: "#b4474c" }, { name: "Adventitia", t: 0.38, c: "#d8a593" }];
const WALL_T = WALL.reduce((a, w) => a + w.t, 0);
const FAT_T = 2.6;

/** Friendly vessel names, in words. */
export function vesselName(key: string): string {
  const [obj, i] = key.split("#");
  const n = Number(i);
  if (obj === "Left coronary artery") return "Left main";
  if (obj === "Anterior interventricular artery") return n === 0 ? "Left anterior descending" : "A branch of the LAD";
  if (obj === "Circumflex artery of heart") return n === 0 ? "Circumflex" : "A branch of the circumflex";
  if (obj === "Septal branches of anterior interventricular artery") return "A septal branch";
  if (obj === "Right coronary artery") return n === 0 ? "Right coronary artery" : "A branch of the right coronary";
  if (obj === "Right inferolateral branch of right coronary artery") return "Right inferolateral branch";
  return obj;
}

export class CrossSection {
  tree: Target = "left";
  key = "Left coronary artery#0";
  idx = 0;
  followTip = false;
  /** what the last drawn slice showed in the lumen (for the e2e check) */
  lastLumen: "blood" | "contrast" = "blood";
  readonly ring: THREE.Mesh;
  private P: THREE.Vector3[] = [];
  private T: THREE.Vector3[] = [];
  private N: THREE.Vector3[] = [];
  private B: THREE.Vector3[] = [];

  constructor(private readonly lines: Lines, ringMat: THREE.Material) {
    this.ring = new THREE.Mesh(new THREE.TorusGeometry(1, 0.09, 12, 64), ringMat);
    this.ring.renderOrder = 5;
    this.setKey("left", "Left coronary artery#0", 0);
  }

  static ostialKey(t: Target) { return t === "left" ? "Left coronary artery#0" : "Right coronary artery#0"; }
  get line(): Line { return this.lines[this.tree][this.key]; }
  get count() { return this.P.length; }

  setKey(tree: Target, key: string, idx: number) {
    this.tree = tree;
    this.key = key;
    const L = this.line;
    this.P = L.points.map((p) => new THREE.Vector3(p[0], p[1], p[2]));
    const n = this.P.length;
    this.T = this.P.map((_, i) => this.P[Math.min(i + 1, n - 1)].clone().sub(this.P[Math.max(i - 1, 0)]).normalize());
    // parallel-transport frames, so the slice never spins as it slides along the vessel
    let N0 = new THREE.Vector3(0, 0, 1).cross(this.T[0]);
    if (N0.lengthSq() < 1e-6) N0 = new THREE.Vector3(1, 0, 0).cross(this.T[0]);
    N0.normalize();
    this.N = [N0];
    for (let i = 1; i < n; i++) {
      const v = this.N[i - 1].clone();
      v.sub(this.T[i].clone().multiplyScalar(v.dot(this.T[i]))).normalize();
      this.N.push(v);
    }
    this.B = this.T.map((t, i) => t.clone().cross(this.N[i]));
    this.setIndex(idx);
  }

  setIndex(i: number) {
    this.idx = Math.max(0, Math.min(this.P.length - 1, Math.round(i)));
    const r = this.radius() + WALL_T + 0.35;
    this.ring.position.copy(this.point());
    this.ring.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), this.T[this.idx]);
    this.ring.scale.setScalar(r);
  }

  /** Slider position 0..1 along the current spline (proximal -> distal). */
  get fraction() { return this.P.length > 1 ? this.idx / (this.P.length - 1) : 0; }
  setFraction(f: number) { this.setIndex(f * (this.P.length - 1)); }

  point() { return this.P[this.idx].clone(); }
  tangent() { return this.T[this.idx].clone(); }
  radius() { return this.line.radius_mm[this.idx]; }
  s() { return this.line.s_mm[this.idx]; }

  /** Nearest centreline sample of either tree to a picked 3D point. */
  pick(p: THREE.Vector3): boolean {
    let bd = Infinity, bt: Target = "left", bk = "", bi = 0;
    for (const tree of ["left", "right"] as Target[])
      for (const [key, L] of Object.entries(this.lines[tree]))
        for (let i = 0; i < L.points.length; i++) {
          const q = L.points[i];
          const d = (q[0] - p.x) ** 2 + (q[1] - p.y) ** 2 + (q[2] - p.z) ** 2;
          if (d < bd) { bd = d; bt = tree; bk = key; bi = i; }
        }
    if (bd > 36) return false;                                   // farther than 6 mm: not on a coronary
    const tree = bt, key = bk, i = bi;
    this.followTip = false;
    this.setKey(tree, key, i);
    return true;
  }

  /** Put the slice where the catheter tip is: on the ostial spline of the target tree, at the sample nearest the tip. */
  toTip(tree: Target, tip: THREE.Vector3) {
    this.setKey(tree, CrossSection.ostialKey(tree), 0);
    let k = 0, dmin = Infinity;
    this.P.forEach((q, i) => { const d = q.distanceToSquared(tip); if (d < dmin) { dmin = d; k = i; } });
    // 1.5 mm proximal to the tip end, so the slice cuts THROUGH the catheter (the tip is the catheter's end face)
    let j = k;
    while (j > 0 && this.P[j].distanceTo(this.P[k]) < 1.5) j--;
    this.setIndex(j);
  }

  /** Where the catheter crosses this slice plane (mm in the slice's N, B axes), or null. */
  catheterCrossing(path: THREE.Vector3[] | null): [number, number] | null {
    if (!path || path.length < 2) return null;
    const P0 = this.point(), T = this.tangent(), N = this.N[this.idx], B = this.B[this.idx];
    let best: [number, number, number] | null = null;
    for (let i = 0; i < path.length - 1; i++) {
      const a = path[i].clone().sub(P0).dot(T), b = path[i + 1].clone().sub(P0).dot(T);
      if (a === b || a * b > 0) continue;
      const c = path[i].clone().lerp(path[i + 1], a / (a - b)).sub(P0);
      const x = c.dot(N), y = c.dot(B), d = Math.hypot(x, y);
      if (d < this.radius() + 1.5 && (!best || d < best[2])) best = [x, y, d];
    }
    return best ? [best[0], best[1]] : null;
  }

  /** Draw the slice. fill = (front, back) mm along the tree (contrast where back <= s <= front). */
  draw(cv: HTMLCanvasElement, fill: THREE.Vector2, cathXY: [number, number] | null, catheterFilled: boolean) {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    const W = Math.round(cv.clientWidth * dpr), H = Math.round(cv.clientHeight * dpr);
    if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
    const g = cv.getContext("2d")!;
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.clearRect(0, 0, W, H);
    const r = this.radius();
    const cx = W * 0.4, cy = H * 0.52;
    const k = (Math.min(W, H) * 0.34) / (r + WALL_T + FAT_T);           // px per mm, fitted to the panel
    // epicardial fat: a band of fat lobules, densest next to the vessel and thinning outward (illustrative)
    const outer = (r + WALL_T + FAT_T) * k, inner = (r + WALL_T) * k;
    const fat = g.createRadialGradient(cx, cy, inner, cx, cy, outer);
    fat.addColorStop(0, "rgba(226,198,128,0.62)");
    fat.addColorStop(0.65, "rgba(220,192,124,0.38)");
    fat.addColorStop(1, "rgba(214,186,120,0)");
    g.fillStyle = fat;
    g.beginPath(); g.arc(cx, cy, outer, 0, 2 * Math.PI); g.fill();
    const rnd = (i: number) => { const x = Math.sin(i * 12.9898 + 78.233) * 43758.5453; return x - Math.floor(x); };
    for (let i = 0; i < 70; i++) {
      const t = Math.pow(rnd(i), 1.4), ang = 2 * Math.PI * rnd(i + 100);
      const rr = inner + (outer - inner) * (0.08 + 0.7 * t), lr = (0.22 + 0.2 * rnd(i + 200)) * k;
      g.fillStyle = `rgba(236,212,146,${(0.14 * (1 - t)).toFixed(3)})`;
      g.strokeStyle = `rgba(186,156,92,${(0.22 * (1 - t)).toFixed(3)})`;
      g.lineWidth = Math.max(1, 0.03 * k);
      g.beginPath(); g.arc(cx + rr * Math.cos(ang), cy + rr * Math.sin(ang), lr, 0, 2 * Math.PI); g.fill(); g.stroke();
    }
    // wall: adventitia (outer) -> media -> intima (inner)
    let rad = r + WALL_T;
    for (const w of [...WALL].reverse()) {
      g.fillStyle = w.c;
      g.beginPath(); g.arc(cx, cy, rad * k, 0, 2 * Math.PI); g.fill();
      rad -= w.t;
    }
    // lumen: blood, or contrast (bright) when the fill window covers this slice; a soft edge at the moving front
    const s = this.s();
    const front = fill.x, back = fill.y;
    const fIn = front > 1e8 ? 1 : Math.min(1, Math.max(0, (front - s) / 4 + 0.5)) * Math.min(1, Math.max(0, (s - back) / 4 + 0.5));
    const lum = g.createRadialGradient(cx, cy, 0, cx, cy, r * k);
    const blood = [96, 14, 20], contrast = [244, 240, 232];
    const mix = (a: number[], b: number[], t: number) => a.map((x, i) => Math.round(x + (b[i] - x) * t));
    const c0 = mix(blood, contrast, fIn), c1 = mix([70, 8, 14], [214, 208, 198], fIn);
    lum.addColorStop(0, `rgb(${c0})`); lum.addColorStop(1, `rgb(${c1})`);
    g.fillStyle = lum;
    g.beginPath(); g.arc(cx, cy, r * k, 0, 2 * Math.PI); g.fill();
    // catheter tip (6F: 2 mm outer, ~1.4 mm inner), where the engaged catheter crosses this plane
    let cathPx: [number, number] | null = null;
    if (cathXY) {
      const [x, y] = cathXY;
      cathPx = [cx + x * k, cy - y * k];
      // the catheter wall in its own blue-grey with a dark outline, so it reads against contrast AND against blood
      g.fillStyle = "#8fa6c4";
      g.beginPath(); g.arc(cathPx[0], cathPx[1], 1.0 * k, 0, 2 * Math.PI); g.fill();
      g.strokeStyle = "rgba(20,26,36,0.9)"; g.lineWidth = Math.max(1.5, 0.06 * k); g.stroke();
      g.fillStyle = catheterFilled ? `rgb(${contrast})` : "rgb(120,24,30)";
      g.beginPath(); g.arc(cathPx[0], cathPx[1], 0.7 * k, 0, 2 * Math.PI); g.fill();
    }
    // labels with leader lines (right side), no numbers
    const fs = Math.round(14 * dpr);
    g.font = `${fs}px system-ui, "Segoe UI", sans-serif`;
    g.textBaseline = "middle";
    const lx = W * 0.79;
    const items: [string, number, number][] = [];                         // label, anchor x, anchor y
    const at = (rr: number, ang: number): [number, number] => [cx + rr * k * Math.cos(ang), cy - rr * k * Math.sin(ang)];
    items.push(["Epicardial fat", ...at(r + WALL_T + FAT_T * 0.45, 0.95)]);
    items.push(["Adventitia", ...at(r + WALL_T - 0.19, 0.55)]);
    items.push(["Media", ...at(r + 0.12 + 0.15, 0.2)]);
    items.push(["Intima", ...at(r + 0.06, -0.15)]);
    items.push([fIn > 0.5 ? "Lumen: contrast" : "Lumen: blood", ...at(r * 0.8, -0.75)]);   // outside the catheter (1 mm)
    this.lastLumen = fIn > 0.5 ? "contrast" : "blood";
    if (cathPx) items.push(["Catheter tip", cathPx[0], cathPx[1]]);
    const ys = items.map((_, i) => H * 0.2 + i * (H * 0.6) / Math.max(items.length - 1, 1));
    items.forEach(([text, ax, ay], i) => {
      g.strokeStyle = "rgba(233,237,242,0.55)";
      g.lineWidth = dpr;
      g.beginPath(); g.moveTo(ax, ay); g.lineTo(lx - 10 * dpr, ys[i]); g.stroke();
      g.fillStyle = "#e9edf2";
      g.beginPath(); g.arc(ax, ay, 2.2 * dpr, 0, 2 * Math.PI); g.fill();
      g.fillText(text, lx - 4 * dpr, ys[i]);
    });
  }
}
