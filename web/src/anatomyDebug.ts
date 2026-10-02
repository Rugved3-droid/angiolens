// TEMPORARY debug viewer for the Z-Anatomy export. NOT connected to the C-arm or projection code.
// World = canonical LPS-oriented atlas frame (mm): +X patient left, +Y posterior, +Z superior. Nothing is moved here.
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

const CORONARY_COLORS: Record<string, string> = {
  "Left coronary artery": "#ffffff",
  "Anterior interventricular artery": "#00c8ff",
  "Septal branches of anterior interventricular artery": "#7ef0ff",
  "Circumflex artery of heart": "#39ff6a",
  "Right coronary artery": "#ff2d2d",
  "Right inferolateral branch of right coronary artery": "#ffa02d",
};
const CHAMBERS = new Set(["Left ventricle", "Right ventricle", "Left atrium", "Right atrium"]);
// per-spline branches (LAD_branch_NN ...): one hue family per parent vessel, distinct colour per branch
const FAMILY: Record<string, [number, number]> = { LAD: [185, 250], LCx: [75, 150], RCA: [330, 395] };
function branchColor(name: string): string | null {
  const m = /^(LAD|LCx|RCA)_branch_(\d+)$/.exec(name);
  if (!m) return null;
  const [h0, h1] = FAMILY[m[1]];
  const i = Number(m[2]) - 1;
  const n = m[1] === "RCA" ? 14 : 6;
  const h = (h0 + ((h1 - h0) * ((i * 7) % n)) / Math.max(n - 1, 1)) % 360;
  return `hsl(${h}, 95%, ${i % 2 ? 62 : 50}%)`;
}
const params = new URLSearchParams(location.search);
const closeUp = (params.get("view") ?? "").startsWith("heart_");

const canvas = document.getElementById("c") as HTMLCanvasElement;
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
const scene = new THREE.Scene();
scene.background = new THREE.Color("#101318");
const camera = new THREE.PerspectiveCamera(30, 1, 1, 20000);
const controls = new OrbitControls(camera, canvas);
scene.add(new THREE.HemisphereLight("#ffffff", "#30343c", 1.2));
const key = new THREE.DirectionalLight("#ffffff", 1.6);
camera.add(key);
key.position.set(300, 400, 600);
scene.add(camera);

const nameOf = (o: THREE.Object3D) => (o.userData?.anatomical_name as string) ?? o.name;
const pickables: THREE.Mesh[] = [];
let heartCentre = new THREE.Vector3();

function assertVerbatim(root: THREE.Object3D, file: string) {
  root.updateMatrixWorld(true);
  root.traverse((o) => {
    if ((o as THREE.Mesh).isMesh && !o.matrixWorld.equals(new THREE.Matrix4()))
      throw new Error(`${file}: node "${nameOf(o)}" has a non-identity transform; export must bake LPS mm into vertices`);
  });
}

async function load() {
  const loader = new GLTFLoader();
  const [skel, heart] = await Promise.all([
    loader.loadAsync("/anatomy/z_anatomy_skeleton.glb"), loader.loadAsync("/anatomy/z_anatomy_heart.glb"),
  ]);
  assertVerbatim(skel.scene, "skeleton");
  assertVerbatim(heart.scene, "heart");
  skel.scene.traverse((o) => {
    if (!(o as THREE.Mesh).isMesh) return;
    (o as THREE.Mesh).material = new THREE.MeshLambertMaterial({ color: "#e8e0cc", transparent: true, opacity: 0.2, depthWrite: false });
    o.renderOrder = 2;
  });
  const legend: string[] = [];
  heart.scene.traverse((o) => {
    if (!(o as THREE.Mesh).isMesh) return;
    const m = o as THREE.Mesh;
    const n = nameOf(o);
    const bc = branchColor(n);
    if (bc) {
      m.material = new THREE.MeshStandardMaterial({ color: bc, emissive: bc, emissiveIntensity: 0.5, roughness: 0.35 });
      m.material.visible = closeUp;
      m.renderOrder = 4;
      if (closeUp) legend.push(`<div><span class="sw" style="background:${bc}"></span>${n} <i>(spline ${o.userData.spline_index} of ${o.userData.parent_vessel})</i></div>`);
      pickables.push(m);
      return;
    }
    if (CORONARY_COLORS[n]) {
      m.material = new THREE.MeshStandardMaterial({ color: CORONARY_COLORS[n], emissive: CORONARY_COLORS[n], emissiveIntensity: 0.55, roughness: 0.4 });
      m.renderOrder = 3;
      const split = o.children.some((c) => /_branch_\d+$/.test(nameOf(c)));
      if (closeUp && split) (m.material as THREE.Material).visible = false; // shown as its separately coloured splines
      if (!(closeUp && split)) legend.push(`<div><span class="sw" style="background:${CORONARY_COLORS[n]}"></span>${n} <i>(${o.userData.source_object_type})</i></div>`);
    } else if (CHAMBERS.has(n) || /papillary/i.test(n)) {
      m.material = new THREE.MeshStandardMaterial({ color: "#8c3a30", roughness: 0.6 });
    } else if (/vein|sinus/i.test(n) || o.userData.source_parent === "Cardiac veins.g") {
      m.material = new THREE.MeshStandardMaterial({ color: "#4a5fa8", roughness: 0.6 });
    } else {
      m.material = new THREE.MeshStandardMaterial({ color: "#c9b8a8", roughness: 0.6, transparent: true, opacity: 0.55 });
    }
    pickables.push(m);
  });
  skel.scene.visible = !closeUp;
  scene.add(skel.scene, heart.scene);
  const box = new THREE.Box3();
  heart.scene.traverse((o) => { if ((o as THREE.Mesh).isMesh && CHAMBERS.has(nameOf(o))) box.expandByObject(o); });
  heartCentre = box.getCenter(new THREE.Vector3());
  document.getElementById("legend")!.innerHTML = (closeUp ? "<b>Coronaries: per-spline branches (unnamed; label in Label mode)</b>" : "<b>Coronary objects (from the hierarchy)</b>") + legend.sort().join("");
  addAxes(heartCentre.clone().add(closeUp ? new THREE.Vector3(-75, -40, 60) : new THREE.Vector3(-170, -60, 120)), closeUp ? 30 : 70);
}

