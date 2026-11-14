// Captures for Fig. 2 and Fig. 5 from the unmodified atlas app (headless Chromium, real GPU). UI chrome (toolbar, drawer,
// captions, hover labels, footer) is hidden with CSS for the screenshot only; the canvas content is untouched.
//   Fig. 2: Scene 4 split view (3D scene beside its projection) at four of the app's named views.
//   Fig. 5: one Predict item (spider target, LCA, mirror toggle ON so a mirror distractor appears), tiles exactly as rendered.
// Writes paper/results/raw/fig2_<view>.png, fig5_tile_<k>.rgba, fig5_tiles.json.
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { argv, chromium, GPU_ARGS, REPO, startDev } from "./harness.mjs";

const raw = resolve(REPO, "paper", "results", "raw");
mkdirSync(raw, { recursive: true });
const server = await startDev(5197);
const browser = await chromium.launch({ args: GPU_ARGS[argv("gl", "d3d11")] });
const HIDE = "#bar,#drawer,#caption,#hover,#foot,#names,#sel,#fader{display:none!important}";
const VIEWS = [["raocaud", "left"], ["spider", "left"], ["rao30", "right"], ["lao45", "right"]];
const only = argv("only", "");

if (!only || only === "fig2") {
  for (const [v, inj] of VIEWS) {
    const ctx = await browser.newContext({ viewport: { width: 1600, height: 820 }, deviceScaleFactor: 2 });
    const page = await ctx.newPage();
    await page.goto(`http://localhost:5197/atlas.html?scene=4&carm=${v}&cam=split&inject=${inj}`);
    await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
    await page.evaluate(() => window.atlas.setBeat(false));
    await page.addStyleTag({ content: HIDE });
    await page.waitForTimeout(2500);                                 // camera move into the split view settles
    const pose = await page.evaluate(() => [window.atlas.lab.carm.alphaDeg, window.atlas.lab.carm.betaDeg, window.atlas.lab.injected]);
    await page.screenshot({ path: resolve(raw, `fig2_${v}.png`) });
    console.log(`fig2 ${v}: pose ${pose}`);
    await ctx.close();
  }
}
if (!only || only === "fig5") {
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  await page.goto("http://localhost:5197/atlas.html?scene=4&carm=ap&predict");
  await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
  const r = await page.evaluate(async (seed) => {
    const P = await import("/src/predict.ts");
    window.atlas.setBeat(false);
    const p = window.atlas.predict;
    const preset = p.d.presets.find((x) => x.alpha === 40 && x.beta === -30 && x.tree === "left");
    const cands = P.makeCandidates(preset.alpha, preset.beta, true, P.rng(seed));
    const tiles = cands.map((c) => p.renderCandidate(c, preset.tree));
    const enc = (ta) => { const u = new Uint8Array(ta.buffer); let s = ""; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return btoa(s); };
    return { px: window.atlas.lab.angio.px, preset, cands, tiles: tiles.map(enc) };
  }, 20261114);
  r.tiles.forEach((t, k) => writeFileSync(resolve(raw, `fig5_tile_${k}.rgba`), Buffer.from(t, "base64")));
  delete r.tiles;
  writeFileSync(resolve(raw, "fig5_tiles.json"), JSON.stringify(r, null, 1));
  console.log("fig5 tiles:", r.cands.map((c) => `${c.kind} (${c.alpha},${c.beta}${c.mirrorLR ? ",LR" : ""}${c.mirrorUD ? ",UD" : ""})`).join(" | "));
}
await browser.close(); await server.close();
