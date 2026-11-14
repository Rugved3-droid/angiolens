// E3 browser side: Predict mode on the atlas (the shipped app, atlas.html Scene 4), driven through its own PredictMode object.
// Part 1 (logic, no rendering): web/src/predict.ts makeCandidates over EVERY integer target alpha -90..90 x beta -45..45, both
//   mirror settings: four distinct kinds, exactly one correct, each kind's angles/mirror flags equal its label's transformation.
// Part 2 (rendered items): seeded rounds of the real flow (next -> tiles -> answer correctly -> the C-arm moves to the target ->
//   next), with the mirror toggle off and on, plus every preset target forced through the same renderCandidate. For each
//   candidate: (a) the tile shown to the learner is byte-compared with an independent render of that candidate's pose (+ its
//   mirror flag) by the same renderer; (b) the vessel-only path length at that pose (mirror applied) is returned sparse.
// Output: paper/results/raw/e3_items.json (+ e3_masks/<item>_<k>.idx|.val), paper/results/raw/e3_logic.json
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { argv, chromium, GPU_ARGS, REPO, startDev } from "./harness.mjs";

const raw = resolve(REPO, "paper", "results", "raw");
const dir = resolve(raw, "e3_masks");
mkdirSync(dir, { recursive: true });
const ROUNDS = Number(argv("rounds", "300"));
const SEED = Number(argv("seed", "20261114"));
const server = await startDev(5194);
const browser = await chromium.launch({ args: GPU_ARGS[argv("gl", "d3d11")] });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
page.on("pageerror", (e) => { console.log("pageerror", String(e)); process.exitCode = 1; });
await page.goto("http://localhost:5194/atlas.html?scene=4&carm=ap&predict");
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
await page.evaluate(() => localStorage.removeItem("cpt.predict.history.atlas"));

// ---------- part 1: candidate logic over the whole integer grid ----------
const logic = await page.evaluate(async () => {
  const P = await import("/src/predict.ts");
  const rand = P.rng(1);
  const res = { targets: 0, sets: 0, ok: 0, threw: 0, threwOutsideDegenerate: 0, bad: [], kindCount: {} };
  for (let a = -90; a <= 90; a++) for (let b = -45; b <= 45; b++) for (const mirror of [false, true]) {
    res.targets += mirror ? 0 : 1;
    let c;
    try { c = P.makeCandidates(a, b, mirror, rand); } catch {
      res.threw++;
      if (Math.abs(a) >= P.DEGENERATE_DEG || Math.abs(b) >= P.DEGENERATE_DEG) res.threwOutsideDegenerate++;
      continue;
    }
    res.sets++;
    const kinds = c.map((x) => x.kind);
    const exp = { correct: [a, b, false, false], "alpha-flip": [-a, b, false, false], "beta-flip": [a, -b, false, false],
      "both-flip": [-a, -b, false, false], "mirror-lr": [a, b, true, false], "mirror-ud": [a, b, false, true] };
    const labelsOk = c.every((x) => { const e = exp[x.kind]; return x.alpha === e[0] && x.beta === e[1] && x.mirrorLR === e[2] && x.mirrorUD === e[3]; });
    // no two candidates may describe the same image: same pose and same mirror flags, or a flip of an angle that is 0
    const keys = c.map((x) => `${x.alpha}|${x.beta}|${x.mirrorLR}|${x.mirrorUD}`);
    const ok = c.length === 4 && new Set(kinds).size === 4 && kinds.filter((k) => k === "correct").length === 1 && labelsOk &&
      new Set(keys).size === 4;
    for (const k of kinds) res.kindCount[k] = (res.kindCount[k] ?? 0) + 1;
    if (ok) res.ok++; else if (res.bad.length < 20) res.bad.push({ a, b, mirror, c });
  }
  // drawPose never returns a degenerate target (|a| < 5 and |b| < 5), over 100000 seeded draws
  const r2 = P.rng(2); let prev = { alpha: 0, beta: 0 }, degenerate = 0;
  const presets = [{ name: "x", alpha: -30, beta: 0, tree: "left" }];
  for (let i = 0; i < 100000; i++) {
    const p = P.drawPose(r2, presets, prev);
    if (Math.abs(p.alpha) < P.DEGENERATE_DEG && Math.abs(p.beta) < P.DEGENERATE_DEG) degenerate++;
    prev = p;
  }
  res.drawPoseDegenerate = degenerate;
  res.DEGENERATE_DEG = P.DEGENERATE_DEG;
  return res;
});
writeFileSync(resolve(raw, "e3_logic.json"), JSON.stringify(logic, null, 1));
console.log(`  logic: ${logic.ok}/${logic.sets} candidate sets valid; threw ${logic.threw} (outside degenerate zone ${logic.threwOutsideDegenerate}); drawPose degenerate ${logic.drawPoseDegenerate}`);

