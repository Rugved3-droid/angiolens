// E3 follow-up: why do a few Predict tiles differ from an independent re-render by a few bytes?
// Replays the E3 seeded flow (mirror off, seed+1000; mirror on, seed+2000) through the unmodified atlas PredictMode. For every
// candidate tile it compares the tile with (1) an immediate re-render and (2) five further re-renders, and for any difference
// records the pixel positions, the channel deltas, and the renderer state (lab.injected before/after, fill window, field, puff).
// Output: paper/results/e3/e3_tile_probe.json
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { argv, chromium, GPU_ARGS, REPO, startDev } from "./harness.mjs";

const ROUNDS = Number(argv("rounds", "300"));
const SEED = Number(argv("seed", "20261114"));
const server = await startDev(5196);
const browser = await chromium.launch({ args: GPU_ARGS[argv("gl", "d3d11")] });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
await page.goto("http://localhost:5196/atlas.html?scene=4&carm=ap&predict");
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
const out = { rounds: ROUNDS, seed: SEED, findings: [], tilesCompared: 0, tilesDiffering: 0, repeatRendersDiffering: 0 };
for (const [mi, mirror] of [false, true].entries()) {
  await page.evaluate(({ seed, mirror }) => {
    localStorage.removeItem("cpt.predict.history.atlas");
    window.atlas.setBeat(false);
    const p = window.atlas.predict; p.animMs = 0; p.setSeed(seed); p.useMirror = mirror; window.atlas.lab.setPose(0, 0);
  }, { seed: SEED + 1000 * (mi + 1), mirror });
  for (let r = 0; r < ROUNDS; r++) {
    const res = await page.evaluate(async () => {
      const G = await import("/src/geometry.ts");
      const p = window.atlas.predict, lab = window.atlas.lab, A = lab.angio;
      const injBefore = lab.injected;
      const rafsBefore = window.__probeFrames ?? 0;
      p.next();
      const { cands, to } = p.round;
      const tiles = p.tileImages.map((t) => t.slice());
      const injAfter = lab.injected;
      const iso = [lab.iso.x, lab.iso.y, lab.iso.z];
      const px = A.px;
      const flip = (img, c) => {
        if (!c.mirrorLR && !c.mirrorUD) return img;
        const o = new Uint8ClampedArray(img.length);
        for (let y = 0; y < px; y++) for (let x = 0; x < px; x++) {
          const sy = c.mirrorUD ? px - 1 - y : y, sx = c.mirrorLR ? px - 1 - x : x;
          o.set(img.subarray((sy * px + sx) * 4, (sy * px + sx) * 4 + 4), (y * px + x) * 4);
        }
        return o;
      };
      const render = (c) => { A.render(new G.CArm(c.alpha, c.beta, iso), lab.detectorMm, to.tree, 7); return flip(A.readImage(), c); };
      const diffs = (a, b) => { const d = []; for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) d.push([i >> 2, i & 3, a[i] - b[i]]); return d; };
      const rows = [];
      cands.forEach((c, k) => {
        const again = render(c);
        const d = diffs(tiles[k], again);
        let repeat = 0;
        for (let j = 0; j < 5; j++) repeat += diffs(again, render(c)).length ? 1 : 0;
        const th = A.readThickness().thickness;           // last render = this candidate's pose (mirror not applied)
        rows.push({ kind: c.kind, alpha: c.alpha, beta: c.beta, n: d.length, repeat,
          pixels: d.slice(0, 40).map(([pix, ch, dv]) => ({ row: Math.floor(pix / px), col: pix % px, ch, dv, vessel: th[pix] > 0 })) });
      });
      p.choose(cands.findIndex((c) => c.kind === "correct"));
      return { target: to, injBefore, injAfter, fill: [A.fill.value.x, A.fill.value.y], field: A.fieldOn.value,
        params: { ...A.params }, rows };
    });
    for (const row of res.rows) {
      out.tilesCompared++;
      out.repeatRendersDiffering += row.repeat;
      if (row.n) { out.tilesDiffering++; out.findings.push({ round: r, mirror, target: res.target, injBefore: res.injBefore, injAfter: res.injAfter,
        fill: res.fill, field: res.field, ...row }); }
    }
  }
}
writeFileSync(resolve(REPO, "paper", "results", "e3", "e3_tile_probe.json"), JSON.stringify(out, null, 1));
console.log(`tiles compared ${out.tilesCompared}, differing ${out.tilesDiffering}, repeat renders differing ${out.repeatRendersDiffering}`);
for (const f of out.findings) console.log(JSON.stringify({ round: f.round, mirror: f.mirror, t: [f.target.alpha, f.target.beta, f.target.tree], inj: [f.injBefore, f.injAfter], kind: f.kind, n: f.n, repeat: f.repeat, px: f.pixels.slice(0, 6) }));
await browser.close(); await server.close();
