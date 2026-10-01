// Linked selection (both panels) and Label mode on the phantom case.
import { chromium } from "playwright";
import { createServer } from "vite";
const server = await createServer({ server: { port: 5179, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
const url = "http://localhost:5179/?case=phantom&e2e=1&px=256";
await page.goto(url);
await page.waitForSelector("body[data-ready='1']");
let failed = 0;
const check = (name, cond, extra = "") => { console.log(`${cond ? "PASS" : "FAIL"} ${name} ${extra}`); if (!cond) failed++; };

await page.evaluate(() => { localStorage.clear(); window.__cpt.setPose(-30, -25, "left"); });
const edges = await page.evaluate(() => window.__cpt.edges);
const leftEdges = edges.filter((e) => e.tree === "left");
for (const e of leftEdges) {
  const [x, y] = await page.evaluate((id) => window.__cpt.angioClientPoint(id), e.id);
  await page.mouse.click(x, y);
  const st = await page.evaluate(() => window.__cpt.state());
  check(`angiogram click selects edge ${e.id}`, st.selected === e.id, `(got ${st.selected})`);
}
await page.evaluate(() => window.__cpt.frame("patient"));
await page.waitForTimeout(200);
for (const e of leftEdges) {
  const [x, y] = await page.evaluate((id) => window.__cpt.sceneClientPoint(id), e.id);
  await page.mouse.click(x, y);
  const st = await page.evaluate(() => window.__cpt.state());
  check(`3D click selects edge ${e.id}`, st.selected === e.id, `(got ${st.selected})`);
}
// empty space deselects
const box = await page.locator("#angio-overlay").boundingBox();
await page.mouse.click(box.x + 5, box.y + box.height - 5);
check("click on empty angiogram deselects", (await page.evaluate(() => window.__cpt.state())).selected === null);

// label mode
await page.check("#label-mode");
const target = leftEdges[0].id;
const [x, y] = await page.evaluate((id) => window.__cpt.angioClientPoint(id), target);
await page.mouse.click(x, y);
await page.selectOption("#label-picker", "LAD");
check("branch label assigned", (await page.evaluate(() => window.__cpt.state())).label === "LAD");
check("selection text shows label", (await page.textContent("#selection")).includes("LAD"));
await page.reload();
await page.waitForSelector("body[data-ready='1']");
await page.evaluate(() => window.__cpt.setPose(-30, -25, "left"));
const [x2, y2] = await page.evaluate((id) => window.__cpt.angioClientPoint(id), target);
await page.mouse.click(x2, y2);
check("label persists across reload", (await page.evaluate(() => window.__cpt.state())).label === "LAD");
const [download] = await Promise.all([page.waitForEvent("download"), page.check("#label-mode").then(() => page.click("#export-labels"))]);
const text = await (await download.createReadStream()).toArray().then((c) => Buffer.concat(c).toString());
const file = JSON.parse(text);
check("exported labels.json", file.case_id === "phantom" && file.labels[String(target)] === "LAD", text.slice(0, 120));
if (errors.length) { console.log("page errors", errors); failed++; }
await browser.close(); await server.close();
process.exit(failed ? 1 : 0);
