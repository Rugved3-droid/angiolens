// Stills for tuning peel-tour cameras: node e2e/peel_probe.mjs  -> out/review/v1_1_peel/probe_*.png
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";
import { createServer } from "vite";
const out = new URL("../../out/review/v1_1_peel/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
mkdirSync(out, { recursive: true });
const server = await createServer({ server: { port: 5200, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.goto("http://localhost:5200/atlas.html?scene=1&ff=peel&still");
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
await page.waitForTimeout(2000);
const SHOTS = JSON.parse(process.argv[2] ?? "[]");   // [{name, peel:{key:mm}, at:"LM"|"RCA"|[x,y,z], dir:[..], dist}]
for (const s of SHOTS) {
  await page.evaluate((s) => {
    const A = window.atlas, p = A.peel; p.reset(true);
    for (const [k, mm] of Object.entries(s.peel ?? {})) p.hold(k, mm);
    const { camera, controls } = A.dbg;
    const t = Array.isArray(s.at) ? s.at : A.ostiaLPS[s.at];
    const n = Math.hypot(...s.dir);
    camera.position.set(t[0] + s.dir[0] / n * s.dist, t[1] + s.dir[1] / n * s.dist, t[2] + s.dir[2] / n * s.dist);
    camera.up.set(0, 0, 1); camera.lookAt(...t); controls.target.set(...t);
  }, s);
  await page.waitForTimeout(1800);
  await page.screenshot({ path: `${out}probe_${s.name}.png` });
  for (const [x, y] of s.pick ?? []) {
    await page.mouse.move(x, y); await page.waitForTimeout(300);
    console.log(s.name, x, y, await page.evaluate(() => { const e = document.getElementById("hover"); return e && e.style.display !== "none" ? e.textContent : "(nothing)"; }));
  }
}
await browser.close(); await server.close();
