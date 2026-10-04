// Phase 1 angiogram: per-pixel path length through closed meshes, I = exp(-k t).
//
// Path length is accumulated order-independently. Each fragment adds (|x - S| - SOD) to an EXIT
// sum or an ENTRY sum, plus 1 to the matching counter. Exit means the outward face normal points
// along the ray. For a closed mesh, path length = exit sum - entry sum. Subtracting SOD keeps the
// values small for float precision; the offsets cancel because entries and exits pair up.
// Rasterization can drop one crossing of a pair at a silhouette, so pixels whose counts disagree
// are repaired from valid neighbors in the composite pass.
// Facing comes from world-space face normals, never from triangle winding, because the
// C-arm clip matrix is mirror-handed (see geometry.ts).
import * as THREE from "three";
import type { CArm } from "./geometry";

// Optional variants (atlas Scene 5, D53); with neither, the shaders are exactly the validated Phase 1 ones:
//  * field: the atlas's position-only heartbeat field (the SAME GLSL and uniforms as the 3D heart), applied to the rest
//    positions while uFieldOn = 1 (cine). Facing still uses the rest face normals (the field is a small, smooth deformation).
//  * fill: a per-vertex distance along the coronary tree (_s, mm from the effective ostium); fragments outside
//    [uFill.y, uFill.x] are dropped. The entry and exit of one thin-tube crossing share nearly the same _s, so they are kept
//    or dropped together; a split pair at the front is handled by the usual count repair. Illustrative, not physics.
//  * uWeight scales a mesh's path length (the catheter vs the guidewire in the device channel).
const THICKNESS_VERT = (field: string, fill: boolean) => /* glsl */ `
  ${field ? field + "\n  uniform float uFieldOn;" : ""}
  ${fill ? "attribute float _s; varying float vS;" : ""}
  varying vec3 vWorld;
  varying vec3 vNormal;
  void main() {
    vec3 p = position;
    ${field ? "if (uFieldOn > 0.5) p = cptBeat(p);" : ""}
    ${fill ? "vS = _s;" : ""}
    vWorld = (modelMatrix * vec4(p, 1.0)).xyz;
    vNormal = normal;               // face normal (geometry is non-indexed), world == model
    gl_Position = projectionMatrix * viewMatrix * vec4(vWorld, 1.0);
  }`;

const THICKNESS_FRAG = (fill: boolean) => /* glsl */ `
  uniform vec3 uSource;
  uniform float uSod;
  uniform float uWeight;
  ${fill ? "uniform vec2 uFill; varying float vS;" : ""}
  varying vec3 vWorld;
  varying vec3 vNormal;
  void main() {
    ${fill ? "if (vS > uFill.x || vS < uFill.y) discard;" : ""}
    vec3 ray = vWorld - uSource;
    float L = (length(ray) - uSod) * uWeight;
    gl_FragColor = dot(vNormal, ray) > 0.0 ? vec4(L, 0.0, 1.0, 0.0) : vec4(0.0, L, 0.0, 1.0);
  }`;

const QUAD_VERT = /* glsl */ `
  varying vec2 vUv;
  void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`;

// Path length at uv; a pixel with unequal entry/exit counts takes the mean of valid 4-neighbors.
const PATH_LENGTH_GLSL = /* glsl */ `
  float rawPath(sampler2D tex, vec2 uv, out bool ok) {
    vec4 a = texture2D(tex, uv);
    ok = abs(a.b - a.a) < 0.5;
    return a.r - a.g;
  }
  float pathLength(sampler2D tex, vec2 uv, vec2 texel) {
    bool ok;
    float t = rawPath(tex, uv, ok);
    if (ok) return t;
    float sum = 0.0, n = 0.0;
    vec2 offs[4] = vec2[4](vec2(1, 0), vec2(-1, 0), vec2(0, 1), vec2(0, -1));
    for (int k = 0; k < 4; k++) {
      float v = rawPath(tex, uv + offs[k] * texel, ok);
      if (ok) { sum += v; n += 1.0; }
    }
    return n > 0.0 ? sum / n : 0.0;
  }`;

