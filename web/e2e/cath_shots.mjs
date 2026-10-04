// Scene 5 review (D53): engaged JL4/JR4 root close-ups, the X-ray at RAO 30 / CAUD 25 mid-injection, and a recording of the
// full femoral LCA sequence from the operator camera with the monitor inset.   node e2e/cath_shots.mjs [shots|video|all]
import { mkdirSync, writeFileSync } from "node:fs";
import { chromium } from "playwright";
import { createServer } from "vite";
const out = new URL("../../out/review/cath/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
mkdirSync(out, { recursive: true });
const what = process.argv[2] ?? "all";
const server = await createServer({ server: { port: 5184, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const open = async (q, vp = { width: 1600, height: 1000 }) => {
  const page = await browser.newPage({ viewport: vp });
  page.on("pageerror", (e) => { console.log("pageerror", String(e)); process.exitCode = 1; });
  page.on("console", (m) => m.type() === "error" && console.log("console", m.text()));
  await page.goto(`http://localhost:5184/atlas.html?${q}`);
  await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
  return page;
};
/** The angiogram render target as a PNG, row 0 = top (+v), exactly as readImage() returns it. */
const saveXray = async (page, path) => {
  const url = await page.evaluate(() => {
    const lab = window.atlas.lab;
    const px = lab.angio.px, rgba = lab.angio.readImage();
    const c = Object.assign(document.createElement("canvas"), { width: px, height: px });
    c.getContext("2d").putImageData(new ImageData(rgba, px, px), 0, 0);
    return c.toDataURL("image/png");
  });
  writeFileSync(path, Buffer.from(url.split(",")[1], "base64"));
};

if (what === "shots" || what === "all") {
  const SHOTS = [
    ["root_JL4_engaged", "scene=5&target=left&engaged&cam=root"],
    ["root_JR4_engaged", "scene=5&target=right&engaged&cam=root"],
    ["lab_RAO30_CAUD25_mid_injection_LCA", "scene=5&target=left&engaged&carm=raocaud&cam=room&fill=0.55"],
    ["operator_femoral_engaged_LCA", "scene=5&target=left&engaged&carm=raocaud&cam=operator&fill=0.55"],
    ["operator_radial_engaged_RCA", "scene=5&access=radial&target=right&engaged&carm=lao45&cam=operator&fill=0.7"],
    ["scene3_operator_radial", "scene=3&op=radial&cam=operator"],
  ];
  for (const [name, q] of SHOTS) {
    const page = await open(`${q}&still`);
    await page.waitForTimeout(2500);
    await page.screenshot({ path: `${out}${name}.png`, timeout: 120000 });
    if (name.includes("mid_injection")) await saveXray(page, `${out}xray_RAO30_CAUD25_mid_injection_LCA.png`);
    console.log("wrote", name);
    await page.close();
  }
}
if (what === "video" || what === "all") {
  // spider view (LAO 40 / CAUD 30): a standard left-coronary view, and the detector stays on the far side of the operator
  const page = await open("scene=5&access=femoral&target=left&carm=spider&cam=operator", { width: 1280, height: 800 });
  await page.waitForTimeout(1500);
  const b64 = await page.evaluate(async () => {
    const src = document.getElementById("c");
    const W = src.width, H = src.height;
    const outC = Object.assign(document.createElement("canvas"), { width: W, height: H });
    const g = outC.getContext("2d");
    const sx = W / innerWidth;
    let run = true;
    const label = (el, text) => {
      const r = el.getBoundingClientRect();
      g.strokeStyle = "rgba(255,255,255,0.25)"; g.lineWidth = sx; g.strokeRect(r.left * sx, r.top * sx, r.width * sx, r.height * sx);
      g.fillStyle = "#9aa6b4"; g.font = `${11 * sx}px system-ui`; g.fillText(text, r.left * sx, (r.top - 6) * sx);
    };
    const draw = () => {
      const bg = g.createRadialGradient(W / 2, H * 0.38, 0, W / 2, H * 0.38, W * 0.75);
      bg.addColorStop(0, "#2a3140"); bg.addColorStop(0.55, "#141820"); bg.addColorStop(1, "#090b0f");
      g.fillStyle = bg; g.fillRect(0, 0, W, H);
      g.drawImage(src, 0, 0, W, H);
      if (getComputedStyle(document.getElementById("monitor")).display !== "none") label(document.getElementById("monitorImage"), "IMAGE");
      const cap = document.getElementById("caption");
      const op = Number(getComputedStyle(cap).opacity);
      if (cap.textContent && op > 0.01) {
        g.globalAlpha = op;
        g.font = `${15 * sx}px system-ui, Segoe UI, sans-serif`;
        const tw = g.measureText(cap.textContent).width + 36 * sx, th = 40 * sx;
        g.fillStyle = "rgba(14,18,25,0.72)"; g.beginPath(); g.roundRect((W - tw) / 2, H - 22 * sx - th, tw, th, 10 * sx); g.fill();
        g.fillStyle = "#e9edf2"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(cap.textContent, W / 2, H - 22 * sx - th / 2);
        g.textAlign = "start"; g.textBaseline = "alphabetic"; g.globalAlpha = 1;
      }
      g.fillStyle = "#9aa6b4"; g.font = `${11 * sx}px system-ui`;
      g.fillText(document.getElementById("foot").textContent, 12 * sx, H - 8 * sx);
      if (run) requestAnimationFrame(draw);
    };
    draw();
    const rec = new MediaRecorder(outC.captureStream(30), { mimeType: "video/webm;codecs=vp9", videoBitsPerSecond: 12e6 });
    const chunks = [];
    rec.ondataavailable = (e) => chunks.push(e.data);
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    rec.start(250);
    await sleep(1500);
    document.getElementById("bRun").click();                 // wire + catheter advance, wire out, shape, engage
    await sleep(11200);
    document.getElementById("bInject").click();              // contrast: fill, hold, wash out (cine: the heart beats)
    await sleep(5200);
    rec.stop(); run = false;
    await new Promise((r) => (rec.onstop = r));
    const buf = new Uint8Array(await new Blob(chunks, { type: "video/webm" }).arrayBuffer());
    let s = ""; for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode(...buf.subarray(i, i + 0x8000));
    return btoa(s);
  });
  writeFileSync(`${out}sequence_femoral_LCA_operator.webm`, Buffer.from(b64, "base64"));
  console.log("wrote sequence_femoral_LCA_operator.webm");
}
await browser.close(); await server.close();
