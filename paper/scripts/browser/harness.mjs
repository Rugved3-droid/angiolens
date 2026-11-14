// Shared harness for the paper's browser measurements: the app's own Vite dev server (web/) and Playwright Chromium.
// Measurement only: it loads the unmodified app modules and pages; nothing in web/src is changed.
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

export const HERE = dirname(fileURLToPath(import.meta.url));
export const REPO = resolve(HERE, "..", "..", "..");
export const WEB = resolve(REPO, "web");
const require = createRequire(resolve(WEB, "package.json"));
export const { chromium } = require("playwright");
const vite = await import(pathToFileURL(require.resolve("vite")).href);

/** Real GPU (ANGLE D3D11) by default, as the app's atlas suites use; `swiftshader` for the software path. */
export const GPU_ARGS = { d3d11: ["--use-angle=d3d11", "--ignore-gpu-blocklist"],
  swiftshader: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] };

export async function startDev(port) {
  const server = await vite.createServer({ root: WEB, configFile: resolve(WEB, "vite.config.ts"), logLevel: "error",
    server: { port, strictPort: true } });
  await server.listen();
  return server;
}

export async function startPreview(port) {
  const server = await vite.preview({ root: WEB, configFile: resolve(WEB, "vite.config.ts"), logLevel: "error",
    preview: { port, strictPort: true } });
  return server;
}

export function b64ToF64(s) {
  const buf = Buffer.from(s, "base64");
  return new Float64Array(buf.buffer, buf.byteOffset, buf.byteLength / 8);
}

export function argv(name, dflt) {
  const a = process.argv.find((x) => x.startsWith(`--${name}=`));
  return a ? a.slice(name.length + 3) : dflt;
}
