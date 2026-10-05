// v1.1 study session run-through, recorded (Playwright video): welcome -> pre-test -> atlas training (tour, then Predict
// practice) -> post-test -> results -> CSV. Human-like pace; the training is abbreviated (the tour's first 25 s, 3 practice
// answers). node e2e/study_recording.mjs  -> out/review/v1_1/study_session.webm, study_results.png, study_session.csv
import { copyFileSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { chromium } from "playwright";
import { createServer } from "vite";
const out = new URL("../../out/review/v1_1/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
const vdir = `${out}video_tmp/`;
mkdirSync(vdir, { recursive: true });
const server = await createServer({ server: { port: 5197, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const VP = { width: 1152, height: 720 };
const ctx = await browser.newContext({ viewport: VP, recordVideo: { dir: vdir, size: VP } });
const page = await ctx.newPage();
page.on("pageerror", (e) => console.log("pageerror", String(e)));
const wait = (ms) => page.waitForTimeout(ms);
await page.goto("http://localhost:5197/study.html");
await page.evaluate(() => localStorage.clear());
await page.goto("http://localhost:5197/study.html");
await page.waitForSelector("#sWelcome.on");
await wait(2500);
await page.fill("#code", "");
await page.type("#code", "R2-0417", { delay: 120 });
await wait(800);
await page.click("#start");
await page.waitForSelector("#sIntro.on");
await wait(3500);

// a plausible learner: some errors before training, fewer after (the clicks are scripted; the record is real)
async function test(plan) {
  await page.click("#introGo");
  await page.waitForSelector("#sQuestion.on", { timeout: 120000 });
  for (let q = 0; q < 10; q++) {
    await page.waitForFunction((q) => document.getElementById("qcount").textContent.includes(`question ${q + 1} of`) &&
      !document.getElementById("tiles").classList.contains("wait"), q);
    await wait(1600 + ((q * 7919) % 5) * 450);
    const kinds = await page.$$eval("#tiles .tile", (t) => t.map((x) => x.dataset.kind));
    const want = plan[q];
    const pick = kinds.includes(want) ? want : kinds.find((k) => k !== "correct");
    const tile = await page.$(`#tiles .tile[data-kind="${pick}"]`);
    const bb = await tile.boundingBox();
    await page.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2, { steps: 12 });
    await wait(300);
    await tile.click();
  }
}
await test(["correct", "alpha-flip", "mirror", "correct", "beta-flip", "axis-swap", "correct", "alpha-flip", "correct", "mirror"]);
await page.waitForSelector("#sIntro.on");
await wait(4500);
await page.click("#introGo");
await page.waitForURL(/atlas\.html\?study=/, { timeout: 60000 });
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
await wait(2000);
await page.click("#bPlay");
await wait(25000);
await page.click("#tStop");
await wait(1500);
await page.evaluate(() => window.atlas.goScene(4));
await wait(3500);
await page.click("#bPredict");
await wait(3000);
for (const right of [true, false, true]) {
  const i = await page.evaluate((right) => { const k = window.atlas.predict.kinds(); return right ? k.indexOf("correct") : k.findIndex((x) => x !== "correct"); }, right);
  await wait(2200);
  await page.click(`.pr-tile >> nth=${i}`);
  await wait(3500);
  await page.click("#pr-next");
  await wait(1500);
}
await page.click("#sbFinish");
await page.waitForURL(/study\.html\?code=/, { timeout: 60000 });
await page.waitForSelector("#sIntro.on");
await wait(3500);
await test(["correct", "correct", "beta-flip", "correct", "correct", "correct", "axis-swap", "correct", "correct", "correct"]);
await page.waitForSelector("#sResults.on");
await wait(1500);
await page.screenshot({ path: `${out}study_results.png`, fullPage: true });
const [dl] = await Promise.all([page.waitForEvent("download"), page.click("#csv")]);
copyFileSync(await dl.path(), `${out}study_session.csv`);
await wait(4000);
const video = page.video();
await ctx.close();
const vpath = await video.path();
renameSync(vpath, `${out}study_session.webm`);
console.log("wrote study_session.webm", Math.round(readFileSync(`${out}study_session.webm`).length / 1e6), "MB; study_results.png; study_session.csv");
await browser.close(); await server.close();
