// HERO scene: an explanatory, illustration-style view of the same geometry.
// Everything lives in the patient's LPS frame (mm). The patient is supine, so the room's "up" (toward the
// ceiling) is -y (anterior); the floor is toward +y. The C-arm, beam and detector come from the same CArm as
// the X-ray rendering, so nothing here can drift from the projection math.
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import type { CaseData } from "./caseData";
import type { CArm, Vec3 } from "./geometry";

const v3 = (p: Vec3) => new THREE.Vector3(p[0], p[1], p[2]);
const ROOM_UP = new THREE.Vector3(0, -1, 0); // anterior = toward the ceiling for a supine patient

export interface HeroAssets {
  heart: THREE.BufferGeometry | null;
  aorta: THREE.BufferGeometry | null;
  veins: THREE.BufferGeometry | null;
  body: THREE.BufferGeometry | null;
}

export type HeroView = "room" | "heart" | "beam" | "split";

/** Fresnel "glass" skin: nearly clear when seen face-on, glowing at grazing angles; gentle breathing swell. */
function glassSkinMaterial(heartZ: number) {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: THREE.FrontSide,
    uniforms: {
      uTime: { value: 0 },
      uHeartZ: { value: heartZ },
      uEdge: { value: new THREE.Color("#bfe3ff") },
      uBody: { value: new THREE.Color("#d9ecff") },
    },
    vertexShader: /* glsl */ `
      uniform float uTime;
      uniform float uHeartZ;
      varying vec3 vN;
      varying vec3 vV;
      void main() {
        // breathing: ~3 mm swell of the chest/upper abdomen, 15 breaths per minute
        float w = exp(-pow((position.z - (uHeartZ - 60.0)) / 170.0, 2.0));
        float breath = 0.5 - 0.5 * cos(uTime * 6.2831853 / 4.0);
        vec3 p = position + normal * (3.0 * w * breath);
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        vN = normalize(normalMatrix * normal);
        vV = normalize(-mv.xyz);
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */ `
      uniform vec3 uEdge;
      uniform vec3 uBody;
      varying vec3 vN;
      varying vec3 vV;
      void main() {
        float f = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), 2.6);
        gl_FragColor = vec4(mix(uBody, uEdge, f), 0.035 + 0.55 * f);
      }`,
  });
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

export class HeroScene {
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(32, 1, 10, 20000);
  controls: OrbitControls;
  private readonly skin: THREE.ShaderMaterial | null = null;
  private readonly carmRig = new THREE.Group(); // oriented in the beam frame (u, v, d) at the isocenter
  private readonly detectorScreen: THREE.Mesh;
  private readonly beam: THREE.Mesh;
  private readonly beamEdges: THREE.LineSegments;
  private readonly arc: THREE.Mesh;
  private readonly hub: THREE.Mesh;
  private readonly standArm: THREE.Mesh;
  private readonly standPivot: THREE.Vector3;
  private readonly table = new THREE.Group();
  private view: HeroView = "room";
  private readonly coronaries: Record<"left" | "right", THREE.Mesh[]> = { left: [], right: [] };
  private carm: CArm | null = null;
  private readonly heartCentroid: THREE.Vector3;
  readonly tableTopY: number;
  readonly floorY: number;
  private t0 = performance.now();

  constructor(dom: HTMLElement, renderer: THREE.WebGLRenderer, data: CaseData, assets: HeroAssets, angioTexture: THREE.Texture) {
    const iso = v3(data.isocenter);
    this.scene.background = new THREE.Color("#0e1117");
    const pmrem = new THREE.PMREMGenerator(renderer);
    this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    this.camera.up.copy(ROOM_UP);
    this.controls = new OrbitControls(this.camera, dom);
    this.controls.enableDamping = true;
    this.controls.target.copy(iso);

    // lights: soft key from the ceiling/front-left, cool rim from behind, warm fill
    const key = new THREE.DirectionalLight("#fff4ea", 2.2);
    key.position.copy(iso).add(new THREE.Vector3(600, -1400, 900));
    const rim = new THREE.DirectionalLight("#9cc8ff", 1.4);
    rim.position.copy(iso).add(new THREE.Vector3(-900, 400, -700));
    const fill = new THREE.HemisphereLight("#ffe9dc", "#1a1f2a", 0.6);
    fill.position.copy(ROOM_UP);
    this.scene.add(key, rim, fill);

    // ---- anatomy from THIS patient's CT (LPS, verbatim) ----
    const anatomy = new THREE.Group();
    const myocardium = new THREE.MeshPhysicalMaterial({
      color: "#7a2e26", roughness: 0.6, metalness: 0, sheen: 0.45, sheenColor: new THREE.Color("#e8826c"),
      sheenRoughness: 0.55, clearcoat: 0.12, clearcoatRoughness: 0.5,
    });
    const aortaMat = new THREE.MeshPhysicalMaterial({
      color: "#e9c9b6", roughness: 0.45, sheen: 0.4, sheenColor: new THREE.Color("#fff0e6"), clearcoat: 0.2,
    });
    const veinMat = new THREE.MeshPhysicalMaterial({ color: "#5d6fae", roughness: 0.5, sheen: 0.3, sheenColor: new THREE.Color("#b9c6ff") });
    const coronary = new THREE.MeshPhysicalMaterial({
      color: "#ff2a2a", emissive: "#7a0000", emissiveIntensity: 0.8, roughness: 0.2, clearcoat: 1, clearcoatRoughness: 0.08,
    });
    // "always readable": the parts of the coronaries hidden behind the heart are drawn as a faint red ghost
    const coronaryGhost = new THREE.MeshBasicMaterial({
      color: "#ff3030", transparent: true, opacity: 0.38, depthWrite: false, depthFunc: THREE.GreaterDepth,
    });
    const addMesh = (g: THREE.BufferGeometry | null, mat: THREE.Material, order = 0) => {
      if (!g) return null;
      const geom = g.clone();
      if (!geom.getAttribute("normal")) geom.computeVertexNormals();
      const m = new THREE.Mesh(geom, mat);
      m.renderOrder = order;
      anatomy.add(m);
      return m;
    };
    addMesh(assets.heart, myocardium);
    addMesh(assets.aorta, aortaMat);
    addMesh(assets.veins, veinMat);
    for (const t of ["left", "right"] as const) {
      this.coronaries[t] = [addMesh(data.lumen[t], coronary.clone(), 1)!, addMesh(data.lumen[t], coronaryGhost.clone(), 2)!];
    }
    this.scene.add(anatomy);
    this.heartCentroid = assets.heart
      ? (() => { assets.heart!.computeBoundingBox(); return assets.heart!.boundingBox!.getCenter(new THREE.Vector3()); })()
      : iso.clone();

    // ---- patient body: CC0 MakeHuman mesh, approximate fit (see body_fit.json) ----
    let bodyBack = iso.y + 120;
    let bodyZ: [number, number] = [iso.z - 1300, iso.z + 500];
    if (assets.body) {
      this.skin = glassSkinMaterial(this.heartCentroid.z);
      const body = new THREE.Mesh(assets.body, this.skin);
      body.renderOrder = 5;
      this.scene.add(body);
      assets.body.computeBoundingBox();
      const bb = assets.body.boundingBox!;
      bodyBack = bb.max.y;
      bodyZ = [bb.min.z, bb.max.z];
    }

    // ---- cath table (patient lies on it: table top at the body's most posterior point) ----
    this.tableTopY = bodyBack + 2;
    this.floorY = this.tableTopY + 950;
    const tableMat = new THREE.MeshPhysicalMaterial({ color: "#d9dde3", roughness: 0.35, metalness: 0.1, clearcoat: 0.6 });
    const len = bodyZ[1] - bodyZ[0] + 500;
    const top = new THREE.Mesh(roundedBox(520, 50, len, 18), tableMat);
    top.position.set(0, this.tableTopY + 25, (bodyZ[0] + bodyZ[1]) / 2 - 150);
    const pad = new THREE.Mesh(roundedBox(480, 30, len - 80, 14),
      new THREE.MeshPhysicalMaterial({ color: "#2b3442", roughness: 0.8 }));
    pad.position.set(0, this.tableTopY + 2, top.position.z);
    const columnMat = new THREE.MeshPhysicalMaterial({ color: "#c3c8cf", roughness: 0.4, metalness: 0.3 });
    const column = new THREE.Mesh(roundedBox(260, this.floorY - this.tableTopY - 50, 360, 30), columnMat);
    column.position.set(0, (this.tableTopY + 50 + this.floorY) / 2, bodyZ[0] + 350);
    const floor = new THREE.Mesh(new THREE.CircleGeometry(3200, 96), new THREE.ShaderMaterial({
      transparent: true, depthWrite: false,
      uniforms: { uColor: { value: new THREE.Color("#1d2430") } },
      vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
      fragmentShader: "uniform vec3 uColor; varying vec2 vUv; void main(){ float r = length(vUv - 0.5) * 2.0; gl_FragColor = vec4(uColor, 0.9 * (1.0 - smoothstep(0.25, 1.0, r))); }",
    }));
    floor.rotation.x = Math.PI / 2; // circle in the x-z plane, normal -y (toward the ceiling, i.e. visible from the room)
    floor.position.set(iso.x, this.floorY, iso.z);
    this.table.add(top, pad, column);
    this.scene.add(this.table, floor);
    // C-arm stand at the head end: floor column + an arm to the C-arm hub (updated per pose)
    this.standPivot = new THREE.Vector3(iso.x, iso.y - 150, bodyZ[1] + 700);
    const standCol = new THREE.Mesh(roundedBox(200, this.floorY - this.standPivot.y, 200, 30),
      new THREE.MeshPhysicalMaterial({ color: "#e4e8ee", roughness: 0.35, clearcoat: 0.6 }));
    standCol.position.set(this.standPivot.x, (this.standPivot.y + this.floorY) / 2, this.standPivot.z);
    this.scene.add(standCol);

    // ---- C-arm (generic, built in code), oriented each frame from the CArm basis ----
    const shell = new THREE.MeshPhysicalMaterial({ color: "#eef1f5", roughness: 0.3, metalness: 0.05, clearcoat: 0.8, clearcoatRoughness: 0.2 });
    const dark = new THREE.MeshPhysicalMaterial({ color: "#2a313c", roughness: 0.5, metalness: 0.2 });
    // rig local frame: x = u (screen right), y = v (screen up, toward the head), z = d (toward the detector)
    const sod = 750, sid = 1000;
    const R = sid / 2 + 90; // arc radius: clears source and detector housings
    const zMid = (sid - sod) - sid / 2; // centre of S..D along d, relative to iso
    const arcGeom = new THREE.TorusGeometry(R, 42, 24, 96, Math.PI);
    // the torus half lies in its local x-y plane from +x through +y to -x; map +x -> +d (detector), -x -> -d (source),
    // +y -> +v (toward the head): local x->z, y->y
    arcGeom.applyMatrix4(new THREE.Matrix4().makeBasis(new THREE.Vector3(0, 0, 1), new THREE.Vector3(0, 1, 0), new THREE.Vector3(-1, 0, 0)));
    this.arc = new THREE.Mesh(arcGeom, shell);
    this.arc.position.set(0, 0, zMid);
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(110, 110, 160, 40), dark);
    hub.rotation.z = Math.PI / 2; // axis along local x (u)
    hub.position.set(0, R + 40, zMid);
    this.hub = hub;
    this.standArm = new THREE.Mesh(new THREE.CylinderGeometry(55, 55, 1, 32), new THREE.MeshPhysicalMaterial({ color: "#e4e8ee", roughness: 0.35, clearcoat: 0.6 }));
    this.scene.add(this.standArm);
    // detector housing (+d side) with the live angiogram on its OUTER face, seen from outside (u right, v up)
    const DET_DEPTH = 110, DET_BEVEL = 12;
    const det = new THREE.Mesh(roundedBox(330, 330, DET_DEPTH, 24), shell);
    det.position.set(0, 0, sid - sod + DET_DEPTH / 2 + DET_BEVEL);
    const W = data.detectorMm;
    this.detectorScreen = new THREE.Mesh(new THREE.PlaneGeometry(W, W),
      new THREE.MeshBasicMaterial({ map: angioTexture, toneMapped: false }));
    this.detectorScreen.position.set(0, 0, sid - sod + DET_DEPTH + 2 * DET_BEVEL + 1); // outer face; normal +d; uv: u right, v up
    const detFace = new THREE.Mesh(new THREE.PlaneGeometry(W, W), new THREE.MeshPhysicalMaterial({ color: "#1b2230", roughness: 0.2, clearcoat: 1 }));
    detFace.position.set(0, 0, sid - sod - 1);
    detFace.rotation.y = Math.PI; // faces the patient
    // X-ray tube housing (-d side)
    const tube = new THREE.Mesh(new THREE.CylinderGeometry(120, 140, 260, 40), shell);
    tube.rotation.x = Math.PI / 2;
    tube.position.set(0, 0, -sod - 110);
    const collimator = new THREE.Mesh(roundedBox(170, 170, 70, 16), dark);
    collimator.position.set(0, 0, -sod + 30);
    // translucent beam: pyramid from the focal spot to the detector corners
    const h = W / 2;
    const S = new THREE.Vector3(0, 0, -sod);
    const C = [[-h, -h], [h, -h], [h, h], [-h, h]].map(([x, y]) => new THREE.Vector3(x, y, sid - sod));
    const beamGeom = new THREE.BufferGeometry().setFromPoints([S, C[0], C[1], S, C[1], C[2], S, C[2], C[3], S, C[3], C[0]]);
    beamGeom.computeVertexNormals();
    this.beam = new THREE.Mesh(beamGeom, new THREE.MeshBasicMaterial({
      color: "#9fd4ff", transparent: true, opacity: 0.11, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending,
    }));
    this.beam.renderOrder = 6;
    this.beamEdges = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(C.flatMap((c) => [S, c])),
      new THREE.LineBasicMaterial({ color: "#bfe4ff", transparent: true, opacity: 0.35 }));
    this.carmRig.add(this.arc, hub, det, this.detectorScreen, detFace, tube, collimator, this.beam, this.beamEdges);
    this.carmRig.matrixAutoUpdate = false;
    this.scene.add(this.carmRig);
    this.setView("room");
  }

  /** The injected tree is fully opaque; the other is dimmed (it is not in the angiogram). */
  setInjected(tree: "left" | "right") {
    for (const t of ["left", "right"] as const) {
      const [solid, ghost] = this.coronaries[t];
      const m = solid.material as THREE.MeshPhysicalMaterial;
      m.transparent = t !== tree;
      m.opacity = t === tree ? 1 : 0.28;
      m.depthWrite = t === tree;
      (ghost.material as THREE.MeshBasicMaterial).opacity = t === tree ? 0.38 : 0.08;
    }
  }

  /** Place the C-arm for a pose: rig basis = (u, v, d) at the isocenter (no extra transforms). */
  setCArm(carm: CArm) {
    const m = new THREE.Matrix4().makeBasis(v3(carm.u), v3(carm.v), v3(carm.d));
    m.setPosition(v3(carm.iso));
    this.carmRig.matrix.copy(m);
    this.carmRig.matrixWorldNeedsUpdate = true;
    this.carmRig.updateMatrixWorld(true);
    const hubW = this.hub.getWorldPosition(new THREE.Vector3());
    const len = hubW.distanceTo(this.standPivot);
    this.standArm.scale.set(1, len, 1);
    this.standArm.position.copy(hubW).add(this.standPivot).multiplyScalar(0.5);
    this.standArm.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), this.standPivot.clone().sub(hubW).normalize());
    this.carm = carm;
    if (this.view === "split") this.setView("split");
  }

  /**
   * room:  the whole lab, ceiling up.
   * heart: anatomical close-up, anterior view with the head up; C-arm hidden.
   * beam:  side-on to the beam (perpendicular to d), from above the table: tube -> heart -> detector.
   * split: the heart seen from the DETECTOR side with screen-up = v, i.e. laid out like the angiogram next to it
   *        (seen from the tube side it would be mirrored). C-arm hidden.
   */
  setView(view: HeroView, carm?: CArm | null) {
    this.view = view;
    carm = carm ?? this.carm;
    const c = this.heartCentroid;
    const place = (pos: THREE.Vector3, target: THREE.Vector3, up: THREE.Vector3) => {
      this.camera.up.copy(up);
      this.camera.position.copy(pos);
      this.camera.lookAt(target);
      const el = this.controls.domElement as HTMLElement;
      this.controls.dispose();
      (this as { controls: OrbitControls }).controls = new OrbitControls(this.camera, el);
      this.controls.enableDamping = true;
      this.controls.target.copy(target);
      this.controls.update();
    };
    const hideRig = view === "heart" || view === "split";
    this.carmRig.visible = !hideRig;
    this.standArm.visible = !hideRig;
    this.table.visible = !hideRig;
    if (view === "room") place(c.clone().add(new THREE.Vector3(-2200, -1500, -1700)), c.clone().add(new THREE.Vector3(0, 250, 150)), ROOM_UP); // patient right, toward the feet: the stand stays behind
    else if (view === "heart") place(c.clone().add(new THREE.Vector3(110, -600, 70)), c, new THREE.Vector3(0, 0, 1));
    else if (view === "beam" && carm) {
      // perpendicular to the beam, on the room-up side (anterior), slightly toward the head
      let n = v3(carm.d).cross(new THREE.Vector3(0, 0, 1)).normalize();
      if (n.dot(ROOM_UP) < 0) n.negate();
      const mid = v3(carm.source).add(v3(carm.detectorCenter)).multiplyScalar(0.5);
      place(mid.clone().addScaledVector(n, 1900).addScaledVector(ROOM_UP, 500).add(new THREE.Vector3(0, 0, 300)), mid, ROOM_UP);
    } else if (view === "split" && carm) {
      place(c.clone().addScaledVector(v3(carm.d), 520), c, v3(carm.v));
    }
  }

  render(r: THREE.WebGLRenderer) {
    if (this.skin) this.skin.uniforms.uTime.value = (performance.now() - this.t0) / 1000;
    this.controls.update();
    r.render(this.scene, this.camera);
  }
}

export function captionFor(alpha: number, beta: number): string {
  const a = Math.round(alpha), b = Math.round(beta);
  const side = a === 0 ? "straight above the patient" : `toward the patient's ${a > 0 ? "left" : "right"}`;
  const tilt = b === 0 ? "" : ` and tilted toward the ${b > 0 ? "head" : "feet"}`;
  const name = a === 0 && b === 0 ? "AP" : `${a === 0 ? "AP" : `${a > 0 ? "LAO" : "RAO"} ${Math.abs(a)}`}${b === 0 ? "" : ` / ${b > 0 ? "CRAN" : "CAUD"} ${Math.abs(b)}`}`;
  return `${name}: the detector sits ${side}${tilt}; the X-rays travel from the tube, through the heart, to the detector.`;
}
