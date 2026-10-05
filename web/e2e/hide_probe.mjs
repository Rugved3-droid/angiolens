// Hides named meshes one at a time and screenshots, to identify an object in a review shot.
//   node e2e/hide_probe.mjs "scene=6&carm=raocaud&still" "Superior vena cava" "Inferior vena cava (thoracic part)" ...
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";
import { createServer } from "vite";
const [q, ...names] = process.argv.slice(2);
const out = new URL("../../out/review/v1_1/probe/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
mkdirSync(out, { recursive: true });
const server = await createServer({ server: { port: 5193, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.goto(`http://localhost:5193/atlas.html?${q}`);
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
await page.waitForTimeout(2500);
await page.screenshot({ path: `${out}none.png`, clip: { x: 0, y: 60, width: 640, height: 700 } });
for (const [i, n] of names.entries()) {
  const found = await page.evaluate((n) => {
    let k = 0;
    window.atlas.dbg.scene.traverse((o) => { if (o.isMesh && (o.userData?.anatomical_name ?? o.name) === n) { o.userData.wasVisible = o.visible; o.visible = false; k++; } });
    return k;
  }, n);
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${out}hide_${i}.png`, clip: { x: 0, y: 60, width: 640, height: 700 } });
  console.log(`hide_${i}.png: "${n}" (${found} meshes)`);
  await page.evaluate((n) => window.atlas.dbg.scene.traverse((o) => { if (o.isMesh && (o.userData?.anatomical_name ?? o.name) === n) o.visible = o.userData.wasVisible; }), n);
}
await browser.close(); await server.close();
