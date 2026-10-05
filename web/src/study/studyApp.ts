// STUDY page (study.html, v1.1): welcome -> pre-test (ASOCA) -> training (atlas.html?study=<code>) -> post-test (ASOCA) ->
// results + CSV. The session lives in localStorage (anonymous code only), so it survives the trip to the atlas and back.
// Tiles are rendered by the validated X-ray engine (AngioRenderer, the same calls as Predict); none is mirrored except the
// deliberate "mirror" wrong answer.
import * as THREE from "three";
import { AngioRenderer } from "../angio";
import { loadCase, loadGeometry, type CaseData } from "../caseData";
import { CArm } from "../geometry";
import {
  CODE_RE, ERROR_KINDS, ERROR_TEXT, hashCode, newCode, newSession, promptFor, sessionCsv, setPoses, summarizePhase, tilesFor,
  type Phase, type Session, type StudyPose, type Tile,
} from "./studyCore";
import { loadSessions, saveSession, currentCode, setCurrent, PREDICT_HISTORY_KEY } from "./studyStore";

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const params = new URLSearchParams(location.search);
const LETTERS = ["A", "B", "C", "D"];
const NOISE_SEED = 7;                      // the same noise on all four tiles of a question: noise is never a cue

function show(id: string) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.toggle("on", s.id === id));
  window.scrollTo(0, 0);
}

// ---------------- the patient (ASOCA) and the engine, loaded once ----------------
let engine: { data: CaseData; angio: AngioRenderer; renderer: THREE.WebGLRenderer; ref: RefView } | null = null;
async function ensureEngine() {
  if (engine) return engine;
  $("loading").classList.add("on");
  const caseId = params.get("case") ?? "Normal_12";
  const data = await loadCase(caseId);
  const canvas = $<HTMLCanvasElement>("refCanvas");
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: params.has("e2e") });
  renderer.setPixelRatio(1);
  const angio = new AngioRenderer(renderer, { left: data.lumen.left, right: data.lumen.right, bone: data.bone, extension: null }, 512);
  const files: string[] = data.meta.files ?? [];
  const heart = files.includes("heart.glb") ? await loadGeometry(`${import.meta.env.BASE_URL}cases/${caseId}/heart.glb`).catch(() => null) : null;
  engine = { data, angio, renderer, ref: new RefView(renderer, data, heart) };
  $("loading").classList.remove("on");
  return engine;
}

/** One tile's pixels (row 0 = top). Mirroring only for the deliberate "mirror" wrong answer. */
function renderTile(t: Tile, tree: "left" | "right"): ImageData {
  const { angio, data } = engine!;
  angio.render(new CArm(t.alpha, t.beta, data.isocenter), data.detectorMm, tree, NOISE_SEED);
  const img = angio.readImage();
  const px = angio.px;
  if (!t.mirrorLR) return new ImageData(new Uint8ClampedArray(img), px, px);
  const out = new Uint8ClampedArray(img.length);
  for (let r = 0; r < px; r++)
    for (let c = 0; c < px; c++) out.set(img.subarray((r * px + (px - 1 - c)) * 4, (r * px + (px - 1 - c)) * 4 + 4), (r * px + c) * 4);
  return new ImageData(out, px, px);
}

