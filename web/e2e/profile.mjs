// Frame-rate profile of one view: toggles layers off one at a time and reports fps and draw calls (quality pass, D60).
//   node e2e/profile.mjs "scene=5&carm=spider&engaged"
import { chromium } from "playwright";
import { createServer } from "vite";
const q = process.argv[2] ?? "scene=5&carm=spider&engaged";
const server = await createServer({ server: { port: 5186, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist", ...(process.env.UNCAPPED ? ["--disable-gpu-vsync", "--disable-frame-rate-limit"] : [])] });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
page.on("pageerror", (e) => console.log("pageerror", String(e)));
await page.goto(`http://localhost:5186/atlas.html?${q}&still`);   // still: no adaptive resolution while profiling
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
await page.waitForTimeout(7000);
const res = await page.evaluate(async () => {
  const { scene, renderer, bodyGroup } = window.atlas.dbg;
  const measure = () => new Promise((r) => { let n = 0; const t0 = performance.now();
    const f = () => { n++; if (performance.now() - t0 < 2000) requestAnimationFrame(f); else r(Math.round((n * 1000) / (performance.now() - t0))); };
    requestAnimationFrame(f); });
  const out = {};
  out.all = await measure();
  out.calls = renderer.info.render.calls; out.tris = renderer.info.render.triangles;
  const skel = bodyGroup.children[0], skin = bodyGroup.children[1];
  skel.visible = false; out.noSkeleton = await measure(); skel.visible = true;
  skin.visible = false; out.noSkin = await measure(); skin.visible = true;
  bodyGroup.visible = false; out.noBody = await measure(); bodyGroup.visible = true;
  const lab = window.atlas.lab;
  lab.rig.visible = false; out.noRig = await measure(); lab.rig.visible = true;
  lab.room.visible = false; out.noRoom = await measure(); lab.room.visible = true;
  const rg = window.atlas.dbg.routesGroup; const rv = rg.visible; rg.visible = false; out.noRoutes = await measure(); rg.visible = rv;
  out.prNow = renderer.getPixelRatio();
  const pr = renderer.getPixelRatio(); renderer.setPixelRatio(pr * 0.6); out.pixelRatio06 = await measure(); renderer.setPixelRatio(pr);
  return out;
});
console.log(q, JSON.stringify(res));
await browser.close(); await server.close();
