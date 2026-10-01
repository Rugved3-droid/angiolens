// Browser metrics (live + worker maps) must equal the Python reference on the phantom.
import { readFileSync } from "node:fs";
import { chromium } from "playwright";
import { createServer } from "vite";
const exp = JSON.parse(readFileSync(new URL("../public/cases/phantom/expected.json", import.meta.url))).metrics;
const server = await createServer({ server: { port: 5179, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await page.goto("http://localhost:5179/?case=phantom&e2e=1&px=128");
await page.waitForSelector("body[data-ready='1']");
let failed = 0;
const check = (n, ok, x = "") => { console.log(`${ok ? "PASS" : "FAIL"} ${n} ${x}`); if (!ok) failed++; };
for (const [pose, e] of Object.entries(exp.poses)) {
  const [a, b] = pose.split(",").map(Number);
  const m = await page.evaluate(([a, b, id]) => { window.__cpt.setPose(a, b, "left"); window.__cpt.select(id); return window.__cpt.metrics(); }, [a, b, exp.target_edge]);
  const ok = ["F", "O_inter", "O_self", "O_any"].every((k) => Math.abs(m[k] - e[k]) < 1e-9);
  check(`live metrics @${pose}`, ok, JSON.stringify({ app: m, py: e }));
}
await page.waitForFunction(() => window.__cpt.optimum() !== null, null, { timeout: 60000 });
const o = await page.evaluate(() => window.__cpt.optimum());
check("worker map optimum = Python", o.alpha === exp.optimum[0] && o.beta === exp.optimum[1] && Math.abs(o.cost - exp.optimum[2]) < 1e-6,
  JSON.stringify({ app: o, py: exp.optimum }));
if (errors.length) { console.log(errors); failed++; }
await browser.close(); await server.close();
process.exit(failed ? 1 : 0);
