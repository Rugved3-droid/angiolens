// v1.1 X-ray shadow mode vs the engine (feature flag "shadow"):  node e2e/shadow.e2e.mjs
// At 5 standard views (LCA) + 1 RCA view: the displayed shadow (the screen in the detector plane, seen from behind = image
// orientation) against the engine's projection: its vessel path length > 0 (readThickness; the shown image adds a 1 px blur).
// PASS needs, per view: best alignment shift within 1 px, mean boundary distance <= 1 px both ways, IoU >= 0.85.
// Writes out/review/v1_1_shadow/shadow_validation.png (per view: engine | shadow | overlay) and shadow_validation.json.
import { mkdirSync, writeFileSync } from "node:fs";
import { chromium } from "playwright";
import { createServer } from "vite";
const out = new URL("../../out/review/v1_1_shadow/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
mkdirSync(out, { recursive: true });
const server = await createServer({ server: { port: 5195, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const fail = (m) => { console.log("FAIL", m); process.exitCode = 1; };
const ok = (m) => console.log("PASS", m);
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
page.on("pageerror", (e) => fail(`pageerror ${e}`));
await page.goto("http://localhost:5195/atlas.html?scene=4&ff=shadow&shadow&still");
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
await page.waitForTimeout(1500);
const VIEWS = [["AP", 0, 0, "left"], ["RAO 30", -30, 0, "left"], ["LAO 45", 45, 0, "left"], ["RAO 30 / CAUD 25", -30, -25, "left"],
  ["LAO 40 / CAUD 30 (spider)", 40, -30, "left"], ["LAO 45 (RCA)", 45, 0, "right"]];
const res = await page.evaluate(async (VIEWS) => {
  const { lab, shadow } = window.atlas;
  const PX = 512;
  const p = lab.angio.params, keep = { ...p };
  const results = [], panels = [];
  for (const [name, a, b, tree] of VIEWS) {
    lab.setPose(a, b);
    const carm = lab.carm;
    // engine: vessel only
    Object.assign(p, { kBone: 0, kSoft: 0, noise: 0, showBone: false });
    lab.angio.render(carm, lab.detectorMm, tree, 0);
    const img = lab.angio.readImage();
    Object.assign(p, keep);
    let bg = 0;
    for (let i = 0; i < 64; i++) bg = Math.max(bg, img[i * 4]);
    // the engine's geometric projection: its vessel PATH LENGTH (the GPU = CPU validated quantity), before the display blur
    // (the composite softens the shown image with a 3x3 kernel, which widens every vessel by about a pixel)
    const T = lab.angio.readThickness().thickness;
    const E = new Uint8Array(PX * PX);
    for (let i = 0; i < PX * PX; i++) E[i] = T[i] > 0.01 ? 1 : 0;
    const S = shadow.shadowMask(carm, tree, PX);
    // best integer shift of S onto E (IoU)
    const iou = (dx, dy) => {
      let inter = 0, uni = 0;
      for (let r = 0; r < PX; r++) for (let c = 0; c < PX; c++) {
        const e = E[r * PX + c], rr = r - dy, cc = c - dx;
        const s = rr >= 0 && rr < PX && cc >= 0 && cc < PX ? S[rr * PX + cc] : 0;
        if (e && s) inter++;
        if (e || s) uni++;
      }
      return uni ? inter / uni : 0;
    };
    let best = { dx: 0, dy: 0, iou: -1 };
    for (let dy = -3; dy <= 3; dy++) for (let dx = -3; dx <= 3; dx++) { const v = iou(dx, dy); if (v > best.iou) best = { dx, dy, iou: v }; }
    const iou0 = iou(0, 0);
    // boundary distances (BFS distance transform from one mask's boundary, sampled at the other's boundary)
    const boundary = (M) => { const B = []; for (let r = 1; r < PX - 1; r++) for (let c = 1; c < PX - 1; c++) { const i = r * PX + c;
      if (M[i] && (!M[i - 1] || !M[i + 1] || !M[i - PX] || !M[i + PX])) B.push(i); } return B; };
    const dist = (B) => { const D = new Float32Array(PX * PX).fill(1e9); const q = []; for (const i of B) { D[i] = 0; q.push(i); }
      // two-pass chamfer (3-4) approximation of the Euclidean distance, in px
      for (let r = 0; r < PX; r++) for (let c = 0; c < PX; c++) { const i = r * PX + c;
        if (c > 0) D[i] = Math.min(D[i], D[i - 1] + 1); if (r > 0) D[i] = Math.min(D[i], D[i - PX] + 1);
        if (r > 0 && c > 0) D[i] = Math.min(D[i], D[i - PX - 1] + 1.4142); if (r > 0 && c < PX - 1) D[i] = Math.min(D[i], D[i - PX + 1] + 1.4142); }
      for (let r = PX - 1; r >= 0; r--) for (let c = PX - 1; c >= 0; c--) { const i = r * PX + c;
        if (c < PX - 1) D[i] = Math.min(D[i], D[i + 1] + 1); if (r < PX - 1) D[i] = Math.min(D[i], D[i + PX] + 1);
        if (r < PX - 1 && c < PX - 1) D[i] = Math.min(D[i], D[i + PX + 1] + 1.4142); if (r < PX - 1 && c > 0) D[i] = Math.min(D[i], D[i + PX - 1] + 1.4142); }
      return D; };
    const BE = boundary(E), BS = boundary(S);
    const DE = dist(BE), DS = dist(BS);
    const stat = (B, D) => { const v = B.map((i) => D[i]).sort((x, y) => x - y); return { mean: v.reduce((s, x) => s + x, 0) / Math.max(1, v.length),
      p95: v[Math.floor(v.length * 0.95)] ?? 0, max: v[v.length - 1] ?? 0 }; };
    const s2e = stat(BS, DE), e2s = stat(BE, DS);
    const area = { engine: E.reduce((s, x) => s + x, 0), shadow: S.reduce((s, x) => s + x, 0) };
    results.push({ name, alpha: a, beta: b, tree, best, iou0, s2e, e2s, area });
    // panel: engine | shadow | overlay (engine red, shadow cyan, both white)
    const cv = document.createElement("canvas"); cv.width = PX * 3; cv.height = PX;
    const g = cv.getContext("2d"); const id = g.createImageData(PX * 3, PX);
    for (let r = 0; r < PX; r++) for (let c = 0; c < PX; c++) {
      const i = r * PX + c, e = E[i], s = S[i];
      const put = (k, R, G, B) => { const j = (r * PX * 3 + k * PX + c) * 4; id.data[j] = R; id.data[j + 1] = G; id.data[j + 2] = B; id.data[j + 3] = 255; };
      put(0, img[i * 4], img[i * 4 + 1], img[i * 4 + 2]);
      put(1, s ? 20 : 225, s ? 30 : 232, s ? 45 : 245);
      put(2, e && s ? 255 : e ? 255 : s ? 40 : 12, e && s ? 255 : e ? 60 : s ? 220 : 16, e && s ? 255 : e ? 60 : s ? 255 : 24);
    }
    g.putImageData(id, 0, 0);
    g.fillStyle = "#ffd257"; g.font = "bold 22px Segoe UI"; g.fillText(`${name}  ·  engine | shadow | overlay`, 12, 30);
    panels.push(cv.toDataURL("image/png"));
  }
  lab.setPose(-30, -25);
  return { results, panels };
}, VIEWS);
for (const r of res.results) {
  const shiftOk = Math.abs(r.best.dx) <= 1 && Math.abs(r.best.dy) <= 1;
  const msg = `${r.name}: best shift (${r.best.dx}, ${r.best.dy}) px, IoU ${r.iou0.toFixed(3)} (best ${r.best.iou.toFixed(3)}), ` +
    `boundary mean ${r.s2e.mean.toFixed(2)} / ${r.e2s.mean.toFixed(2)} px (p95 ${r.s2e.p95.toFixed(2)} / ${r.e2s.p95.toFixed(2)})`;
  if (shiftOk && r.s2e.mean <= 1 && r.e2s.mean <= 1 && r.iou0 >= 0.85) ok(msg); else fail(msg);
}
// one figure: the panels stacked
const fig = await page.evaluate(async (panels) => {
  const imgs = await Promise.all(panels.map((u) => new Promise((r) => { const i = new Image(); i.onload = () => r(i); i.src = u; })));
  const cv = document.createElement("canvas"); cv.width = imgs[0].width / 2; cv.height = (imgs[0].height / 2) * imgs.length;
  const g = cv.getContext("2d");
  imgs.forEach((im, k) => g.drawImage(im, 0, k * im.height / 2, im.width / 2, im.height / 2));
  return cv.toDataURL("image/png");
}, res.panels);
writeFileSync(`${out}shadow_validation.png`, Buffer.from(fig.split(",")[1], "base64"));
writeFileSync(`${out}shadow_validation.json`, JSON.stringify(res.results, null, 1));
await browser.close(); await server.close();
