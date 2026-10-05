// Close-ups of the aortic root (D62 review): the camera moves toward a point and looks at it.
//   node e2e/root_zoom.mjs [outdir]     -> out/review/<outdir>/zoom_*.png
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";
import { createServer } from "vite";
const out = new URL(`../../out/review/${process.argv[2] ?? "v1_1"}/`, import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
mkdirSync(out, { recursive: true });
const server = await createServer({ server: { port: 5191, strictPort: true } });
await server.listen();
const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
const SHOTS = [
  // name, query, look-at point (LPS mm), camera distance (mm), direction from the point (LPS, normalised in-page)
  ["zoom_lm", "scene=1&view=root&still", [28.5, -22.4, 1328.7], 45, [0.55, -0.75, 0.35]],
  ["zoom_rca", "scene=1&view=root&still", [5.2, -43.0, 1331.5], 45, [-0.2, -0.95, 0.25]],
  ["zoom_root_front", "scene=1&view=root&still", [16, -30, 1325], 95, [0.2, -0.95, 0.2]],
  ["zoom_lm_engaged", "scene=5&cam=root&engaged&still", [28.5, -22.4, 1328.7], 50, [0.55, -0.75, 0.35]],
];
for (const [name, q, at, dist, dir] of SHOTS) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  page.on("pageerror", (e) => console.log("pageerror", name, String(e)));
  await page.goto(`http://localhost:5191/atlas.html?${q}${process.env.SUFFIX ?? ""}`);
  await page.waitForSelector("body[data-ready='1']", { timeout: 300000 });
  await page.waitForTimeout(2500);
  await page.evaluate(([at, dist, dir]) => {
    const cam = window.atlas.dbg.camera;
    const n = Math.hypot(...dir);
    cam.position.set(at[0] + (dir[0] / n) * dist, at[1] + (dir[1] / n) * dist, at[2] + (dir[2] / n) * dist);
    cam.up.set(0, 0, 1);
    cam.lookAt(at[0], at[1], at[2]);
    window.atlas.dbg.controls.target.set(at[0], at[1], at[2]);
  }, [at, dist, dir]);
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${out}${process.env.PREFIX ?? ""}${name}.png` });
  await page.close();
}
await browser.close(); await server.close();
console.log("wrote", SHOTS.map((s) => s[0]).join(", "));
