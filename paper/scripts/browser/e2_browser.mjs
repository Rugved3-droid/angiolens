// E2 browser side: GPU path-length images of the synthetic orientation phantom (case e2_orient) through the classic app's
// unmodified renderer (?case=...&e2e=1 exposes window.__cpt.setPose, which renders and reads back the vessel path length,
// row 0 = top). Poses from paper/results/raw/e2_input.json. Output: paper/results/raw/e2_gpu/<a>_<b>.f32 (n*n float32).
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { argv, chromium, GPU_ARGS, REPO, startDev } from "./harness.mjs";

const raw = resolve(REPO, "paper", "results", "raw");
const inp = JSON.parse(readFileSync(resolve(raw, "e2_input.json"), "utf8"));
const dir = resolve(raw, inp.gpu_dir ?? "e2_gpu");
mkdirSync(dir, { recursive: true });
const server = await startDev(5193);
const browser = await chromium.launch({ args: GPU_ARGS[argv("gl", "d3d11")] });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
page.on("pageerror", (e) => { console.log("pageerror", String(e)); process.exitCode = 1; });
await page.goto(`http://localhost:5193/?case=${inp.case}&e2e=1&px=${inp.px}`);
await page.waitForSelector("body[data-ready='1']", { timeout: 120000 });
for (const [a, b] of inp.poses) {
  const t = await page.evaluate(([a, b]) => window.__cpt.setPose(a, b, "left").thickness, [a, b]);
  writeFileSync(resolve(dir, `${a}_${b}.f32`), Buffer.from(new Float32Array(t).buffer));
}
writeFileSync(resolve(raw, inp.meta ?? "e2_gpu_meta.json"), JSON.stringify({ chromium: browser.version(), gl: argv("gl", "d3d11") }));
console.log(`  ${inp.poses.length} GPU phantom images`);
await browser.close(); await server.close();
