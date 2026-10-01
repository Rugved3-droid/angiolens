// C-arm projection geometry in the LPS patient frame. Mirrors preprocess/cpt/geometry.py exactly;
// every rule is in CONVENTIONS.md and is tested in web/tests/geometry.test.ts against Python fixtures.
// Never mirror or rotate an image at display time: if a view looks wrong, fix the geometry.

export type Vec3 = [number, number, number];

export const SID_MM = 1000;
export const SOD_MM = 750;
export const ALPHA_RANGE: [number, number] = [-90, 90]; // LAO +, RAO -
export const BETA_RANGE: [number, number] = [-45, 45]; // CRAN +, CAUD -

export const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
export const scale = (a: Vec3, s: number): Vec3 => [a[0] * s, a[1] * s, a[2] * s];
export const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross = (a: Vec3, b: Vec3): Vec3 => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
export const norm = (a: Vec3): number => Math.hypot(a[0], a[1], a[2]);
export const normalize = (a: Vec3): Vec3 => scale(a, 1 / norm(a));

const rad = (deg: number) => (deg * Math.PI) / 180;

/** Unit vector from isocenter toward the detector: (sin a cos b, -cos a cos b, sin b). */
export function detectorDirection(alphaDeg: number, betaDeg: number): Vec3 {
  const a = rad(alphaDeg);
  const b = rad(betaDeg);
  return [Math.sin(a) * Math.cos(b), -Math.cos(a) * Math.cos(b), Math.sin(b)];
}

/** Screen right u and up v: v = normalize(z - (z.d)d), u = v x d (so u x v = d). */
export function screenAxes(d: Vec3): { u: Vec3; v: Vec3 } {
  const z: Vec3 = [0, 0, 1];
  const vRaw = sub(z, scale(d, dot(z, d)));
  if (norm(vRaw) < 1e-9) throw new Error("screen up undefined: d parallel to z");
  const v = normalize(vRaw);
  return { u: cross(v, d), v };
}

export function viewLabel(alphaDeg: number, betaDeg: number): string {
  const a = Math.round(alphaDeg);
  const b = Math.round(betaDeg);
  const primary = a === 0 ? "AP" : `${a > 0 ? "LAO" : "RAO"} ${Math.abs(a)}`;
  return b === 0 ? primary : `${primary} / ${b > 0 ? "CRAN" : "CAUD"} ${Math.abs(b)}`;
}

export class CArm {
  readonly d: Vec3;
  readonly u: Vec3;
  readonly v: Vec3;
  readonly iso: Vec3;
  readonly source: Vec3;
  readonly detectorCenter: Vec3;

  constructor(
    readonly alphaDeg: number,
    readonly betaDeg: number,
    isocenter: Vec3,
    readonly tableOffset: Vec3 = [0, 0, 0],
    readonly sid = SID_MM,
    readonly sod = SOD_MM,
  ) {
    if (alphaDeg < ALPHA_RANGE[0] || alphaDeg > ALPHA_RANGE[1]) throw new Error(`alpha ${alphaDeg} out of range`);
    if (betaDeg < BETA_RANGE[0] || betaDeg > BETA_RANGE[1]) throw new Error(`beta ${betaDeg} out of range`);
    this.iso = add(isocenter, tableOffset);
    this.d = detectorDirection(alphaDeg, betaDeg);
    ({ u: this.u, v: this.v } = screenAxes(this.d));
    this.source = sub(this.iso, scale(this.d, sod));
    this.detectorCenter = add(this.iso, scale(this.d, sid - sod));
  }

  get label(): string {
    return viewLabel(this.alphaDeg, this.betaDeg);
  }

  /** Depth of p along the beam axis measured from the source plane. */
  depth(p: Vec3): number {
    return dot(sub(p, this.source), this.d);
  }

  magnification(p: Vec3): number {
    return this.sid / this.depth(p);
  }

  /** Intersection of ray S->p with the detector plane (LPS mm). */
  detectorHit(p: Vec3): Vec3 {
    const depth = this.depth(p);
    if (depth <= 0) throw new Error("point at or behind the source plane");
    return add(this.source, scale(sub(p, this.source), this.sid / depth));
  }

  /** Screen coordinates (q.u, q.v) in detector mm, origin on the central ray. */
  project(p: Vec3): [number, number] {
    const q = sub(this.detectorHit(p), this.detectorCenter);
    return [dot(q, this.u), dot(q, this.v)];
  }

  screenToLps(x: number, y: number): Vec3 {
    return add(this.detectorCenter, add(scale(this.u, x), scale(this.v, y)));
  }

  /**
   * Column-major 4x4 (WebGL order) mapping LPS -> clip space for a detector of `detectorMm` width:
   *   x_c = (2 SID / W)(p-S).u,  y_c = (2 SID / W)(p-S).v,  w_c = (p-S).d,  z_c = A w_c + B.
   * NDC x,y equal screen mm / (W/2), so +u is right and +v is up by construction.
   * The matrix is mirror-handed (u x v = d points toward the viewer), so renderers must not
   * rely on triangle winding for facing; they use world-space face normals instead.
   */
  clipMatrix(detectorMm: number, near = 1, far = 2 * SID_MM): number[] {
    const k = (2 * this.sid) / detectorMm;
    const A = (far + near) / (far - near);
    const B = (-2 * far * near) / (far - near);
    const S = this.source;
    const r0 = [k * this.u[0], k * this.u[1], k * this.u[2], -k * dot(this.u, S)];
    const r1 = [k * this.v[0], k * this.v[1], k * this.v[2], -k * dot(this.v, S)];
    const r3 = [this.d[0], this.d[1], this.d[2], -dot(this.d, S)];
    const r2 = r3.map((x, i) => A * x + (i === 3 ? B : 0));
    // column-major
    return [0, 1, 2, 3].flatMap((c) => [r0[c], r1[c], r2[c], r3[c]]);
  }
}

/** F = 1 - sum|dp - (dp.r) r| / sum|dp|, r = unit ray from source to each pair midpoint. */
export function foreshortening(points: Vec3[], source: Vec3): number {
  if (points.length < 2) throw new Error("need at least two samples");
  let perp = 0;
  let total = 0;
  for (let i = 1; i < points.length; i++) {
    const dp = sub(points[i], points[i - 1]);
    const r = normalize(sub(scale(add(points[i], points[i - 1]), 0.5), source));
    perp += norm(sub(dp, scale(r, dot(dp, r))));
    total += norm(dp);
  }
  if (total === 0) throw new Error("zero-length segment");
  return 1 - perp / total;
}

/** Detector raster: pixel (col,row) with row 0 at the TOP (+v) and col 0 at the LEFT (-u). */
export function screenToPixel(x: number, y: number, detectorMm: number, nPx: number): [number, number] {
  const px = detectorMm / nPx;
  return [(x + detectorMm / 2) / px - 0.5, (detectorMm / 2 - y) / px - 0.5];
}

export function pixelToScreen(col: number, row: number, detectorMm: number, nPx: number): [number, number] {
  const px = detectorMm / nPx;
  return [(col + 0.5) * px - detectorMm / 2, detectorMm / 2 - (row + 0.5) * px];
}
