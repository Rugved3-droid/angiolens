// npm run launch:v1 - builds and serves the FROZEN v1.0 release, whatever branch this checkout is on.
//
// v1.0 lives in its own git worktree (../coronary-projection-trainer-v1.0, detached at the tag), with its own node_modules and a
// snapshot of the v1.0 anatomy data (../coronary-projection-trainer-v1.0-data: the data is git-ignored, so a later rebuild on
// v1.1 must never reach the v1.0 demo). Served on port 5177 (v1.1 uses 5178), opened at /atlas.html.
import { execSync, spawn } from "node:child_process";
import { cpSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repo = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const tree = resolve(repo, "../coronary-projection-trainer-v1.0");
const data = resolve(repo, "../coronary-projection-trainer-v1.0-data");
const web = join(tree, "web");
const sh = (cmd, cwd) => execSync(cmd, { cwd, stdio: "inherit", shell: true });
const out = (cmd, cwd) => execSync(cmd, { cwd, encoding: "utf8" }).trim();

if (!existsSync(tree)) {
  console.log("[launch:v1] creating the v1.0 worktree");
  sh(`git worktree add --detach "${tree}" v1.0`, repo);
}
const head = out("git rev-parse HEAD", tree), tag = out("git rev-list -n 1 v1.0", repo);
if (head !== tag) throw new Error(`[launch:v1] the v1.0 worktree is at ${head.slice(0, 7)}, not the v1.0 tag (${tag.slice(0, 7)}). Refusing.`);
if (out("git status --porcelain", tree)) throw new Error("[launch:v1] the v1.0 worktree has local changes. Refusing.");
for (const d of ["anatomy", "cases"]) {
  const dst = join(web, "public", d);
  if (!existsSync(dst)) {
    if (!existsSync(join(data, d))) throw new Error(`[launch:v1] missing the v1.0 data snapshot ${join(data, d)}`);
    console.log(`[launch:v1] restoring the v1.0 ${d} data`);
    cpSync(join(data, d), dst, { recursive: true });
  }
}
if (!existsSync(join(web, "node_modules"))) sh("npm ci", web);
sh("npm run build", web);
console.log("[launch:v1] serving v1.0 (frozen) at http://localhost:5177/atlas.html");
spawn("npx vite preview --port 5177 --strictPort --open /atlas.html", { cwd: web, stdio: "inherit", shell: true });
