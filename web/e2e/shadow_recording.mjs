// v1.1 shadow-mode recording (feature flag "shadow"): the C-arm swings through standard views with the shadow and the streaming
// rays live, then the beam view, then the RCA.   node e2e/shadow_recording.mjs  -> out/review/v1_1_shadow/shadow_mode.webm
import { mkdirSync, writeFileSync } from "node:fs";
import { chromium } from "playwright";
import { createServer } from "vite";
const out = new URL("../../out/review/v1_1_shadow/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
mkdirSync(out, { recursive: true });
const server = await createServer({ server: { port: 5196, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
page.on("pageerror", (e) => console.log("pageerror", String(e)));
await page.goto("http://localhost:5196/atlas.html?scene=4&ff=shadow&shadow&rays&carm=ap");
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
await page.waitForTimeout(2500);
const result = await page.evaluate(async () => {
  const A = window.atlas;
  const gl = A.dbg.renderer.domElement;
  const outC = Object.assign(document.createElement("canvas"), { width: gl.width, height: gl.height });
  const g = outC.getContext("2d");
  let cap = "", run = true;
  // the page's background (a radial gradient: the same as the tour recorder)
  const bg = g.createRadialGradient(outC.width / 2, outC.height * 0.38, 0, outC.width / 2, outC.height * 0.38, outC.width * 0.75);
  bg.addColorStop(0, "#2a3140"); bg.addColorStop(0.55, "#141820"); bg.addColorStop(1, "#090b0f");
  const draw = () => {
    // the WebGL canvas is transparent over the page background: paint the background first, or old frames show through
    g.fillStyle = bg; g.fillRect(0, 0, outC.width, outC.height);
    g.drawImage(gl, 0, 0);
    if (cap) {
      const s = outC.width / 1280;
      g.font = `${Math.round(17 * s)}px Segoe UI`;
      const w = g.measureText(cap).width + 40 * s;
      g.fillStyle = "rgba(13,18,25,0.82)";
      g.beginPath(); g.roundRect((outC.width - w) / 2, outC.height - 70 * s, w, 40 * s, 10 * s); g.fill();
      g.fillStyle = "#e9edf2"; g.textAlign = "center"; g.fillText(cap, outC.width / 2, outC.height - 44 * s);
    }
    g.font = `600 ${Math.round(13 * outC.width / 1280)}px Segoe UI`; g.textAlign = "left"; g.fillStyle = "#f2c14e";
    g.fillText("X-RAY SHADOW MODE (v1.1)", 20 * outC.width / 1280, 30 * outC.width / 1280);
    if (run) requestAnimationFrame(draw);
  };
  requestAnimationFrame(draw);
  const rec = new MediaRecorder(outC.captureStream(30), { mimeType: "video/webm;codecs=vp9", videoBitsPerSecond: 5e6 });
  const chunks = [];
  rec.ondataavailable = (e) => chunks.push(e.data);
  rec.start(500);
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const step = async (c, fn, ms) => { cap = c; fn?.(); await wait(ms); };
  await step("A point light at the X-ray tube: the coronary arteries cast their shadow on the detector.", null, 4500);
  await step("The rays stream from the source, past the vessels, to the detector.", null, 3500);
  await step("Swing to RAO 30: the shadow is the angiogram (inset), live with the C-arm.", () => A.setCArmView("rao30", 2800), 5000);
  await step("LAO 45.", () => A.setCArmView("lao45", 2800), 4500);
  await step("LAO 40 / CAUD 30: the spider view.", () => A.setCArmView("spider", 2800), 4800);
  await step("From the side: tube, vessels and detector on one line.", () => A.setLabCam("beam", 2400), 4200);
  await step("RAO 30 / CAUD 25, seen side-on.", () => A.setCArmView("raocaud", 2800), 4800);
  await step("Back in the room: now the right coronary.", () => { A.setLabCam("room", 2400); }, 3000);
  await step("Right coronary (RCA) shadow at RAO 30 / CAUD 25.", () => A.setInject("right"), 3500);
  await step("LAO 45: the RCA's classic C shape, in the shadow and on the image alike.", () => A.setCArmView("lao45", 2800), 5200);
  rec.stop(); run = false;
  await new Promise((r) => (rec.onstop = r));
  const buf = new Uint8Array(await new Blob(chunks, { type: "video/webm" }).arrayBuffer());
  let s = ""; for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  return btoa(s);
});
writeFileSync(`${out}shadow_mode.webm`, Buffer.from(result, "base64"));
console.log("wrote shadow_mode.webm", Math.round(Buffer.from(result, "base64").length / 1e6), "MB");
await browser.close(); await server.close();
