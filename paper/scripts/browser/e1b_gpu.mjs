// E1b browser side: the APP's GPU angiogram (atlas Scene 4, web/src/angio.ts) at every pose in paper/results/raw/e1b_input.json.
// Each image is the renderer's own readThickness() (vessel path length, mm, row 0 = top), sent back SPARSE (nonzero pixels).
// Output: paper/results/raw/e1b_gpu/<tree>_<a>_<b>.npy-like pair (idx int32 + val float32), plus repaired-pixel counts.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { argv, chromium, GPU_ARGS, REPO, startDev } from "./harness.mjs";

const raw = resolve(REPO, "paper", "results", "raw");
const inp = JSON.parse(readFileSync(resolve(raw, "e1b_input.json"), "utf8"));
const dir = resolve(raw, "e1b_gpu");
mkdirSync(dir, { recursive: true });
const server = await startDev(5192);
const browser = await chromium.launch({ args: GPU_ARGS[argv("gl", "d3d11")] });
const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
page.on("pageerror", (e) => { console.log("pageerror", String(e)); process.exitCode = 1; });
await page.goto("http://localhost:5192/atlas.html?scene=4&carm=ap&cam=room");
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
const info = await page.evaluate(async () => {
  window.atlas.setBeat(false);
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const gl = window.atlas.dbg.renderer.getContext();
  const ext = gl.getExtension("WEBGL_debug_renderer_info");
  return { px: window.atlas.lab.angio.px, detectorMm: window.atlas.lab.detectorMm,
    iso: [window.atlas.lab.iso.x, window.atlas.lab.iso.y, window.atlas.lab.iso.z],
    gpu: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER) };
});
const meta = { ...info, chromium: browser.version(), poses: [] };
let k = 0;
for (const [tree, a, b] of inp.poses) {
  const r = await page.evaluate(({ tree, a, b }) => {
    const lab = window.atlas.lab;
    lab.injected = tree;
    lab.setPose(a, b);
    lab.renderImage();
    const { thickness, repaired } = lab.angio.readThickness();
    const idx = [], val = [];
    for (let i = 0; i < thickness.length; i++) if (thickness[i] !== 0) { idx.push(i); val.push(thickness[i]); }
    const enc = (ta) => { const u = new Uint8Array(ta.buffer); let s = ""; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return btoa(s); };
    return { idx: enc(new Int32Array(idx)), val: enc(new Float32Array(val)), repaired, pose: [lab.carm.alphaDeg, lab.carm.betaDeg] };
  }, { tree, a, b });
  if (r.pose[0] !== a || r.pose[1] !== b) throw new Error(`pose not applied: asked ${a},${b} got ${r.pose}`);
  writeFileSync(resolve(dir, `${tree}_${a}_${b}.idx`), Buffer.from(r.idx, "base64"));
  writeFileSync(resolve(dir, `${tree}_${a}_${b}.val`), Buffer.from(r.val, "base64"));
  meta.poses.push({ tree, alpha: a, beta: b, repaired: r.repaired });
  if (++k % 100 === 0) process.stdout.write(`\r  GPU images ${k}/${inp.poses.length}`);
}
writeFileSync(resolve(raw, "e1b_gpu_meta.json"), JSON.stringify(meta));
console.log(`\n  ${k} GPU images, ${info.gpu}`);
await browser.close(); await server.close();
