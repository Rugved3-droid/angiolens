// X-RAY SHADOW MODE (v1.1, feature flag "shadow"): a point light at the X-ray source casts the injected coronary tree's shadow
// onto the detector, live with the C-arm, with optional streaming rays from the source past the vessels to the detector.
//
// Why it is the same picture as the X-ray: a point source and an opaque body give a CENTRAL projection onto the receiving plane,
// exactly the engine's geometry (CArm: rays from the source S through p to the plane at SID). The shadow is the silhouette
// (where the path length is > 0), so it matches the engine's vessel mask, not its grey levels.
//   - light: a spot light (a point light with a cone) at S, aimed at the detector centre; the cone just covers the detector,
//     so a 4096 shadow map gives ~0.09 mm per texel at the detector (an image pixel is 0.49 mm).
//   - casters: the injected tree's X-ray solid (the same mesh the engine renders), static (the engine's static frame).
//   - receiver: a glowing translucent screen in the EXACT detector plane (the validated geometry, displayed as validated).
//     In shadow mode the detector housing turns to glass and its two faces give way, so the screen is seen from both sides
//     like a shadow-puppet screen; from outside the detector it is oriented exactly like the angiogram (right = u, up = v).
//     The screen is a lightbox (unlit glow) under a ShadowMaterial overlay (the shadow term only, either side).
// Nothing here touches the projection math or the X-ray renderer: it is a separate scene drawn after the lab, depth-tested
// against it (the patient and the hardware still occlude it).
import * as THREE from "three";
import type { CArm, Vec3 } from "./geometry";

const MAP = 4096;

const v3 = (a: Vec3) => new THREE.Vector3(a[0], a[1], a[2]);

export class ShadowMode {
  on = false;
  rays = false;
  readonly scene = new THREE.Scene();
  private readonly light: THREE.SpotLight;
  private readonly receiver: THREE.Group;
  private readonly overlay: THREE.Mesh;
  private readonly overlayMat: THREE.ShadowMaterial;
  private readonly casters: Record<"left" | "right", THREE.Mesh>;
  private readonly rayLines: THREE.LineSegments;
  private readonly rayMat: THREE.ShaderMaterial;
  private carm: CArm | null = null;
  private tree: "left" | "right" = "left";