const COMPOSITE_FRAG = /* glsl */ `
  uniform sampler2D uVessel;
  uniform sampler2D uBone;
  uniform sampler2D uSoft;
  uniform sampler2D uDevice;
  uniform vec2 uTexel;
  uniform float uKVessel;
  uniform float uKBone;
  uniform float uKSoft;
  uniform float uKDevice;
  uniform float uBackground;
  uniform float uNoise;
  uniform float uSeed;
  varying vec2 vUv;
  float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233)) + uSeed) * 43758.5453); }
  ${PATH_LENGTH_GLSL}
  void main() {
    // slight blur: 3x3 binomial kernel on (repaired) path length
    vec2 t = vec2(0.0);
    float w[3] = float[3](1.0, 2.0, 1.0);
    for (int i = -1; i <= 1; i++)
      for (int j = -1; j <= 1; j++) {
        vec2 uv = vUv + vec2(float(i), float(j)) * uTexel;
        t += w[i + 1] * w[j + 1] * vec2(pathLength(uVessel, uv, uTexel), pathLength(uBone, uv, uTexel));
      }
    t /= 16.0;
    float s = uKSoft > 0.0 ? max(pathLength(uSoft, vUv, uTexel), 0.0) : 0.0;
    float dv = uKDevice > 0.0 ? max(pathLength(uDevice, vUv, uTexel), 0.0) : 0.0;
    float I = uBackground * exp(-uKVessel * max(t.x, 0.0) - uKBone * max(t.y, 0.0) - uKSoft * s - uKDevice * dv);
    I += uNoise * (hash(gl_FragCoord.xy) - 0.5);
    gl_FragColor = vec4(vec3(clamp(I, 0.0, 1.0)), 1.0);
  }`;

export interface AngioMeshes {
  left: THREE.BufferGeometry;
  right: THREE.BufferGeometry;
  bone: THREE.BufferGeometry | null;
  /** non-expert extension (right tree), rendered only with the RCA and only when its toggle is on */
  extension: THREE.BufferGeometry | null;
  /** optional faint soft-tissue channel (atlas X-ray: the heart silhouette); attenuation params.kSoft per mm, 0 = off */
  soft?: THREE.BufferGeometry | null;
}

export interface AngioOptions {
  /** GLSL defining vec3 cptBeat(vec3) + its uniforms: the 3D heart's motion field, applied to vessel/soft/device while on */
  field?: { glsl: string; uniforms: Record<string, THREE.IUniform> };
}

export class AngioRenderer {
  readonly px: number;
  readonly vesselRT: THREE.WebGLRenderTarget;
  readonly boneRT: THREE.WebGLRenderTarget;
  readonly softRT: THREE.WebGLRenderTarget;
  readonly deviceRT: THREE.WebGLRenderTarget;
  readonly angioRT: THREE.WebGLRenderTarget;
  readonly floatPrecision: "float" | "half";
  /** contrast fill window (mm along the tree): fragments with _s outside [y, x] are dropped; default: everything */
  readonly fill = { value: new THREE.Vector2(1e9, -1e9) };
  /** 1 = apply the motion field (cine); 0 = rest geometry (the validated static frame) */
  readonly fieldOn = { value: 0 };
  private readonly vesselScene = new THREE.Scene();
  private readonly boneScene = new THREE.Scene();
  private readonly softScene = new THREE.Scene();
  private readonly deviceScene = new THREE.Scene();
  private puff: THREE.Mesh | null = null;
  private readonly camera = new THREE.Camera();
  private readonly meshes: Record<"left" | "right" | "bone" | "extension" | "soft", THREE.Mesh | null>;
  private readonly composite: THREE.ShaderMaterial;
  private readonly compositeScene = new THREE.Scene();
  private readonly quadCamera = new THREE.Camera();
  params = { kVessel: 0.35, kBone: 0.012, kSoft: 0, kDevice: 0, background: 0.78, noise: 0.035, showBone: true, showExtension: false };

