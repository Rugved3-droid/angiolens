// Review screenshots of a real case: node e2e/screens.mjs Normal_12
import { chromium } from "playwright";
import { createServer } from "vite";
const caseId = process.argv[2] ?? "Normal_12";
const outDir = new URL(`../../out/review/${caseId}/`, import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
const server = await createServer({ server: { port: 5179, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await page.goto(`http://localhost:5179/?case=${caseId}&e2e=1`);
await page.waitForSelector("body[data-ready='1']", { timeout: 120000 });
const shots = JSON.parse(process.argv[3] ?? "[]");
for (const s of shots) {
  for (const id of s.check ?? []) await page.check(id);
  if (s.labels) await page.evaluate((l) => { window.__cpt.labelEdges(l); }, s.labels);
  if (s.approve) await page.evaluate(() => window.__cpt.approve());
  if (s.rcaRule) await page.selectOption("#rca-rule", s.rcaRule);
  await page.evaluate((s) => {
    window.__cpt.setPose(s.a, s.b, s.tree);
    if (s.sample) window.__cpt.selectSample(...s.sample); else window.__cpt.select(s.sel ?? null);
    if (s.orbit) window.__cpt.orbit(...s.orbit); else window.__cpt.frame(s.frame ?? "carm");
  }, s);
  if (s.waitMaps) await page.waitForFunction(() => window.__cpt.optimum && window.__cpt.optimum() !== null, null, { timeout: 120000 });
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${outDir}${s.name}.png` });
  console.log("wrote", s.name);
}
if (errors.length) console.log("errors", errors);
await browser.close(); await server.close();
