// v1.1 PEEL MODE (feature flag "peel"; Scene 1; display transforms only).
// Click-drag a peelable structure to slide it away along an anatomical direction; release and it springs back; double-click
// to keep it removed; Reset restores everything. Only the 3D display meshes move (their object position): the X-ray, the
// validated geometry and every other mesh are untouched.
// The mini-tour "Where do the coronaries come from?" drives the same peels with the camera.
import * as THREE from "three";

export type PeelKey = "fat" | "pulmonary" | "laa" | "raa" | "ra" | "aorta";
export const PEEL_LABEL: Record<PeelKey, string> = {
  fat: "Epicardial fat", pulmonary: "Pulmonary trunk", laa: "Left atrial appendage", raa: "Right atrial appendage",
  ra: "Right atrium", aorta: "Aorta",
};
/** Peel directions in LPS (+x left, +y posterior, +z superior); the fat lifts radially from the heart at the grab point. */
export const PEEL_DIR: Record<Exclude<PeelKey, "fat">, [number, number, number]> = {
  pulmonary: [0.15, -0.75, 0.65],   // forward and up, off the aortic root: uncovers the left main
  laa: [0.75, -0.25, 0.6],          // out to the left and up, off the left main and circumflex
  raa: [-0.55, -0.65, 0.5],         // forward, right and up, off the right coronary origin
  ra: [-0.95, -0.2, 0.2],           // to the right, out of the right atrioventricular groove
  aorta: [-0.2, -0.1, 1.0],         // up
};
const MAX_DRAG_MM = 70, REMOVED_MM = 115;

interface Group {
  key: PeelKey;
  meshes: THREE.Mesh[];
  dir: THREE.Vector3;
  amount: number;
  target: number;
  vel: number;
  removed: boolean;
}

export interface PeelDeps {
  canvas: HTMLCanvasElement;
  camera: THREE.PerspectiveCamera;
  controls: { enabled: boolean };
  heartC: THREE.Vector3;
  enabled: () => boolean;
  onChange: () => void;
}

export class PeelMode {
  private groups = new Map<PeelKey, Group>();
  private ray = new THREE.Raycaster();
  private drag: { g: Group; x0: number; y0: number; a0: number; pxPerMm: THREE.Vector2 } | null = null;

  constructor(private readonly d: PeelDeps) {
    const c = d.canvas;
    // capture phase: a grab on a peelable must win over the orbit controls
    c.addEventListener("pointerdown", (e) => this.down(e), { capture: true });
    window.addEventListener("pointermove", (e) => this.move(e));
    window.addEventListener("pointerup", () => this.up());
    c.addEventListener("dblclick", (e) => this.dbl(e));
  }

  register(key: PeelKey, meshes: THREE.Mesh[]) {
    const dir = key === "fat" ? new THREE.Vector3(0, -1, 0) : new THREE.Vector3(...PEEL_DIR[key]).normalize();
    this.groups.set(key, { key, meshes: meshes.filter(Boolean), dir, amount: 0, target: 0, vel: 0, removed: false });
  }

  isRemoved(key: PeelKey) { return !!this.groups.get(key)?.removed; }

  get anyPeeled() { return [...this.groups.values()].some((g) => g.removed || Math.abs(g.amount) > 0.5); }

