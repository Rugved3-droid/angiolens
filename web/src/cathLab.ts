// Scenes 3 and 4 (D50): the cath lab around the glass Z-Anatomy patient, and the X-ray pass.
// Same rules as hero.ts: everything is in the atlas's LPS frame (mm); the patient is supine, so the room's "up" (toward the
// ceiling) is -y (anterior). The C-arm rig is oriented every frame by the SAME CArm basis (u, v, d) that drives the angiogram,
// at the FIXED isocenter (both coronary trees' volume centroid, atlas_xray.json), so the hardware can never drift from the
// projection. The angiogram is the validated GPU path-length renderer (angio.ts) on the closed atlas meshes (D49).
// Nothing is ever mirrored or rotated for display: the detector shows the image on its OUTER face, u right / v up, exactly as
// in the hero scene, and the monitor inset blits the render target unchanged (texture (0,0) = the (-u,-v) corner).
import * as THREE from "three";
import { AngioRenderer, type AngioOptions } from "./angio";
import { CArm, type Vec3 } from "./geometry";

export const ROOM_UP = new THREE.Vector3(0, -1, 0);
const v3 = (p: Vec3) => new THREE.Vector3(p[0], p[1], p[2]);

export interface AtlasXray {
  left: THREE.BufferGeometry;
  right: THREE.BufferGeometry;
  bone: THREE.BufferGeometry;
  heart: THREE.BufferGeometry;
  isocenter: Vec3;
}

function roundedBox(w: number, h: number, d: number, r: number) {
  const s = new THREE.Shape();
  s.moveTo(-w / 2 + r, -h / 2);
  s.lineTo(w / 2 - r, -h / 2); s.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r);
  s.lineTo(w / 2, h / 2 - r); s.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2);
  s.lineTo(-w / 2 + r, h / 2); s.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r);
  s.lineTo(-w / 2, -h / 2 + r); s.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2);
  const g = new THREE.ExtrudeGeometry(s, { depth: d, bevelEnabled: true, bevelSize: r * 0.5, bevelThickness: r * 0.5, bevelSegments: 3 });
  g.translate(0, 0, -d / 2);
  return g;
}

/** Detector face: dark glass until exposed; the image builds outward from the centre (uReveal 0 -> 1). */
function detectorMaterial(map: THREE.Texture) {
  return new THREE.ShaderMaterial({
    uniforms: { uMap: { value: map }, uReveal: { value: 1 }, uOn: { value: 0 } },
    vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
    fragmentShader: /* glsl */ `
      uniform sampler2D uMap; uniform float uReveal; uniform float uOn; varying vec2 vUv;
      void main() {
        vec3 off = vec3(0.06, 0.08, 0.11);
        vec3 img = texture2D(uMap, vUv).rgb;
        float r = length(vUv - 0.5) * 1.42;
        float edge = uReveal * 1.12;
        float m = 1.0 - smoothstep(edge - 0.1, edge, r);
        float glow = exp(-pow((r - edge) / 0.025, 2.0)) * 0.45 * (1.0 - step(0.999, uReveal));
        gl_FragColor = vec4(mix(off, img, m * uOn) + glow * uOn * vec3(0.55, 0.85, 1.0), 1.0);
      }`,
  });
}

export class CathLab {
  readonly room = new THREE.Group();        // table, floor, stand column, stand arm
  readonly rig = new THREE.Group();         // the C-arm, in the beam frame (u, v, d) at the isocenter
  readonly angio: AngioRenderer;
  readonly iso: THREE.Vector3;
  readonly detectorMm = 250;
  readonly tableTopY: number;
  readonly floorY: number;
  carm: CArm;
  injected: "left" | "right" = "left";
  private readonly hub: THREE.Mesh;
  private readonly standArm: THREE.Mesh;
  private readonly standPivot: THREE.Vector3;
  private readonly det: THREE.ShaderMaterial;
  private readonly beamMat: THREE.MeshBasicMaterial;
  private readonly beamEdgeMat: THREE.LineBasicMaterial;
  private readonly beamGroup = new THREE.Group();
  private xray = 0;                          // 0 = beam off, 1 = on (smoothly)
  private xrayTarget = 0;
  private reveal = 1;
  private swing: { from: [number, number]; to: [number, number]; t0: number; ms: number; done?: () => void } | null = null;

