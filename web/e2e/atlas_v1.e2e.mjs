// v1.0 checks (D56-D59): Predict on the atlas, the Scene 6 sync (X-ray dot = engine projection, slice fill = shared window),
// and the scene stepper.   node e2e/atlas_v1.e2e.mjs
import { chromium } from "playwright";
import { createServer } from "vite";
const server = await createServer({ server: { port: 5190, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const fail = (m) => { console.log("FAIL", m); process.exitCode = 1; };
const ok = (m) => console.log("PASS", m);
const open = async (q) => {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  page.on("pageerror", (e) => fail(`pageerror ${e}`));
  await page.goto(`http://localhost:5190/atlas.html?${q}`);
  await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
  await page.waitForTimeout(1500);
  return page;
};

// 1. Predict on the atlas: four distinct candidate kinds incl. the correct one; answering records it and moves the C-arm
{
  const page = await open("scene=4&carm=ap&predict");
  const r = await page.evaluate(async () => {
    const p = window.atlas.predict;
    p.animMs = 0;
    const kinds = p.kinds(), target = p.target();
    // the live lab shows the QUESTION's injection while it is asked (toolbar and image agree with the prompt)
    const injAtQuestion = window.atlas.lab.injected;
    const barTree = [...document.querySelectorAll("#bar .seg button.on")].map((b) => b.textContent).join("|");
    const tiles = [...document.querySelectorAll(".pr-tile")];
    tiles[kinds.indexOf("correct")].click();
    await new Promise((res) => setTimeout(res, 300));
    const lab = window.atlas.lab;
    return { kinds, distinct: new Set(kinds).size, n: p.summary().n, correct: p.summary().correct,
      pose: [lab.carm.alphaDeg, lab.carm.betaDeg], target: [target.alpha, target.beta], tiles: tiles.length,
      correctTileGreen: tiles[kinds.indexOf("correct")].classList.contains("pr-correct"), tree: target.tree, injAtQuestion, barTree };
  });
  if (r.tiles === 4 && r.distinct === 4 && r.kinds.includes("correct")) ok(`Predict: 4 distinct candidates ${r.kinds.join(", ")}`);
  else fail(`Predict candidates ${JSON.stringify(r)}`);
  if (r.n >= 1 && r.correct >= 1 && r.correctTileGreen) ok("Predict: the correct answer is recorded and shown");
  else fail(`Predict record ${JSON.stringify(r)}`);
  const barOk = r.barTree.includes(r.tree === "left" ? "LCA" : "RCA");
  if (r.injAtQuestion === r.tree && barOk) ok(`Predict: the lab and toolbar show the question's ${r.tree} injection`);
  else fail(`Predict tree sync: question ${r.tree}, lab ${r.injAtQuestion}, toolbar ${r.barTree}`);
  if (Math.abs(r.pose[0] - r.target[0]) < 1e-6 && Math.abs(r.pose[1] - r.target[1]) < 1e-6) ok(`Predict: the C-arm moved to the target ${r.target}`);
  else fail(`Predict pose ${r.pose} != target ${r.target}`);
  await page.close();
}

// 2. Scene 6 sync: the dot is CArm.project(slice point) mapped to the monitor; the slice fills with the shared window
{
  const page = await open("scene=6&carm=raocaud&still");
  const r = await page.evaluate(async () => {
    const { lab, cross } = window.atlas;
    const raf = () => new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(res)));
    const res = [];
    for (const f of [0.0, 0.5, 0.9]) {
      window.atlas.sliceTo(f);
      await raf();
      const p = cross.point();
      const [x, y] = lab.carm.project([p.x, p.y, p.z]);
      const img = document.getElementById("monitorImage").getBoundingClientRect();
      const dot = document.getElementById("xrayDot").getBoundingClientRect();
      const want = [img.left + (x / lab.detectorMm + 0.5) * img.width, img.top + (0.5 - y / lab.detectorMm) * img.height];
      const got = [dot.left + dot.width / 2, dot.top + dot.height / 2];          // the dot is centred on its point (translate -50%)
      res.push({ f, err: Math.hypot(want[0] - got[0], want[1] - got[1]) });
    }
    // contrast window: before the slice -> blood; covering the slice -> contrast (read back from the drawn label)
    const s = cross.s();
    const label = async (front) => { lab.angio.fill.value.set(front, -1e9); await raf(); return cross.lastLumen; };
    const before = await label(s - 30), after = await label(s + 30);
    return { dots: res, before, after };
  });
  const worst = Math.max(...r.dots.map((d) => d.err));
  if (worst < 1.0) ok(`Scene 6: X-ray dot at the engine's projection (worst ${worst.toFixed(2)} px over 3 slice positions)`);
  else fail(`Scene 6 dot error ${JSON.stringify(r.dots)}`);
  if (r.before === "blood" && r.after === "contrast") ok("Scene 6: the slice lumen follows the shared fill window (blood -> contrast)");
  else fail(`Scene 6 fill sync ${r.before} -> ${r.after}`);
  await page.close();
}

// 3. The stepper reaches all six scenes
{
  const page = await open("scene=1&still");
  const seen = [];
  for (let s = 1; s <= 6; s++) {
    await page.evaluate((n) => window.atlas.goScene(n, 0), s);
    await page.waitForTimeout(600);
    seen.push(await page.$eval("#steps .step.on", (e) => e.textContent));
  }
  if (seen.join("|") === "Heart|In the chest|Cath lab|X-ray|Catheter|Cross-section") ok(`stepper: ${seen.join(" -> ")}`);
  else fail(`stepper ${seen}`);
  await page.close();
}
await browser.close(); await server.close();
