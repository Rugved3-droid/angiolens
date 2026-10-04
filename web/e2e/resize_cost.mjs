// How long does a render-scale change (canvas reallocation) stall a frame?   node e2e/resize_cost.mjs
import { chromium } from "playwright";
import { createServer } from "vite";
const server = await createServer({ server: { port: 5189, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.goto("http://localhost:5189/atlas.html?scene=5&cam=operator&engaged&still");
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
await page.waitForTimeout(2000);
const r = await page.evaluate(async () => {
  const { renderer } = window.atlas.dbg;
  const out = [];
  for (const pr of [0.9, 0.8, 1.0, 0.7, 1.0]) {
    let worst = 0, last = performance.now(), n = 0;
    await new Promise((res) => { const f = (now) => { worst = Math.max(worst, now - last); last = now; if (++n < 40) requestAnimationFrame(f); else res(); };
      renderer.setPixelRatio(pr); requestAnimationFrame(f); });
    out.push({ pr, worstFrameMs: Math.round(worst) });
  }
  return out;
});
console.log(JSON.stringify(r));
await browser.close(); await server.close();
