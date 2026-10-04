// Diagnoses the stall when entering Scene 6 from an engaged Scene 5: frame times + CPU profile top self-time (D60 quality pass).
//   node e2e/scene6_stall.mjs
import { chromium } from "playwright";
import { createServer } from "vite";
const server = await createServer({ server: { port: 5188, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
page.on("pageerror", (e) => console.log("pageerror", String(e)));
await page.goto("http://localhost:5188/atlas.html?scene=5&cam=root&engaged");
await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
await page.waitForTimeout(6000);
const cdp = await page.context().newCDPSession(page);
await cdp.send("Profiler.enable");
await cdp.send("Profiler.setSamplingInterval", { interval: 200 });
await cdp.send("Profiler.start");
const res = await page.evaluate(async (PRE) => {
  const A = window.atlas, r = A.dbg.renderer;
  const progs0 = r.info.programs.length;
  const times = [];
  let last = performance.now(), run = true;
  const f = () => { const t = performance.now(); times.push(Math.round(t - last)); last = t; if (run) requestAnimationFrame(f); };
  requestAnimationFrame(f);
  await new Promise((res) => setTimeout(res, 300));
  if (PRE === "2") { const st = document.createElement("style"); st.textContent = "*{backdrop-filter:none !important}"; document.head.appendChild(st); await new Promise((res) => setTimeout(res, 300)); }
  if (PRE === "3") { A.goScene(6, 0); await new Promise((res) => setTimeout(res, 1500)); A.goScene(5, 0); await new Promise((res) => setTimeout(res, 1500)); A.setLabCam("root", 0); await new Promise((res) => setTimeout(res, 800)); times.length = 0; }
  if (PRE === "4") A.dbg.ghostMesh.material.visible = false;
  if (PRE === "5") { const m = A.dbg.ghostMesh.material; m.depthFunc = 3; m.polygonOffset = false; }
  if (PRE === "6") { const m = A.dbg.ghostMesh.material; m.polygonOffset = false; }
  if (PRE === "1") { const sp = document.getElementById("slicePanel"); sp.style.display = "flex"; sp.style.opacity = "0.01"; await new Promise((res) => setTimeout(res, 300)); sp.style.opacity = ""; }
  A.goScene(6, 2600);
  await new Promise((res) => setTimeout(res, 2800));
  A.injectCath();
  await new Promise((res) => setTimeout(res, 2500));
  run = false;
  return { progs0, progs1: r.info.programs.length, slow: times.map((t, i) => [i, t]).filter(([, t]) => t > 34) };
}, process.env.PRE ?? "");
const { profile } = await cdp.send("Profiler.stop");
console.log(JSON.stringify(res));
const self = new Map();
const dt = profile.timeDeltas;
const byId = new Map(profile.nodes.map((n) => [n.id, n]));
profile.samples.forEach((id, i) => {
  const n = byId.get(id); const cf = n.callFrame;
  const k = `${cf.functionName || "(anon)"} ${cf.url.split("/").pop()}:${cf.lineNumber + 1}`;
  self.set(k, (self.get(k) ?? 0) + (dt[i] ?? 0) / 1000);
}, process.env.PRE ?? "");
for (const [k, v] of [...self].sort((a, b) => b[1] - a[1]).slice(0, 18)) console.log(v.toFixed(0).padStart(6), "ms", k);
await browser.close(); await server.close();
