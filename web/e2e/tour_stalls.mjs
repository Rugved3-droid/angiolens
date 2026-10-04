// Plays the guided tour WITHOUT recording and logs every slow frame (> 50 ms) with the tour step and caption (quality pass, D60).
//   node e2e/tour_stalls.mjs
import { chromium } from "playwright";
import { createServer } from "vite";
const server = await createServer({ server: { port: 5187, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
page.on("pageerror", (e) => { console.log("pageerror", String(e)); process.exitCode = 1; });
await page.goto("http://localhost:5187/atlas.html?scene=1");
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
await page.waitForTimeout(1500);
const r = await page.evaluate(async () => {
  const slow = [];
  let last = performance.now(), frames = 0, over22 = 0, run = true;
  const f = (now) => {
    const dt = now - last; last = now; frames++;
    if (dt > 22.2) over22++;
    if (dt > 50) slow.push({ t: Math.round(now), dt: Math.round(dt), dots: [...document.querySelectorAll("#tDots .dot")].findIndex((d) => d.classList.contains("on")),
      caption: document.getElementById("caption").textContent.slice(0, 60) });
    if (run) requestAnimationFrame(f);
  };
  requestAnimationFrame(f);
  const t0 = performance.now();
  window.atlas.startTour();
  await new Promise((res) => { const g = () => (document.getElementById("tourBar").style.display === "none" && performance.now() - t0 > 3000) || performance.now() - t0 > 150000 ? res() : setTimeout(g, 250); g(); });
  run = false;
  return { seconds: (performance.now() - t0) / 1000, frames, framesSlowerThan45fps: over22, slow };
});
console.log(JSON.stringify({ seconds: Math.round(r.seconds), meanFps: Math.round(r.frames / r.seconds), framesSlowerThan45fps: r.framesSlowerThan45fps }));
for (const s of r.slow) console.log(`  stall ${s.dt} ms at step ${s.dots}: ${s.caption}`);
await browser.close(); await server.close();