  constructor(private readonly renderer: THREE.WebGLRenderer, trees: Record<"left" | "right", THREE.BufferGeometry>,
    private readonly detectorMm: number) {
    renderer.shadowMap.enabled = true;               // only lights with castShadow use it: the lab's own scene has none
    renderer.shadowMap.type = THREE.PCFShadowMap;
    this.light = new THREE.SpotLight("#e6f2ff", 3.2, 0, 0.2, 0, 0);
    this.light.castShadow = true;
    this.light.shadow.mapSize.set(MAP, MAP);
    this.light.shadow.bias = 0;
    this.light.shadow.normalBias = 0;
    this.light.shadow.autoUpdate = false;              // the casters are static: redraw the map only when the pose or tree changes
    this.scene.add(this.light, this.light.target);
    this.scene.add(new THREE.AmbientLight("#20304a", 0.6));
    const hidden = new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: false });
    this.casters = {
      left: new THREE.Mesh(trees.left, hidden),
      right: new THREE.Mesh(trees.right, hidden),
    };
    for (const m of Object.values(this.casters)) { m.castShadow = true; m.frustumCulled = false; this.scene.add(m); }
    const plane = new THREE.PlaneGeometry(detectorMm, detectorMm);
    const glow = new THREE.Mesh(plane, new THREE.MeshBasicMaterial({ color: "#dce8f8", side: THREE.DoubleSide }));
    this.overlayMat = new THREE.ShadowMaterial({ color: "#0b1626", opacity: 0.92, side: THREE.DoubleSide,
      polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -2 });
    this.overlay = new THREE.Mesh(plane, this.overlayMat);
    this.overlay.receiveShadow = true;
    this.overlay.renderOrder = 1;
    this.receiver = new THREE.Group();
    this.receiver.add(glow, this.overlay);
    this.receiver.matrixAutoUpdate = false;
    this.scene.add(this.receiver);
    // streaming rays: source -> vessel point (bright, flowing), vessel point -> detector (faint: the vessel absorbs it)
    this.rayMat = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      uniforms: { uTime: { value: 0 } },
      vertexShader: /* glsl */ `attribute float aDist; attribute float aPart; varying float vDist; varying float vPart;
        void main(){ vDist = aDist; vPart = aPart; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: /* glsl */ `uniform float uTime; varying float vDist; varying float vPart;
        void main(){
          float pulse = smoothstep(0.75, 1.0, fract((vDist - uTime * 420.0) / 140.0));
          float a = vPart < 0.5 ? 0.16 + 0.55 * pulse : 0.06 + 0.12 * pulse;
          gl_FragColor = vec4(vec3(0.62, 0.86, 1.0) * a, a);
        }`,
    });
    this.rayLines = new THREE.LineSegments(new THREE.BufferGeometry(), this.rayMat);
    this.rayLines.frustumCulled = false;
    this.scene.add(this.rayLines);
    this.rayPts = { left: samplePoints(trees.left, 40), right: samplePoints(trees.right, 40) };
  }
  private readonly rayPts: Record<"left" | "right", THREE.Vector3[]>;

  /** Place everything for this C-arm pose and injected tree (cheap when nothing changed). */
  update(carm: CArm, tree: "left" | "right") {
    if (carm === this.carm && tree === this.tree) return;
    this.carm = carm; this.tree = tree;
    const S = v3(carm.source), C = v3(carm.detectorCenter), d = v3(carm.d);
    this.light.position.copy(S);
    this.light.target.position.copy(C);
    this.light.target.updateMatrixWorld();
    const half = this.detectorMm / 2;
    this.light.angle = Math.atan((half * Math.SQRT2 + 6) / carm.sid);
    this.light.shadow.camera.near = carm.sid * 0.3;
    this.light.shadow.camera.far = carm.sid + 20;
    this.light.shadow.camera.updateProjectionMatrix();
    this.light.shadow.needsUpdate = true;
    // receiver: local x = u, y = v, z = d (u x v = d: a proper rotation), in the detector plane itself
    const m = new THREE.Matrix4().makeBasis(v3(carm.u), v3(carm.v), d);
    m.setPosition(C);
    this.receiver.matrix.copy(m);
    this.receiver.matrixWorldNeedsUpdate = true;
    this.casters.left.visible = tree === "left";
    this.casters.right.visible = tree === "right";
    // rays: S -> P (part 0) and P -> the detector plane (part 1); aDist = mm from the source (for the flow)
    const pos: number[] = [], dist: number[] = [], part: number[] = [];
    for (const P of this.rayPts[tree]) {
      const depth = P.clone().sub(S).dot(d);
      const Q = S.clone().add(P.clone().sub(S).multiplyScalar(carm.sid / depth));   // CArm.detectorHit
      const dp = P.distanceTo(S), dq = Q.distanceTo(S);
      pos.push(S.x, S.y, S.z, P.x, P.y, P.z, P.x, P.y, P.z, Q.x, Q.y, Q.z);
      dist.push(0, dp, dp, dq);
      part.push(0, 0, 1, 1);
    }
    const g = this.rayLines.geometry;
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute("aDist", new THREE.Float32BufferAttribute(dist, 1));
    g.setAttribute("aPart", new THREE.Float32BufferAttribute(part, 1));
  }

  /** Draw over the frame already rendered with `camera` (depth kept: the lab occludes the shadow where it should). */
  render(camera: THREE.Camera, timeS: number) {
    if (!this.on) return;
    this.rayLines.visible = this.rays;
    this.rayMat.uniforms.uTime.value = timeS;
    const ac = this.renderer.autoClear;
    this.renderer.autoClear = false;
    this.renderer.render(this.scene, camera);
    this.renderer.autoClear = ac;
  }

  /**
   * Validation: the displayed shadow screen seen from behind the detector (screen right = u, up = v, as the engine's
   * image), as a px x px mask, row 0 = top (1 = shadow). The overlay alone (the shadow term), on black.
   */
  shadowMask(carm: CArm, tree: "left" | "right", px: number): Uint8Array {
    this.update(carm, tree);
    const half = this.detectorMm / 2;
    const cam = new THREE.OrthographicCamera(-half, half, half, -half, 1, 100);
    const C = v3(carm.detectorCenter), d = v3(carm.d);
    cam.position.copy(C).addScaledVector(d, 20);           // behind the detector, looking back toward the source
    cam.up.copy(v3(carm.v));
    cam.lookAt(C);
    cam.updateMatrixWorld();
    const sm = new THREE.ShadowMaterial({ color: "#ffffff", opacity: 1, side: THREE.DoubleSide });
    const glow = this.receiver.children[0];
    glow.visible = false;
    this.overlay.material = sm;
    const rt = new THREE.WebGLRenderTarget(px, px);
    const prevBg = this.scene.background;
    this.scene.background = new THREE.Color("#000000");
    const ray = this.rayLines.visible;
    this.rayLines.visible = false;
    this.renderer.setRenderTarget(rt);
    this.renderer.clear();
    this.renderer.render(this.scene, cam);
    const buf = new Uint8Array(px * px * 4);
    this.renderer.readRenderTargetPixels(rt, 0, 0, px, px, buf);
    this.renderer.setRenderTarget(null);
    this.scene.background = prevBg;
    this.overlay.material = this.overlayMat;
    glow.visible = true;
    this.rayLines.visible = ray;
    rt.dispose(); sm.dispose();
    const out = new Uint8Array(px * px);
    for (let r = 0; r < px; r++)                           // WebGL rows start at the bottom: row 0 = top here
      for (let c = 0; c < px; c++) out[r * px + c] = buf[((px - 1 - r) * px + c) * 4] > 127 ? 1 : 0;
    return out;
  }
}

/** Up to n surface points spread over the tree (farthest-point sampling of the mesh vertices). */
function samplePoints(g: THREE.BufferGeometry, n: number): THREE.Vector3[] {
  const p = g.getAttribute("position");
  const step = Math.max(1, Math.floor(p.count / 3000));
  const pool: THREE.Vector3[] = [];
  for (let i = 0; i < p.count; i += step) pool.push(new THREE.Vector3().fromBufferAttribute(p, i));
  const out = [pool[0]];
  const dmin = pool.map((q) => q.distanceToSquared(pool[0]));
  while (out.length < n && out.length < pool.length) {
    let k = 0;
    for (let i = 1; i < pool.length; i++) if (dmin[i] > dmin[k]) k = i;
    out.push(pool[k]);
    for (let i = 0; i < pool.length; i++) dmin[i] = Math.min(dmin[i], pool[i].distanceToSquared(pool[k]));
  }
  return out;
}
