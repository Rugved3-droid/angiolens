// End-to-end: the browser's GPU path-length image must match the Python reference renderer.
//   python preprocess/scripts/build_phantom.py && node e2e/phantom.e2e.mjs
// Also asserts the comparison is sensitive: a left-right or up-down mirrored image must FAIL.
import { readFileSync } from "node:fs";
import { chromium } from "playwright";
import { createServer } from "vite";

const expected = JSON.parse(readFileSync(new URL("../public/cases/phantom/expected.json", import.meta.url)));
const px = expected.px;

const server = await createServer({ configFile: new URL("../vite.config.ts", import.meta.url).pathname.replace(/^\/(\w:)/, "$1"), server: { port: 5179, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
await page.goto(`http://localhost:5179/?case=phantom&e2e=1&px=${px}`);
await page.waitForSelector("body[data-ready='1']", { timeout: 60000 });

function stats(a, b) {
  let ma = 0, mb = 0;
  for (let i = 0; i < a.length; i++) { ma += a[i]; mb += b[i]; }
  ma /= a.length; mb /= b.length;
  let sab = 0, saa = 0, sbb = 0, mae = 0;
  for (let i = 0; i < a.length; i++) {
    sab += (a[i] - ma) * (b[i] - mb); saa += (a[i] - ma) ** 2; sbb += (b[i] - mb) ** 2; mae += Math.abs(a[i] - b[i]);
  }
  return { r: sab / Math.sqrt(saa * sbb), mae: mae / a.length };
}
const mirrorLR = (img) => img.map((_, i) => img[Math.floor(i / px) * px + (px - 1 - (i % px))]);
const mirrorUD = (img) => img.map((_, i) => img[(px - 1 - Math.floor(i / px)) * px + (i % px)]);

let failed = 0;
for (const [pose, exp] of Object.entries(expected.images)) {
  const [a, b] = pose.split(",").map(Number);
  const { thickness: got, repaired } = await page.evaluate(([a, b]) => window.__cpt.setPose(a, b, "left"), [a, b]);
  const s = stats(got, exp);
  const lr = stats(mirrorLR(got), exp);
  const ud = stats(mirrorUD(got), exp);
  const ok = s.r > 0.95 && s.mae < 0.25 && lr.r < 0.8 && ud.r < 0.8;
  if (!ok) failed++;
  console.log(`${ok ? "PASS" : "FAIL"} pose ${pose}: r=${s.r.toFixed(4)} mae=${s.mae.toFixed(3)} mm, repaired px ${repaired} | mirrored L-R r=${lr.r.toFixed(3)}, U-D r=${ud.r.toFixed(3)}`);
}
const shot = new URL("../../out/review/e2e_phantom.png", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
await page.evaluate(() => window.__cpt.setPose(-30, -25, "left"));
await page.screenshot({ path: shot });
console.log("screenshot", shot);
if (errors.length) { console.log("page errors:", errors); failed++; }
await browser.close();
await server.close();
process.exit(failed ? 1 : 0);
