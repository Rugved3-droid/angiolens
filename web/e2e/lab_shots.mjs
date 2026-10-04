// Review screenshots of Scenes 3-4 (cath lab + X-ray pass) and the swing recording (web/atlas.html).
//   needs web/public/anatomy/ from export + build_atlas_xray.py;  node e2e/lab_shots.mjs [shots|video|all]
import { mkdirSync, writeFileSync } from "node:fs";
import { chromium } from "playwright";
import { createServer } from "vite";
const out = new URL("../../out/review/lab/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
mkdirSync(out, { recursive: true });
const what = process.argv[2] ?? "all";
const server = await createServer({ server: { port: 5182, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const ready = (page) => page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
const open = async (q, vp = { width: 1600, height: 1000 }) => {
  const page = await browser.newPage({ viewport: vp });
  page.on("pageerror", (e) => { console.log("pageerror", String(e)); process.exitCode = 1; });
  page.on("console", (m) => m.type() === "error" && console.log("console", m.text()));
  await page.goto(`http://localhost:5182/atlas.html?${q}`);
  await ready(page);
  return page;
};

if (what === "shots" || what === "all") {
  const SHOTS = [
    ["lab_AP", "scene=4&carm=ap&cam=room"], ["lab_RAO30", "scene=4&carm=rao30&cam=room"], ["lab_LAO45", "scene=4&carm=lao45&cam=room"],
    ["lab_RAO30_CAUD25", "scene=4&carm=raocaud&cam=room"], ["lab_LAO40_CAUD30_spider", "scene=4&carm=spider&cam=room"],
    ["lab_operator_view", "scene=3&carm=ap&cam=operator"], ["xray_beam_view_RAO30_CAUD25", "scene=4&carm=raocaud&cam=beam"],
    ["xray_side_by_side_spider", "scene=4&carm=spider&cam=split"], ["xray_side_by_side_LAO45_right", "scene=4&carm=lao45&cam=split&inject=right"],
  ];
  for (const [name, q] of SHOTS) {
    const page = await open(`${q}&still`);
    await page.waitForTimeout(2500);
    await page.screenshot({ path: `${out}${name}.png`, timeout: 120000 });
    console.log("wrote", name);
    await page.close();
  }
}
if (what === "video" || what === "all") {
  // in-page recording (MediaRecorder on a 2D composite of the WebGL canvas, the monitor frame and the caption), driven by the
  // same functions the buttons call: X-ray scene at AP, then one swing to RAO 30 / CAUD 25; the image builds on the detector.
  const page = await open("scene=4&carm=ap&cam=room", { width: 1280, height: 800 });
  await page.waitForTimeout(1500);
  const b64 = await page.evaluate(async () => {
    const src = document.getElementById("c");
    const W = src.width, H = src.height;
    const outC = Object.assign(document.createElement("canvas"), { width: W, height: H });
    const g = outC.getContext("2d");
    const sx = W / innerWidth;
    let run = true;
    const draw = () => {
      const bg = g.createRadialGradient(W / 2, H * 0.38, 0, W / 2, H * 0.38, W * 0.75);
      bg.addColorStop(0, "#2a3140"); bg.addColorStop(0.55, "#141820"); bg.addColorStop(1, "#090b0f");
      g.fillStyle = bg; g.fillRect(0, 0, W, H);
      g.drawImage(src, 0, 0, W, H);
      const mon = document.getElementById("monitor");
      if (getComputedStyle(mon).display !== "none") {
        const r = document.getElementById("monitorImage").getBoundingClientRect();
        g.strokeStyle = "rgba(255,255,255,0.25)"; g.lineWidth = 1 * sx; g.strokeRect(r.left * sx, r.top * sx, r.width * sx, r.height * sx);
        g.fillStyle = "#9aa6b4"; g.font = `${11 * sx}px system-ui`; g.fillText("IMAGE", r.left * sx, (r.top - 6) * sx);
      }
      const cap = document.getElementById("caption");
      const op = Number(getComputedStyle(cap).opacity);
      if (cap.textContent && op > 0.01) {
        g.globalAlpha = op;
        g.font = `${16 * sx}px system-ui, Segoe UI, sans-serif`;
        const tw = g.measureText(cap.textContent).width + 36 * sx, th = 42 * sx;
        g.fillStyle = "rgba(14,18,25,0.72)"; g.beginPath(); g.roundRect((W - tw) / 2, H - 22 * sx - th, tw, th, 10 * sx); g.fill();
        g.fillStyle = "#e9edf2"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(cap.textContent, W / 2, H - 22 * sx - th / 2);
        g.textAlign = "start"; g.textBaseline = "alphabetic";
        g.globalAlpha = 1;
      }
      if (run) requestAnimationFrame(draw);
    };
    draw();
    const rec = new MediaRecorder(outC.captureStream(30), { mimeType: "video/webm;codecs=vp9", videoBitsPerSecond: 12e6 });
    const chunks = [];
    rec.ondataavailable = (e) => chunks.push(e.data);
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    rec.start(250);
    await sleep(2000);                                                     // AP, image on the detector
    window.atlas.setCArmView("raocaud", 2600);                          // the swing (the function the toolbar calls)
    await sleep(6500);                                                     // swing + the new image building
    rec.stop(); run = false;
    await new Promise((r) => (rec.onstop = r));
    const buf = new Uint8Array(await new Blob(chunks, { type: "video/webm" }).arrayBuffer());
    let s = ""; for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode(...buf.subarray(i, i + 0x8000));
    return btoa(s);
  });
  writeFileSync(`${out}swing_AP_to_RAO30_CAUD25.webm`, Buffer.from(b64, "base64"));
  console.log("wrote swing_AP_to_RAO30_CAUD25.webm");
}
await browser.close(); await server.close();
