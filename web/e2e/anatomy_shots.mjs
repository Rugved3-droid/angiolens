// Debug-viewer screenshots of the Z-Anatomy export (anterior, left/right lateral, superior, inferior).
//   copy assets/anatomy/*.glb -> web/public/anatomy/ first;  node e2e/anatomy_shots.mjs
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";
import { createServer } from "vite";
const out = new URL("../../out/review/anatomy/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
mkdirSync(out, { recursive: true });
const server = await createServer({ server: { port: 5179, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
for (const v of (process.argv.slice(2).length ? process.argv.slice(2) : ["anterior", "left", "right", "superior", "inferior", "heart_anterior", "heart_lao"])) {
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  page.on("pageerror", (e) => console.log("pageerror", String(e)));
  await page.goto(`http://localhost:5179/anatomy.html?view=${v}`);
  await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${out}zanatomy_${v}.png`, timeout: 120000 });
  console.log("wrote", v);
  await page.close();
}
await browser.close(); await server.close();
