// Atlas scenes (the LOOK): Scene 1 = the Z-Anatomy heart close-up; Scene 2 = the same heart inside the same atlas body.
// NOT connected to the C-arm or the projection code. World = canonical LPS-oriented atlas frame in mm (+X patient left,
// +Y posterior, +Z superior); every GLB node has an identity transform and nothing is moved, mirrored or rotated here.
// The only motion is a procedural heartbeat/breathing displacement FIELD applied in the vertex shader. The same field is
// evaluated for myocardium, coronaries and veins at their rest positions, so vessels on the surface stay on the surface.
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { CathLab } from "./cathLab";
import { CathSim, type Access, type Target } from "./cath";

const params = new URLSearchParams(location.search);
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

// ---------------- renderer, camera, studio lighting ----------------
const canvas = $<HTMLCanvasElement>("c");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setClearColor(0x000000, 0);
document.body.style.background = "radial-gradient(ellipse at 50% 38%, #2a3140 0%, #141820 55%, #090b0f 100%)";

const scene = new THREE.Scene();
scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 0.55;
const camera = new THREE.PerspectiveCamera(30, 1, 5, 20000);
scene.add(camera);
// soft studio rig that travels with the camera: warm key upper-left, cool rim from behind, gentle fill
const key = new THREE.DirectionalLight("#fff1e4", 2.1); key.position.set(-0.6, 0.8, 0.9); camera.add(key); camera.add(key.target);
const rim = new THREE.DirectionalLight("#a9cbff", 1.5); rim.position.set(0.7, 0.3, -1.0); camera.add(rim); camera.add(rim.target);
const fill = new THREE.DirectionalLight("#ffd9cc", 0.45); fill.position.set(0.8, -0.4, 0.6); camera.add(fill); camera.add(fill.target);
for (const l of [key, rim, fill]) l.target.position.set(0, 0, -1);
scene.add(new THREE.HemisphereLight("#fff4ee", "#1a1e26", 0.35));
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.08;

// ---------------- the shared motion field (heartbeat + breathing) ----------------
const motion = {
  uBase: { value: new THREE.Vector3() }, uAxis: { value: new THREE.Vector3(0, 0, -1) }, uLen: { value: 80 },
  uVent: { value: 0 }, uAtr: { value: 0 }, uBreath: { value: 0 }, uHeartC: { value: new THREE.Vector3() },
  uEnv: { value: new THREE.Vector2(1e5, 1e5 + 1) },
};
// uEnv = (r0, r1): the field acts fully within r0 of the heart centre (every heart and coronary vertex lies inside r0, so the
// heart moves exactly as before) and fades to zero by r1, so the far aorta, the access routes and the limbs stay still.
const FIELD = /* glsl */ `
uniform vec3 uBase; uniform vec3 uAxis; uniform float uLen; uniform float uVent; uniform float uAtr; uniform float uBreath;
uniform vec3 uHeartC; uniform vec2 uEnv;
vec3 cptBeat0(vec3 p) {
  vec3 r = p - uBase;
  float a = dot(r, uAxis);
  float h = a / uLen;                                   // 0 at the LV base, 1 at the apex, < 0 over the atria
  float wv = smoothstep(-0.15, 0.25, h);
  float wa = 1.0 - wv;
  vec3 rad = r - uAxis * a;
  vec3 q = uBase + uAxis * a + rad * (1.0 - 0.065 * wv * uVent - 0.05 * wa * uAtr);
  q += uAxis * (5.0 * uVent * wv * (1.0 - clamp(h, 0.0, 1.0)));   // base descends toward a nearly still apex
  q += vec3(0.0, 0.0, -2.5 * uBreath);                              // the diaphragm carries the heart down on inspiration
  return q;
}
vec3 cptBeat(vec3 p) {
  return p + (cptBeat0(p) - p) * (1.0 - smoothstep(uEnv.x, uEnv.y, length(p - uHeartC)));
}`;
/** Rim light on the heart, 0 in the close-up and 1 in the chest view, so the heart separates from the ribs behind the glass. */
const rimU = { uRim: { value: 0 }, uRimColor: { value: new THREE.Color("#ffe3d8") } };
// Myocardium as tissue, not plastic (polish pass). Three terms are added to three.js's physical lighting:
//  * muscle-fibre normal detail: fine helical ridges around the LV long axis, computed from the REST position, so the
//    pattern stays on the muscle while the heart beats; value noise breaks the regularity;
//  * wrap lighting: a warm term in the terminator region, where light would scatter through tissue;
//  * a faint view-dependent warm back-scatter at grazing angles.
const TISSUE_FRAG_HEAD = /* glsl */ `
uniform vec3 uBase; uniform vec3 uAxis; varying vec3 vRest;
float cptHash(vec3 p) { return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453); }
float cptNoise(vec3 p) {
  vec3 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(cptHash(i), cptHash(i + vec3(1,0,0)), f.x), mix(cptHash(i + vec3(0,1,0)), cptHash(i + vec3(1,1,0)), f.x), f.y),
             mix(mix(cptHash(i + vec3(0,0,1)), cptHash(i + vec3(1,0,1)), f.x), mix(cptHash(i + vec3(0,1,1)), cptHash(i + vec3(1,1,1)), f.x), f.y), f.z);
}`;
const TISSUE_NORMAL = /* glsl */ `
{
  vec3 rr = vRest - uBase;
  float aa = dot(rr, uAxis);
  vec3 radial = rr - uAxis * aa;
  vec3 e1 = normalize(cross(uAxis, abs(uAxis.z) < 0.9 ? vec3(0.0, 0.0, 1.0) : vec3(1.0, 0.0, 0.0)));
  vec3 e2 = cross(uAxis, e1);
  float R = max(length(radial), 1.0);
  float theta = atan(dot(radial, e2), dot(radial, e1));
  float n = cptNoise(vRest * 0.35);
  float phase = 4.5 * (aa + 0.45 * theta * R) + 6.0 * n;           // ~1.4 mm ridges, helical, irregular
  vec3 circ = normalize(cross(uAxis, radial) + 1e-5);
  vec3 g = normalize(mat3(viewMatrix) * normalize(uAxis + 0.45 * circ));
  g = g - normal * dot(g, normal);
  float fade = 1.0 - smoothstep(0.6, 1.6, fwidth(phase));          // ridges smaller than a pixel fade out (no moire)
  normal = normalize(normal + fade * (0.075 * cos(phase) * normalize(g + 1e-5) + 0.03 * (cptNoise(vRest * 1.7) - 0.5) * g));
}`;
const TISSUE_LIGHT = /* glsl */ `
{
  vec3 L = normalize(vec3(-0.6, 0.8, 1.9));                        // the camera-carried key light, in view space
  float ndl = dot(normal, L);
  float wrap = clamp((ndl + 0.55) / 1.55, 0.0, 1.0) - clamp(ndl, 0.0, 1.0);
  float back = pow(1.0 - clamp(dot(normal, normalize(vViewPosition)), 0.0, 1.0), 2.5);   // vViewPosition: surface -> camera
  outgoingLight += diffuseColor.rgb * vec3(1.0, 0.45, 0.35) * (0.55 * wrap + 0.18 * back);
}`;
const RIM_LIGHT = /* glsl */ `
outgoingLight += uRimColor * pow(1.0 - clamp(dot(normal, normalize(vViewPosition)), 0.0, 1.0), 3.0) * 0.38 * uRim;`;
/** Scene 5 contrast window (mm along the coronary tree from the effective ostium): the SAME uniform object as the X-ray's
 *  angio.fill once the cath lab exists, so the 3D glow and the angiogram fill together. Default: no contrast. */
