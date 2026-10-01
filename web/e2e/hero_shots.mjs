// Hero look review: 4 screenshots at RAO 30 / CAUD 25 + a recording of the C-arm swinging from AP.
//   node e2e/hero_shots.mjs [views...]   (views: room heart beam split video)
import { mkdirSync, renameSync, readdirSync } from "node:fs";
import { chromium } from "playwright";
import { createServer } from "vite";
const want = process.argv.slice(2).length ? process.argv.slice(2) : ["room", "heart", "beam", "split", "video"];
const out = new URL("../../out/review/hero/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
mkdirSync(out, { recursive: true });
const server = await createServer({ server: { port: 5179, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu-rasterization"] });
const vp = { width: 1600, height: 1000 };
for (const v of want.filter((x) => x !== "video")) {
  const page = await browser.newPage({ viewport: vp });
  page.on("pageerror", (e) => console.log("pageerror", String(e)));
  await page.goto(`http://localhost:5179/?case=Normal_12&e2e=1&simple=1&alpha=-30&beta=-25&inject=left&hero_view=${v}`);
  await page.waitForSelector("body[data-ready='1']", { timeout: 180000 });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${out}hero_${v}.png`, timeout: 120000 });
  console.log("wrote", v);
  await page.close();
}
if (want.includes("video")) {
  const ctx = await browser.newContext({ viewport: vp, recordVideo: { dir: out, size: vp } });
  const page = await ctx.newPage();
  await page.goto(`http://localhost:5179/?case=Normal_12&e2e=1&simple=1&inject=left&hero_view=room&swing=0,0:-30,-25&swing_delay=2500&swing_ms=3500`);
  await page.waitForSelector("body[data-ready='1']", { timeout: 180000 });
  await page.waitForTimeout(8000);
  const vid = page.video();
  await ctx.close();
  const p = await vid.path();
  renameSync(p, `${out}hero_swing_AP_to_RAO30_CAUD25.webm`);
  console.log("wrote video");
}
await browser.close(); await server.close();