function label(text: string, color: string, pos: THREE.Vector3, size = 26) {
  const c = document.createElement("canvas");
  c.width = 256; c.height = 128;
  const g = c.getContext("2d")!;
  g.font = "bold 96px system-ui"; g.textAlign = "center"; g.textBaseline = "middle";
  g.lineWidth = 10; g.strokeStyle = "#000"; g.strokeText(text, 128, 64);
  g.fillStyle = color; g.fillText(text, 128, 64);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), depthTest: false }));
  s.scale.set(size * 2, size, 1);
  s.position.copy(pos);
  s.renderOrder = 10;
  scene.add(s);
}

function addAxes(o: THREE.Vector3, L = 70) {
  for (const [dir, pos, neg, color] of [[new THREE.Vector3(1, 0, 0), "L", "R", "#ff5c5c"], [new THREE.Vector3(0, 1, 0), "P", "A", "#5cdc5c"],
    [new THREE.Vector3(0, 0, 1), "S", "I", "#6aa8ff"]] as [THREE.Vector3, string, string, string][]) {
    scene.add(new THREE.ArrowHelper(dir, o, L, new THREE.Color(color).getHex(), 12, 7));
    scene.add(new THREE.ArrowHelper(dir.clone().negate(), o, L * 0.6, new THREE.Color(color).multiplyScalar(0.5).getHex(), 0.01, 0.01));
    label(pos, color, o.clone().addScaledVector(dir, L + L * 0.23), L * 0.37);
    label(neg, "#bbbbbb", o.clone().addScaledVector(dir, -(L * 0.6 + L * 0.2)), L * 0.29);
  }
}

const VIEWS: Record<string, { dir: THREE.Vector3; up: THREE.Vector3; title: string }> = {
  anterior: { dir: new THREE.Vector3(0, -1, 0), up: new THREE.Vector3(0, 0, 1), title: "ANTERIOR view (from the front): patient's LEFT is on the viewer's RIGHT" },
  left: { dir: new THREE.Vector3(1, 0, 0), up: new THREE.Vector3(0, 0, 1), title: "LEFT LATERAL view (from the patient's left)" },
  right: { dir: new THREE.Vector3(-1, 0, 0), up: new THREE.Vector3(0, 0, 1), title: "RIGHT LATERAL view (from the patient's right)" },
  superior: { dir: new THREE.Vector3(0, 0, 1), up: new THREE.Vector3(0, -1, 0), title: "SUPERIOR view (from the head), anterior up" },
  inferior: { dir: new THREE.Vector3(0, 0, -1), up: new THREE.Vector3(0, -1, 0), title: "INFERIOR view (from the FEET), anterior up: patient's LEFT on the viewer's RIGHT" },
  heart_anterior: { dir: new THREE.Vector3(0, -1, 0), up: new THREE.Vector3(0, 0, 1), title: "HEART close-up, ANTERIOR (patient's left on the viewer's right)" },
  heart_lao: { dir: new THREE.Vector3(0.7, -0.7, 0.12).normalize(), up: new THREE.Vector3(0, 0, 1), title: "HEART close-up, LAO-ish (from the front-left)" },
};

function setView(v: string) {
  const V = VIEWS[v];
  camera.up.copy(V.up);
  camera.position.copy(heartCentre).addScaledVector(V.dir, v.startsWith("heart_") ? 330 : 780);
  controls.target.copy(heartCentre);
  camera.lookAt(heartCentre);
  controls.update();
  document.getElementById("view")!.textContent = V.title;
}

const ray = new THREE.Raycaster();
canvas.addEventListener("pointermove", (e) => {
  ray.setFromCamera(new THREE.Vector2((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1), camera);
  const h = ray.intersectObjects(pickables, false)[0];
  const u = h?.object.userData ?? {};
  document.getElementById("hover")!.textContent = h ? `${nameOf(h.object)}  [${u.source_object_type ?? "?"}]${u.parent_vessel ? ` spline ${u.spline_index} of ${u.parent_vessel}` : ""}` : "";
});

function frame() {
  renderer.setSize(innerWidth, innerHeight, false);
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}

load().then(() => {
  document.querySelectorAll<HTMLButtonElement>("#bar button").forEach((b) => (b.onclick = () => setView(b.dataset.v!)));
  setView(new URLSearchParams(location.search).get("view") ?? "anterior");
  document.body.dataset.ready = "1";
  frame();
}).catch((e) => { document.getElementById("view")!.textContent = String(e); throw e; });