const fillU = { uFill: { value: new THREE.Vector2(-1e9, -1e9) } };
// contrast in 3D: the filled part glows, with a brighter band at the moving front (needs the per-vertex _s from atlas_fill.bin)
const FILL_LIGHT = /* glsl */ `
{
  float filled = step(vS, uFill.x) * step(uFill.y, vS);
  float band = uFill.x < 1e8 ? exp(-pow((vS - uFill.x) / 4.0, 2.0)) : 0.0;
  outgoingLight = mix(outgoingLight, vec3(1.0, 0.93, 0.82), 0.55 * filled) + vec3(1.0, 0.75, 0.45) * 1.6 * band;
}`;
function withBeat<T extends THREE.Material>(m: T, opts: { tissue?: boolean; fill?: boolean } = {}): T {
  m.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, motion, rimU, opts.fill ? fillU : {});
    sh.vertexShader = FIELD + "\nvarying vec3 vRest;\n" + (opts.fill ? "attribute float _s; varying float vS;\n" : "")
      + sh.vertexShader.replace("#include <begin_vertex>",
        "vec3 transformed = cptBeat(vec3(position));\n  vRest = position;" + (opts.fill ? "\n  vS = _s;" : ""));
    let f = "uniform float uRim; uniform vec3 uRimColor;\n" + (opts.tissue ? TISSUE_FRAG_HEAD : "varying vec3 vRest;") + "\n"
      + (opts.fill ? "uniform vec2 uFill; varying float vS;\n" : "") + sh.fragmentShader;
    if (opts.tissue) f = f.replace("#include <normal_fragment_maps>", "#include <normal_fragment_maps>\n" + TISSUE_NORMAL);
    f = f.replace("#include <opaque_fragment>", (opts.tissue ? TISSUE_LIGHT : "") + (opts.fill ? FILL_LIGHT : "") + RIM_LIGHT
      + "\n#include <opaque_fragment>");
    sh.fragmentShader = f;
  };
  m.customProgramCacheKey = () => (opts.tissue ? "cptBeatTissue" : opts.fill ? "cptBeatFill" : "cptBeat");
  return m;
}
/** Shared section plane for the body (skin + bones) in the axial views: keep dot(n, p) + w >= 0. */
const clipU = { value: new THREE.Vector4(0, 0, 1, 1e6) };
/** Chest-wall breathing for bones: anterior chest rises a little, the spine stays put. Plus the shared section plane. */
function withChestRise<T extends THREE.Material>(m: T): T {
  m.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, motion, { uClip: clipU });
    sh.vertexShader = "uniform float uBreath; uniform vec3 uHeartC; varying vec3 vCptW;\n" + sh.vertexShader.replace("#include <begin_vertex>", `
      vec3 transformed = vec3(position);
      float wz = exp(-pow((position.z - uHeartC.z) / 170.0, 2.0));
      float wy = smoothstep(uHeartC.y + 70.0, uHeartC.y - 30.0, position.y);
      transformed.y -= 2.5 * uBreath * wz * wy;
      vCptW = transformed;`);
    sh.fragmentShader = "uniform vec4 uClip; varying vec3 vCptW;\n" + sh.fragmentShader.replace("void main() {",
      "void main() {\n  if (dot(uClip.xyz, vCptW) + uClip.w < 0.0) discard;");
  };
  m.customProgramCacheKey = () => "cptChest";
  return m;
}

// ---------------- materials ----------------
// polish pass: myocardium muted toward brown with little specular (tissue, not plastic); coronaries brighter and more
// saturated, with a small emissive lift, so they are the first thing the eye reads; the aorta stays a softer red
const ventricleMat = withBeat(new THREE.MeshPhysicalMaterial({
  color: "#5a2c23", roughness: 0.74, specularIntensity: 0.32, sheen: 0.22, sheenColor: new THREE.Color("#c48a74"),
  sheenRoughness: 0.7,
}), { tissue: true });
const atriumMat = withBeat(new THREE.MeshPhysicalMaterial({
  color: "#7a4a3a", roughness: 0.78, specularIntensity: 0.3, sheen: 0.2, sheenColor: new THREE.Color("#d0a084"),
  sheenRoughness: 0.75,
}), { tissue: true });
const coronaryMat = withBeat(new THREE.MeshPhysicalMaterial({
  color: "#ff1418", emissive: "#a0000a", emissiveIntensity: 0.8, roughness: 0.24, clearcoat: 0.9, clearcoatRoughness: 0.12,
}));
const veinMat = withBeat(new THREE.MeshPhysicalMaterial({
  color: "#1e2c72", emissive: "#060a24", roughness: 0.36, clearcoat: 0.5, clearcoatRoughness: 0.25,
}));
// great vessels (D46), illustration convention: the aorta and its branches a softer arterial red than the coronaries (so the
// coronaries still read where they leave the aortic wall), the venae cavae blue, the pulmonary arteries a LIGHTER blue
// (standard convention; lighter than the cavae and the cardiac veins)
const aortaMat = withBeat(new THREE.MeshPhysicalMaterial({
  color: "#b9473a", roughness: 0.42, sheen: 0.35, sheenColor: new THREE.Color("#f2a08c"), sheenRoughness: 0.5,
  clearcoat: 0.45, clearcoatRoughness: 0.3,
}));
const cavaMat = withBeat(new THREE.MeshPhysicalMaterial({
  color: "#3552a6", emissive: "#070d26", roughness: 0.4, clearcoat: 0.45, clearcoatRoughness: 0.3,
}));
const pulmonaryMat = withBeat(new THREE.MeshPhysicalMaterial({
  color: "#4f80cc", emissive: "#081428", roughness: 0.5, clearcoat: 0.2, clearcoatRoughness: 0.4,
}));
const boneMat = (opacity: number) => withChestRise(new THREE.MeshStandardMaterial({
  color: "#e4dac4", roughness: 0.6, transparent: true, opacity, depthWrite: false,
}));
const boneTrunk = boneMat(0.32);
const boneLimb = boneMat(0.18);

