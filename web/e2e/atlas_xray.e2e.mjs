// Scene 4's angiogram is the validated engine on the atlas: the GPU path length (angio.ts) of each closed atlas tree must
// match the exact CPU mesh renderer (preprocess/cpt/meshrender.py, fixtures from atlas_xray_fixtures.py) at the standard
// views, and its left-right and up-down MIRROR images must fail the same comparison (no display flips anywhere). D50.
import { chromium } from "playwright";
import { createServer } from "vite";
const server = await createServer({ server: { port: 5183, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
page.on("pageerror", (e) => { console.log("pageerror", String(e)); process.exitCode = 1; });
await page.goto("http://localhost:5183/atlas.html?scene=4&carm=ap&cam=room");
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
const res = await page.evaluate(async () => {
  const lab = window.atlas.lab;
  const index = await (await fetch("/anatomy/xray_ref_index.json")).json();
  const corr = (a, b) => {
    let ma = 0, mb = 0; for (let i = 0; i < a.length; i++) { ma += a[i]; mb += b[i]; } ma /= a.length; mb /= b.length;
    let sab = 0, saa = 0, sbb = 0;
    for (let i = 0; i < a.length; i++) { const x = a[i] - ma, y = b[i] - mb; sab += x * y; saa += x * x; sbb += y * y; }
    return sab / Math.sqrt(saa * sbb);
  };
  const out = [];
  for (const f of index) {
    const ref = new Float32Array(await (await fetch(`/anatomy/${f.file}`)).arrayBuffer());
    lab.injected = f.tree;
    lab.setPose(f.alpha, f.beta);
    lab.renderImage();
    const { thickness: gpu, repaired } = lab.angio.readThickness();
    const n = f.px;
    const lr = new Float32Array(n * n), ud = new Float32Array(n * n);
    for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) { lr[r * n + c] = gpu[r * n + (n - 1 - c)]; ud[r * n + c] = gpu[(n - 1 - r) * n + c]; }
    let mae = 0, cnt = 0;
    for (let i = 0; i < ref.length; i++) if (ref[i] > 0 || gpu[i] > 0) { mae += Math.abs(ref[i] - gpu[i]); cnt++; }
    out.push({ pose: `${f.tree} ${f.alpha},${f.beta}`, r: corr(gpu, ref), mae: mae / cnt, repaired, rLR: corr(lr, ref), rUD: corr(ud, ref) });
  }
  // the cine field (D53): with the heartbeat on, the X-ray geometry follows the 3D heart's field (the image must CHANGE);
  // with it off again, the static frame is the validated one (r = 1 against the CPU reference)
  const f = index.find((x) => x.tree === "left" && x.alpha === -30 && x.beta === -25);
  const ref = new Float32Array(await (await fetch(`/anatomy/${f.file}`)).arrayBuffer());
  lab.injected = "left"; lab.setPose(f.alpha, f.beta);
  window.atlas.setBeat(true);
  let rMin = 1;
  for (let k = 0; k < 30; k++) {                       // sample a heartbeat: the field runs in the frame loop
    await new Promise((r) => requestAnimationFrame(r));
    lab.renderImage();
    rMin = Math.min(rMin, corr(lab.angio.readThickness().thickness, ref));
    await new Promise((r) => setTimeout(r, 30));
  }
  window.atlas.setBeat(false);
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  lab.renderImage();
  out.push({ cine: true, rMinBeating: rMin, rStill: corr(lab.angio.readThickness().thickness, ref) });
  return out;
});
for (const x of res) {
  if (x.cine) {
    const ok = x.rMinBeating < 0.995 && x.rStill > 0.9999;
    if (!ok) process.exitCode = 1;
    console.log(`${ok ? "PASS" : "FAIL"} cine field: beating min r=${x.rMinBeating.toFixed(4)} (must move), beat off r=${x.rStill.toFixed(5)} (static match)`);
    continue;
  }
  const ok = x.r > 0.95 && x.mae < 0.25 && x.rLR < 0.6 && x.rUD < 0.6;
  if (!ok) process.exitCode = 1;
  console.log(`${ok ? "PASS" : "FAIL"} ${x.pose}: r=${x.r.toFixed(4)} mae=${x.mae.toFixed(3)} mm, repaired px ${x.repaired} | mirrored L-R r=${x.rLR.toFixed(3)}, U-D r=${x.rUD.toFixed(3)}`);
}
await browser.close(); await server.close();