// ---------- part 2: rendered items ----------
const setup = await page.evaluate(() => {
  window.atlas.setBeat(false);
  const p = window.atlas.predict;
  p.animMs = 0;
  return { presets: p.d.presets, px: window.atlas.lab.angio.px, detectorMm: window.atlas.lab.detectorMm,
    iso: [window.atlas.lab.iso.x, window.atlas.lab.iso.y, window.atlas.lab.iso.z] };
});

async function item(mode, payload) {
  return page.evaluate(async ({ mode, payload }) => {
    const G = await import("/src/geometry.ts");
    const P = await import("/src/predict.ts");
    const p = window.atlas.predict, lab = window.atlas.lab;
    let cands, to, tiles;
    if (mode === "flow") {
      p.next();
      ({ cands, to } = p.round);
      tiles = p.tileImages;
    } else {                                     // forced preset target through the same renderCandidate
      to = { ...payload.preset, source: payload.preset.name };
      cands = P.makeCandidates(to.alpha, to.beta, payload.mirror, P.rng(payload.seed));
      tiles = cands.map((c) => p.renderCandidate(c, to.tree));
    }
    const px = lab.angio.px;
    const iso = [lab.iso.x, lab.iso.y, lab.iso.z];
    const flip = (img, c, ch) => {
      if (!c.mirrorLR && !c.mirrorUD) return img;
      const out = new img.constructor(img.length);
      for (let r = 0; r < px; r++) for (let col = 0; col < px; col++) {
        const sr = c.mirrorUD ? px - 1 - r : r, sc = c.mirrorLR ? px - 1 - col : col;
        for (let k = 0; k < ch; k++) out[(r * px + col) * ch + k] = img[(sr * px + sc) * ch + k];
      }
      return out;
    };
    const enc = (ta) => { const u = new Uint8Array(ta.buffer); let s = ""; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return btoa(s); };
    const out = [];
    for (let k = 0; k < cands.length; k++) {
      const c = cands[k];
      // independent render of the labelled pose, same renderer and noise seed as the tiles (predictUI.ts ROUND_SEED_NOISE = 7)
      lab.angio.render(new G.CArm(c.alpha, c.beta, iso), lab.detectorMm, to.tree, 7);
      const img = flip(lab.angio.readImage(), c, 4);
      let diff = 0; for (let i = 0; i < img.length; i++) if (img[i] !== tiles[k][i]) diff++;
      const th = flip(lab.angio.readThickness().thickness, c, 1);
      const idx = [], val = [];
      for (let i = 0; i < th.length; i++) if (th[i] !== 0) { idx.push(i); val.push(th[i]); }
      out.push({ kind: c.kind, alpha: c.alpha, beta: c.beta, mirrorLR: c.mirrorLR, mirrorUD: c.mirrorUD, tileBytesDiffer: diff,
        idx: enc(new Int32Array(idx)), val: enc(new Float32Array(val)) });
    }
    const target = { alpha: to.alpha, beta: to.beta, tree: to.tree, source: to.source };
    if (mode === "flow") { p.choose(cands.findIndex((c) => c.kind === "correct")); }   // the C-arm moves to the target
    return { target, cands: out };
  }, { mode, payload });
}

const items = [];
const save = (id, r, extra) => {
  r.cands.forEach((c, k) => {
    writeFileSync(resolve(dir, `${id}_${k}.idx`), Buffer.from(c.idx, "base64"));
    writeFileSync(resolve(dir, `${id}_${k}.val`), Buffer.from(c.val, "base64"));
    delete c.idx; delete c.val;
  });
  items.push({ id, ...extra, ...r });
};
let n = 0;
for (const [mi, mirror] of [false, true].entries()) {
  for (const [pi, preset] of setup.presets.entries()) {
    const id = `preset${pi}_m${+mirror}`;
    save(id, await item("preset", { preset, mirror, seed: SEED + pi }), { mode: "preset", mirror });
  }
  await page.evaluate(({ seed, mirror }) => { const p = window.atlas.predict; p.setSeed(seed); p.useMirror = mirror;
    window.atlas.lab.setPose(0, 0); }, { seed: SEED + 1000 * (mi + 1), mirror });
  for (let r = 0; r < ROUNDS; r++) {
    const id = `flow_m${+mirror}_${String(r).padStart(4, "0")}`;
    save(id, await item("flow", {}), { mode: "flow", mirror });
    if (++n % 50 === 0) process.stdout.write(`\r  rendered rounds ${n}/${2 * ROUNDS}`);
  }
}
writeFileSync(resolve(raw, "e3_items.json"), JSON.stringify({ ...setup, seed: SEED, rounds_per_setting: ROUNDS,
  chromium: browser.version(), items }));
console.log(`\n  ${items.length} Predict items written`);
await page.evaluate(() => localStorage.removeItem("cpt.predict.history.atlas"));
await browser.close(); await server.close();
