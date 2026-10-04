// Prints, per C-arm fade group, its distance from the camera and its alpha in a given view (D60 quality pass).
//   node e2e/fade_probe.mjs "scene=5&carm=spider&engaged"
import { chromium } from "playwright";
import { createServer } from "vite";
const q = process.argv[2] ?? "scene=5&carm=spider&engaged";
const server = await createServer({ server: { port: 5189, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.goto(`http://localhost:5189/atlas.html?${q}`);
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
await page.waitForTimeout(3000);
const res = await page.evaluate(() => {
  const lab = window.atlas.lab;
  const cam = window.atlas.dbg.renderer && window.atlas.lab ? null : null;
  const out = [];
  const camPos = window.atlas.dbg.camera?.position;
  for (const g of lab.fadeGroups) {
    const m = g.meshes[0];
    m.geometry.computeBoundingSphere();
    const s = m.geometry.boundingSphere.clone().applyMatrix4(m.matrixWorld);
    out.push({ name: m.name || m.geometry.type, n: g.meshes.length, r: Math.round(s.radius), a: +g.a.toFixed(2),
      d: camPos ? Math.round(s.center.distanceTo(camPos) - s.radius) : null });
  }
  return out;
});
console.log(JSON.stringify(res, null, 0));
await browser.close(); await server.close();
