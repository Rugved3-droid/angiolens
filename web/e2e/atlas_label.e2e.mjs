// Label mode: hover finds an unlabeled branch, a click selects it, picking "D1" names it, hover then shows "D1",
// and the label survives a reload (localStorage). Real pointer events only.
import { chromium } from "playwright";
import { createServer } from "vite";
const server = await createServer({ server: { port: 5181, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
page.on("pageerror", (e) => { console.log("pageerror", String(e)); process.exitCode = 1; });
await page.goto("http://localhost:5181/atlas.html?scene=1&view=front&label&still");
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
await page.waitForTimeout(1500);
let hit = null;
outer: for (let y = 250; y < 820; y += 6) for (let x = 480; x < 1160; x += 6) {
  await page.mouse.move(x, y);
  const t = await page.$eval("#hover", (e) => (e.style.display === "block" ? e.textContent : ""));
  if (t.startsWith("Unlabeled branch")) { hit = [x, y, t]; break outer; }
}
if (!hit) throw new Error("no branch found under the pointer");
console.log("hover:", hit[2]);
await page.mouse.click(hit[0], hit[1]);
await page.waitForTimeout(200);
console.log("panel:", await page.$eval("#sel", (e) => e.textContent));
await page.click("#names button:text-is('D1')");
await page.mouse.move(hit[0] + 1, hit[1]); await page.mouse.move(hit[0], hit[1]);
const after = await page.$eval("#hover", (e) => e.textContent);
console.log("hover after naming:", after);
await page.reload();
await page.waitForSelector("body[data-ready='1']");
await page.waitForTimeout(800);
await page.mouse.move(hit[0] + 1, hit[1]); await page.mouse.move(hit[0], hit[1]);
const reloaded = await page.$eval("#hover", (e) => e.textContent);
console.log("after reload:", reloaded);
const ok = after === "D1" && reloaded === "D1";
console.log(ok ? "LABEL E2E PASS" : "LABEL E2E FAIL");
if (!ok) process.exitCode = 1;
await browser.close(); await server.close();
