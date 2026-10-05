// Names what is under given screen points (the app's own hover tooltip): identifies objects seen in review shots.
//   node e2e/hover_probe.mjs "scene=6&carm=raocaud&still" 1280x800 120,280 640,900 ...
import { chromium } from "playwright";
import { createServer } from "vite";
const [q, size, ...pts] = process.argv.slice(2);
const [w, h] = size.split("x").map(Number);
const server = await createServer({ server: { port: 5192, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: w, height: h } });
await page.goto(`http://localhost:5192/atlas.html?${q}`);
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
await page.waitForTimeout(2500);
for (const p of pts) {
  const [x, y] = p.split(",").map(Number);
  await page.mouse.move(x, y);
  await page.waitForTimeout(400);
  const name = await page.evaluate(() => { const e = document.getElementById("hover"); return e && e.style.display !== "none" ? e.textContent : "(nothing)"; });
  console.log(`${x},${y}: ${name}`);
}
await browser.close(); await server.close();
