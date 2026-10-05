// npm run verify - every gate before a commit (v1.1 rule: never commit red).
//   pytest, typecheck, vitest, the browser suites (phantom, atlas GPU-vs-CPU + cine, label, Predict, v1 checks, interaction,
//   metrics, segments, and any v1.1 suite listed below), then the static build. Stops at the first failure, exit code 1.
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repo = resolve(web, "..");
const py = resolve(repo, ".venv/Scripts/python.exe");
const steps = [
  ["pytest", py, ["-m", "pytest", "-q"], repo],
  ["typecheck", "npx", ["tsc", "--noEmit"], web],
  ["vitest", "npx", ["vitest", "run"], web],
  ...["phantom", "atlas_xray", "atlas_label", "predict", "atlas_v1", "interaction", "metrics", "segments", "study", "shadow", "peel"]
    .map((s) => [`e2e ${s}`, "node", [`e2e/${s}.e2e.mjs`], web]),
  ["build", "npm", ["run", "build"], web],
];
const t0 = Date.now();
for (const [name, cmd, args, cwd] of steps) {
  if (name.startsWith("e2e ") && !require_exists(resolve(web, args[0]))) { console.log(`- ${name}: not present, skipped`); continue; }
  const t = Date.now();
  const r = spawnSync(cmd, args, { cwd, encoding: "utf8", shell: true, maxBuffer: 64 << 20 });
  const text = `${r.stdout ?? ""}\n${r.stderr ?? ""}`;
  const failLine = text.split("\n").find((l) => /^FAIL\b|^\s*FAIL\s|failed|Error:/.test(l) && !/0 failed/.test(l));
  const ok = r.status === 0 && !/^FAIL\b/m.test(r.stdout ?? "");
  console.log(`${ok ? "PASS" : "FAIL"} ${name} (${((Date.now() - t) / 1000).toFixed(0)} s)`);
  if (!ok) {
    console.log(text.split("\n").filter((l) => !/X4122|X3595|\[vite\]/.test(l)).slice(-40).join("\n"));
    if (failLine) console.log(`first failure line: ${failLine}`);
    process.exit(1);
  }
}
console.log(`ALL GREEN (${((Date.now() - t0) / 60000).toFixed(1)} min)`);

function require_exists(p) {
  try { return spawnSync("node", ["-e", `process.exit(require('fs').existsSync(${JSON.stringify(p)})?0:1)`]).status === 0; } catch { return false; }
}