/** The welded skin (D48): one surface; _arm/_leg are per-vertex weights from the atlas region names, used to fade the limbs. */
function glassSkin() {
  return new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, side: THREE.DoubleSide,
    uniforms: {
      ...motion, uFade: { value: 0 }, uLimbFade: { value: 1 }, uClip: clipU,
      uBody: { value: new THREE.Color("#cfe4ff") }, uEdge: { value: new THREE.Color("#8fd0ff") },
    },
    vertexShader: /* glsl */ `
      uniform float uBreath; uniform vec3 uHeartC;
      attribute float _arm; attribute float _leg;
      varying vec3 vN; varying vec3 vV; varying vec3 vW; varying float vLimb;
      void main() {
        float w = exp(-pow((position.z - (uHeartC.z - 40.0)) / 190.0, 2.0));
        vec3 p = position + normal * (3.5 * w * uBreath);
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        vW = p;
        vLimb = max(_arm, _leg);
        vN = normalize(normalMatrix * normal);
        vV = normalize(-mv.xyz);
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */ `
      uniform float uFade; uniform float uLimbFade; uniform vec4 uClip; uniform vec3 uBody; uniform vec3 uEdge;
      varying vec3 vN; varying vec3 vV; varying vec3 vW; varying float vLimb;
      void main() {
        if (dot(uClip.xyz, vW) + uClip.w < 0.0) discard;
        vec3 n = normalize(vN), v = normalize(vV);
        float f = pow(1.0 - abs(dot(n, v)), 2.4);
        vec3 l = normalize(vec3(-0.5, 0.7, 0.6));
        float spec = pow(max(dot(reflect(-l, n * sign(dot(n, v))), v), 0.0), 48.0);
        vec3 c = mix(uBody, uEdge, f) + spec * 0.35;
        gl_FragColor = vec4(c, uFade * mix(1.0, uLimbFade, vLimb) * (0.016 + 0.42 * f + 0.1 * spec));
      }`,
  });
}
const skinMat = glassSkin();
const clipPlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 1e6);

// ---------------- names ----------------
const FRIENDLY: Record<string, string> = {
  "Left coronary artery": "Left main coronary artery",
  "Anterior interventricular artery": "Left anterior descending artery",
  "Septal branches of anterior interventricular artery": "Septal branches of the LAD",
  "Circumflex artery of heart": "Left circumflex artery",
  "Right coronary artery": "Right coronary artery",
  "Right inferolateral branch of right coronary artery": "Right inferolateral branch",
  "????????": "Cardiac vein (unnamed in the atlas)",
  "Bifurcation of pulmonary trunk": "Pulmonary trunk (bifurcation)",
  "Inferior vena cava (thoracic part)": "Inferior vena cava",
};
const AORTA = new Set(["Ascending aorta", "Aortic arch", "Thoracic aorta", "Abdominal aorta", "Brachiocephalic trunk",
  "Left common carotid artery", "Left subclavian artery"]);
const CAVA = new Set(["Superior vena cava", "Inferior vena cava (thoracic part)"]);
const PULMONARY = new Set(["Pulmonary trunk", "Bifurcation of pulmonary trunk", "Left pulmonary artery", "Right pulmonary artery"]);
const SHORT: Record<string, string> = { LAD: "LAD", LCx: "circumflex", RCA: "right coronary" };
const CORONARY = new Set(Object.keys(FRIENDLY).slice(0, 6));
const VENTRICLES = new Set(["Left ventricle", "Right ventricle"]);
const ATRIA = new Set(["Left atrium", "Right atrium"]);
const LIMB_RE = /humer|radius|ulna|scaphoid|lunate|triquetr|pisiform|trapezi|capitate|hamate|metacarp|phalan|sesamoid|carp|hand|digit|palm|thenar|forearm|antebrach|brachial|cubital|arm\b|arm\.|of arm|wrist|femur|tibia|fibula|patella|talus|calcane|tars|foot|thigh|leg\b|leg\.|knee|ankle|gluteal|crural|femoral|popliteal|malleol|toe/i;

const nameOf = (o: THREE.Object3D) => (o.userData?.anatomical_name as string) ?? o.name;
const cleanName = (n: string) => FRIENDLY[n] ?? n.replace(/\s*\(\/\/.*\)$/, "");

// ---------------- branch labels (Label mode) ----------------
const LABEL_GROUPS: [string, string[]][] = [
  ["Left anterior descending", ["LAD (main vessel)", "D1", "D2", "D3", "Septal", "Other LAD branch"]],
  ["Circumflex", ["LCx (main vessel)", "OM1", "OM2", "OM3", "Ramus intermedius", "Left PDA", "Left PLB", "Atrial branch", "Other LCx branch"]],
  ["Right coronary", ["RCA (main vessel)", "Conus", "SA nodal", "RV branch", "Acute marginal", "PDA", "PLB", "AV nodal", "Other RCA branch"]],
];
const STORE = "cpt.atlas.branchLabels.v1";
let labels: Record<string, string> = {};
try { labels = JSON.parse(localStorage.getItem(STORE) ?? "{}").labels ?? {}; } catch { labels = {}; }
const saveLabels = () => { try { localStorage.setItem(STORE, JSON.stringify(labelFile())); } catch { /* private mode: export still works */ } };
const labelFile = () => ({ version: 1, source: "Z-Anatomy Startup.blend (atlas export)", nodes: "LAD/LCx/RCA_branch_NN", labels, saved: new Date().toISOString() });

// ---------------- state ----------------
const branches: THREE.Mesh[] = [];
const pickables: THREE.Mesh[] = [];
const veins: THREE.Mesh[] = [];
const bodyGroup = new THREE.Group();
const routesGroup = new THREE.Group();          // catheter access routes (D47): hidden unless asked for
routesGroup.visible = false;
const rootHide: THREE.Mesh[] = [];              // structures in front of the aortic root, faded out in the root close-up
const atriaMeshes: THREE.Mesh[] = [];
const ostia: Record<string, { p: THREE.Vector3; n: THREE.Vector3 }> = {};
const limbMeshes: THREE.Mesh[] = [];
const heartC = new THREE.Vector3();
let sceneNo: 1 | 2 | 3 | 4 | 5 = 1;
let lab: CathLab | null = null;
const treeLeft: THREE.Mesh[] = [];
const treeRight: THREE.Mesh[] = [];
const coronaryDimMat = withBeat(new THREE.MeshPhysicalMaterial({
  color: "#ff1418", emissive: "#3a0004", roughness: 0.3, transparent: true, opacity: 0.22, depthWrite: false,
}));
let fade = 0;
let limbFade = 1;
let labelMode = false;
let selected: THREE.Mesh | null = null;

// ---- Scene 5 (D53): catheter + contrast, ILLUSTRATIVE ----
let cath: CathSim | null = null;
const fillable = new Set<THREE.Mesh>();                  // 3D coronary nodes that carry the per-vertex _s (contrast fill)
const coronaryFillMat = withBeat(new THREE.MeshPhysicalMaterial({
  color: "#ff1418", emissive: "#a0000a", emissiveIntensity: 0.8, roughness: 0.24, clearcoat: 0.9, clearcoatRoughness: 0.12,
}), { fill: true });
const catheterMat = withBeat(new THREE.MeshPhysicalMaterial({
  color: "#e8eef6", roughness: 0.32, clearcoat: 0.7, clearcoatRoughness: 0.2, emissive: "#8aa2bf", emissiveIntensity: 0.55,
}));
const wireMat = withBeat(new THREE.MeshPhysicalMaterial({ color: "#c9d2dc", metalness: 0.9, roughness: 0.22 }));
const puffMat = new THREE.MeshBasicMaterial({ color: "#fff1dc", transparent: true, opacity: 0.45, depthWrite: false });
/** Heartbeat: always on in Scenes 1-2; paused by default in Scenes 3-5 ("Beating heart" toggle); on during a cine injection. */
let beatOn = false;
let cathAccess: Access = "femoral_right";
let cathTarget: Target = "left";
let operatorAccess: "femoral" | "radial" = "femoral";

function branchColor(name: string): string {
  const m = /^(LAD|LCx|RCA)_branch_(\d+)$/.exec(name)!;
  const fam: Record<string, [number, number, number]> = { LAD: [190, 250, 6], LCx: [70, 150, 6], RCA: [300, 400, 14] };
  const [h0, h1, n] = fam[m[1]];
  const i = Number(m[2]) - 1;
  return `hsl(${(h0 + ((h1 - h0) * ((i * 5) % n)) / Math.max(n - 1, 1)) % 360}, 90%, ${i % 2 ? 64 : 52}%)`;
}
const labelMats = new Map<THREE.Mesh, THREE.MeshPhysicalMaterial>();
function refreshBranchLook() {
  for (const b of branches) {
    if (!labelMode) { b.material = coronaryMat; continue; }
    let m = labelMats.get(b);
    if (!m) { m = withBeat(new THREE.MeshPhysicalMaterial({ roughness: 0.35, clearcoat: 0.6 })); labelMats.set(b, m); }
    const lab = labels[b.name];
    const col = new THREE.Color(lab ? "#f2f2f2" : branchColor(b.name));
    m.color.copy(col);
    m.emissive.copy(b === selected ? new THREE.Color("#ffd24a") : col.clone().multiplyScalar(lab ? 0.15 : 0.35));
    m.emissiveIntensity = b === selected ? 1.2 : 1;
    b.material = m;
  }
}

// ---------------- loading ----------------
async function load() {
  const loader = new GLTFLoader();
  const get = (f: string) => loader.loadAsync(`/anatomy/${f}`).catch(() => null);
  // z_anatomy_heart.glb carries the atlas's authored vessel radii (D46); z_anatomy_heart_illustrative.glb is comparison only
  const [heart, skel, skin, routes] = await Promise.all([get("z_anatomy_heart.glb"), get("z_anatomy_skeleton.glb"),
    get("z_anatomy_skin.glb"), get("z_anatomy_access_routes.glb")]);
  if (!heart) throw new Error("z_anatomy_heart.glb missing in web/public/anatomy/");
  for (const g of [heart, skel, skin, routes]) g?.scene.updateMatrixWorld(true);
  const id = new THREE.Matrix4();
  [heart, skel, skin, routes].forEach((g) => g?.scene.traverse((o) => {
    if ((o as THREE.Mesh).isMesh && !o.matrixWorld.equals(id)) throw new Error(`node "${nameOf(o)}" has a non-identity transform`);
  }));

  const lv: THREE.Vector3[] = [], la: THREE.Vector3[] = [], box = new THREE.Box3();
  heart.scene.traverse((o) => {
    const m = o as THREE.Mesh;
    if (!m.isMesh) return;
    const n = nameOf(o);
    const os = o.userData.effective_ostium_LPS as number[] | undefined;
    if (os) ostia[n === "Left coronary artery" ? "LM" : "RCA"] = {
      p: new THREE.Vector3(...os), n: new THREE.Vector3(...(o.userData.effective_ostium_wall_normal_LPS as number[])),
    };
    if (/_branch_\d+$/.test(n)) {
      m.material = coronaryMat; branches.push(m); pickables.push(m);
    } else if (AORTA.has(n) || CAVA.has(n) || PULMONARY.has(n)) {
      m.material = AORTA.has(n) ? aortaMat : CAVA.has(n) ? cavaMat : pulmonaryMat;
      pickables.push(m);
      if (PULMONARY.has(n)) rootHide.push(m);
    } else if (CORONARY.has(n)) {
      m.material = coronaryMat;
      const split = o.children.some((c) => /_branch_\d+$/.test(nameOf(c)));
      if (split) m.material = new THREE.MeshBasicMaterial({ visible: false });   // drawn as its separate splines (children)
      else pickables.push(m);
    } else if (VENTRICLES.has(n) || ATRIA.has(n)) {
      m.material = VENTRICLES.has(n) ? ventricleMat : atriumMat;
      pickables.push(m);
      if (ATRIA.has(n)) atriaMeshes.push(m);
      box.expandByObject(m);
      const p = m.geometry.getAttribute("position");
      const tgt = n === "Left ventricle" ? lv : n === "Left atrium" ? la : null;
      if (tgt) for (let i = 0; i < p.count; i++) tgt.push(new THREE.Vector3().fromBufferAttribute(p, i));
    } else if (o.userData.source_parent === "Cardiac veins.g" || /vein|sinus|\?\?\?/i.test(n)) {
      m.material = veinMat; veins.push(m); pickables.push(m);
    } else {
      m.visible = false;   // valves and papillary muscles (inside the heart)
    }
  });
  if (!ostia.LM || !ostia.RCA) throw new Error("effective ostia missing from z_anatomy_heart.glb (re-export, D46)");
  box.getCenter(heartC);
  // beat axis from the geometry itself: LV base (LV vertices nearest the LA) -> LV apex
  const laC = la.reduce((a, b) => a.add(b), new THREE.Vector3()).divideScalar(la.length);
  const d = lv.map((v) => v.distanceTo(laC)).sort((a, b) => a - b);
  const cut = d[Math.floor(d.length * 0.1)];
  const near = lv.filter((v) => v.distanceTo(laC) <= cut);
  const base = near.reduce((a, b) => a.add(b), new THREE.Vector3()).divideScalar(near.length);
  const apex = lv.reduce((best, v) => (v.distanceTo(base) > best.distanceTo(base) ? v : best), lv[0]);
  motion.uBase.value.copy(base);
  motion.uAxis.value.copy(apex.clone().sub(base).normalize());
  motion.uLen.value = apex.distanceTo(base);
  motion.uHeartC.value.copy(heartC);
  // beat envelope: r0 just encloses every chamber, coronary and cardiac-vein vertex, so they move exactly as before
  let r0 = 0;
  const pv = new THREE.Vector3();
  heart.scene.traverse((o) => {
    const m = o as THREE.Mesh;
    if (!m.isMesh || !(m.material === ventricleMat || m.material === atriumMat || m.material === coronaryMat || m.material === veinMat
      || branches.includes(m))) return;
    const p = m.geometry.getAttribute("position");
    for (let i = 0; i < p.count; i++) r0 = Math.max(r0, pv.fromBufferAttribute(p, i).distanceTo(heartC));
  });
  motion.uEnv.value.set(r0 + 2, r0 + 120);
  scene.add(heart.scene);
  if (routes) {
    routes.scene.traverse((o) => {
      const m = o as THREE.Mesh;
      if (m.isMesh) { m.material = aortaMat; pickables.push(m); }
    });
    routesGroup.add(routes.scene);
  }
  scene.add(routesGroup);

  if (skel) skel.scene.traverse((o) => {
    const m = o as THREE.Mesh;
    if (!m.isMesh) return;
    if (/\.g$/.test(nameOf(o))) { m.visible = false; return; }   // the atlas's flat "SKELETAL SYSTEM" label board, not a bone
    const limb = LIMB_RE.test(nameOf(o));
    m.material = limb ? boneLimb : boneTrunk;
    m.renderOrder = 1;
    if (limb) limbMeshes.push(m);
  });
  if (skin) skin.scene.traverse((o) => {
    const m = o as THREE.Mesh;
    if (!m.isMesh) return;
    if (!m.geometry.getAttribute("_arm") || !m.geometry.getAttribute("_leg")) throw new Error("skin is not the welded export (D48)");
    m.material = skinMat;
    m.renderOrder = 2;
  });
  if (skel) bodyGroup.add(skel.scene);
  if (skin) bodyGroup.add(skin.scene);
  scene.add(bodyGroup);

  // ---- Scenes 3-4 (D50): the cath lab and the X-ray pass, on the closed atlas X-ray meshes (D49) ----
  const xrMeta = await fetch("/anatomy/atlas_xray.json").then((r) => (r.ok ? r.json() : null)).catch(() => null);
  const xrGeo = await Promise.all(["left", "right", "bone", "heart"].map((t) => get(`atlas_xray_${t}.glb`)));
  if (xrMeta && xrGeo.every(Boolean) && skin) {
    const geo = (g: Awaited<ReturnType<typeof get>>) => {
      let out: THREE.BufferGeometry | null = null;
      g!.scene.traverse((o) => { if ((o as THREE.Mesh).isMesh) out = (o as THREE.Mesh).geometry; });
      return out!;
    };
    const bodyBox = new THREE.Box3().setFromObject(skin.scene);
    // ---- Scene 5 data (D53): catheter routes/shapes and the contrast-fill distances (per vertex, along the tree) ----
    const cathData = await fetch("/anatomy/atlas_cath.json").then((r) => (r.ok ? r.json() : null)).catch(() => null);
    const fillBuf = await fetch("/anatomy/atlas_fill.bin").then((r) => (r.ok ? r.arrayBuffer() : null)).catch(() => null);
    const xl = geo(xrGeo[0]), xr = geo(xrGeo[1]);
    const fillOf = (key: string, g: THREE.BufferGeometry) => {
      const e = cathData?.fill_index?.[key];
      if (!e || !fillBuf) return false;
      const p = g.getAttribute("position");
      if (p.count !== e.count || Math.abs(p.getX(0) - e.first_vertex[0]) > 0.01 || Math.abs(p.getZ(0) - e.first_vertex[2]) > 0.01)
        throw new Error(`fill data does not match ${key} (re-run build_atlas_cath.py)`);
      g.setAttribute("_s", new THREE.BufferAttribute(new Float32Array(fillBuf, e.offset * 4, e.count), 1));
      return true;
    };
    if (cathData) { fillOf("xray_left", xl); fillOf("xray_right", xr); }
    lab = new CathLab(renderer, { left: xl, right: xr, bone: geo(xrGeo[2]), heart: geo(xrGeo[3]), isocenter: xrMeta.isocenter_LPS },
      bodyBox, { glsl: FIELD, uniforms: motion });
    fillU.uFill = lab.angio.fill;                       // ONE fill window for the 3D glow and the X-ray
    lab.room.visible = lab.rig.visible = false;
    scene.add(lab.room, lab.rig);
    for (const b of branches) (/^RCA_/.test(b.name) ? treeRight : treeLeft).push(b);
    heart.scene.traverse((o) => {
      const n = nameOf(o);
      if (n === "Left coronary artery" || n === "Septal branches of anterior interventricular artery") treeLeft.push(o as THREE.Mesh);
      if (n === "Right inferolateral branch of right coronary artery") treeRight.push(o as THREE.Mesh);
    });
    if (cathData) {
      for (const m of [...treeLeft, ...treeRight]) if (fillOf(`node:${nameOf(m)}`, m.geometry)) fillable.add(m);
      cath = new CathSim(cathData, lab.angio, catheterMat, wireMat, puffMat);
      lab.angio.fill.value.set(1e9, -1e9);              // the sim starts with "no contrast"; outside Scene 5 the trees are full
      lab.angio.setDevices([]);
      cath.group.visible = false;
      scene.add(cath.group);
      cath.onPhase = (p) => cathCaption(p);
    }
  }

  // compile every program now (body included) so the pull-out never stalls on a first-use shader compile
  bodyGroup.visible = true;
  camera.position.copy(heartC).add(new THREE.Vector3(0, -1050, 0));
  camera.lookAt(heartC);
  await renderer.compileAsync(scene, camera);
  camera.position.set(0, 0, 0);
  bodyGroup.visible = false;

  // labels shipped as a file (optional) when this browser has none
  if (!Object.keys(labels).length) {
    try {
      const r = await fetch("/anatomy/atlas_branch_labels.json");
      if (r.ok && r.headers.get("content-type")?.includes("json")) labels = (await r.json()).labels ?? {};
    } catch { /* none */ }
  }
}

// ---------------- camera moves ----------------
type Pose = { pos: THREE.Vector3; target: THREE.Vector3; up: THREE.Vector3 };
const HEART_DIST = 330, CHEST_DIST = 1050;
const DIRS: Record<string, { dir: THREE.Vector3; up: THREE.Vector3; caption: string }> = {
  front: { dir: new THREE.Vector3(0, -1, 0), up: new THREE.Vector3(0, 0, 1), caption: "Front: you face the patient, so their left side is on your right." },
  lao: { dir: new THREE.Vector3(0.7, -0.7, 0.12), up: new THREE.Vector3(0, 0, 1), caption: "From the front-left: the left side of the heart turns toward you." },
  left: { dir: new THREE.Vector3(1, 0, 0), up: new THREE.Vector3(0, 0, 1), caption: "Left side: the chest wall is on your left, the spine on your right, and the apex points toward you." },
  right: { dir: new THREE.Vector3(-1, 0, 0), up: new THREE.Vector3(0, 0, 1), caption: "Right side: the chest wall is on your right, and the apex points away from you." },
  feet: { dir: new THREE.Vector3(0, 0.0001, -1), up: new THREE.Vector3(0, -1, 0), caption: "From the feet: the heart's apex points to the patient's left, which is on your right." },
  head: { dir: new THREE.Vector3(0, 0.0001, 1), up: new THREE.Vector3(0, -1, 0), caption: "From the head: the patient's left is on your left, and the apex points left and forward." },
};
const CLIP: Record<string, [THREE.Vector3, number] | null> = {
  feet: [new THREE.Vector3(0, 0, 1), -125], head: [new THREE.Vector3(0, 0, -1), -125],
};
const ROOT_DIST = 165, BODY_DIST = 3900;
const ROOT_CAPTION = "The aortic root: both coronary arteries leave the aorta just above the valve.";
function poseFor(view: string, dist: number): Pose {
  if (view === "root") {
    // looking at the aortic root from outside both ostia: the mean of the two wall normals, lifted a little toward the head;
    // screen-up is the patient's superior direction
    const target = ostia.LM.p.clone().add(ostia.RCA.p).multiplyScalar(0.5);
    const dir = ostia.LM.n.clone().add(ostia.RCA.n).normalize().add(new THREE.Vector3(0, 0, 0.35)).normalize();
    return { pos: target.clone().addScaledVector(dir, ROOT_DIST), target, up: new THREE.Vector3(0, 0, 1) };
  }
  if (view === "body") {
    // whole body from the front (review of the access routes): centred between the head and the knees
    const target = new THREE.Vector3(heartC.x, heartC.y, heartC.z - 420);
    return { pos: target.clone().add(new THREE.Vector3(0, -BODY_DIST, 0)), target, up: new THREE.Vector3(0, 0, 1) };
  }
  const V = DIRS[view];
  const target = heartC.clone().add(new THREE.Vector3(0, 0, dist > 500 ? 35 : 0));
  return { pos: target.clone().addScaledVector(V.dir.clone().normalize(), dist), target, up: V.up.clone() };
}
let tween: ((now: number) => boolean) | null = null;
const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
function moveTo(to: Pose, ms: number, onT?: (e: number) => void) {
  const from: Pose = { pos: camera.position.clone(), target: controls.target.clone(), up: camera.up.clone() };
  if (from.pos.distanceTo(from.target) < 1e-3) { from.pos.copy(to.pos); from.target.copy(to.target); from.up.copy(to.up); }   // first placement
  const d0 = from.pos.clone().sub(from.target), d1 = to.pos.clone().sub(to.target);
  const r0 = d0.length(), r1 = d1.length();
  const q = new THREE.Quaternion().setFromUnitVectors(d0.clone().normalize(), d1.clone().normalize());
  const qi = new THREE.Quaternion();
  const t0 = performance.now();
  document.body.dataset.moving = "1";
  controls.enabled = false;
  tween = (now) => {
    const t = Math.min(1, (now - t0) / ms), e = ease(t);
    qi.identity().slerp(q, e);
    const dir = d0.clone().normalize().applyQuaternion(qi);
    const tgt = from.target.clone().lerp(to.target, e);
    camera.position.copy(tgt).addScaledVector(dir, Math.exp(Math.log(r0) + (Math.log(r1) - Math.log(r0)) * e));
    camera.up.copy(from.up.clone().lerp(to.up, e).normalize());
    controls.target.copy(tgt);
    camera.lookAt(tgt);
    onT?.(e);
    if (t >= 1) {
      controls.enabled = true;
      document.body.dataset.moving = "0";
      return false;
    }
    return true;
  };
  if (ms === 0) { tween(performance.now() + 1); tween = null; }
}
function setClip(view: string, e = 1) {
  const c = CLIP[view];
  const far = 1e6;
  if (!c) { clipPlane.set(new THREE.Vector3(0, 0, 1), far); }
  else {
    const [n, off] = c;
    const constant = -n.dot(heartC) - off;          // keep the side of the plane facing away from the camera
    clipPlane.set(n, THREE.MathUtils.lerp(constant + 1500, constant, e));   // starts beyond the body: nothing clipped
  }
  clipU.value.set(clipPlane.normal.x, clipPlane.normal.y, clipPlane.normal.z, clipPlane.constant);
}

let currentView = "front";
function caption(text: string) {
  const c = $("caption");
  c.style.opacity = "0";
  setTimeout(() => { c.textContent = text; c.style.opacity = "1"; }, 250);
}
let rootFade = 1;                                 // 1 = structures in front of the aortic root fully shown
/** Fade toward the root close-up: the atria (their appendages cover both ostia), the pulmonary arteries and the cardiac veins
 *  disappear; the ventricles become a ghost so the right-ventricular outflow tract no longer hides the root. */
function setOpacity(m: THREE.Material, op: number) {
  const t = op < 0.999;
  if (m.transparent !== t) { m.transparent = t; m.depthWrite = !t; m.needsUpdate = true; }
  m.opacity = op;
}
function setRootFade(v: number) {
  rootFade = v;
  rootHide.forEach((m) => (m.visible = v > 0.02));
  setOpacity(pulmonaryMat, v);
  setOpacity(atriumMat, v);
  setOpacity(ventricleMat, 0.22 + 0.78 * v);
  // Scene 5: the catheter lies INSIDE the aorta, so the root close-up turns the aortic wall to glass
  // (and the access routes share this material: the catheter must be seen advancing inside them)
  setOpacity(aortaMat, sceneNo === 5 ? 0.3 : 1);
  atriaMeshes.forEach((m) => (m.visible = v > 0.02));
  const veinsOn = $("bVeins").classList.contains("on") && !labelMode;
  veins.forEach((m) => (m.visible = veinsOn && v > 0.5));
}
/** Scene 1 views: the whole heart, or a close-up of the aortic root (the pulmonary trunk in front of it is taken away). */
function setHeartView(v: "front" | "root", ms: number) {
  if (sceneNo !== 1) return;
  currentView = v;
  document.querySelectorAll<HTMLButtonElement>("#heartViews button").forEach((b) => b.classList.toggle("on", b.dataset.v === v));
  const f0 = rootFade, f1 = v === "root" ? 0 : 1;
  if (f1 > 0) setRootFade(Math.max(f0, 0.03));
  moveTo(poseFor(v, HEART_DIST), ms, (e) => setRootFade(THREE.MathUtils.lerp(f0, f1, e)));
  caption(v === "root" ? ROOT_CAPTION : "The heart. Drag to turn it; point at a vessel to see its name.");
}
function setRoutes(on: boolean) { routesGroup.visible = on; }

// ---------------- Scenes 3-4: cath lab and X-ray pass (D50) ----------------
// Standard views by name; captions in words (no numbers), as everywhere in the explainer.
const CARM_VIEWS: Record<string, { a: number; b: number; caption: string }> = {
  ap: { a: 0, b: 0, caption: "Straight on: the detector sits right above the chest." },
  rao30: { a: -30, b: 0, caption: "Right anterior oblique: the detector swings toward the patient's right." },
  lao45: { a: 45, b: 0, caption: "Left anterior oblique: the detector swings toward the patient's left." },
  raocaud: { a: -30, b: -25, caption: "Right oblique, tilted toward the feet: the circumflex and its branches open up." },
  spider: { a: 40, b: -30, caption: "The spider view: left oblique and toward the feet; the left main splits like a spider's legs." },
};
type LabCam = "room" | "operator" | "beam" | "split" | "root";
let labCam: LabCam = "room";
let carmView = "ap";
function labPose(cam: LabCam): Pose {
  if (cam === "operator") return lab!.operatorPose(heartC, sceneNo === 5 ? (cathAccess === "radial_right" ? "radial" : "femoral") : operatorAccess);
  if (cam === "beam") return lab!.beamPose();
  if (cam === "split") return lab!.detectorSidePose(heartC);
  if (cam === "root") return poseFor("root", HEART_DIST);
  return lab!.roomPose(heartC);
}
function syncLabButtons() {
  const on = (sel: string, v: string | undefined) =>
    document.querySelectorAll<HTMLButtonElement>(sel).forEach((b) => b.classList.toggle("on", b.dataset.v === v));
  on("#carmViews button", carmView);
  on("#labCams button, #xrCams button, #cathCams button", labCam === "operator" && sceneNo === 3 ? `operator-${operatorAccess}` : labCam);
  on("#inject button", lab?.injected);
  on("#cathAccess button", cathAccess);
  on("#cathTarget button", cathTarget);
  $("bBeat").classList.toggle("on", beatOn);
}
/** Side-by-side (Scene 4) shows only the heart next to the image; the aortic-root close-up (Scene 5) hides the room and body. */
function applySplit() {
  const split = sceneNo === 4 && labCam === "split";
  const root = sceneNo === 5 && labCam === "root";
  if (lab) { lab.room.visible = !split && !root; lab.rig.visible = !split && !root; }
  bodyGroup.visible = !split && !root;
  $("monitor").style.display = (sceneNo === 4 || sceneNo === 5) && !split ? "block" : "none";
  $("splitLabel").style.display = split ? "block" : "none";
}
function setLabCam(cam: LabCam, ms: number) {
  if (!lab || sceneNo < 3) return;
  labCam = cam;
  applySplit();
  syncLabButtons();
  const r0 = rootFade, r1 = cam === "root" ? 0 : 1;
  if (r1 > 0) setRootFade(Math.max(r0, 0.03));
  moveTo(labPose(cam), ms, (e) => setRootFade(THREE.MathUtils.lerp(r0, r1, e)));
  caption(cam === "root" ? "The aortic root, close: the catheter tip sits in the coronary's opening."
    : cam === "operator" ? ((sceneNo === 5 ? cathAccess === "radial_right" : operatorAccess === "radial")
      ? "The operator's view: beside the patient's right shoulder, over the arm board (radial access)."
      : "The operator's view: standing at the patient's right side, at the hip (femoral access).")
    : cam === "beam" ? "Side-on to the beam: tube, heart and detector in one line. Drag to orbit; the projection stays fixed."
    : cam === "split" ? "Left: the heart turned the way the detector sees it. Right: the image it makes."
    : "The cath lab: the C-arm turns around the patient, and the heart stays at its centre.");
}
function setCArmView(v: string, ms: number) {
  if (!lab || sceneNo < 3) return;
  carmView = v;
  syncLabButtons();
  const V = CARM_VIEWS[v];
  lab.swingTo(V.a, V.b, ms, () => {
    if (labCam === "beam" || labCam === "split") moveTo(labPose(labCam), 0);
  });
  caption(V.caption);
}
function setInject(t: "left" | "right") {
  if (!lab) return;
  lab.setInjected(t);
  applyInjectionLook();
  syncLabButtons();
  caption(t === "left" ? "Contrast in the left coronary artery: only that tree shows on the image."
    : "Contrast in the right coronary artery: only that tree shows on the image.");
}
/** Scene 4: the non-injected tree is dimmed in 3D (it does not appear on the image). Scene 5: the target tree shows the
 *  contrast fill, the other is dimmed. Everywhere else both trees are full. */
function applyInjectionLook() {
  const on = (sceneNo === 4 || sceneNo === 5) && !!lab;
  const inj = sceneNo === 5 ? cathTarget : lab?.injected;
  for (const [tree, list] of [["left", treeLeft], ["right", treeRight]] as const)
    for (const m of list)
      m.material = !on ? coronaryMat : inj !== tree ? coronaryDimMat : sceneNo === 5 && fillable.has(m) ? coronaryFillMat : coronaryMat;
}
const FOOT_DEFAULT = "Z-Anatomy atlas (CC BY-SA 4.0) · vessel sizes are the atlas's own, not a patient's";
/** Leaving Scene 5: no catheter, contrast everywhere again (Scene 4 shows whole trees), routes hidden. */
function leaveCath() {
  if (!cath) return;
  cath.reset();
  cath.group.visible = false;
  lab?.angio.fill.value.set(1e9, -1e9);
  lab?.angio.setDevices([]);
  routesGroup.visible = params.has("routes");
  $("foot").textContent = FOOT_DEFAULT;
}
function showLab(n: 3 | 4 | 5, ms: number) {
  if (!lab) { caption("The cath lab needs the atlas X-ray meshes (build_atlas_xray.py)."); return; }
  if (n === 5 && !cath) { caption("Scene 5 needs build_atlas_cath.py."); return; }
  const from = sceneNo;
  sceneNo = n;
  if (labelMode) setLabelMode(false);
  for (const [id, s] of [["bHeart", 1], ["bPatient", 2], ["bLab", 3], ["bXray", 4], ["bCath", 5]] as const) $(id).classList.toggle("on", n === s);
  $("views").style.display = "none";
  $("heartViews").style.display = "none";
  $("carmViews").style.display = "contents";
  $("labCams").style.display = n === 3 ? "contents" : "none";
  $("xrCams").style.display = n === 4 ? "contents" : "none";
  $("inject").style.display = n === 4 ? "contents" : "none";
  $("cathCtl").style.display = n === 5 ? "contents" : "none";
  $("cathCams").style.display = n === 5 ? "contents" : "none";
  $("bBeat").style.display = "";
  if (n === 3 && !["room", "operator"].includes(labCam)) labCam = "room";
  if (n === 4 && !["room", "beam", "split"].includes(labCam)) labCam = "room";
  if (n === 5 && !["room", "operator", "beam", "root"].includes(labCam)) labCam = "operator";
  if (n !== 5 && from === 5) leaveCath();
  if (n === 5) {
    cath!.access = cathAccess;
    cath!.target = cathTarget;
    lab.injected = cathTarget;
    cath!.group.visible = true;
    routesGroup.visible = true;
    $("foot").textContent = "Catheter and contrast are ILLUSTRATIVE, not physics · Z-Anatomy atlas (CC BY-SA 4.0)";
    if (from !== 5) cath!.reset();
  }
  lab.room.visible = lab.rig.visible = true;
  bodyGroup.visible = true;
  applySplit();
  applyInjectionLook();
  lab.setXray(n >= 4);
  syncLabButtons();
  const f0 = fade, lf0 = limbFade, rf0 = rootFade, rf1 = n === 5 && labCam === "root" ? 0 : 1;
  setClip("front");
  moveTo(labPose(labCam), ms, (e) => {
    fade = THREE.MathUtils.lerp(f0, 1, THREE.MathUtils.smoothstep(e, 0, 0.6));
    limbFade = THREE.MathUtils.lerp(lf0, 1, e);
    setRootFade(THREE.MathUtils.lerp(rf0, rf1, e));
  });
  caption(n === 3 ? "The cath lab: the C-arm turns around the patient, and the heart stays at its centre."
    : n === 4 ? "X-rays travel from the tube, through the chest, to the detector, where the image forms."
    : `Catheter, ${cathAccess === "femoral_right" ? "from the right groin" : "from the right wrist"}: press Run.`);
}

// ---- Scene 5 controls ----
function cathCaption(p: string) {
  const shape = cathTarget === "left" ? "JL4" : "JR4";
  const art = cathTarget === "left" ? "left main" : "right coronary artery";
  caption(p === "advance" ? `The J-tipped wire leads; the catheter follows it up ${cathAccess === "femoral_right" ? "the aorta" : "the arm and into the aorta"}.`
    : p === "withdraw" ? "The wire comes out; the catheter can now take its own shape."
    : p === "shape" ? `The ${shape} catheter takes its shape in the aortic root and turns toward the ${art}.`
    : p === "engaged" ? `Engaged: the tip sits in the opening of the ${art}. Press Inject.`
    : p === "inject" ? "Contrast: it fills the tree from the opening outward, holds, then washes out." : "");
}
function setCathAccess(a: Access) {
  cathAccess = a;
  if (cath) { cath.access = a; cath.reset(); }
  syncLabButtons();
  if (sceneNo === 5) { if (labCam === "operator") moveTo(labPose("operator"), 1800); cathCaption(""); caption(`Access: ${a === "femoral_right" ? "the right femoral artery, in the groin" : "the right radial artery, at the wrist"}. Press Run.`); }
}
function setCathTarget(t: Target) {
  cathTarget = t;
  if (cath) { cath.target = t; cath.reset(); }
  if (lab) lab.injected = t;
  applyInjectionLook();
  syncLabButtons();
  caption(t === "left" ? "Target: the left coronary, with a JL4 catheter. Press Run." : "Target: the right coronary, with a JR4 catheter. Press Run.");
}
function setBeat(on: boolean) {
  beatOn = on;
  syncLabButtons();
}

function showScene(n: 1 | 2, ms: number) {
  if (sceneNo === 5) leaveCath();
  sceneNo = n;
  if (lab) {
    lab.setXray(false);
    lab.room.visible = lab.rig.visible = false;
    applyInjectionLook();
    $("monitor").style.display = "none";
    $("splitLabel").style.display = "none";
    for (const id of ["carmViews", "labCams", "xrCams", "inject", "cathCtl", "cathCams"]) $(id).style.display = "none";
    $("bBeat").style.display = "none";
    for (const id of ["bLab", "bXray", "bCath"]) $(id).classList.remove("on");
  }
  $("bHeart").classList.toggle("on", n === 1);
  $("bPatient").classList.toggle("on", n === 2);
  $("views").style.display = n === 2 ? "contents" : "none";
  $("heartViews").style.display = n === 1 ? "contents" : "none";
  document.querySelectorAll<HTMLButtonElement>("#heartViews button").forEach((b) => b.classList.toggle("on", b.dataset.v === "front"));
  const f0 = fade;
  const lf0 = limbFade;
  const rf0 = rootFade;
  currentView = n === 1 && currentView === "lao" ? "lao" : "front";
  if (n === 2) bodyGroup.visible = true;
  setClip("front");
  moveTo(poseFor(currentView, n === 1 ? HEART_DIST : CHEST_DIST), ms, (e) => {
    // the body fades in during the second half of the pull-out (out during the first half of the push-in)
    fade = n === 2 ? THREE.MathUtils.smoothstep(e, 0.3, 0.95) : f0 * (1 - THREE.MathUtils.smoothstep(e, 0.0, 0.55));
    limbFade = THREE.MathUtils.lerp(lf0, 1, e);
    setRootFade(THREE.MathUtils.lerp(rf0, 1, e));
    if (e >= 1 && n === 1) bodyGroup.visible = false;
  });
  caption(n === 1 ? "The heart. Drag to turn it; point at a vessel to see its name."
    : "The heart in the chest: the skin is glass, the ribs, sternum and spine show faintly.");
}
function setView(v: string, ms: number) {
  if (sceneNo !== 2) return;
  const prev = currentView;
  currentView = v;
  document.querySelectorAll<HTMLButtonElement>("#views button").forEach((b) => b.classList.toggle("on", b.dataset.v === v));
  const lf0 = limbFade, lf1 = v === "left" || v === "right" ? 0 : 1;
  const prevClip = CLIP[prev], nextClip = CLIP[v];
  moveTo(poseFor(v, v === "body" ? BODY_DIST : CHEST_DIST), ms, (e) => {
    limbFade = THREE.MathUtils.lerp(lf0, lf1, e);
    if (nextClip) setClip(v, THREE.MathUtils.smoothstep(e, 0.2, 0.8));
    else if (prevClip) setClip(prev, 1 - THREE.MathUtils.smoothstep(e, 0.0, 0.5));
    else setClip(v);
  });
  caption(v === "body" ? "The whole patient, from the front." : DIRS[v].caption);
}

// ---------------- hover + label picking ----------------
const ray = new THREE.Raycaster();
const tip = $("hover");
function pick(e: PointerEvent): THREE.Mesh | null {
  const r = canvas.getBoundingClientRect();
  ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera);
  const hits = ray.intersectObjects(pickables.filter((m) => m.visible && (m.material as THREE.Material).visible), false);
  return (hits[0]?.object as THREE.Mesh) ?? null;
}
function describe(m: THREE.Mesh): string {
  const n = nameOf(m);
  const b = /^(LAD|LCx|RCA)_branch_\d+$/.exec(n);
  if (!b) return cleanName(n);
  const lab = labels[n];
  if (lab) return lab;
  return labelMode ? `Unlabeled branch of the ${SHORT[b[1]]}` : `${cleanName(m.userData.parent_vessel)} (branch not yet named)`;
}
canvas.addEventListener("pointermove", (e) => {
  const h = pick(e);
  if (!h) { tip.style.display = "none"; canvas.style.cursor = ""; return; }
  tip.textContent = describe(h);
  tip.style.display = "block";
  tip.style.left = `${e.clientX + 14}px`;
  tip.style.top = `${e.clientY + 12}px`;
  canvas.style.cursor = labelMode && branches.includes(h) ? "pointer" : "";
});
canvas.addEventListener("pointerleave", () => (tip.style.display = "none"));
let down: [number, number] | null = null;
canvas.addEventListener("pointerdown", (e) => (down = [e.clientX, e.clientY]));
canvas.addEventListener("pointerup", (e) => {
  if (!labelMode || !down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
  const h = pick(e);
  if (h && branches.includes(h)) select(h);
});
function select(m: THREE.Mesh | null) {
  selected = m;
  refreshBranchLook();
  renderNames();
}
function renderNames() {
  const sel = $("sel");
  const box = $("names");
  box.innerHTML = "";
  if (!selected) { sel.textContent = "No branch selected"; return; }
  const fam = /^(LAD|LCx|RCA)/.exec(selected.name)![1];
  sel.textContent = labels[selected.name] ? `Selected: ${labels[selected.name]}` : `Selected: unlabeled branch of the ${SHORT[fam]}`;
  const order = [...LABEL_GROUPS].sort((a, b) => Number(b[0].startsWith(fam === "LAD" ? "Left" : fam === "LCx" ? "Circ" : "Right")) - Number(a[0].startsWith(fam === "LAD" ? "Left" : fam === "LCx" ? "Circ" : "Right")));
  for (const [grp, names] of order) {
    const g = document.createElement("div"); g.className = "grp"; g.textContent = grp; box.appendChild(g);
    const row = document.createElement("div"); row.className = "names";
    for (const n of names) {
      const b = document.createElement("button");
      b.textContent = n;
      if (labels[selected.name] === n) b.className = "cur";
      b.onclick = () => { labels[selected!.name] = n; saveLabels(); select(selected); };
      row.appendChild(b);
    }
    box.appendChild(row);
  }
  const clr = document.createElement("div"); clr.className = "row";
  const cb = document.createElement("button"); cb.textContent = "Clear label";
  cb.onclick = () => { delete labels[selected!.name]; saveLabels(); select(selected); };
  clr.appendChild(cb); box.appendChild(clr);
}
function setLabelMode(on: boolean) {
  labelMode = on;
  $("bLabel").classList.toggle("on", on);
  $("labelPanel").style.display = on ? "block" : "none";
  if (!on) selected = null;
  const veinsOn = $("bVeins").classList.contains("on");
  veins.forEach((v) => (v.visible = !on && veinsOn));                  // dark-blue veins would compete with the blue LAD family
  refreshBranchLook();
  renderNames();
}
$("lExport").onclick = () => {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(labelFile(), null, 1)], { type: "application/json" }));
  a.download = "atlas_branch_labels.json";
  a.click();
};
$("lImportBtn").onclick = () => $<HTMLInputElement>("lImport").click();
$<HTMLInputElement>("lImport").onchange = async (e) => {
  const f = (e.target as HTMLInputElement).files?.[0];
  if (!f) return;
  const j = JSON.parse(await f.text());
  if (j.version !== 1 || typeof j.labels !== "object") { alert("Not an atlas branch-label file"); return; }
  labels = j.labels; saveLabels(); refreshBranchLook(); renderNames();
};

// ---------------- buttons ----------------
$("bHeart").onclick = () => showScene(1, 2600);
$("bPatient").onclick = () => showScene(2, 3600);
document.querySelectorAll<HTMLButtonElement>("#views button").forEach((b) => (b.onclick = () => setView(b.dataset.v!, 2200)));
document.querySelectorAll<HTMLButtonElement>("#heartViews button").forEach((b) => (b.onclick = () => setHeartView(b.dataset.v as "front" | "root", 2400)));
$("bVeins").onclick = () => {
  const on = !veins[0]?.visible;
  veins.forEach((v) => (v.visible = on));
  $("bVeins").classList.toggle("on", on);
};
$("bLabel").onclick = () => setLabelMode(!labelMode);
$("bLab").onclick = () => showLab(3, 3200);
$("bXray").onclick = () => showLab(4, 2400);
document.querySelectorAll<HTMLButtonElement>("#carmViews button").forEach((b) => (b.onclick = () => setCArmView(b.dataset.v!, 2600)));
document.querySelectorAll<HTMLButtonElement>("#labCams button, #xrCams button, #cathCams button").forEach((b) => (b.onclick = () => {
  const v = b.dataset.v!;
  if (v.startsWith("operator-")) operatorAccess = v.slice(9) as "femoral" | "radial";   // Scene 3: femoral / radial position
  setLabCam((v.startsWith("operator") ? "operator" : v) as LabCam, 2200);
}));
$("bCath").onclick = () => showLab(5, 2600);
$("bBeat").onclick = () => setBeat(!beatOn);
document.querySelectorAll<HTMLButtonElement>("#cathAccess button").forEach((b) => (b.onclick = () => setCathAccess(b.dataset.v as Access)));
document.querySelectorAll<HTMLButtonElement>("#cathTarget button").forEach((b) => (b.onclick = () => setCathTarget(b.dataset.v as Target)));
$("bRun").onclick = () => { if (cath && sceneNo === 5) { cath.access = cathAccess; cath.target = cathTarget; cath.run(); } };
$("bInject").onclick = () => cath?.inject();
document.querySelectorAll<HTMLButtonElement>("#inject button").forEach((b) => (b.onclick = () => setInject(b.dataset.v as "left" | "right")));

// ---------------- the image: monitor inset and side-by-side (raw blit of the angiogram render target, no flips) ----------------
const blitMat = new THREE.ShaderMaterial({
  uniforms: { uMap: { value: null as THREE.Texture | null } }, depthTest: false, depthWrite: false,
  vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
  fragmentShader: "uniform sampler2D uMap; varying vec2 vUv; void main(){ gl_FragColor = vec4(texture2D(uMap, vUv).rgb, 1.0); }",
});
const blitScene = new THREE.Scene();
const blitQuad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), blitMat);
blitQuad.frustumCulled = false;
blitScene.add(blitQuad);
const blitCam = new THREE.Camera();
/** Draw the angiogram into the rectangle of a DOM element (CSS px). Texture (0,0) = the (-u,-v) corner: u right, v up. */
function blitInto(el: HTMLElement) {
  const c = canvas.getBoundingClientRect(), r = el.getBoundingClientRect();
  const pr = renderer.getPixelRatio();
  const x = (r.left - c.left) * pr, y = (c.bottom - r.bottom) * pr, w = r.width * pr, h = r.height * pr;
  blitMat.uniforms.uMap.value = lab!.angio.angioRT.texture;
  renderer.setScissorTest(true);
  renderer.setScissor(x / pr, y / pr, w / pr, h / pr);
  renderer.setViewport(x / pr, y / pr, w / pr, h / pr);
  renderer.render(blitScene, blitCam);
  renderer.setScissorTest(false);
  renderer.setViewport(0, 0, c.width, c.height);
}

// ---------------- frame loop ----------------
let lastNow = performance.now();
const t0 = performance.now();
const still = params.has("still");          // screenshots: freeze motion at end-diastole / mid-breath
function tick(now: number) {
  const t = still ? 0 : (now - t0) / 1000;
  const ph = (t / 0.94) % 1;                                          // ~64 beats per minute
  // Scenes 1-2: always beating and breathing. Scenes 3-5 (the lab): breath held (as for an acquisition); the heartbeat is
  // paused unless "Beating heart" is on, or a cine injection runs (then the X-ray beats with the same field, angio.fieldOn).
  const inLab = sceneNo >= 3;
  const cine = !!cath?.cine && sceneNo === 5;
  const beating = !inLab || beatOn || cine;
  motion.uVent.value = beating && ph < 0.42 ? Math.pow(Math.sin((Math.PI * ph) / 0.42), 1.6) : 0;
  motion.uAtr.value = beating && ph > 0.8 ? Math.pow(Math.sin((Math.PI * (ph - 0.8)) / 0.2), 2) : 0;
  motion.uBreath.value = !inLab && (sceneNo === 2 || fade > 0) ? 0.5 - 0.5 * Math.cos((2 * Math.PI * t) / 4.6) : 0;
  if (lab) lab.angio.fieldOn.value = inLab && beating ? 1 : 0;
  skinMat.uniforms.uFade.value = fade;
  skinMat.uniforms.uLimbFade.value = limbFade;
  boneTrunk.opacity = 0.13 * fade;
  rimU.uRim.value = fade;                      // the heart's rim light follows the body fade-in (chest view only)
  boneLimb.opacity = 0.07 * fade * limbFade;
  limbMeshes.forEach((m) => (m.visible = limbFade > 0.01));
  if (tween && !tween(now)) tween = null;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== Math.floor(w * renderer.getPixelRatio()) || canvas.height !== Math.floor(h * renderer.getPixelRatio())) {
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  const dt = Math.min(0.1, (now - lastNow) / 1000);
  lastNow = now;
  if (lab && sceneNo >= 3) {
    const swinging = lab.swinging;
    lab.update(now, dt);
    // live fluoroscopy: re-render the image whenever the catheter moves, the contrast changes, or the heart beats
    const moved = sceneNo === 5 && cath ? cath.update(dt) : false;
    if (sceneNo >= 4 && !swinging && (moved || lab.angio.fieldOn.value > 0)) lab.renderImage();
    if (swinging && !tween && (labCam === "beam" || labCam === "split")) {   // these cameras ride with the C-arm
      const p = labPose(labCam);
      camera.up.copy(p.up); camera.position.copy(p.pos); controls.target.copy(p.target); camera.lookAt(p.target);
    }
  }
  if (!tween) controls.update();
  const split = sceneNo === 4 && labCam === "split" && lab;
  if (split) {
    // left half: the heart from the detector side; right half: the image (square, centred)
    const half = Math.floor(w / 2);
    camera.aspect = half / h;
    camera.updateProjectionMatrix();
    renderer.setViewport(0, 0, half, h);
    renderer.setScissor(0, 0, half, h);
    renderer.setScissorTest(true);
    renderer.render(scene, camera);
    renderer.setScissorTest(false);
    renderer.setViewport(0, 0, w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    blitInto($("splitImage"));
  } else {
    renderer.render(scene, camera);
    if (lab && (sceneNo === 4 || sceneNo === 5)) blitInto($("monitorImage"));
  }
  requestAnimationFrame(tick);
}

caption("Loading the atlas…");
load().then(() => {
  const sp = Number(params.get("scene") ?? 1);
  /** Review hook: freeze the contrast at a fraction of the fill (Scene 5), with the reflux puff at its peak if early. */
  const cathFill = (frac: number) => {
    if (!cath || !lab) return;
    const max = (cath as unknown as { data: { trees: Record<string, { max_distance_mm: number }> } }).data.trees[cathTarget].max_distance_mm;
    lab.angio.fill.value.set(-8 + (max + 8) * frac, -1e9);
    lab.renderImage();
  };
  const hooks = () => ((window as unknown as Record<string, unknown>).atlas = { showScene, setView, setHeartView, setRoutes, showLab,
    setCArmView, setLabCam, setInject, lab, cath, setCathAccess, setCathTarget, setBeat, cathFill });
  if ((sp === 3 || sp === 4 || sp === 5) && lab) {
    // ?scene=3|4|5&carm=ap|rao30|lao45|raocaud|spider&cam=room|operator|beam|split|root&inject=left|right
    //  Scene 3: &op=femoral|radial.  Scene 5: &access=femoral|radial&target=left|right&engaged&fill=0..1 (review, recording)
    const cv = params.get("carm") ?? "ap";
    const V = CARM_VIEWS[cv] ?? CARM_VIEWS.ap;
    carmView = CARM_VIEWS[cv] ? cv : "ap";
    lab.setPose(V.a, V.b);
    if (params.get("inject") === "right") lab.injected = "right";
    if (params.get("op") === "radial") operatorAccess = "radial";
    if (params.get("access") === "radial") cathAccess = "radial_right";
    if (params.get("target") === "right") cathTarget = "right";
    labCam = (params.get("cam") as LabCam) ?? (sp === 5 ? "operator" : "room");
    bodyGroup.visible = true;
    fade = 1;
    showLab(sp as 3 | 4 | 5, 0);
    if (sp === 4 && labCam !== "split") caption(V.caption);
    if (sp >= 4) { lab.setXray(true, false); }
    if (sp === 5 && params.has("engaged")) {
      cath!.engageNow();
      if (params.has("fill")) cathFill(Number(params.get("fill")));
      else lab.renderImage();
    }
    requestAnimationFrame(tick);
    requestAnimationFrame(() => requestAnimationFrame(() => (document.body.dataset.ready = "1")));
    hooks();
    return;
  }
  const s = sp === 2 ? 2 : 1;
  const v = params.get("view") ?? (s === 1 ? "front" : "front");
  currentView = s === 1 && v === "lao" ? "lao" : "front";
  bodyGroup.visible = s === 2;
  fade = s === 2 ? 1 : 0;
  showScene(s, 0);
  if (s === 1 && v === "lao") { moveTo(poseFor("lao", HEART_DIST), 0); caption(DIRS.lao.caption); }
  if (s === 1 && v === "root") setHeartView("root", 0);
  if (s === 2 && v !== "front") setView(v, 0);
  if (params.has("routes")) setRoutes(true);          // review only: the catheter access routes stay hidden in the scenes
  if (params.has("label")) setLabelMode(true);
  requestAnimationFrame(tick);
  requestAnimationFrame(() => requestAnimationFrame(() => (document.body.dataset.ready = "1")));
  // automation hooks for the review recording (same code paths as the buttons)
  hooks();
}).catch((e) => { caption(String(e)); throw e; });
