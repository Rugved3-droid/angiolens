// Review screenshots + a short recording of the atlas scenes (web/atlas.html).
//   copy z_anatomy_{heart,heart_illustrative,access_routes,skeleton,skin}.glb from assets/anatomy/ -> web/public/anatomy/ first
//   (not z_anatomy_skin_regions.glb, the per-region intermediate);  node e2e/atlas_shots.mjs [shots|video|all]
import { mkdirSync, writeFileSync } from "node:fs";
import { chromium } from "playwright";
import { createServer } from "vite";
const out = new URL("../../out/review/atlas/", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
mkdirSync(out, { recursive: true });
const what = process.argv[2] ?? "all";
const server = await createServer({ server: { port: 5180, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const VP = { width: 1600, height: 1000 };
const ready = (page) => page.waitForSelector("body[data-ready='1']", { timeout: 300000 });

if (what === "shots" || what === "all") {
  const SHOTS = [
    ["scene1_heart_front", "scene=1&view=front"], ["scene1_heart_lao", "scene=1&view=lao"], ["scene1_aortic_root", "scene=1&view=root"],
    ["scene2_chest_front", "scene=2&view=front"], ["scene2_chest_left", "scene=2&view=left"], ["scene2_chest_feet", "scene=2&view=feet"],
    ["scene2_body_access_routes", "scene=2&view=body&routes"],      // review only: the routes are hidden in the scenes
    ...(process.env.EXTRA ? process.env.EXTRA.split(";").map((s) => s.split("|")) : []),
  ];
  for (const [name, q] of SHOTS) {
    const page = await browser.newPage({ viewport: VP });
    page.on("pageerror", (e) => console.log("pageerror", String(e)));
    page.on("console", (m) => m.type() === "error" && console.log("console", m.text()));
    await page.goto(`http://localhost:5180/atlas.html?${q}&still`);
    await ready(page);
    await page.waitForTimeout(1800);
    await page.screenshot({ path: `${out}${name}.png`, timeout: 120000 });
    console.log("wrote", name);
    await page.close();
  }
}
if (what === "video" || what === "all") {
  // In-page recording: the WebGL canvas + background + caption are composited into a 2D canvas every animation frame and
  // recorded with MediaRecorder at the page's real frame rate (Playwright's screencast drops most transition frames).
  // The scene is driven by the same buttons a user clicks.
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  page.on("pageerror", (e) => console.log("pageerror", String(e)));
  await page.goto("http://localhost:5180/atlas.html?scene=1&view=front");
  await ready(page);
  await page.waitForTimeout(1000);
  const b64 = await page.evaluate(async () => {
    const src = document.getElementById("c");
    const W = src.width, H = src.height;
    const out = Object.assign(document.createElement("canvas"), { width: W, height: H });
    const g = out.getContext("2d");
    const sx = W / innerWidth;
    let run = true;
    const draw = () => {
      const bg = g.createRadialGradient(W / 2, H * 0.38, 0, W / 2, H * 0.38, W * 0.75);
      bg.addColorStop(0, "#2a3140"); bg.addColorStop(0.55, "#141820"); bg.addColorStop(1, "#090b0f");
      g.fillStyle = bg; g.fillRect(0, 0, W, H);
      g.drawImage(src, 0, 0, W, H);
      const cap = document.getElementById("caption");
      const op = Number(getComputedStyle(cap).opacity);
      if (cap.textContent && op > 0.01) {
        g.globalAlpha = op;
        g.font = `${16 * sx}px system-ui, Segoe UI, sans-serif`;
        const tw = g.measureText(cap.textContent).width + 36 * sx, th = 42 * sx;
        g.fillStyle = "rgba(14,18,25,0.72)"; g.beginPath(); g.roundRect((W - tw) / 2, H - 22 * sx - th, tw, th, 10 * sx); g.fill();
        g.fillStyle = "#e9edf2"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(cap.textContent, W / 2, H - 22 * sx - th / 2);
        g.globalAlpha = 1;
      }
      if (run) requestAnimationFrame(draw);
    };
    draw();
    const rec = new MediaRecorder(out.captureStream(30), { mimeType: "video/webm;codecs=vp9", videoBitsPerSecond: 12e6 });
    const chunks = [];
    rec.ondataavailable = (e) => chunks.push(e.data);
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    rec.start(250);
    await sleep(2500);                                                   // heartbeat in the close-up
    document.getElementById("bPatient").click();                         // pull-out into the chest
    await sleep(5200);
    document.querySelector("#views button[data-v='feet']").click();      // one view change
    await sleep(4300);
    rec.stop(); run = false;
    await new Promise((r) => (rec.onstop = r));
    const buf = new Uint8Array(await new Blob(chunks, { type: "video/webm" }).arrayBuffer());
    let s = ""; for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode(...buf.subarray(i, i + 0x8000));
    return btoa(s);
  });
  writeFileSync(`${out}pullout_and_view_change.webm`, Buffer.from(b64, "base64"));
  console.log("wrote pullout_and_view_change.webm");
}
await browser.close(); await server.close();
