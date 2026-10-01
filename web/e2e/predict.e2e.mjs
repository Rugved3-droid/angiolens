// PREDICT mode: candidates, orientation of the correct tile, mirror distractor, scoring, C-arm reveal, persistence.
import { chromium } from "playwright";
import { createServer } from "vite";
const server = await createServer({ server: { port: 5179, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1500, height: 1100 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
const url = "http://localhost:5179/?case=phantom&e2e=1&px=128";
await page.goto(url);
await page.waitForSelector("body[data-ready='1']");
await page.evaluate(() => localStorage.clear());
await page.reload();
await page.waitForSelector("body[data-ready='1']");
let failed = 0;
const check = (n, ok, x = "") => { console.log(`${ok ? "PASS" : "FAIL"} ${n} ${x}`); if (!ok) failed++; };
const P = (fn, arg) => page.evaluate(fn, arg);

await P(() => { const p = window.__cpt.predict; p.setSeed(12345); p.setAnimMs(0); p.setMode("predict"); });
check("C-arm controls locked in Predict", await P(() => window.__cpt.predict.locked()));
const corr = (a, b) => {
  const n = a.length; let ma = 0, mb = 0; for (let i = 0; i < n; i++) { ma += a[i]; mb += b[i]; } ma /= n; mb /= n;
  let s = 0, sa = 0, sb = 0; for (let i = 0; i < n; i++) { s += (a[i] - ma) * (b[i] - mb); sa += (a[i] - ma) ** 2; sb += (b[i] - mb) ** 2; }
  return s / Math.sqrt(sa * sb);
};
const px = 128;
const mirrorLR = (img) => img.map((_, i) => img[Math.floor(i / px) * px + (px - 1 - (i % px))]);

let orientChecks = 0, orientFail = 0;
for (let round = 0; round < 6; round++) {
  const kinds = await P(() => window.__cpt.predict.kinds());
  const target = await P(() => window.__cpt.predict.target());
  check(`round ${round}: four distinct candidates incl. one correct`, new Set(kinds).size === 4 && kinds.filter((k) => k === "correct").length === 1, kinds.join(","));
  const ci = kinds.indexOf("correct");
  const tile = await P((i) => window.__cpt.predict.tile(i), ci);
  // independent reference: vessel path length at the target pose (row 0 = top), darker = more contrast
  const thick = (await P(([a, b, t]) => window.__cpt.setPose(a, b, t), [target.alpha, target.beta, target.tree])).thickness;
  const dark = tile.map((v) => 255 - v);
  const r = corr(dark, thick), rm = corr(mirrorLR(dark), thick);
  orientChecks++;
  // tiles also contain bone shadow and noise, so r is ~0.45-0.6; a mirrored tile gives ~0
  if (!(r > 0.3 && rm < r - 0.3)) orientFail++;
  console.log(`   target ${target.alpha},${target.beta} ${target.tree}: r(correct tile, path length) = ${r.toFixed(3)}, mirrored ${rm.toFixed(3)}`);
  // answer: alternate a wrong pick and the correct pick
  const pick = round % 2 === 0 ? kinds.findIndex((k) => k !== "correct") : ci;
  const pickedKind = kinds[pick];
  const before = await P(() => window.__cpt.predict.summary());
  await P((i) => window.__cpt.predict.choose(i), pick);
  const after = await P(() => window.__cpt.predict.summary());
  const ok = pickedKind === "correct" ? after.correct === before.correct + 1 : after.errors[pickedKind] === before.errors[pickedKind] + 1;
  check(`round ${round}: answer recorded as ${pickedKind}`, ok && after.n === before.n + 1);
  const pose = await P(() => window.__cpt.predict.pose());
  check(`round ${round}: C-arm revealed at the target`, pose.alpha === target.alpha && pose.beta === target.beta && pose.tree === target.tree, JSON.stringify(pose));
  await P(() => window.__cpt.predict.next());
}
check("correct tile is never mirrored (matches the target's path-length image)", orientFail === 0, `${orientChecks} rounds`);

// mirror toggle
await P(() => { window.__cpt.predict.setMirror(true); window.__cpt.predict.next(); });
const kinds = await P(() => window.__cpt.predict.kinds());
check("mirror toggle offers an L-R mirror instead of both-flipped", kinds.includes("mirror-lr") && !kinds.includes("both-flip"), kinds.join(","));
const t0 = await P((i) => window.__cpt.predict.tile(i), kinds.indexOf("correct"));
const tm = await P((i) => window.__cpt.predict.tile(i), kinds.indexOf("mirror-lr"));
check("mirror distractor = exact L-R flip of the correct tile", JSON.stringify(mirrorLR(t0)) === JSON.stringify(tm));

const s1 = await P(() => window.__cpt.predict.summary());
await page.reload();
await page.waitForSelector("body[data-ready='1']");
const s2 = await P(() => window.__cpt.predict.summary());
check("stats persist across reload", s2.n === s1.n && s2.correct === s1.correct, `${s2.n} answers`);
if (errors.length) { console.log(errors); failed++; }
await browser.close(); await server.close();
process.exit(failed ? 1 : 0);
