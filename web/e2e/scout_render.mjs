// Scouting renders (v1.1 item 4; report only): each candidate in three.js with the atlas's lighting (camera-carried warm key,
// cool rim, soft fill, hemisphere, RoomEnvironment), from the FRONT like the Z-Anatomy heart close-up, framed to fit.
//   node e2e/scout_render.mjs UID ...   -> out/review/scouting/render_<uid>.png and scout_compare.png (with the Z-Anatomy shot)
// glTF is +Y up; Sketchfab exports face +Z. Orientation is a guess per model (listed in SCOUTING.md); nothing is integrated.
import { mkdirSync, writeFileSync } from "node:fs";
import { chromium } from "playwright";
import { createServer } from "vite";
const out = new URL("../../out/review/scouting/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
mkdirSync(out, { recursive: true });
const repo = new URL("../../", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
const server = await createServer({ server: { port: 5201, strictPort: true, fs: { allow: [repo] } } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: 900, height: 940 } });
page.on("pageerror", (e) => console.log("pageerror", String(e)));
page.on("console", (m) => m.type() === "error" && console.log("console", m.text()));
await page.goto("http://localhost:5201/atlas.html?scene=1&still");   // any page: we only need the module graph
const uids = process.argv.slice(2);
for (const uid of uids) {
  const png = await page.evaluate(async ({ uid, repo }) => {
    const THREE = await import("/node_modules/.vite/deps/three.js").catch(() => import("three"));
    const { GLTFLoader } = await import("/node_modules/three/examples/jsm/loaders/GLTFLoader.js");
    const { RoomEnvironment } = await import("/node_modules/three/examples/jsm/environments/RoomEnvironment.js");
    const cv = document.createElement("canvas"); cv.width = 900; cv.height = 900;
    const r = new THREE.WebGLRenderer({ canvas: cv, antialias: true, preserveDrawingBuffer: true });
    r.toneMapping = THREE.ACESFilmicToneMapping; r.outputColorSpace = THREE.SRGBColorSpace;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#141820");
    scene.environment = new THREE.PMREMGenerator(r).fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environmentIntensity = 0.55;
    const cam = new THREE.PerspectiveCamera(30, 1, 0.001, 1000);
    const key = new THREE.DirectionalLight("#fff1e4", 2.1); key.position.set(-0.6, 0.8, 0.9);
    const rim = new THREE.DirectionalLight("#a9cbff", 1.5); rim.position.set(0.7, 0.3, -1.0);
    const fill = new THREE.DirectionalLight("#ffd9cc", 0.45); fill.position.set(0.8, -0.4, 0.6);
    for (const l of [key, rim, fill]) { cam.add(l); cam.add(l.target); }
    scene.add(cam, new THREE.HemisphereLight("#fff4ee", "#1a1e26", 0.35));
    const gltf = await new GLTFLoader().loadAsync(`/@fs/${repo}assets/candidates/${uid}/model.glb`);
    scene.add(gltf.scene);
    gltf.scene.traverse((o) => { if (o.isMesh && o.geometry.getAttribute("color")) { const mats = Array.isArray(o.material) ? o.material : [o.material];
      for (const m of mats) m.vertexColors = true; } });
    const box = new THREE.Box3().setFromObject(gltf.scene);
    const c = box.getCenter(new THREE.Vector3()), s = box.getSize(new THREE.Vector3());
    const R = Math.max(s.x, s.y) / 2 / Math.tan(THREE.MathUtils.degToRad(15)) * 1.12 + s.z / 2;
    cam.position.set(c.x, c.y, c.z + R); cam.lookAt(c); cam.updateMatrixWorld();
    r.render(scene, cam);
    const url = cv.toDataURL("image/png");
    r.dispose();
    return url;
  }, { uid, repo });
  writeFileSync(`${out}render_${uid}.png`, Buffer.from(png.split(",")[1], "base64"));
  console.log("rendered", uid);
}
await browser.close(); await server.close();
