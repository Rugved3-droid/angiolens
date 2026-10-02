// Contact sheet of a review recording (no ffmpeg on this machine): plays the .webm in Chromium and grabs frames.
//   node e2e/video_frames.mjs <path.webm> <out.png> [t1,t2,...]   (seconds)
import { readFileSync } from "node:fs";
import { chromium } from "playwright";
const [src, dst, ts = "0.5,2.5,4.0,8.0"] = process.argv.slice(2);
const times = ts.split(",").map(Number);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 820 } });
const b64 = readFileSync(src).toString("base64");
await page.setContent(`<body style="margin:0;background:#111;display:grid;grid-template-columns:1fr 1fr;gap:4px">
  ${times.map((t, i) => `<div style="position:relative"><canvas id="c${i}" width="636" height="398" style="width:100%"></canvas>
  <span style="position:absolute;left:8px;top:6px;color:#ffd24a;font:14px system-ui">t = ${t} s</span></div>`).join("")}
  <video id="v" muted style="display:none"></video></body>`);
await page.evaluate(async ({ b64, times }) => {
  const v = document.getElementById("v");
  v.src = `data:video/webm;base64,${b64}`;
  await new Promise((r) => (v.onloadeddata = r));
  for (let i = 0; i < times.length; i++) {
    v.currentTime = times[i];
    await new Promise((r) => (v.onseeked = r));
    document.getElementById(`c${i}`).getContext("2d").drawImage(v, 0, 0, 636, 398);
  }
}, { b64, times });
await page.screenshot({ path: dst, fullPage: true });
console.log("wrote", dst);
await browser.close();
