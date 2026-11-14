// E1 browser side: project the atlas centerline points with the APP's TypeScript geometry (web/src/geometry.ts), loaded
// unmodified in Chromium, for every pose in paper/results/raw/e1_input.json. Two browser paths per pose:
//   overlay: CArm.project -> screenToPixel                         (float64; used for overlays, picking, the Scene 6 dot)
//   vertex : CArm.clipMatrix(W) applied in FLOAT32 -> NDC -> pixel (what the GPU vertex stage computes for every mesh vertex)
// Output: paper/results/raw/e1_browser.bin, float64 [pose][point][col_overlay,row_overlay,col_vertex,row_vertex].
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { b64ToF64, chromium, GPU_ARGS, REPO, startDev } from "./harness.mjs";

const raw = resolve(REPO, "paper", "results", "raw");
const inp = JSON.parse(readFileSync(resolve(raw, "e1_input.json"), "utf8"));
const server = await startDev(5191);
const browser = await chromium.launch({ args: GPU_ARGS.swiftshader });   // pure arithmetic: no GPU needed
const page = await browser.newPage();
await page.goto("http://localhost:5191/index.html?e1-harness");             // any app page serves the module graph
const ver = await browser.version();
const out = new Float64Array(inp.poses.length * inp.points.length * 4);
const CH = 50;
for (let k = 0; k < inp.poses.length; k += CH) {
  const s = await page.evaluate(async ({ poses, points, iso, W, n }) => {
    const g = await import("/src/geometry.ts");
    const f = Math.fround;
    const res = new Float64Array(poses.length * points.length * 4);
    let o = 0;
    for (const [a, b] of poses) {
      const c = new g.CArm(a, b, iso);
      const M = c.clipMatrix(W).map(f);                                   // a Float32Array uniform on the GPU
      for (const p of points) {
        const [col, row] = g.screenToPixel(...c.project(p), W, n);
        const x = f(p[0]), y = f(p[1]), z = f(p[2]);
        const cx = f(f(f(f(M[0] * x) + f(M[4] * y)) + f(M[8] * z)) + M[12]);
        const cy = f(f(f(f(M[1] * x) + f(M[5] * y)) + f(M[9] * z)) + M[13]);
        const cw = f(f(f(f(M[3] * x) + f(M[7] * y)) + f(M[11] * z)) + M[15]);
        const nx = f(cx / cw), ny = f(cy / cw);
        // NDC -> pixel with row 0 at the top: the same mapping the renderer's readback uses (angio.ts readImage flips GL rows)
        res[o++] = col; res[o++] = row; res[o++] = ((nx + 1) / 2) * n - 0.5; res[o++] = ((1 - ny) / 2) * n - 0.5;
      }
    }
    const u8 = new Uint8Array(res.buffer);
    let bin = ""; for (let i = 0; i < u8.length; i += 0x8000) bin += String.fromCharCode(...u8.subarray(i, i + 0x8000));
    return btoa(bin);
  }, { poses: inp.poses.slice(k, k + CH), points: inp.points, iso: inp.iso, W: inp.detector_mm, n: inp.detector_px });
  out.set(b64ToF64(s), k * inp.points.length * 4);
  process.stdout.write(`\r  poses ${Math.min(k + CH, inp.poses.length)}/${inp.poses.length}`);
}
writeFileSync(resolve(raw, "e1_browser.bin"), Buffer.from(out.buffer));
writeFileSync(resolve(raw, "e1_browser_meta.json"), JSON.stringify({ chromium: ver, node: process.version }));
console.log(`\n  wrote e1_browser.bin (${inp.poses.length} poses x ${inp.points.length} points), Chromium ${ver}`);
await browser.close(); await server.close();
