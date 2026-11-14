// E5. Performance of the shipped app (production build, web/dist served by `vite preview`), measured by automation only.
//   node paper/scripts/browser/e5_performance.mjs [--reps=5] [--seconds=10] [--headed=1]
// Configurations: headless Chromium on the real GPU (ANGLE D3D11), headless Chromium with SwiftShader (software rendering, no
// GPU), and, with --headed=1, a visible Chromium window on this machine's desktop on the discrete GPU (D3D11 +
// --force_high_performance_gpu; the GPU actually used is read back from WebGL and recorded per run).
// Per repetition (a fresh browser context, so nothing is cached):
//   load_ms   : navigation start -> the app's own ready flag (body[data-ready='1']), atlas Scene 1 (default) and Scene 4 (X-ray),
//               EACH in its own fresh context (cold: no shared HTTP cache, no compiled shaders). v1 loaded Scene 4 after Scene 1 in
//               the same context (warm); that run is kept in paper/results/e5_v1_warm/.
//   bytes     : sum of transferSize over every resource of the Scene 4 load
//   rotation  : Scene 4, C-arm swept continuously (alpha = 90 sin(2 pi t / 6 s), beta = 30 sin(2 pi t / 4 s)) every animation
//               frame for --seconds, the live X-ray re-rendered EVERY frame (worst case; the app itself refreshes it at 15/s)
//               -> frame-interval median / p95 and fps = 1000 / median interval
//   memory    : JS heap used (CDP Performance.getMetrics) after load and after rotation; working set of all Playwright Chromium
//               processes after rotation (Windows Get-Process, ms-playwright executables only)
// Writes paper/results/e5/e5_runs.csv, e5_summary.csv, e5_hardware.json.
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { argv, chromium, GPU_ARGS, REPO, startPreview } from "./harness.mjs";

const OUT = resolve(REPO, "paper", "results", argv("out", "e5"));
mkdirSync(OUT, { recursive: true });
const REPS = Number(argv("reps", "5"));
const SECONDS = Number(argv("seconds", "10"));
const PORT = 5195;
const server = await startPreview(PORT);
const base = `http://localhost:${PORT}`;

function ps(cmd) {
  return execFileSync("powershell.exe", ["-NoProfile", "-Command", cmd], { encoding: "utf8" }).trim();
}
const hardware = JSON.parse(ps(
  "$c=Get-CimInstance Win32_Processor|Select-Object -First 1; $o=Get-CimInstance Win32_OperatingSystem; " +
  "$g=Get-CimInstance Win32_VideoController|ForEach-Object{$_.Name + ' (driver ' + $_.DriverVersion + ')'}; " +
  "@{cpu=$c.Name; cores=$c.NumberOfCores; threads=$c.NumberOfLogicalProcessors; ram_gb=[math]::Round($o.TotalVisibleMemorySize/1MB,1); " +
  "os=$o.Caption + ' ' + $o.Version; gpus=@($g)} | ConvertTo-Json -Compress"));
hardware.node = process.version;

function playwrightWorkingSetMB() {
  const s = ps("(Get-Process | Where-Object { $_.Path -like '*ms-playwright*' } | Measure-Object WorkingSet64 -Sum).Sum");
  return s ? Math.round(Number(s) / 2 ** 20) : null;
}

const configs = [
  { name: "headless_gpu_d3d11", headless: true, args: GPU_ARGS.d3d11 },
  { name: "headless_swiftshader_cpu", headless: true, args: GPU_ARGS.swiftshader },
];
if (argv("headed", "0") === "1") configs.push({ name: "headed_discrete_gpu_d3d11", headless: false, args: [...GPU_ARGS.d3d11, "--force_high_performance_gpu"] });
const only = argv("only", "");
if (only) configs.splice(0, configs.length, ...configs.filter((c) => only.split(",").includes(c.name)));

