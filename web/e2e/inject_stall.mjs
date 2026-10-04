// Diagnoses a stall at the first injection: frame times and shader-program count around injectCath() (quality pass, D60).
//   node e2e/inject_stall.mjs
import { chromium } from "playwright";
import { createServer } from "vite";
const server = await createServer({ server: { port: 5187, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
page.on("pageerror", (e) => console.log("pageerror", String(e)));
await page.goto("http://localhost:5187/atlas.html?scene=5&cam=operator&engaged");
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
await page.waitForTimeout(6000);
const res = await page.evaluate(async () => {
  const A = window.atlas, r = A.dbg.renderer;
  const progs0 = r.info.programs.length;
  const times = [];
  let last = performance.now();
  let run = true;
  const f = () => { const t = performance.now(); times.push(Math.round(t - last)); last = t; if (run) requestAnimationFrame(f); };
  requestAnimationFrame(f);
  await new Promise((res) => setTimeout(res, 500));
  const t0 = performance.now();
  A.injectCath();
  const tCall = performance.now() - t0;
  await new Promise((res) => setTimeout(res, 2500));
  run = false;
  return { tCall: Math.round(tCall), progs0, progs1: r.info.programs.length, slow: times.map((t, i) => [i, t]).filter(([, t]) => t > 25) };
});
console.log(JSON.stringify(res));
await browser.close(); await server.close();
