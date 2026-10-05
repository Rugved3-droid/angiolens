// v1.1 peel mode (feature flag "peel"):  node e2e/peel.e2e.mjs
// Drag a peelable -> it slides along its direction; release -> it springs back; double-click -> removed; Reset -> all back.
// Peeling never touches the X-ray: the angiogram is byte-identical before and after. The mini-tour runs to its end.
import { chromium } from "playwright";
import { createServer } from "vite";
const server = await createServer({ server: { port: 5198, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const fail = (m) => { console.log("FAIL", m); process.exitCode = 1; };
const ok = (m) => console.log("PASS", m);
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
page.on("pageerror", (e) => fail(`pageerror ${e}`));
await page.goto("http://localhost:5198/atlas.html?scene=1&ff=peel&still");
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
await page.waitForTimeout(2500);

// the X-ray before any peel (left tree, RAO 30 / CAUD 25)
const xray = () => page.evaluate(() => { const { lab } = window.atlas; lab.setPose(-30, -25); lab.renderImage();
  const img = lab.angio.readImage(); let h = 0; for (let i = 0; i < img.length; i += 7) h = (h * 31 + img[i]) >>> 0; return h; });
const x0 = await xray();

// screen point of the pulmonary trunk (its world centre, projected)
const pt = await page.evaluate(() => {
  const { scene, camera } = window.atlas.dbg;
  let m = null; scene.traverse((o) => { if (o.isMesh && (o.userData?.anatomical_name ?? o.name) === "Pulmonary trunk") m = o; });
  m.geometry.computeBoundingBox(); const c = m.geometry.boundingBox.getCenter(new m.position.constructor()).project(camera);
  const r = window.atlas.dbg.renderer.domElement.getBoundingClientRect();
  return { x: r.left + (c.x + 1) / 2 * r.width, y: r.top + (1 - c.y) / 2 * r.height };
});
const pos = () => page.evaluate(() => { let m = null; window.atlas.dbg.scene.traverse((o) => { if (o.isMesh && (o.userData?.anatomical_name ?? o.name) === "Pulmonary trunk") m = o; });
  return m.position.length(); });
await page.mouse.move(pt.x, pt.y);
await page.mouse.down();
await page.mouse.move(pt.x + 10, pt.y - 60, { steps: 8 });
await page.mouse.move(pt.x + 20, pt.y - 160, { steps: 8 });
await page.waitForTimeout(200);
const held = await pos();
await page.mouse.up();
await page.waitForTimeout(1600);
const back = await pos();
if (held > 15 && back < 0.5) ok(`drag peels the pulmonary trunk ${held.toFixed(0)} mm; on release it springs back (${back.toFixed(2)} mm)`);
else fail(`drag/spring ${held} -> ${back}`);

await page.mouse.dblclick(pt.x, pt.y);
await page.waitForTimeout(2200);
const removed = await page.evaluate(() => { let m = null; window.atlas.dbg.scene.traverse((o) => { if (o.isMesh && (o.userData?.anatomical_name ?? o.name) === "Pulmonary trunk") m = o; });
  return { d: m.position.length(), vis: m.visible, peeled: window.atlas.peel.anyPeeled }; });
if (removed.d > 100 && !removed.vis) ok("double-click keeps it removed");
else fail(`double-click ${JSON.stringify(removed)}`);
const resetEnabled = await page.evaluate(() => !document.getElementById("bPeelReset").disabled);
await page.click("#bPeelReset");
await page.waitForTimeout(2200);
const after = await page.evaluate(() => { let m = null; window.atlas.dbg.scene.traverse((o) => { if (o.isMesh && (o.userData?.anatomical_name ?? o.name) === "Pulmonary trunk") m = o; });
  return { d: m.position.length(), vis: m.visible }; });
if (resetEnabled && after.d < 0.5 && after.vis) ok("Reset restores it");
else fail(`reset ${resetEnabled} ${JSON.stringify(after)}`);

// every peelable part can be peeled and comes back
const parts = await page.evaluate(async () => {
  const p = window.atlas.peel; const out = {};
  for (const k of ["fat", "pulmonary", "laa", "raa", "ra", "aorta"]) { p.hold(k, 40); }
  await new Promise((r) => setTimeout(r, 1500));
  window.atlas.dbg.scene.traverse((o) => { if (o.isMesh && o.position.length() > 30) out[o.userData?.anatomical_name ?? o.name] = Math.round(o.position.length()); });
  p.reset(true);
  return out;
});
const names = Object.keys(parts);
const want = ["Epicardial fat (illustrative)", "Pulmonary trunk", "Left atrial appendage", "Right atrial appendage", "Right atrium", "Aorta"];
if (want.every((n) => names.includes(n))) ok(`all six peelable structures move: ${want.join(", ")}`);
else fail(`moved: ${names.join(", ")}`);

// the X-ray is unchanged by peeling (display transforms only)
await page.evaluate(() => { const p = window.atlas.peel; for (const k of ["fat", "pulmonary", "laa", "raa", "ra", "aorta"]) p.hold(k, 115); });
await page.waitForTimeout(1500);
const x1 = await xray();
await page.evaluate(() => window.atlas.peel.reset(true));
if (x0 === x1) ok("the X-ray is byte-identical with everything peeled (display transforms only)");
else fail("the X-ray changed while peeled");

// the mini-tour runs to its end and leaves the full tree visible
await page.evaluate(() => window.atlas.goScene(1, 0));
await page.waitForTimeout(800);
const t0 = Date.now();
await page.evaluate(() => window.atlas.runOrigins());
const final = await page.evaluate(() => document.getElementById("caption").textContent);
const peeledAtEnd = await page.evaluate(() => window.atlas.peel.anyPeeled);
if (final.includes("full coronary tree") && peeledAtEnd) ok(`mini-tour "Where do the coronaries come from?" ran in ${((Date.now() - t0) / 1000).toFixed(0)} s`);
else fail(`mini-tour ended with "${final}"`);
await browser.close(); await server.close();