const runs = [];
for (const cfg of configs) {
  const browser = await chromium.launch({ headless: cfg.headless, args: cfg.args });
  hardware[`chromium`] = browser.version();
  for (let rep = 0; rep < REPS; rep++) {
    const coldLoad = async (q) => {                    // a fresh context per scene: nothing cached
      const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
      const page = await ctx.newPage();
      const t0 = Date.now();
      await page.goto(`${base}/atlas.html${q}`, { waitUntil: "commit" });
      await page.waitForSelector("body[data-ready='1']", { timeout: 600000 });
      const ms = await page.evaluate(() => performance.now());
      return { ctx, page, ms, wall: Date.now() - t0 };
    };
    const s1 = await coldLoad("");
    await s1.ctx.close();
    const { ctx, page, ms: scene4 } = await coldLoad("?scene=4&carm=ap&cam=room");
    const scene1 = s1.ms;
    const cdp = await ctx.newCDPSession(page);
    await cdp.send("Performance.enable");
    const heap = async () => Math.round((await cdp.send("Performance.getMetrics")).metrics.find((m) => m.name === "JSHeapUsedSize").value / 2 ** 20 * 10) / 10;
    const bytes = await page.evaluate(() => performance.getEntriesByType("resource").reduce((s, r) => s + (r.transferSize || 0), 0)
      + (performance.getEntriesByType("navigation")[0]?.transferSize || 0));
    const gpu = await page.evaluate(() => {
      const gl = window.atlas.dbg.renderer.getContext();
      const e = gl.getExtension("WEBGL_debug_renderer_info");
      return e ? gl.getParameter(e.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    });
    const heapLoad = await heap();
    const rot = await page.evaluate(async (seconds) => {
      const lab = window.atlas.lab;
      window.atlas.setBeat(false);
      const dts = [];
      const t0 = performance.now();
      let last = t0;
      await new Promise((done) => {
        const step = (now) => {
          const t = (now - t0) / 1000;
          lab.setPose(Math.round(90 * Math.sin((2 * Math.PI * t) / 6) * 100) / 100, Math.round(30 * Math.sin((2 * Math.PI * t) / 4) * 100) / 100);
          lab.renderImage();
          if (now > t0) dts.push(now - last);
          last = now;
          if (t < seconds) requestAnimationFrame(step); else done();
        };
        requestAnimationFrame(step);
      });
      dts.sort((a, b) => a - b);
      const q = (p) => dts[Math.min(dts.length - 1, Math.floor(p * dts.length))];
      return { frames: dts.length, median_ms: q(0.5), p95_ms: q(0.95), max_ms: dts[dts.length - 1] };
    }, SECONDS);
    const heapRot = await heap();
    const wsMB = playwrightWorkingSetMB();
    const row = { config: cfg.name, rep, gpu, load_scene1_ms: Math.round(scene1), load_scene4_ms: Math.round(scene4),
      transfer_mb_scene4: Math.round(bytes / 2 ** 20 * 10) / 10, rotation_frames: rot.frames,
      frame_median_ms: Math.round(rot.median_ms * 100) / 100, frame_p95_ms: Math.round(rot.p95_ms * 100) / 100,
      frame_max_ms: Math.round(rot.max_ms * 100) / 100, fps_median: Math.round((1000 / rot.median_ms) * 10) / 10,
      js_heap_mb_after_load: heapLoad, js_heap_mb_after_rotation: heapRot, chromium_ws_mb_after_rotation: wsMB };
    runs.push(row);
    console.log(JSON.stringify(row));
    await ctx.close();
  }
  await browser.close();
}
const keys = Object.keys(runs[0]);
writeFileSync(resolve(OUT, "e5_runs.csv"), [keys.join(","), ...runs.map((r) => keys.map((k) => typeof r[k] === "string" ? `"${r[k]}"` : r[k]).join(","))].join("\n") + "\n");
const med = (v) => { const s = [...v].sort((a, b) => a - b); return s[Math.floor(s.length / 2)]; };
const num = ["load_scene1_ms", "load_scene4_ms", "transfer_mb_scene4", "fps_median", "frame_p95_ms", "js_heap_mb_after_load", "js_heap_mb_after_rotation", "chromium_ws_mb_after_rotation"];
const lines = [["config", "reps", ...num.map((k) => `${k}_median`), ...num.map((k) => `${k}_min`), ...num.map((k) => `${k}_max`)].join(",")];
for (const cfg of configs) {
  const R = runs.filter((r) => r.config === cfg.name);
  lines.push([cfg.name, R.length, ...num.map((k) => med(R.map((r) => r[k]))), ...num.map((k) => Math.min(...R.map((r) => r[k]))), ...num.map((k) => Math.max(...R.map((r) => r[k])))].join(","));
}
writeFileSync(resolve(OUT, "e5_summary.csv"), lines.join("\n") + "\n");
writeFileSync(resolve(OUT, "e5_hardware.json"), JSON.stringify({ ...hardware, reps: REPS, rotation_seconds: SECONDS, served: "vite preview of web/dist (production build)" }, null, 1));
console.log(lines.join("\n"));
await server.httpServer.close();