/** The 3D reference: the patient's coronaries from the front (AP), rocking +-22 degrees about the head-foot axis. */
class RefView {
  private scene = new THREE.Scene();
  private cam = new THREE.PerspectiveCamera(30, 1, 10, 5000);
  private mats: Record<"left" | "right", THREE.MeshStandardMaterial>;
  private iso: THREE.Vector3;
  private dist: number;
  injected: "left" | "right" = "left";
  constructor(private r: THREE.WebGLRenderer, data: CaseData, heart: THREE.BufferGeometry | null) {
    this.scene.background = new THREE.Color("#0a0f15");
    this.scene.add(new THREE.HemisphereLight("#ffffff", "#223", 1.6));
    const key = new THREE.DirectionalLight("#fff", 2.2); key.position.set(-0.5, -1, 0.8); this.cam.add(key); this.scene.add(this.cam);
    this.mats = {
      left: new THREE.MeshStandardMaterial({ color: "#ff3b3b", roughness: 0.35, emissive: "#550000" }),
      right: new THREE.MeshStandardMaterial({ color: "#ff3b3b", roughness: 0.35, emissive: "#550000" }),
    };
    for (const t of ["left", "right"] as const) this.scene.add(new THREE.Mesh(data.lumen[t], this.mats[t]));
    if (heart) this.scene.add(new THREE.Mesh(heart, new THREE.MeshStandardMaterial({ color: "#8a4a3c", roughness: 0.8, transparent: true,
      opacity: 0.16, depthWrite: false })));
    const box = new THREE.Box3();
    for (const t of ["left", "right"] as const) { data.lumen[t].computeBoundingBox(); box.union(data.lumen[t].boundingBox!); }
    this.iso = box.getCenter(new THREE.Vector3());
    this.dist = (box.getSize(new THREE.Vector3()).length() / 2) / Math.tan(THREE.MathUtils.degToRad(15)) * 0.95;
  }
  draw(t: number) {
    for (const k of ["left", "right"] as const) {
      const on = k === this.injected;
      this.mats[k].color.set(on ? "#ff3b3b" : "#6b3a3a");
      this.mats[k].emissive.set(on ? "#5a0000" : "#000000");
      this.mats[k].opacity = on ? 1 : 0.5;
      this.mats[k].transparent = !on;
    }
    const a = THREE.MathUtils.degToRad(22) * Math.sin(t / 2600);
    // from the front: the camera on the anterior side (-y in LPS), head up (+z); patient's left (+x) on screen right
    this.cam.position.set(this.iso.x + this.dist * Math.sin(a), this.iso.y - this.dist * Math.cos(a), this.iso.z);
    this.cam.up.set(0, 0, 1);
    this.cam.lookAt(this.iso);
    this.r.setRenderTarget(null);
    this.r.setViewport(0, 0, this.r.domElement.width, this.r.domElement.height);
    this.r.render(this.scene, this.cam);
  }
}

// ---------------- session ----------------
let session: Session | null = null;
function save() { if (session) saveSession(session); }

function nextStep() {
  if (!session) return showWelcome();
  const [first, second] = session.order;
  if (session.answers.filter((a) => a.phase === "pre").length < 10) return intro("pre", first);
  if (!session.training.ended) return introTraining();
  if (session.answers.filter((a) => a.phase === "post").length < 10) return intro("post", second);
  return showResults();
}

// ---------------- welcome ----------------
function showWelcome() {
  const box = $<HTMLInputElement>("code");
  box.value = newCode();
  const cur = currentCode();
  const all = loadSessions();
  $("resumeBox").style.display = cur && all[cur] && !all[cur].finished ? "block" : "none";
  if (cur) $("resumeCode").textContent = cur;
  const done = Object.values(all).filter((s) => s.finished).sort((a, b) => (a.finished! < b.finished! ? 1 : -1));
  $("pastCard").style.display = done.length ? "block" : "none";
  $("past").innerHTML = "";
  for (const s of done) {
    const li = document.createElement("li");
    const pre = summarizePhase(s, "pre"), post = summarizePhase(s, "post");
    li.innerHTML = `<b>${s.code}</b> · ${s.finished!.slice(0, 16).replace("T", " ")} · pre ${pre.correct}/10, post ${post.correct}/10 `;
    const b = document.createElement("button");
    b.textContent = "CSV";
    b.style.padding = "2px 10px";
    b.onclick = () => downloadCsv(s);
    li.appendChild(b);
    $("past").appendChild(li);
  }
  show("sWelcome");
}
$("newCode").onclick = () => { $<HTMLInputElement>("code").value = newCode(); $("codeErr").textContent = ""; };
$("start").onclick = () => {
  const code = $<HTMLInputElement>("code").value.trim().toUpperCase();
  if (!CODE_RE.test(code)) {
    $("codeErr").textContent = "Use 3-16 letters, digits or hyphens, with at least one digit (for example P-4K7Q2). No names.";
    return;
  }
  const all = loadSessions();
  if (all[code]) { $("codeErr").textContent = `Code ${code} already has a session on this device. Use a new code, or resume it.`; return; }
  session = newSession(code);
  setCurrent(code);
  save();
  nextStep();
};
$("resume").onclick = () => { session = loadSessions()[currentCode()!]; nextStep(); };

