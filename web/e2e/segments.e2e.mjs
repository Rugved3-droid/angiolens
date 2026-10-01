// A: derived segments from branch labels + approval; B: ray colours = capsule metric; C: heatmap floors / fixed scale.
import { chromium } from "playwright";
import { createServer } from "vite";
const server = await createServer({ server: { port: 5179, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await page.goto("http://localhost:5179/?case=phantom&e2e=1&px=128");
await page.waitForSelector("body[data-ready='1']");
await page.evaluate(() => localStorage.clear());
await page.reload();
await page.waitForSelector("body[data-ready='1']");
let failed = 0;
const check = (n, ok, x = "") => { console.log(`${ok ? "PASS" : "FAIL"} ${n} ${x}`); if (!ok) failed++; };

// ---- A ----
const d0 = await page.evaluate(() => { window.__cpt.labelEdges({ 0: "LM", 2: "LAD", 1: "LCx", 3: "ramus", 4: "RCA" }); return window.__cpt.derivation(); });
const names = d0.segments.map((s) => s.name).sort();
check("derived names come only from labels (no invented D1/OM1)", JSON.stringify(names) === JSON.stringify(
  ["LAD prox+mid+dist (unsplit)", "LCx prox+dist (unsplit)", "LM", "RCA dist", "RCA mid", "RCA prox", "ramus"]), JSON.stringify(names));
check("missing side branches are notes, not issues", d0.issues.length === 0 && d0.notes.some((n) => n.includes("D1")) && d0.notes.some((n) => n.includes("OM1")));
check("unsplit LAD is not mission-eligible", d0.segments.find((s) => s.name.startsWith("LAD")).complete === false);
const rca = d0.segments.filter((s) => s.name.startsWith("RCA ")).map((s) => s.len);
check("no RV marginal: RCA approximate thirds, equal and not mission-eligible", Math.max(...rca) - Math.min(...rca) < 0.6 &&
  d0.segments.filter((s) => s.name.startsWith("RCA ")).every((s) => !s.complete && s.flags.includes("approximate (thirds)")), JSON.stringify(rca));
check("not approved before approval", d0.approved === false);
check("approve", await page.evaluate(() => window.__cpt.approve()) === true);
await page.evaluate(() => { window.__cpt.setPose(45, 0, "right"); window.__cpt.selectSample(4, 50); });
check("click on approved RCA selects the derived segment", await page.evaluate(() => window.__cpt.target()) === "RCA mid",
  await page.evaluate(() => window.__cpt.target()));
await page.evaluate(() => window.__cpt.labelEdges({ 3: "LCx" }));
const d1 = await page.evaluate(() => window.__cpt.derivation());
check("label change voids approval and inconsistent labels are issues", d1.approved === false && d1.issues.length > 0, JSON.stringify(d1.issues));
await page.evaluate(() => { window.__cpt.labelEdges({ 3: "ramus" }); });
check("restoring labels restores the approval (same labels hash)", (await page.evaluate(() => window.__cpt.derivation())).approved === true);

// ---- B ----
let rayChecks = 0, rayMismatch = 0, overlapSeen = 0;
for (const [a, b] of [[0, 0], [-30, -25], [45, 0], [40, 30], [-60, 20]]) {
  for (const sel of [[0, 20], [2, 40], [1, 40], [3, 40]]) {
    const r = await page.evaluate(([a, b, id, idx]) => { window.__cpt.setPose(a, b, "left"); window.__cpt.selectSample(id, idx); return { rays: window.__cpt.rays(), masks: window.__cpt.masks() }; }, [a, b, ...sel]);
    if (!r.masks) continue;
    for (const ray of r.rays) {
      const exp = r.masks.inter[ray.i] ? "inter" : r.masks.self[ray.i] ? "self" : null;
      rayChecks++;
      if (exp) overlapSeen++;
      if (ray.overlap !== exp) rayMismatch++;
    }
  }
}
check("every ray colour equals the capsule metric at its sample", rayMismatch === 0 && rayChecks > 100, `${rayChecks} rays, ${overlapSeen} overlapped, ${rayMismatch} mismatches`);

// ---- C ----
await page.evaluate(() => { window.__cpt.setPose(0, 0, "left"); window.__cpt.selectSample(2, 40); });
await page.waitForFunction(() => window.__cpt.optimum() !== null, null, { timeout: 60000 });
const s = await page.evaluate(() => window.__cpt.scales());
check("per-map scales never below the floors (exact floor values are unit-tested in heatmap.test.ts)", s.F >= 0.2 && s.O_inter >= 0.2 && s.O_self >= 0.2 && s.cost >= 0.4, JSON.stringify(s));
const f = await page.evaluate(() => { window.__cpt.setFixedScale(true); return window.__cpt.scales(); });
check("fixed 0-100% toggle", f.F === 1 && f.O_inter === 1 && f.O_self === 1 && f.cost === 2, JSON.stringify(f));
if (errors.length) { console.log(errors); failed++; }
await browser.close(); await server.close();
process.exit(failed ? 1 : 0);
