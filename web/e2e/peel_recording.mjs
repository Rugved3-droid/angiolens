// v1.1 peel mini-tour recording (feature flag "peel"): "Where do the coronaries come from?", then a hand drag and release
//   node e2e/peel_recording.mjs  -> out/review/v1_1_peel/peel_minitour.webm
import { mkdirSync, writeFileSync } from "node:fs";
import { chromium } from "playwright";
import { createServer } from "vite";
const out = new URL("../../out/review/v1_1_peel/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
mkdirSync(out, { recursive: true });
const server = await createServer({ server: { port: 5199, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
page.on("pageerror", (e) => console.log("pageerror", String(e)));
await page.goto("http://localhost:5199/atlas.html?scene=1&ff=peel");
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
    g.fillText("PEEL MODE (v1.1)", 20 * outC.width / 1280, 30 * outC.width / 1280);
    if (run) requestAnimationFrame(draw);
  };
  requestAnimationFrame(draw);
  const rec = new MediaRecorder(outC.captureStream(30), { mimeType: "video/webm;codecs=vp9", videoBitsPerSecond: 5e6 });
  const chunks = [];
  rec.ondataavailable = (e) => chunks.push(e.data);
  rec.start(500);
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const step = async (c, fn, ms) => { cap = c; fn?.(); await wait(ms); };
  // the app's own caption (the mini-tour writes it) is drawn by the recorder
  const live = setInterval(() => { cap = document.getElementById("caption").textContent; }, 100);
  await wait(1500);
  await A.runOrigins();
  await wait(1500);
  A.peel.reset();
  await wait(1800);
  clearInterval(live);
  cap = "By hand: drag the pulmonary trunk away, release, and it springs back.";
  await wait(1200);
  // a scripted hand drag on the pulmonary trunk (the same code path as the mouse)
  const { scene, camera, renderer } = A.dbg;
  let m = null; scene.traverse((o) => { if (o.isMesh && (o.userData?.anatomical_name ?? o.name) === "Pulmonary trunk") m = o; });
  m.geometry.computeBoundingBox();
  const c = m.geometry.boundingBox.getCenter(m.position.clone()).project(camera);
  const r = renderer.domElement.getBoundingClientRect();
  const x = r.left + (c.x + 1) / 2 * r.width, y = r.top + (1 - c.y) / 2 * r.height;
  const ev = (type, dx, dy) => (type === "pointerdown" ? renderer.domElement : window).dispatchEvent(new PointerEvent(type,
    { clientX: x + dx, clientY: y + dy, button: 0, bubbles: true, pointerId: 1, isPrimary: true }));
  ev("pointerdown", 0, 0);
  for (let k = 1; k <= 40; k++) { ev("pointermove", k * 0.6, -k * 4); await wait(30); }
  await wait(900);
  ev("pointerup", 24, -160);
  await wait(2600);
  cap = "Double-click keeps a part removed; Reset puts everything back.";
  await wait(2500);
  rec.stop(); run = false;
  await new Promise((r) => (rec.onstop = r));
  const buf = new Uint8Array(await new Blob(chunks, { type: "video/webm" }).arrayBuffer());
  let s = ""; for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  return btoa(s);
});
writeFileSync(`${out}peel_minitour.webm`, Buffer.from(result, "base64"));
console.log("wrote peel_minitour.webm", Math.round(Buffer.from(result, "base64").length / 1e6), "MB");
await browser.close(); await server.close();