// ---------------- part intros ----------------
function intro(phase: Phase, set: "A" | "B") {
  const pre = phase === "pre";
  $("introHead").textContent = pre ? "Part 1 of 3" : "Part 3 of 3";
  $("introTitle").textContent = pre ? "Pre-test: 10 questions" : "Post-test: 10 new questions";
  $("introBody").innerHTML = `
    <p>Each question names a C-arm view (for example <b>LAO 30 / CAUD 25</b>) and the injected artery of a real patient
      (coronary arteries from a CT scan). Four angiograms are shown; pick the one this view would make.</p>
    <p>On the left you can see the patient's arteries from the front. ${pre ? "" : "The views are new: none was in the pre-test."}</p>
    <p class="muted">No feedback until the end. Answer as accurately as you can, without rushing. Your response time is recorded.</p>`;
  $("introGo").textContent = "Begin";
  $<HTMLButtonElement>("introGo").onclick = () => runTest(phase, set);
  show("sIntro");
}
function introTraining() {
  $("introHead").textContent = "Part 2 of 3";
  $("introTitle").textContent = "Training: the 3D atlas (about 10 minutes)";
  $("introBody").innerHTML = `
    <p>The atlas opens in this tab. First press <b>▶ Tour</b> (top left) and watch the guided tour to the end (about 80 seconds).</p>
    <p>Then practise: go to <b>X-ray</b> and press <b>Predict</b>. Here you get feedback after every answer. Aim for about 10 minutes in all.</p>
    <p>When you are done, press <b>Finish training</b> in the study bar at the bottom of the atlas to continue to Part 3.</p>`;
  $("introGo").textContent = "Open the atlas";
  $<HTMLButtonElement>("introGo").onclick = () => {
    if (!session) return;
    let hist = 0;
    try { hist = JSON.parse(localStorage.getItem(PREDICT_HISTORY_KEY) ?? "[]").length; } catch { hist = 0; }
    session.training = { ...session.training, started: new Date().toISOString(), histStart: hist };
    save();
    location.href = `${import.meta.env.BASE_URL}atlas.html?study=${encodeURIComponent(session.code)}`;
  };
  show("sIntro");
}

// ---------------- a test (10 questions) ----------------
let raf = 0;
async function runTest(phase: Phase, set: "A" | "B") {
  await ensureEngine();
  const poses = setPoses(set);
  const seed = hashCode(session!.code) ^ (phase === "pre" ? 0x5eed : 0xa11ce);
  // render every tile first (no rendering delay is counted in the response times)
  $("loading").classList.add("on");
  await new Promise((r) => setTimeout(r, 30));
  const qs = poses.map((p, q) => { const tiles = tilesFor(p, q, seed); return { p, tiles, imgs: tiles.map((t) => renderTile(t, p.tree)) }; });
  $("loading").classList.remove("on");
  const start = session!.answers.filter((a) => a.phase === phase).length;
  show("sQuestion");
  cancelAnimationFrame(raf);
  const loop = (t: number) => { engine!.ref.draw(t); raf = requestAnimationFrame(loop); };
  raf = requestAnimationFrame(loop);
  for (let q = start; q < 10; q++) await ask(phase, set, q, qs[q]);
  cancelAnimationFrame(raf);
  nextStep();
}

function ask(phase: Phase, set: "A" | "B", q: number, Q: { p: StudyPose; tiles: Tile[]; imgs: ImageData[] }) {
  return new Promise<void>((resolve) => {
    engine!.ref.injected = Q.p.tree;
    window.scrollTo(0, 0);
    $("qcount").textContent = `${phase === "pre" ? "Pre-test" : "Post-test"} · question ${q + 1} of 10`;
    $("prompt").innerHTML = `Which angiogram is <b>${promptFor(Q.p)}</b>?`;
    $("dots").innerHTML = Array.from({ length: 10 }, (_, i) => `<i class="${i < q ? "done" : i === q ? "now" : ""}"></i>`).join("");
    const host = $("tiles");
    host.innerHTML = "";
    host.classList.add("wait");
    Q.imgs.forEach((img, i) => {
      const d = document.createElement("div");
      d.className = "tile";
      d.dataset.kind = Q.tiles[i].kind;                    // for the automated run-through only (not shown)
      d.innerHTML = `<canvas width="${img.width}" height="${img.height}"></canvas><span class="L">${LETTERS[i]}</span>`;
      d.querySelector("canvas")!.getContext("2d")!.putImageData(img, 0, 0);
      d.onclick = () => {
        if (host.classList.contains("wait")) return;
        host.classList.add("wait");
        const rt = performance.now() - t0;
        session!.answers.push({ phase, set, q, pose: Q.p, offered: Q.tiles.map((t) => t.kind), chosen: Q.tiles[i].kind, rtMs: rt,
          at: new Date().toISOString() });
        if (phase === "post" && q === 9) session!.finished = new Date().toISOString();
        save();
        setTimeout(resolve, 350);
      };
      host.appendChild(d);
    });
    let t0 = 0;
    // the clock starts when the four tiles are on screen
    requestAnimationFrame(() => requestAnimationFrame(() => { host.classList.remove("wait"); t0 = performance.now(); }));
  });
}

