// v1.1 study session, end to end (fast, no video): welcome -> pre-test -> atlas training (study bar) -> post-test -> results + CSV.
//   node e2e/study.e2e.mjs
// Checks: every tile is the engine's image for its pose (pixel-exact), the mirror tile is the exact left-right flip, the
// answers, error types and response times are recorded, the training counts the atlas Predict practice and the tour, the
// results screen matches the record, and the CSV has one row per question with the fixed columns and no name.
import { chromium } from "playwright";
import { createServer } from "vite";
const server = await createServer({ server: { port: 5194, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const fail = (m) => { console.log("FAIL", m); process.exitCode = 1; };
const ok = (m) => console.log("PASS", m);
const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
const page = await ctx.newPage();
page.on("pageerror", (e) => fail(`pageerror ${e}`));
const CODE = "P-E2E01";
await page.goto("http://localhost:5194/study.html");
await page.evaluate(() => localStorage.clear());
await page.goto("http://localhost:5194/study.html");
await page.waitForSelector("#sWelcome.on");

// a name is refused
await page.fill("#code", "John");
await page.click("#start");
if ((await page.textContent("#codeErr")).includes("No names")) ok("a name is refused as a participant code");
else fail("name accepted as a code");
await page.fill("#code", CODE);
await page.click("#start");
await page.waitForSelector("#sIntro.on");

// answer plan: question q -> which kind to click (correct, or a named wrong kind when offered)
const PLAN_PRE = ["correct", "alpha-flip", "correct", "beta-flip", "mirror", "correct", "axis-swap", "correct", "alpha-flip", "correct"];
const PLAN_POST = ["correct", "correct", "beta-flip", "correct", "correct", "mirror", "correct", "correct", "axis-swap", "correct"];
async function runTest(plan, label) {
  await page.click("#introGo");
  await page.waitForSelector("#sQuestion.on", { timeout: 120000 });
  let tilesExact = 0, mirrorExact = 0;
  const chosenKinds = [];
  for (let q = 0; q < 10; q++) {
    await page.waitForFunction((q) => document.getElementById("qcount").textContent.includes(`question ${q + 1} of`) &&
      !document.getElementById("tiles").classList.contains("wait"), q);
    // re-render each tile's pose through the hook and compare
    const check = await page.evaluate(async ({ q, label }) => {
      const s = window.study.session;
      const phase = label;
      const setName = phase === "pre" ? s.order[0] : s.order[1];
      const { SET_A, SET_B, tilesFor, hashCode } = await import("/src/study/studyCore.ts");
      const pose = (setName === "A" ? SET_A : SET_B)[q];
      const seed = hashCode(s.code) ^ (phase === "pre" ? 0x5eed : 0xa11ce);
      const tiles = tilesFor(pose, q, seed);
      const shown = [...document.querySelectorAll("#tiles .tile")].map((t) => {
        const c = t.querySelector("canvas");
        return { kind: t.dataset.kind, px: c.getContext("2d").getImageData(0, 0, c.width, c.height).data };
      });
      let exact = 0, mirror = 0;
      for (let i = 0; i < 4; i++) {
        const want = await window.study.renderPose(tiles[i].alpha, tiles[i].beta, pose.tree, tiles[i].mirrorLR);
        let diff = 0;
        for (let k = 0; k < want.length; k++) diff = Math.max(diff, Math.abs(want[k] - shown[i].px[k]));
        if (diff <= 1 && tiles[i].kind === shown[i].kind) exact++;
        if (tiles[i].kind === "mirror") {
          const corr = await window.study.renderPose(pose.alpha, pose.beta, pose.tree, false);
          const n = Math.sqrt(corr.length / 4);
          let md = 0;
          for (let r = 0; r < n; r++) for (let col = 0; col < n; col++) for (let ch = 0; ch < 3; ch++)
            md = Math.max(md, Math.abs(corr[(r * n + col) * 4 + ch] - shown[i].px[(r * n + (n - 1 - col)) * 4 + ch]));
          if (md <= 1) mirror++;
        }
      }
      return { exact, mirror, hasMirror: tiles.some((t) => t.kind === "mirror"), kinds: tiles.map((t) => t.kind) };
    }, { q, label });
    if (check.exact === 4) tilesExact++;
    if (!check.hasMirror || check.mirror === 1) mirrorExact++;
    const want = plan[q];
    const kinds = check.kinds;
    const pick = kinds.includes(want) ? want : kinds.find((k) => k !== "correct");
    chosenKinds.push(pick);
    await page.waitForTimeout(150 + q * 20);
    await page.click(`#tiles .tile[data-kind="${pick}"]`);
  }
  if (tilesExact === 10) ok(`${label}: all 40 tiles are the engine's images for their poses (pixel-exact)`);
  else fail(`${label}: ${tilesExact}/10 questions with all tiles exact`);
  if (mirrorExact === 10) ok(`${label}: every mirror tile is the exact left-right flip of the correct image`);
  else fail(`${label}: mirror tiles ${mirrorExact}/10`);
  return chosenKinds;
}
const preChosen = await runTest(PLAN_PRE, "pre");

// training: the atlas with the study bar
await page.waitForSelector("#sIntro.on");
if ((await page.textContent("#introTitle")).includes("Training")) ok("after the pre-test: the training part");
else fail("training intro missing");
await page.click("#introGo");
await page.waitForURL(/atlas\.html\?study=/, { timeout: 60000 });
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
await page.waitForSelector("#studyBar");
ok("the atlas opens with the study bar (feature flag ?study=)");
await page.evaluate(() => window.dispatchEvent(new CustomEvent("cpt:tour-complete")));
// two Predict practice answers in the atlas (one correct, one wrong)
await page.evaluate(() => window.atlas.setPredict(true));
await page.waitForTimeout(1500);
for (const correct of [true, false]) {
  await page.evaluate((correct) => {
    const p = window.atlas.predict;
    p.animMs = 0;
    const kinds = p.kinds();
    const i = correct ? kinds.indexOf("correct") : kinds.findIndex((k) => k !== "correct");
    document.querySelectorAll(".pr-tile")[i].click();
  }, correct);
  await page.waitForTimeout(400);
  await page.evaluate(() => document.getElementById("pr-next").click());
  await page.waitForTimeout(600);
}
await page.click("#sbFinish");
await page.waitForURL(/study\.html\?code=/, { timeout: 60000 });
await page.waitForSelector("#sIntro.on", { timeout: 60000 });
const tr = await page.evaluate(() => window.study.session.training);
if (tr.tourCompleted && tr.practiceAnswers === 2 && tr.practiceCorrect === 1 && tr.started && tr.ended)
  ok(`training recorded: tour completed, practice ${tr.practiceCorrect}/${tr.practiceAnswers}`);
else fail(`training record ${JSON.stringify(tr)}`);

const postChosen = await runTest(PLAN_POST, "post");
await page.waitForSelector("#sResults.on");
const s = await page.evaluate(() => window.study.session);
const preOk = preChosen.filter((k) => k === "correct").length, postOk = postChosen.filter((k) => k === "correct").length;
const shownPre = await page.textContent("#rPre"), shownPost = await page.textContent("#rPost");
if (shownPre === `${preOk} / 10` && shownPost === `${postOk} / 10`) ok(`results screen: pre ${shownPre}, post ${shownPost}`);
else fail(`results ${shownPre} ${shownPost} vs ${preOk} ${postOk}`);
const rec = s.answers.map((a) => a.chosen);
if (JSON.stringify(rec) === JSON.stringify([...preChosen, ...postChosen])) ok("every answer recorded with its kind (correct / error type)");
else fail(`recorded ${rec}`);
if (s.answers.every((a) => a.rtMs > 50 && a.rtMs < 60000)) ok("response times recorded for all 20 answers");
else fail("response times");
const preSets = new Set(s.answers.filter((a) => a.phase === "pre").map((a) => `${a.pose.alpha},${a.pose.beta}`));
if (s.answers.filter((a) => a.phase === "post").every((a) => !preSets.has(`${a.pose.alpha},${a.pose.beta}`)) && s.order[0] !== s.order[1])
  ok(`the post-test poses are all new (set ${s.order[0]} then ${s.order[1]})`);
else fail("post-test reused a pre-test pose");

// CSV
const [dl] = await Promise.all([page.waitForEvent("download"), page.click("#csv")]);
const path = await dl.path();
const csv = (await import("node:fs")).readFileSync(path, "utf8");
const lines = csv.trim().split(/\r\n/);
const head = lines[0].split(",");
const col = (r, n) => lines[r].split(",")[head.indexOf(n)];
if (lines.length === 21 && head[0] === "participant" && head.includes("error_type") && head.includes("rt_ms")
    && lines.slice(1).every((l) => l.startsWith(CODE + ",")) && !/name/i.test(head.join()))
  ok(`CSV: 20 rows + header, anonymous code only (${dl.suggestedFilename()})`);
else fail(`CSV shape ${lines.length} ${head}`);
let csvOk = true;
for (let i = 0; i < 20; i++) {
  const k = [...preChosen, ...postChosen][i];
  if (col(i + 1, "chosen") !== k || col(i + 1, "correct") !== (k === "correct" ? "1" : "0") || col(i + 1, "error_type") !== (k === "correct" ? "" : k)) csvOk = false;
}
if (csvOk) ok("CSV rows match the record (chosen, correct, error type)");
else fail("CSV rows differ from the record");
(await import("node:fs")).writeFileSync(new URL("../../out/review/v1_1/study_sample.csv", import.meta.url), csv);
await browser.close(); await server.close();