  constructor(renderer: THREE.WebGLRenderer, xr: AtlasXray, body: THREE.Box3, field?: AngioOptions["field"]) {
    this.iso = v3(xr.isocenter);
    // field: the 3D heart's motion field (same GLSL, same uniforms), applied to the X-ray only during cine (angio.fieldOn)
    this.angio = new AngioRenderer(renderer, { left: xr.left, right: xr.right, bone: xr.bone, extension: null, soft: xr.heart }, 512,
      { field });
    this.angio.params.kSoft = 0.0035;       // the heart: a faint silhouette (~0.3 attenuation through its full depth)
    this.angio.params.kBone = 0.01;         // the skeleton: faint
    this.angio.params.kDevice = 0.3;        // catheter wall (weight 1) and guidewire (weight 5): radiopaque, not contrast
    this.carm = new CArm(0, 0, xr.isocenter);

    // ---- table and floor (the patient lies on the table: its top touches the body's most posterior point) ----
    this.tableTopY = body.max.y + 2;
    this.floorY = this.tableTopY + 950;
    const tableMat = new THREE.MeshPhysicalMaterial({ color: "#d9dde3", roughness: 0.35, metalness: 0.1, clearcoat: 0.6 });
    const len = body.max.z - body.min.z + 500;
    const zc = (body.min.z + body.max.z) / 2 - 150;
    const top = new THREE.Mesh(roundedBox(520, 50, len, 18), tableMat);
    top.position.set(0, this.tableTopY + 25, zc);
    const pad = new THREE.Mesh(roundedBox(480, 30, len - 80, 14), new THREE.MeshPhysicalMaterial({ color: "#2b3442", roughness: 0.8 }));
    pad.position.set(0, this.tableTopY + 2, zc);
    const column = new THREE.Mesh(roundedBox(260, this.floorY - this.tableTopY - 50, 360, 30),
      new THREE.MeshPhysicalMaterial({ color: "#c3c8cf", roughness: 0.4, metalness: 0.3 }));
    column.position.set(0, (this.tableTopY + 50 + this.floorY) / 2, body.min.z + 350);
    const floor = new THREE.Mesh(new THREE.CircleGeometry(3400, 96), new THREE.ShaderMaterial({
      transparent: true, depthWrite: false,
      uniforms: { uColor: { value: new THREE.Color("#1d2430") } },
      vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
      fragmentShader: "uniform vec3 uColor; varying vec2 vUv; void main(){ float r = length(vUv - 0.5) * 2.0; gl_FragColor = vec4(uColor, 0.92 * (1.0 - smoothstep(0.25, 1.0, r))); }",
    }));
    floor.rotation.x = Math.PI / 2;        // in the x-z plane, facing the ceiling (-y)
    floor.position.set(this.iso.x, this.floorY, this.iso.z - 300);
    // C-arm stand at the head end: a floor column and an arm to the C-arm hub (updated per pose)
    this.standPivot = new THREE.Vector3(this.iso.x, this.iso.y - 150, body.max.z + 700);
    const shellSatin = new THREE.MeshPhysicalMaterial({ color: "#eef1f5", roughness: 0.32, metalness: 0.05, clearcoat: 0.7, clearcoatRoughness: 0.25 });
    const standCol = new THREE.Mesh(roundedBox(220, this.floorY - this.standPivot.y, 220, 30), shellSatin);
    standCol.position.set(this.standPivot.x, (this.standPivot.y + this.floorY) / 2, this.standPivot.z);
    this.standArm = new THREE.Mesh(new THREE.CylinderGeometry(58, 58, 1, 32), shellSatin);
    this.room.add(top, pad, column, floor, standCol, this.standArm);

    // ---- C-arm (the hero scene's construction, re-skinned): rig local x = u, y = v, z = d ----
    const accent = new THREE.MeshPhysicalMaterial({ color: "#2a313c", roughness: 0.45, metalness: 0.35 });
    const blueTrim = new THREE.MeshPhysicalMaterial({ color: "#3d8bd6", roughness: 0.35, emissive: "#0b2a4a", emissiveIntensity: 0.6 });
    const sod = this.carm.sod, sid = this.carm.sid;
    const R = sid / 2 + 90;
    const zMid = (sid - sod) - sid / 2;
    const arcGeom = new THREE.TorusGeometry(R, 44, 24, 96, Math.PI);
    arcGeom.applyMatrix4(new THREE.Matrix4().makeBasis(new THREE.Vector3(0, 0, 1), new THREE.Vector3(0, 1, 0), new THREE.Vector3(-1, 0, 0)));
    const arc = new THREE.Mesh(arcGeom, shellSatin);
    arc.position.set(0, 0, zMid);
    const trimGeom = new THREE.TorusGeometry(R - 44, 6, 8, 96, Math.PI);
    trimGeom.applyMatrix4(new THREE.Matrix4().makeBasis(new THREE.Vector3(0, 0, 1), new THREE.Vector3(0, 1, 0), new THREE.Vector3(-1, 0, 0)));
    const trim = new THREE.Mesh(trimGeom, blueTrim);
    trim.position.copy(arc.position);
    this.hub = new THREE.Mesh(new THREE.CylinderGeometry(115, 115, 170, 40), accent);
    this.hub.rotation.z = Math.PI / 2;
    this.hub.position.set(0, R + 40, zMid);
    const DET_DEPTH = 110, DET_BEVEL = 12;
    const W = this.detectorMm;
    const detHouse = new THREE.Mesh(roundedBox(340, 340, DET_DEPTH, 26), shellSatin);
    detHouse.position.set(0, 0, sid - sod + DET_DEPTH / 2 + DET_BEVEL);
    this.det = detectorMaterial(this.angio.angioRT.texture);
    const detScreen = new THREE.Mesh(new THREE.PlaneGeometry(W, W), this.det);
    detScreen.position.set(0, 0, sid - sod + DET_DEPTH + 2 * DET_BEVEL + 1);    // outer face, normal +d; uv: u right, v up
    const detFace = new THREE.Mesh(new THREE.PlaneGeometry(W, W), new THREE.MeshPhysicalMaterial({ color: "#1b2230", roughness: 0.2, clearcoat: 1 }));
    detFace.position.set(0, 0, sid - sod - 1);
    detFace.rotation.y = Math.PI;                                               // faces the patient
    const tube = new THREE.Mesh(new THREE.CylinderGeometry(125, 145, 270, 40), shellSatin);
    tube.rotation.x = Math.PI / 2;
    tube.position.set(0, 0, -sod - 115);
    const collimator = new THREE.Mesh(roundedBox(175, 175, 70, 16), accent);
    collimator.position.set(0, 0, -sod + 30);
    // beam: a translucent pyramid from the focal spot to the detector corners, plus its edges
    const h = W / 2;
    const S = new THREE.Vector3(0, 0, -sod);
    const C = [[-h, -h], [h, -h], [h, h], [-h, h]].map(([x, y]) => new THREE.Vector3(x, y, sid - sod));
    const beamGeom = new THREE.BufferGeometry().setFromPoints([S, C[0], C[1], S, C[1], C[2], S, C[2], C[3], S, C[3], C[0]]);
    this.beamMat = new THREE.MeshBasicMaterial({ color: "#9fd4ff", transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false,
      blending: THREE.AdditiveBlending });
    const beam = new THREE.Mesh(beamGeom, this.beamMat);
    beam.renderOrder = 6;
    this.beamEdgeMat = new THREE.LineBasicMaterial({ color: "#c6e8ff", transparent: true, opacity: 0 });
    const edges = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(C.flatMap((c) => [S, c])), this.beamEdgeMat);
    this.beamGroup.add(beam, edges);
    this.rig.add(arc, trim, this.hub, detHouse, detScreen, detFace, tube, collimator, this.beamGroup);
    this.rig.matrixAutoUpdate = false;
    this.setPose(0, 0);
  }

  get pose(): [number, number] { return [this.carm.alphaDeg, this.carm.betaDeg]; }

  /** Place the C-arm (and, when the X-ray is on, render the angiogram) for a pose. */
  setPose(alpha: number, beta: number) {
    this.carm = new CArm(alpha, beta, [this.iso.x, this.iso.y, this.iso.z]);
    const m = new THREE.Matrix4().makeBasis(v3(this.carm.u), v3(this.carm.v), v3(this.carm.d));
    m.setPosition(v3(this.carm.iso));
    this.rig.matrix.copy(m);
    this.rig.matrixWorldNeedsUpdate = true;
    this.rig.updateMatrixWorld(true);
    const hubW = this.hub.getWorldPosition(new THREE.Vector3());
    this.standArm.scale.set(1, hubW.distanceTo(this.standPivot), 1);
    this.standArm.position.copy(hubW).add(this.standPivot).multiplyScalar(0.5);
    this.standArm.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), this.standPivot.clone().sub(hubW).normalize());
    if (this.xrayTarget > 0) this.renderImage();
  }

  renderImage() {
    this.angio.render(this.carm, this.detectorMm, this.injected, 7);
  }

  setInjected(t: "left" | "right") {
    this.injected = t;
    if (this.xrayTarget > 0) { this.renderImage(); this.reveal = 0; }
  }

  /** X-ray on/off. Turning it on renders the image and lets it build outward on the detector. */
  setXray(on: boolean, build = true) {
    this.xrayTarget = on ? 1 : 0;
    if (on) { this.renderImage(); if (build) this.reveal = 0; }
  }

  /** Smooth swing in angle space (each frame is a real CArm pose; live image while the X-ray is on). */
  swingTo(alpha: number, beta: number, ms: number, done?: () => void) {
    this.swing = { from: this.pose, to: [alpha, beta], t0: performance.now(), ms, done };
  }

  get swinging() { return this.swing !== null; }

  update(now: number, dt: number) {
    if (this.swing) {
      const s = this.swing;
      const t = Math.min(1, (now - s.t0) / s.ms);
      const e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      this.setPose(s.from[0] + (s.to[0] - s.from[0]) * e, s.from[1] + (s.to[1] - s.from[1]) * e);
      if (t >= 1) {
        this.swing = null;
        if (this.xrayTarget > 0) this.reveal = 0;       // the acquisition at the new angle builds on the detector
        s.done?.();
      }
    }
    this.xray += (this.xrayTarget - this.xray) * Math.min(1, dt * 6);
    if (this.reveal < 1) this.reveal = Math.min(1, this.reveal + dt / 1.3);
    const pulse = this.reveal < 1 ? 1 : 0.55;
    this.beamGroup.visible = this.xray > 0.01;
    this.beamMat.opacity = 0.12 * this.xray * pulse;
    this.beamEdgeMat.opacity = 0.4 * this.xray;
    this.det.uniforms.uOn.value = this.xray;
    this.det.uniforms.uReveal.value = this.swing ? 1 : this.reveal;
  }

  /** Camera poses in the room (room up = -y). */
  roomPose(heartC: THREE.Vector3) {
    // from the patient's right, toward the feet, from above: the stand stays behind the C-arm; the C-arm and chest centred
    return { pos: heartC.clone().add(new THREE.Vector3(-1900, -1350, -1450)), target: heartC.clone().add(new THREE.Vector3(0, 60, 80)), up: ROOM_UP.clone() };
  }

  operatorPose(heartC: THREE.Vector3, access: "femoral" | "radial" = "femoral") {
    // eyes ~1.65 m above the floor, at the patient's RIGHT side:
    //  femoral: level with the hip;  radial: beside the right shoulder, over the arm board, looking down the arm to the chest
    if (access === "radial") {
      const eye = new THREE.Vector3(-880, this.floorY - 1650, heartC.z + 120);
      return { pos: eye, target: heartC.clone().add(new THREE.Vector3(-170, 90, -170)), up: ROOM_UP.clone() };
    }
    const eye = new THREE.Vector3(-760, this.floorY - 1650, heartC.z - 620);
    return { pos: eye, target: heartC.clone().add(new THREE.Vector3(0, 80, 40)), up: ROOM_UP.clone() };
  }

  /** Side-on to the beam, from the room-up side: tube -> heart -> detector in one line. */
  beamPose() {
    let n = v3(this.carm.d).cross(new THREE.Vector3(0, 0, 1)).normalize();
    if (n.dot(ROOM_UP) < 0) n.negate();
    const mid = v3(this.carm.source).add(v3(this.carm.detectorCenter)).multiplyScalar(0.5);
    return { pos: mid.clone().addScaledVector(n, 2000).addScaledVector(ROOM_UP, 450).add(new THREE.Vector3(0, 0, 350)), target: mid, up: ROOM_UP.clone() };
  }

  /** The heart seen from the DETECTOR side with screen-up = v: laid out like the angiogram (screen right = u). */
  detectorSidePose(heartC: THREE.Vector3) {
    return { pos: heartC.clone().addScaledVector(v3(this.carm.d), 560), target: heartC.clone(), up: v3(this.carm.v) };
  }
}