// ---------------- results ----------------
function showResults() {
  const s = session!;
  const pre = summarizePhase(s, "pre"), post = summarizePhase(s, "post");
  $("rCode").textContent = s.code;
  $("rPre").textContent = `${pre.correct} / 10`;
  $("rPost").textContent = `${post.correct} / 10`;
  const d = post.correct - pre.correct;
  $("rDelta").textContent = `${d > 0 ? "+" : ""}${d}`;
  $("rDelta").style.color = d > 0 ? "var(--ok)" : d < 0 ? "var(--bad)" : "var(--ink)";
  const sec = (ms: number) => `${(ms / 1000).toFixed(1)} s`;
  $("rPreT").textContent = `median ${sec(pre.medianRtMs)} per question`;
  $("rPostT").textContent = `median ${sec(post.medianRtMs)} per question`;
  const t = s.training;
  const trainMin = t.started && t.ended ? (Date.parse(t.ended) - Date.parse(t.started)) / 60000 : 0;
  $("rTrain").textContent = `training ${trainMin.toFixed(1)} min · ${t.practiceAnswers} practice answers`;
  const bar = (n: number, of: number, color: string) => `<div class="bar"><i style="width:${of ? (100 * n) / of : 0}%;background:${color}"></i></div>`;
  $("rErr").innerHTML = `<tr><th>Wrong answer chosen</th><th class="num">Pre-test</th><th></th><th class="num">Post-test</th><th></th></tr>` +
    ERROR_KINDS.map((k) => `<tr><td>${ERROR_TEXT[k]}</td><td class="num">${pre.errors[k]} of ${pre.offered[k]} offered</td>` +
      `<td>${bar(pre.errors[k], pre.offered[k], "var(--bad)")}</td><td class="num">${post.errors[k]} of ${post.offered[k]} offered</td>` +
      `<td>${bar(post.errors[k], post.offered[k], "var(--bad)")}</td></tr>`).join("") +
    `<tr><td><b>Correct</b></td><td class="num">${pre.correct} of 10</td><td>${bar(pre.correct, 10, "var(--ok)")}</td>` +
    `<td class="num">${post.correct} of 10</td><td>${bar(post.correct, 10, "var(--ok)")}</td></tr>`;
  const total = s.finished ? (Date.parse(s.finished) - Date.parse(s.started)) / 60000 : 0;
  $("rTime").innerHTML = `<tr><th></th><th class="num">Pre-test</th><th class="num">Post-test</th></tr>
    <tr><td>Median response time</td><td class="num">${sec(pre.medianRtMs)}</td><td class="num">${sec(post.medianRtMs)}</td></tr>
    <tr><td>Time answering (all 10)</td><td class="num">${sec(pre.totalMs)}</td><td class="num">${sec(post.totalMs)}</td></tr>
    <tr><td>Training (atlas)</td><td class="num" colspan="2">${trainMin.toFixed(1)} min${t.tourCompleted ? ", guided tour watched to the end" : ""};
      Predict practice ${t.practiceCorrect} / ${t.practiceAnswers} correct</td></tr>
    <tr><td>Whole session</td><td class="num" colspan="2">${total.toFixed(1)} min</td></tr>`;
  $<HTMLButtonElement>("csv").onclick = () => downloadCsv(s);
  $<HTMLButtonElement>("done").onclick = () => { setCurrent(null); session = null; history.replaceState(null, "", location.pathname); showWelcome(); };
  show("sResults");
}

function downloadCsv(s: Session) {
  const blob = new Blob([sessionCsv(s)], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `cpt_study_${s.code}_${(s.finished ?? s.started).slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

// ---------------- start ----------------
const back = params.get("code");
const cur = back ?? currentCode();
if (cur && loadSessions()[cur] && (back || params.has("resume"))) { session = loadSessions()[cur]; setCurrent(cur); nextStep(); }
else showWelcome();
// test hook: the engine image of a pose (the run-through checks every tile against it)
const renderPose = async (alpha: number, beta: number, tree: "left" | "right", mirrorLR = false) => {
  await ensureEngine();
  return Array.from(renderTile({ kind: "correct", alpha, beta, mirrorLR }, tree).data);
};
(window as unknown as Record<string, unknown>).study = { get session() { return session; }, sessionCsv, nextStep, renderPose };
