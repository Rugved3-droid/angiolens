// Which GPU does Playwright Chromium's WebGL use with a given set of flags? Prints the unmasked renderer string.
//   node paper/scripts/browser/gpu_probe.mjs [--headed=1] [--flags=--force_high_performance_gpu]
import { argv, chromium, GPU_ARGS } from "./harness.mjs";

const extra = argv("flags", "").split(",").filter(Boolean);
const browser = await chromium.launch({ headless: argv("headed", "0") !== "1", args: [...GPU_ARGS.d3d11, ...extra] });
const page = await browser.newPage();
const r = await page.evaluate(() => {
  const gl = document.createElement("canvas").getContext("webgl2");
  const e = gl.getExtension("WEBGL_debug_renderer_info");
  return gl.getParameter(e.UNMASKED_RENDERER_WEBGL);
});
console.log(JSON.stringify({ headed: argv("headed", "0") === "1", flags: extra, renderer: r }));
await browser.close();