  constructor(private readonly renderer: THREE.WebGLRenderer, geoms: AngioMeshes, px = 512, private readonly opts: AngioOptions = {}) {
    this.px = px;
    const gl = renderer.getContext() as WebGL2RenderingContext;
    const floatBlend = !!gl.getExtension("EXT_float_blend") && !!gl.getExtension("EXT_color_buffer_float");
    this.floatPrecision = floatBlend ? "float" : "half";
    // nearest filtering: entry/exit counts must never be interpolated between pixels
    const accum = () => new THREE.WebGLRenderTarget(px, px, {
      type: floatBlend ? THREE.FloatType : THREE.HalfFloatType, format: THREE.RGBAFormat,
      minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, depthBuffer: false,
    });
    this.vesselRT = accum();
    this.boneRT = accum();
    this.softRT = accum();
    this.deviceRT = accum();
    this.angioRT = new THREE.WebGLRenderTarget(px, px, {
      minFilter: THREE.LinearMipmapLinearFilter, magFilter: THREE.LinearFilter, depthBuffer: false, generateMipmaps: true,
      anisotropy: Math.min(8, renderer.capabilities.getMaxAnisotropy()),
    });
    this.camera.matrixAutoUpdate = false;
    this.camera.matrixWorldAutoUpdate = false;
    this.meshes = {
      left: this.mk(geoms.left, this.vesselScene, true),
      right: this.mk(geoms.right, this.vesselScene, true),
      bone: this.mk(geoms.bone, this.boneScene, false),
      extension: this.mk(geoms.extension, this.vesselScene, true),
      soft: this.mk(geoms.soft ?? null, this.softScene, true),
    };

    this.composite = new THREE.ShaderMaterial({
      vertexShader: QUAD_VERT, fragmentShader: COMPOSITE_FRAG, depthTest: false, depthWrite: false,
      uniforms: {
        uVessel: { value: this.vesselRT.texture }, uBone: { value: this.boneRT.texture }, uSoft: { value: this.softRT.texture },
        uDevice: { value: this.deviceRT.texture },
        uTexel: { value: new THREE.Vector2(1 / px, 1 / px) },
        uKVessel: { value: 0 }, uKBone: { value: 0 }, uKSoft: { value: 0 }, uKDevice: { value: 0 },
        uBackground: { value: 0 }, uNoise: { value: 0 }, uSeed: { value: 0 },
      },
    });
    const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.composite);
    quad.frustumCulled = false;
    this.compositeScene.add(quad);
  }

  /** A path-length mesh: non-indexed with per-face normals from the (outward) winding. `field`: may follow the motion field. */
  private mk(g: THREE.BufferGeometry | null, scene: THREE.Scene, field: boolean, weight = 1): THREE.Mesh | null {
    if (!g) return null;
    const flat = g.index ? g.toNonIndexed() : g.clone();
    if (flat.getAttribute("position")) {
      flat.deleteAttribute("normal");
      flat.computeVertexNormals(); // non-indexed -> per-face normals from (outward) winding
    }
    const f = field && this.opts.field ? this.opts.field : null;
    const fill = !!flat.getAttribute("_s");
    const m = new THREE.Mesh(flat, new THREE.ShaderMaterial({
      vertexShader: THICKNESS_VERT(f ? f.glsl : "", fill), fragmentShader: THICKNESS_FRAG(fill),
      uniforms: { uSource: { value: new THREE.Vector3() }, uSod: { value: 750 }, uWeight: { value: weight }, uFill: this.fill,
        uFieldOn: this.fieldOn, ...(f ? f.uniforms : {}) },
      side: THREE.DoubleSide, depthTest: false, depthWrite: false, transparent: true,
      blending: THREE.CustomBlending, blendEquation: THREE.AddEquation,
      blendSrc: THREE.OneFactor, blendDst: THREE.OneFactor,
      blendEquationAlpha: THREE.AddEquation, blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneFactor,
    }));
    m.frustumCulled = false;
    scene.add(m);
    return m;
  }

  /** Replace the radiopaque devices (catheter, guidewire): closed meshes, each with its own weight on params.kDevice.
   *  Called every frame while the catheter moves: the meshes and their shader materials are REUSED, only geometry is swapped. */
  setDevices(list: { geometry: THREE.BufferGeometry; weight: number }[]) {
    const ms = this.deviceScene.children as THREE.Mesh[];
    list.forEach((d, i) => {
      if (i >= ms.length) { this.mk(d.geometry, this.deviceScene, true, d.weight); return; }
      const m = ms[i];
      m.geometry.dispose();
      const flat = d.geometry.index ? d.geometry.toNonIndexed() : d.geometry.clone();
      flat.deleteAttribute("normal");
      flat.computeVertexNormals();
      m.geometry = flat;
      (m.material as THREE.ShaderMaterial).uniforms.uWeight.value = d.weight;
      m.visible = true;
    });
    for (let i = list.length; i < ms.length; i++) ms[i].visible = false;
  }

  /** Devices whose geometry the CALLER owns and rewrites in place (non-indexed, outward normals): no clone, no per-frame
   *  allocation (D60). Visibility per device with setDeviceVisible. */
  setDeviceGeometries(list: { geometry: THREE.BufferGeometry; weight: number }[]) {
    for (const c of [...this.deviceScene.children]) this.deviceScene.remove(c);
    for (const d of list) {
      const m = this.mk(new THREE.BufferGeometry(), this.deviceScene, true, d.weight)!;
      m.geometry.dispose();
      m.geometry = d.geometry;
      m.visible = false;
    }
  }
  setDeviceVisible(on: boolean[]) {
    (this.deviceScene.children as THREE.Mesh[]).forEach((m, i) => (m.visible = !!on[i]));
  }

  /** Contrast reflux puff: a closed sphere in the VESSEL channel (same contrast), at `center`, radius r (0 = none). */
  setPuff(center: THREE.Vector3 | null, r: number) {
    if (!this.puff) {
      this.puff = this.mk(new THREE.IcosahedronGeometry(1, 3), this.vesselScene, true);
      this.puff!.matrixAutoUpdate = false;
    }
    const on = !!center && r > 0.05;
    this.puff!.userData.on = on;
    if (on) { this.puff!.matrix.makeScale(r, r, r).setPosition(center!); this.puff!.matrixWorld.copy(this.puff!.matrix); }
  }

  render(carm: CArm, detectorMm: number, injected: "left" | "right", seed = 0) {
    const P = new THREE.Matrix4().fromArray(carm.clipMatrix(detectorMm));
    this.camera.projectionMatrix.copy(P);
    this.camera.projectionMatrixInverse.copy(P).invert();
    for (const [k, m] of Object.entries(this.meshes)) {
      if (!m) continue;
      m.visible =
        k === "bone" ? this.params.showBone
        : k === "extension" ? this.params.showExtension && injected === "right"
        : k === "soft" ? this.params.kSoft > 0
        : k === injected;
      const u = (m.material as THREE.ShaderMaterial).uniforms;
      u.uSource.value.set(...carm.source);
      u.uSod.value = carm.sod;
    }
    const extra = [...this.deviceScene.children, ...(this.puff ? [this.puff] : [])] as THREE.Mesh[];
    for (const m of extra) {
      const u = (m.material as THREE.ShaderMaterial).uniforms;
      u.uSource.value.set(...carm.source);
      u.uSod.value = carm.sod;
    }
    if (this.puff) this.puff.visible = !!this.puff.userData.on;
    const r = this.renderer;
    const prevTarget = r.getRenderTarget();
    const prevClear = r.getClearColor(new THREE.Color());
    const prevAlpha = r.getClearAlpha();
    r.setClearColor(0x000000, 0);
    const passes = [[this.vesselRT, this.vesselScene], [this.boneRT, this.boneScene]] as [THREE.WebGLRenderTarget, THREE.Scene][];
    if (this.meshes.soft && this.params.kSoft > 0) passes.push([this.softRT, this.softScene]);
    const devices = this.deviceScene.children.some((c) => c.visible) && this.params.kDevice > 0;
    if (devices) passes.push([this.deviceRT, this.deviceScene]);
    for (const [rt, scene] of passes) {
      r.setRenderTarget(rt);
      r.clear();
      r.render(scene, this.camera);
    }

    const u = this.composite.uniforms;
    u.uKVessel.value = this.params.kVessel;
    u.uKBone.value = this.params.showBone ? this.params.kBone : 0;
    u.uKSoft.value = this.meshes.soft ? this.params.kSoft : 0;
    u.uKDevice.value = devices ? this.params.kDevice : 0;
    u.uBackground.value = this.params.background;
    u.uNoise.value = this.params.noise;
    u.uSeed.value = seed;
    r.setRenderTarget(this.angioRT);
    r.render(this.compositeScene, this.quadCamera);
    r.setRenderTarget(prevTarget);
    r.setClearColor(prevClear, prevAlpha);
  }

  /** Displayed angiogram (RGBA8) of the last render, row 0 = TOP of the screen (+v). Converting from GL's bottom-up
   *  rows is the standard raster mapping (CONVENTIONS 4), not a mirror. */
  readImage(): Uint8ClampedArray<ArrayBuffer> {
    const px = this.px;
    const raw = new Uint8Array(px * px * 4);
    this.renderer.readRenderTargetPixels(this.angioRT, 0, 0, px, px, raw);
    const out = new Uint8ClampedArray(px * px * 4);
    for (let glRow = 0; glRow < px; glRow++) out.set(raw.subarray(glRow * px * 4, (glRow + 1) * px * 4), (px - 1 - glRow) * px * 4);
    return out;
  }

  /** Vessel path length (mm), row 0 = TOP (+v), same repair rule as the shader. For tests/debugging. */
  readThickness(): { thickness: Float32Array; repaired: number; oddCrossings: number; signMismatch: number } {
    const px = this.px;
    const raw = this.floatPrecision === "float" ? new Float32Array(px * px * 4) : new Uint16Array(px * px * 4);
    this.renderer.readRenderTargetPixels(this.vesselRT, 0, 0, px, px, raw);
    const f = this.floatPrecision === "float" ? (x: number) => x : THREE.DataUtils.fromHalfFloat;
    const at = (row: number, col: number) => {
      const glRow = px - 1 - row; // GL rows start at the bottom (NDC y = -1 = -v)
      const i = (glRow * px + col) * 4;
      const nExit = f(raw[i + 2]), nEntry = f(raw[i + 3]);
      return { t: f(raw[i]) - f(raw[i + 1]), ok: Math.abs(nExit - nEntry) < 0.5, odd: Math.round(nExit + nEntry) % 2 === 1 };
    };
    const out = new Float32Array(px * px);
    let repaired = 0, oddCrossings = 0, signMismatch = 0;
    for (let row = 0; row < px; row++)
      for (let col = 0; col < px; col++) {
        const p = at(row, col);
        if (p.ok) { out[row * px + col] = p.t; continue; }
        repaired++;
        if (p.odd) oddCrossings++; else signMismatch++;
        let sum = 0, n = 0;
        for (const [dr, dc] of [[0, 1], [0, -1], [1, 0], [-1, 0]]) {
          const r2 = row + dr, c2 = col + dc;
          if (r2 < 0 || c2 < 0 || r2 >= px || c2 >= px) continue;
          const q = at(r2, c2);
          if (q.ok) { sum += q.t; n++; }
        }
        out[row * px + col] = n ? sum / n : 0;
      }
    return { thickness: out, repaired, oddCrossings, signMismatch };
  }
}
