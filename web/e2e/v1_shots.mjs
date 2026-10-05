// v1.0 review: every scene at 1280 and 1920 px, the toolbar, Scene 6 mid-injection, Predict, an fps reading per scene, and the
// guided-tour recording.   node e2e/v1_shots.mjs [shots|fps|tour|all]
import { mkdirSync, writeFileSync } from "node:fs";
import { chromium } from "playwright";
import { createServer, preview } from "vite";
const out = new URL(`../../out/review/${process.env.OUT ?? "v1"}/`, import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
mkdirSync(out, { recursive: true });
const what = process.argv[2] ?? "all";
const usePreview = process.env.PREVIEW === "1";           // test the BUILT app (vite preview of dist/) instead of the dev server
const port = 5185;
const server = usePreview ? await preview({ preview: { port, strictPort: true } }) : await createServer({ server: { port, strictPort: true } });
if (!usePreview) await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist", ...(process.env.UNCAPPED ? ["--disable-gpu-vsync", "--disable-frame-rate-limit"] : [])] });
const errors = [];
const open = async (q, vp) => {
  const page = await browser.newPage({ viewport: vp });
  page.on("pageerror", (e) => { errors.push(`${q}: ${e}`); console.log("pageerror", q, String(e)); });
  page.on("console", (m) => m.type() === "error" && (errors.push(`${q}: ${m.text()}`), console.log("console", q, m.text())));
  await page.goto(`http://localhost:${port}/atlas.html?${q}${process.env.SUFFIX ?? ""}`);
  await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
  return page;
};
const ALL_SCENES = [
  ["s1_heart", "scene=1"], ["s1_root", "scene=1&view=root"], ["s2_chest", "scene=2"], ["s2_left", "scene=2&view=left"],
  ["s3_cathlab", "scene=3&carm=raocaud"], ["s3_operator_radial", "scene=3&cam=operator&op=radial"],
  ["s4_xray_room", "scene=4&carm=raocaud"], ["s4_beam", "scene=4&carm=raocaud&cam=beam"], ["s4_split", "scene=4&carm=spider&cam=split"], ["s4_split_raocaud", "scene=4&carm=raocaud&cam=split"],
  ["s4_predict", "scene=4&carm=ap&predict"],
  ["s5_operator", "scene=5&carm=spider&engaged"], ["s5_root", "scene=5&cam=root&engaged"],
  ["s6_slice", "scene=6&carm=raocaud"], ["s6_slice_mid_injection", "scene=6&carm=raocaud&fill=0.5"],
];
// ONLY=s1_root,s5_root: just these views (OUT=v1_1: another folder under out/review/)
const SCENES = process.env.ONLY ? ALL_SCENES.filter(([n]) => process.env.ONLY.split(",").includes(n)) : ALL_SCENES;
if (what === "shots" || what === "all") {
  for (const vp of [{ width: 1280, height: 800 }, { width: 1920, height: 1080 }]) {
    for (const [name, q] of SCENES) {
      const page = await open(`${q}&still`, vp);
      await page.waitForTimeout(2600);
      await page.screenshot({ path: `${out}${vp.width}_${name}.png` });
      if (vp.width === 1280) {
        const bar = await page.$("#bar");
        const bb = await bar.boundingBox();
        const oneRow = bb.height < 50;
        const overflow = await page.evaluate(() => { const b = document.getElementById("bar"); return b.scrollWidth > b.clientWidth + 1; });
        console.log(`${name}: toolbar ${Math.round(bb.width)}x${Math.round(bb.height)} px, one row: ${oneRow}, overflow: ${overflow}`);
        if (name === "s4_xray_room") await bar.screenshot({ path: `${out}toolbar_1280.png` });
      }
      await page.close();
    }
  }
}
if (what === "fps" || what === "all") {
  const res = {};
  for (const [name, q] of SCENES) {
    const page = await open(q, { width: 1600, height: 1000 });
    await page.waitForTimeout(6500);               // the adaptive resolution settles first
    // average over 3 s: requestAnimationFrame count (the page's own loop is the frame loop)
    const fps = await page.evaluate(() => new Promise((r) => { let n = 0; const t0 = performance.now();
      const f = () => { n++; if (performance.now() - t0 < 3000) requestAnimationFrame(f); else r((n * 1000) / (performance.now() - t0)); };
      requestAnimationFrame(f); }));
    res[name] = Math.round(fps);
    console.log(`fps ${name}: ${Math.round(fps)}`);
    await page.close();
  }
  writeFileSync(`${out}fps.json`, JSON.stringify(res, null, 1));
}
if (what === "tour" || what === "all") {
  const page = await open("scene=1", { width: 1280, height: 800 });
  await page.waitForTimeout(1200);
  const result = await page.evaluate(async () => {
    const src = document.getElementById("c");
    const W = src.width, H = src.height;
    const outC = Object.assign(document.createElement("canvas"), { width: W, height: H });
    const g = outC.getContext("2d");
    const sx = W / innerWidth;
    let run = true, frames = 0, slow = 0, last = performance.now(), worst = 0;
    const box = (el) => { const r = el.getBoundingClientRect(); return [r.left * sx, r.top * sx, r.width * sx, r.height * sx]; };
    const panel = (el) => { const [x, y, w, h] = box(el); g.fillStyle = "rgba(13,17,24,0.78)"; g.strokeStyle = "rgba(255,255,255,0.12)";
      g.beginPath(); g.roundRect(x, y, w, h, 10 * sx); g.fill(); g.stroke(); };
    const text = (el, size, color = "#e9edf2") => { const [x, y, w, h] = box(el); g.fillStyle = color; g.font = `${size * sx}px system-ui, Segoe UI`;
      g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(el.textContent, x + w / 2, y + h / 2); g.textAlign = "start"; };
    const vis = (el) => el && getComputedStyle(el).display !== "none" && el.getBoundingClientRect().width > 0;
    const draw = (now) => {
      frames++;
      const dt = now - last; last = now; worst = Math.max(worst, dt); if (dt > 1000 / 45) slow++;
      const bg = g.createRadialGradient(W / 2, H * 0.38, 0, W / 2, H * 0.38, W * 0.75);
      bg.addColorStop(0, "#2a3140"); bg.addColorStop(0.55, "#141820"); bg.addColorStop(1, "#090b0f");
      g.fillStyle = bg; g.fillRect(0, 0, W, H);
      g.drawImage(src, 0, 0, W, H);
      const fd = document.getElementById("fader"); const fo = Number(getComputedStyle(fd).opacity);
      if (fo > 0.01) { g.globalAlpha = fo; g.fillStyle = "#0b0e13"; g.fillRect(0, 0, W, H); g.globalAlpha = 1; }
      // HTML layers composited for the recording: toolbar, tour bar, slice panel, monitor frame, caption
      const bar = document.getElementById("bar"); panel(bar);
      for (const b of bar.querySelectorAll("button")) {
        const on = b.classList.contains("on") || b.classList.contains("accent");
        if (on) { const [x, y, w, h] = box(b); g.fillStyle = b.classList.contains("accent") ? "#e8383d" : "rgba(255,255,255,0.14)"; g.beginPath(); g.roundRect(x, y, w, h, 7 * sx); g.fill(); }
        text(b, 13, b.disabled ? "rgba(233,237,242,0.35)" : "#e9edf2");
      }
      const tb = document.getElementById("tourBar");
      if (vis(tb)) { panel(tb); for (const b of tb.querySelectorAll("button")) text(b, 14);
        for (const d of tb.querySelectorAll(".dot")) { const [x, y, w] = box(d); g.fillStyle = d.classList.contains("on") ? "#ffd24a" : d.classList.contains("done") ? "rgba(255,255,255,0.55)" : "rgba(255,255,255,0.22)";
          g.beginPath(); g.arc(x + w / 2, y + w / 2, w / 2, 0, 7); g.fill(); } }
      const sp = document.getElementById("slicePanel");
      if (vis(sp)) { panel(sp); const c = document.getElementById("sliceCanvas"); const [x, y, w, h] = box(c); g.drawImage(c, x, y, w, h);
        text(sp.querySelector(".ttl"), 15); }
      const mon = document.getElementById("monitor");
      if (vis(mon)) { const [x, y, w, h] = box(document.getElementById("monitorImage")); g.strokeStyle = "rgba(255,255,255,0.25)"; g.strokeRect(x, y, w, h);
        const dot = document.getElementById("xrayDot"); if (vis(dot)) { const [dx, dy, dw] = box(dot); g.strokeStyle = "#ffd24a"; g.lineWidth = 2 * sx;
          g.beginPath(); g.arc(dx + dw / 2, dy + dw / 2, dw / 2, 0, 7); g.stroke(); g.lineWidth = 1; } }
      const cap = document.getElementById("caption");
      const op = Number(getComputedStyle(cap).opacity);
      if (cap.textContent && op > 0.01 && vis(cap)) { g.globalAlpha = op; panel(cap); text(cap, 15); g.globalAlpha = 1; }
      if (run) requestAnimationFrame(draw);
    };
    requestAnimationFrame(draw);
    const rec = new MediaRecorder(outC.captureStream(30), { mimeType: "video/webm;codecs=vp9", videoBitsPerSecond: 6e6 });   // under 30 MB for the 80 s tour
    const chunks = [];
    rec.ondataavailable = (e) => chunks.push(e.data);
    rec.start(500);
    const t0 = performance.now();
    window.atlas.startTour();
    await new Promise((r) => { const f = () => (document.getElementById("tourBar").style.display === "none" && performance.now() - t0 > 3000) || performance.now() - t0 > 150000 ? r() : setTimeout(f, 250); f(); });
    await new Promise((r) => setTimeout(r, 1500));
    rec.stop(); run = false;
    await new Promise((r) => (rec.onstop = r));
    const buf = new Uint8Array(await new Blob(chunks, { type: "video/webm" }).arrayBuffer());
    let s = ""; for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode(...buf.subarray(i, i + 0x8000));
    return { b64: btoa(s), seconds: (performance.now() - t0) / 1000, frames, slowFrames: slow, worstFrameMs: Math.round(worst) };
  });
  writeFileSync(`${out}tour.webm`, Buffer.from(result.b64, "base64"));
  const stats = { seconds: Math.round(result.seconds), frames: result.frames, meanFps: Math.round(result.frames / result.seconds),
    framesSlowerThan45fps: result.slowFrames, worstFrameMs: result.worstFrameMs };
  writeFileSync(`${out}tour_stats.json`, JSON.stringify(stats, null, 1));
  console.log("wrote tour.webm", JSON.stringify(stats));
}
writeFileSync(`${out}errors.json`, JSON.stringify(errors, null, 1));
console.log("page errors:", errors.length);
await browser.close();
if (usePreview) server.httpServer.close(); else await server.close();