  private pick(e: MouseEvent): { g: Group; p: THREE.Vector3 } | null {
    const r = this.d.canvas.getBoundingClientRect();
    this.ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), this.d.camera);
    let best: { g: Group; p: THREE.Vector3; t: number } | null = null;
    for (const g of this.groups.values()) {
      const vis = g.meshes.filter((m) => m.visible);
      const hit = this.ray.intersectObjects(vis, false)[0];
      if (hit && (!best || hit.distance < best.t)) best = { g, p: hit.point, t: hit.distance };
    }
    return best;
  }

  private screenPerMm(p: THREE.Vector3, dir: THREE.Vector3) {
    const r = this.d.canvas.getBoundingClientRect();
    const a = p.clone().project(this.d.camera), b = p.clone().addScaledVector(dir, 10).project(this.d.camera);
    return new THREE.Vector2(((b.x - a.x) * r.width) / 2 / 10, (-(b.y - a.y) * r.height) / 2 / 10);
  }

  private down(e: PointerEvent) {
    if (!this.d.enabled() || e.button !== 0) return;
    const hit = this.pick(e);
    if (!hit || hit.g.removed) return;
    e.stopImmediatePropagation();
    e.preventDefault();
    const g = hit.g;
    if (g.key === "fat") g.dir.copy(hit.p).sub(this.d.heartC).normalize();     // lift off the heart where it was grabbed
    let s = this.screenPerMm(hit.p, g.dir);
    if (s.length() < 0.2) s = new THREE.Vector2(0, -1);                         // pointing at the camera: drag up to peel
    this.drag = { g, x0: e.clientX, y0: e.clientY, a0: g.amount, pxPerMm: s };
    this.d.controls.enabled = false;
    document.body.style.cursor = "grabbing";
  }

  private move(e: PointerEvent) {
    if (!this.drag) return;
    const { g, x0, y0, a0, pxPerMm } = this.drag;
    const along = ((e.clientX - x0) * pxPerMm.x + (e.clientY - y0) * pxPerMm.y) / pxPerMm.lengthSq();
    g.amount = g.target = Math.max(0, Math.min(MAX_DRAG_MM, a0 + along));
    g.vel = 0;
  }

  private up() {
    if (!this.drag) return;
    this.drag.g.target = 0;                     // release: it springs back
    this.drag = null;
    this.d.controls.enabled = true;
    document.body.style.cursor = "";
    this.d.onChange();
  }

  private dbl(e: MouseEvent) {
    if (!this.d.enabled()) return;
    const hit = this.pick(e);
    if (!hit) return;
    if (hit.g.key === "fat") hit.g.dir.copy(hit.p).sub(this.d.heartC).normalize();
    this.remove(hit.g.key);
  }

  /** keep it removed (slides far away, then hides) */
  remove(key: PeelKey) {
    const g = this.groups.get(key);
    if (!g) return;
    g.removed = true;
    g.target = REMOVED_MM;
    this.d.onChange();
  }

  /** for the mini-tour: slide to an amount (mm); it stays there (no spring back) */
  hold(key: PeelKey, mm: number, dir?: THREE.Vector3) {
    const g = this.groups.get(key);
    if (!g) return;
    if (dir) g.dir.copy(dir).normalize();
    g.target = mm;
    g.removed = mm >= REMOVED_MM;
    this.d.onChange();
  }

  reset(instant = false) {
    for (const g of this.groups.values()) {
      g.removed = false; g.target = 0;
      if (instant) { g.amount = 0; g.vel = 0; this.apply(g); }
      for (const m of g.meshes) m.visible = true;
    }
    this.d.onChange();
  }

  /** springs: slightly under-damped, so a release settles with a small bounce */
  update(dt: number) {
    const k = 70, c = 2 * Math.sqrt(k) * 0.72;
    for (const g of this.groups.values()) {
      if (this.drag?.g === g) { this.apply(g); continue; }
      const a = k * (g.target - g.amount) - c * g.vel;
      g.vel += a * Math.min(dt, 0.05);
      g.amount += g.vel * Math.min(dt, 0.05);
      if (Math.abs(g.target - g.amount) < 0.05 && Math.abs(g.vel) < 0.05) { g.amount = g.target; g.vel = 0; }
      this.apply(g);
    }
  }

  private apply(g: Group) {
    for (const m of g.meshes) {
      m.position.copy(g.dir).multiplyScalar(g.amount);
      if (g.removed && g.amount > REMOVED_MM - 5) m.visible = false;   // never forces visible: other modes hide these too
    }
  }
}
