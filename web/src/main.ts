import * as THREE from "three";
import "./style.css";
import { AngioRenderer } from "./angio";
import { type CaseData, type Edge, loadCase, type Tree } from "./caseData";
import { ALPHA_RANGE, BETA_RANGE, CArm, screenToPixel, pixelToScreen, type Vec3, add, scale } from "./geometry";
import { CULPRIT_COLOR, LABEL_NAMES, type LabelName, LabelStore, SELECT_COLOR } from "./labels";
import { nearestSample, pickSampleInAngio, projectionRays, type Ray, samplesRays } from "./rays";
import { EXTENSION_COLOR, SELF_COLOR, Scene3D } from "./scene3d";
import { buildTarget, MetricsPanel, type Target } from "./metricsPanel";
import { type DerivedSegment, type Derivation, deriveSegments } from "./segments";
import { LABEL_COLORS } from "./labels";
import { packSamples } from "./metrics";
import { PredictMode } from "./predictUI";
import { captionFor, HeroScene, type HeroView } from "./hero";
import { loadGeometry } from "./caseData";

const SEGMENT_COLORS: Record<string, string> = {
  LM: "#f0f0f0", "LAD prox": "#1f6fd1", "LAD mid": "#4a9ae0", "LAD dist": "#8cc4f5",
  "LCx prox": "#2ca02c", "LCx dist": "#6fcf6f", "RCA prox": "#d62728", "RCA mid": "#ff5c5c", "RCA dist": "#ff9e9e",
};
const segColor = (s: DerivedSegment) => SEGMENT_COLORS[s.name] ?? LABEL_COLORS[s.branch] ?? "#cccccc";

// Presets: [name, alpha (LAO+), beta (CRAN+), tree it is meant for]
const PRESETS: [string, number, number, Tree][] = [
  ["RAO caudal", -30, -25, "left"],
  ["RAO cranial", -30, 30, "left"],
  ["AP cranial", 0, 35, "left"],
  ["LAO cranial", 40, 30, "left"],
  ["LAO caudal (spider)", 45, -30, "left"],
  ["AP caudal", 0, -30, "left"],
  ["LAO 45 (RCA)", 45, 0, "right"],
  ["RAO 30 (RCA)", -30, 0, "right"],
  ["LAO cranial (RCA)", 30, 20, "right"],
];

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const params = new URLSearchParams(location.search);

interface State {
  alpha: number;
  beta: number;
  injected: Tree;
  selected: number | null;
  selectedIdx: number;
  labelMode: boolean;
  showSegments: boolean;
  mode: "explore" | "predict";
}

async function main() {
  const caseId = params.get("case") ?? "Normal_12";
  let data: CaseData;
  try {
    data = await loadCase(caseId);
  } catch (e) {
    $("status").textContent = `Could not load case "${caseId}". Run preprocess/scripts/build_case.py first. (${e})`;
    throw e;
  }
  const clampNum = (v: string | null, lo: number, hi: number, d: number) =>
    v === null || Number.isNaN(Number(v)) ? d : Math.min(hi, Math.max(lo, Number(v)));
  const state: State = {
    alpha: clampNum(params.get("alpha"), ...ALPHA_RANGE, 0),
    beta: clampNum(params.get("beta"), ...BETA_RANGE, 0),
    injected: params.get("inject") === "right" ? "right" : "left",
    selected: null,
    selectedIdx: 0,
    labelMode: false,
    showSegments: true,
    mode: "explore",
  };

  const canvas = $("gl") as HTMLCanvasElement;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: params.has("e2e") });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.autoClear = false;

  const px = Number(params.get("px") ?? 512);
  const angio = new AngioRenderer(renderer, {
    left: data.lumen.left, right: data.lumen.right, bone: data.bone, extension: data.extension?.mesh ?? null,
  }, px);
  const scene3d = new Scene3D($("scene-panel"), data, angio.angioRT.texture);
  const labels = new LabelStore(caseId, data.edges);
  const labelStatus = await labels.init();

  // ---------- HERO (simple, explanatory presentation; default) ----------
  const base = `${import.meta.env.BASE_URL}cases/${caseId}/`;
  const files: string[] = data.meta.files ?? [];
  const opt = (f: string) => (files.includes(f) ? loadGeometry(base + f) : Promise.resolve(null));
  const [heroHeart, heroAorta, heroVeins, heroBody] = await Promise.all([opt("heart.glb"), opt("aorta.glb"), opt("veins.glb"), opt("body.glb")]);
  const hero = new HeroScene($("hero-panel"), renderer, data, { heart: heroHeart, aorta: heroAorta, veins: heroVeins, body: heroBody }, angio.angioRT.texture);
  let simple = !(params.has("advanced") || (params.has("e2e") && !params.has("simple")));
  let heroView: HeroView = (params.get("hero_view") as HeroView) ?? "room";
  const applyLayout = () => {
    document.body.classList.toggle("simple", simple);
    document.body.classList.toggle("split", simple && heroView === "split");
    $("advanced-toggle").textContent = simple ? "Advanced" : "Simple view";
    dirty = true;
  };
  $("advanced-toggle").onclick = () => { simple = !simple; if (!simple && state.mode === "predict") setMode("explore"); applyLayout(); };

  // blit quad for showing the angiogram texture in the left viewport (uv(0,0) = bottom-left = -u,-v)
  const blitScene = new THREE.Scene();
  const blit = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.MeshBasicMaterial({ map: angio.angioRT.texture }));
  blit.frustumCulled = false;
  blitScene.add(blit);
  const blitCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

  const overlay = $("angio-overlay") as HTMLCanvasElement;
  let carm = new CArm(state.alpha, state.beta, data.isocenter);
  let rays: Ray[] = [];
  let culprits = new Set<number>();
  let derivation: Derivation = { segments: [], rcaRule: "none", boundaries: [], issues: [], notes: [] };
  let target: Target | null = null;
  let targetSeg: DerivedSegment | null = null;
  let dirty = true;
  const rcaTruncated = !!data.meta.annotation?.rca_distal_truncated;
  const segAt = (edgeId: number, idx: number) =>
    derivation.segments.find((s) => s.members.some((mm) => mm.edgeId === edgeId && idx >= mm.i0 && idx <= mm.i1)) ?? null;
  const segmentsApproved = () => labels.approvalValid(derivation.rcaRule) && derivation.issues.length === 0;
  const segTarget = (s: DerivedSegment): Target => ({
    key: `seg:${s.name}`, name: s.name, edges: s.members.map((mm) => edgeById.get(mm.edgeId)!),
    samples: packSamples(s.pts, s.radius), pts: s.pts, bif: s.bif, note: s.flags.join("; "),
  });
  // expert edges + (when its toggle is on) the separate non-expert extension layer
  const extOn = () => !!data.extension && scene3d.vis.extension;
  const allEdges = () => (extOn() ? [...data.edges, ...data.extension!.edges] : data.edges);
  const allNodes = data.extension ? [...data.nodes, ...data.extension.nodes] : data.nodes;
  const edgeById = new Map([...data.edges, ...(data.extension?.edges ?? [])].map((e) => [e.id, e]));
  const injectedEdges = () => allEdges().filter((e) => e.tree === state.injected);
  const panel = new MetricsPanel(data.isocenter, (a, b) => { state.alpha = a; state.beta = b; update(); },
    () => { syncControls(); dirty = true; });
  const predict = new PredictMode({
    angio, iso: data.isocenter, detectorMm: data.detectorMm, caseId,
    presets: PRESETS.map(([name, alpha, beta, tree]) => ({ name, alpha, beta, tree })),
    getPose: () => ({ alpha: state.alpha, beta: state.beta, tree: state.injected }),
    setPose: (a, b, tree) => { state.alpha = a; state.beta = b; state.injected = tree; update(); },
    requestRender: () => { dirty = true; },
  });
  const cArmLocked = () => state.mode === "predict";
  function setMode(mode: State["mode"]) {
    state.mode = mode;
    document.body.classList.toggle("mode-predict", mode === "predict");
    document.querySelectorAll<HTMLButtonElement>("#modes button").forEach((b) => b.classList.toggle("on", b.dataset.mode === mode));
    for (const el of document.querySelectorAll<HTMLInputElement | HTMLButtonElement>("#alpha, #beta, #presets button, #goto-opt"))
      el.disabled = mode === "predict";
    if (mode === "predict") { state.selected = null; predict.enter(); } else predict.exit();
    update();
  }
  document.querySelectorAll<HTMLButtonElement>("#modes button").forEach((b) => (b.onclick = () => setMode(b.dataset.mode as State["mode"])));

  function update() {
    carm = new CArm(state.alpha, state.beta, data.isocenter);
    if (state.selected !== null && edgeById.get(state.selected)?.nonExpert && !extOn()) state.selected = null;
    const sel = state.selected !== null ? edgeById.get(state.selected)! : null;
    derivation = deriveSegments(data.edges, data.nodes, labels.labels, { rcaDistalTruncated: rcaTruncated });
    // metric target: the approved derived segment under the click; before approval, the labeled branch / edge
    targetSeg = sel && sel.tree === state.injected && segmentsApproved() ? segAt(sel.id, state.selectedIdx) : null;
    target = sel && sel.tree === state.injected ? (targetSeg ? segTarget(targetSeg) : buildTarget(sel, allEdges(), allNodes, labels)) : null;
    const inTarget = new Set(target?.edges.map((e) => e.id) ?? []);
    const others = injectedEdges().filter((e) => !inTarget.has(e.id));
    panel.update(carm, target, others, `${state.injected}|ext:${extOn()}`);
    // rays and overlap colouring come ONLY from the 2D capsule metric (the 3D ray test is a hidden diagnostic)
    const live = panel.live;
    rays = target && live ? samplesRays(carm, target.pts).map((r) => ({
      ...r, overlap: live.m.interMask[r.sampleIndex!] ? "inter" as const : live.m.selfMask[r.sampleIndex!] ? "self" as const : null,
    })) : [];
    culprits = new Set(live ? [...live.m.interBy].filter((k) => k >= 0).map((k) => others[k].id) : []);
    scene3d.setCArm(carm, data.detectorMm);
    scene3d.setRays(carm, rays);
    hero.setCArm(carm);
    hero.setInjected(state.injected);
    $("hero-caption").textContent = captionFor(state.alpha, state.beta);
    $<HTMLInputElement>("h-alpha").value = String(state.alpha);
    $<HTMLInputElement>("h-beta").value = String(state.beta);
    angio.params.showExtension = extOn();
    const showSeg = state.showSegments && derivation.segments.length > 0;
    const segOfVertex = (edgeId: number, idx: number) => { const s = segAt(edgeId, idx); return s ? segColor(s) : null; };
    const inSel = targetSeg
      ? (edgeId: number, idx: number) => targetSeg!.members.some((mm) => mm.edgeId === edgeId && idx >= mm.i0 && idx <= mm.i1)
      : undefined;
    scene3d.recolor(labels, data.edges, state.injected, state.selected, culprits,
      showSeg || inSel ? (e, i) => (showSeg ? segOfVertex(e, i) : null) : undefined, inSel);
    scene3d.setBoundaries(showSeg ? derivation.boundaries.map((b) => ({ name: b.name, pos: b.pos })) : []);
    scene3d.applyVisibility();
    syncControls();
    dirty = true;
  }

  // ---------- controls ----------
  const alphaIn = $<HTMLInputElement>("alpha");
  const betaIn = $<HTMLInputElement>("beta");
  alphaIn.min = String(ALPHA_RANGE[0]);
  alphaIn.max = String(ALPHA_RANGE[1]);
  betaIn.min = String(BETA_RANGE[0]);
  betaIn.max = String(BETA_RANGE[1]);
  alphaIn.oninput = () => { state.alpha = Number(alphaIn.value); update(); };
  betaIn.oninput = () => { state.beta = Number(betaIn.value); update(); };
  const presetBox = $("presets");
  for (const [name, a, b, tree] of PRESETS) {
    const btn = document.createElement("button");
    btn.textContent = name;
    btn.title = `${new CArm(a, b, [0, 0, 0]).label}, inject ${tree === "left" ? "LCA" : "RCA"}`;
    btn.onclick = () => { Object.assign(state, { alpha: a, beta: b, injected: tree }); update(); };
    presetBox.appendChild(btn);
  }
  for (const tree of ["left", "right"] as Tree[]) {
    $<HTMLInputElement>(`inject-${tree}`).onchange = () => { state.injected = tree; update(); };
  }
  if (data.extension) {
    scene3d.vis.extension = !!data.extension.meta.default_visible;
    $("ext-status").textContent = `${data.extension.meta.status}, ${data.extension.meta.total_length_mm} mm @ ${data.extension.meta.threshold_hu} HU`;
    $("ext-status").title = (data.extension.meta.caveats ?? []).join("\n");
  } else {
    $("ext-row").style.display = "none";
  }
  for (const key of Object.keys(scene3d.vis) as (keyof typeof scene3d.vis)[]) {
    const box = $<HTMLInputElement>(`vis-${key}`);
    box.checked = scene3d.vis[key];
    box.onchange = () => {
      scene3d.vis[key] = box.checked;
      if (key === "bone") angio.params.showBone = box.checked;
      update();
    };
  }
  $("frame-patient").onclick = () => { scene3d.frame("patient", carm); dirty = true; };
  $("frame-carm").onclick = () => { scene3d.frame("carm", carm); dirty = true; };
  $<HTMLInputElement>("label-mode").onchange = (ev) => {
    state.labelMode = (ev.target as HTMLInputElement).checked;
    syncControls();
  };
  const picker = $<HTMLSelectElement>("label-picker");
  picker.append(new Option("(clear label)", ""), ...LABEL_NAMES.map((n) => new Option(n, n)));
  picker.onchange = () => {
    if (state.selected === null) return;
    labels.set(state.selected, (picker.value || null) as LabelName | null);
    update();
  };
  $("export-labels").onclick = () => {
    const blob = new Blob([JSON.stringify(labels.toFile(), null, 1)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "labels.json";
    a.click();
    URL.revokeObjectURL(a.href);
  };
  $<HTMLInputElement>("import-labels").onchange = async (ev) => {
    const f = (ev.target as HTMLInputElement).files?.[0];
    if (!f) return;
    try {
      $("label-status").textContent = labels.apply(JSON.parse(await f.text()), f.name);
      labels.save();
    } catch (e) {
      $("label-status").textContent = String(e);
    }
    update();
  };
  window.addEventListener("keydown", (e) => {
    if ((e.target as HTMLElement).tagName === "INPUT" || (e.target as HTMLElement).tagName === "SELECT") return;
    if (cArmLocked()) {
      const k = ["a", "b", "c", "d"].indexOf(e.key.toLowerCase());
      if (k >= 0) predict.choose(k);
      else if (e.key === "Enter" || e.key === "n") predict.next();
      return;
    }
    const step = e.shiftKey ? 5 : 1;
    const clamp = (v: number, [lo, hi]: [number, number]) => Math.min(hi, Math.max(lo, v));
    if (e.key === "ArrowLeft") state.alpha = clamp(state.alpha - step, ALPHA_RANGE);
    else if (e.key === "ArrowRight") state.alpha = clamp(state.alpha + step, ALPHA_RANGE);
    else if (e.key === "ArrowUp") state.beta = clamp(state.beta + step, BETA_RANGE);
    else if (e.key === "ArrowDown") state.beta = clamp(state.beta - step, BETA_RANGE);
    else return;
    e.preventDefault();
    update();
  });

  function select(p: { id: number; idx: number } | null) {
    state.selected = p?.id ?? null;
    state.selectedIdx = p?.idx ?? 0;
    update();
  }

  const wf = $<HTMLInputElement>("w-f"), wo = $<HTMLInputElement>("w-o");
  const onWeights = () => {
    panel.weights = { wF: Number(wf.value), wO: Number(wo.value) };
    $("w-f-val").textContent = Number(wf.value).toFixed(1);
    $("w-o-val").textContent = Number(wo.value).toFixed(1);
    panel.redrawMaps();
    syncControls();
  };
  wf.oninput = wo.oninput = onWeights;
  $<HTMLInputElement>("fixed-scale").onchange = (ev) => {
    panel.fixedScale = (ev.target as HTMLInputElement).checked;
    panel.redrawMaps();
  };
  $("goto-opt").onclick = () => {
    const o = panel.optimum();
    if (o) { state.alpha = o.alpha; state.beta = o.beta; update(); }
  };

  function syncMetrics() {
    const live = panel.live;
    const box = $("metrics-live");
    if (!live) {
      box.innerHTML = "<span class='hint'>Select a vessel segment (injected tree) to see its metrics and angle-space maps.</span>";
      return;
    }
    const pct = (v: number) => `${(100 * v).toFixed(0)}%`;
    const { m, target } = live;
    const o = panel.optimum();
    box.innerHTML =
      `<b>${target.name}</b> · ${target.edges.length} edge(s), ${(target.pts.length * 0.5).toFixed(0)} mm` +
      (target.edges.some((e) => e.nonExpert) ? ` <span style="color:${EXTENSION_COLOR}">[includes NON-EXPERT]</span>` : "") +
      `<table class="mt"><tr><td>foreshortening</td><td>${pct(m.F)}</td></tr>` +
      `<tr><td><span class="sw" style="background:${CULPRIT_COLOR}"></span>inter-vessel overlap</td><td>${pct(m.O_inter)}</td></tr>` +
      `<tr><td><span class="sw" style="background:${SELF_COLOR}"></span>self-overlap</td><td>${pct(m.O_self)}</td></tr>` +
      `<tr><td>combined cost</td><td>${panel.cost(m).toFixed(2)}</td></tr></table>` +
      (o ? `<div class="hint">map optimum: ${new CArm(o.alpha, o.beta, [0, 0, 0]).label} (cost ${o.cost.toFixed(2)})</div>` : "<div class='hint'>computing maps…</div>") +
      (target.note ? `<div class="hint">${target.note}</div>` : "");
  }

  // ---------- derived segments (approval) ----------
  $<HTMLInputElement>("seg-show").checked = state.showSegments;
  $<HTMLInputElement>("seg-show").onchange = (ev) => { state.showSegments = (ev.target as HTMLInputElement).checked; update(); };
  $("seg-approve").onclick = () => {
    if (segmentsApproved()) labels.approve(null);
    else if (derivation.issues.length === 0) labels.approve(derivation.rcaRule);
    update();
  };
  function syncSegments() {
    const ok = segmentsApproved();
    const chip = (s: DerivedSegment) =>
      `<span class="seg" style="border-color:${segColor(s)}" title="${s.flags.join("; ")}">${s.name} ${s.lengthMm.toFixed(0)} mm` +
      `${s.flags.length ? " &#9873;" : ""}${s.complete ? "" : " (not mission-eligible)"}</span>`;
    $("seg-list").innerHTML = (derivation.segments.map(chip).join(" ") || "<span class=\"hint\">no labeled branches yet</span>") +
      (derivation.issues.length ? `<div class="seg-issues">${derivation.issues.map((i) => `&#9888; ${i}`).join("<br>")}</div>` : "") +
      (derivation.notes.length ? `<div class="hint">${derivation.notes.map((i) => `&#8505; ${i}`).join("<br>")}</div>` : "") +
      (derivation.boundaries.length ? `<div class="hint">splits: ${derivation.boundaries.map((b) => `${b.name} at ${b.rule}`).join("; ")}</div>` : "");
    const btn = $<HTMLButtonElement>("seg-approve");
    btn.textContent = ok ? "Revoke approval" : "Approve segmentation";
    btn.disabled = !ok && (derivation.issues.length > 0 || derivation.segments.length === 0);
    $("seg-status").textContent = ok ? `APPROVED (${labels.approval!.approved.slice(0, 10)}, RCA: ${labels.approval!.rca_rule})`
      : labels.approval ? "approval void: labels or RCA rule changed since approval" : "not approved";
  }

  function syncControls() {
    syncMetrics();
    alphaIn.value = String(state.alpha);
    betaIn.value = String(state.beta);
    $("alpha-val").textContent = state.alpha === 0 ? "0" : `${state.alpha > 0 ? "LAO" : "RAO"} ${Math.abs(state.alpha)}`;
    $("beta-val").textContent = state.beta === 0 ? "0" : `${state.beta > 0 ? "CRAN" : "CAUD"} ${Math.abs(state.beta)}`;
    $<HTMLInputElement>(`inject-${state.injected}`).checked = true;
    $("readout").textContent = carm.label;
    $("inject-badge").textContent = state.injected === "left" ? "LCA injection" : "RCA injection";
    const sel = state.selected !== null ? edgeById.get(state.selected)! : null;
    const info = $("selection");
    syncSegments();
    if (!sel) {
      info.innerHTML = "Click a vessel in either panel.";
    } else {
      const overl = rays.filter((r) => r.overlap).length;
      const names = [...culprits].map((id) => labels.name(edgeById.get(id)!)).join(", ");
      info.innerHTML =
        `<b style="color:${SELECT_COLOR}">${sel.nonExpert && !labels.labels.has(sel.id) ? "non-expert extension" : labels.name(sel)}</b>` +
        (sel.nonExpert ? ` <span style="color:${EXTENSION_COLOR}">[NON-EXPERT trace]</span>` : "") +
        ` · ${sel.tree === "left" ? "LCA" : "RCA"} tree · ${sel.lengthMm.toFixed(1)} mm` +
        (sel.tree !== state.injected
          ? `<br><i>Not injected: switch to ${sel.tree === "left" ? "LCA" : "RCA"} injection to see it in the angiogram.</i>`
          : (targetSeg ? `<br>segment <b>${targetSeg.name}</b>` : "") + `<br>${overl}/${rays.length} rays on overlapped samples (capsule metric)` +
            (names ? `: <span style="color:${CULPRIT_COLOR}">${names}</span>` : ""));
    }
    $("label-row").style.display = state.labelMode ? "" : "none";
    picker.disabled = sel === null;
    picker.value = sel ? (labels.labels.get(sel.id) ?? "") : "";
  }

  // ---------- picking ----------
  overlay.addEventListener("click", (ev) => {
    const r = overlay.getBoundingClientRect();
    const [x, y] = pixelToScreen(((ev.clientX - r.left) / r.width) * px - 0.5, ((ev.clientY - r.top) / r.height) * px - 0.5, data.detectorMm, px);
    select(pickSampleInAngio(carm, x, y, injectedEdges()));
  });
  const scenePanel = $("scene-panel");
  let down: [number, number] | null = null;
  scenePanel.addEventListener("pointerdown", (e) => (down = [e.clientX, e.clientY]));
  scenePanel.addEventListener("pointerup", (e) => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return; // a drag, not a click
    const r = scenePanel.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    const trees: Tree[] = state.labelMode ? ["left", "right"] : [state.injected, state.injected === "left" ? "right" : "left"];
    const hit = scene3d.pick(ndc, trees);
    if (!hit) return select(null);
    // nearest centerline sample among edges of the tree that was hit
    const hitP: Vec3 = [hit.x, hit.y, hit.z];
    select(nearestSample(hitP, allEdges()));
  });
  scene3d.controls.addEventListener("change", () => (dirty = true));

  // ---------- overlay (2D, drawn in detector raster coordinates) ----------
  function drawOverlay() {
    const r = overlay.getBoundingClientRect();
    const dpr = Math.min(devicePixelRatio, 2);
    overlay.width = Math.round(r.width * dpr);
    overlay.height = Math.round(r.height * dpr);
    const g = overlay.getContext("2d")!;
    g.clearRect(0, 0, overlay.width, overlay.height);
    const toCanvas = (p: Vec3): [number, number] => {
      const [c, row] = screenToPixel(...carm.project(p), data.detectorMm, px);
      return [((c + 0.5) / px) * overlay.width, ((row + 0.5) / px) * overlay.height];
    };
    const drawEdge = (e: Edge, color: string, width: number) => {
      g.strokeStyle = color;
      g.lineWidth = width * dpr;
      g.globalAlpha = 0.85;
      g.beginPath();
      e.pts.forEach((p, i) => (i ? g.lineTo(...toCanvas(p)) : g.moveTo(...toCanvas(p))));
      g.stroke();
      g.globalAlpha = 1;
    };
    if (extOn() && state.injected === "right") {
      g.setLineDash([4 * dpr, 4 * dpr]);
      for (const e of data.extension!.edges) drawEdge(e, EXTENSION_COLOR, 1);
      g.setLineDash([]);
    }
    const drawPts = (pts: Vec3[], color: string, width: number) => drawEdge({ pts } as Edge, color, width);
    if (state.showSegments) {
      g.font = `600 ${10 * dpr}px system-ui`;
      for (const s of derivation.segments.filter((s) => s.tree === state.injected)) {
        drawPts(s.pts, segColor(s), 1.2);
        const [x, y] = toCanvas(s.pts[Math.floor(s.pts.length / 2)]);
        g.lineWidth = 3 * dpr; g.strokeStyle = "#000"; g.strokeText(s.name, x + 5 * dpr, y - 4 * dpr);
        g.fillStyle = segColor(s); g.fillText(s.name, x + 5 * dpr, y - 4 * dpr);
      }
      for (const b of derivation.boundaries) {
        const owner = derivation.segments.find((s) => s.pts.includes(b.pos));
        if (owner && owner.tree !== state.injected) continue;
        const [x, y] = toCanvas(b.pos);
        g.fillStyle = "#fff"; g.strokeStyle = "#000"; g.lineWidth = 1.5 * dpr;
        g.beginPath(); g.arc(x, y, 3.2 * dpr, 0, 2 * Math.PI); g.fill(); g.stroke();
      }
    }
    for (const id of culprits) drawEdge(edgeById.get(id)!, CULPRIT_COLOR, 1.5);
    if (target) drawPts(target.pts, SELECT_COLOR, 2);
    if (panel.live) {
      const { target, m } = panel.live;
      target.pts.forEach((p, i) => {
        if (!m.interMask[i] && !m.selfMask[i]) return;
        const [x, y] = toCanvas(p);
        g.fillStyle = m.interMask[i] ? CULPRIT_COLOR : SELF_COLOR;
        g.beginPath();
        g.arc(x, y, 1.6 * dpr, 0, 2 * Math.PI);
        g.fill();
      });
    }
    for (const ray of rays) {
      const [x, y] = toCanvas(ray.p);
      g.fillStyle = ray.overlap === "inter" ? CULPRIT_COLOR : ray.overlap === "self" ? SELF_COLOR : SELECT_COLOR;
      g.beginPath();
      g.arc(x, y, 2.2 * dpr, 0, 2 * Math.PI);
      g.fill();
    }
    // orientation glyph: patient axes projected through the same C-arm (bottom-left)
    const o = toCanvas(carm.iso);
    const glyph: [Vec3, string, string][] = [[[1, 0, 0], "L", "#ff7070"], [[0, 1, 0], "P", "#70e070"], [[0, 0, 1], "S", "#80b4ff"]];
    const gx = 40 * dpr;
    const gy = overlay.height - 40 * dpr;
    g.font = `bold ${11 * dpr}px system-ui`;
    for (const [dir, name, color] of glyph) {
      const t = toCanvas(add(carm.iso, scale(dir, 40)));
      const dx = t[0] - o[0];
      const dy = t[1] - o[1];
      const L = Math.hypot(dx, dy);
      const k = (28 * dpr) / Math.max((40 * carm.sid / carm.sod / data.detectorMm) * overlay.width, 1e-6);
      g.strokeStyle = g.fillStyle = color;
      g.lineWidth = 2 * dpr;
      if (L < 3 * dpr) {
        g.beginPath();
        g.arc(gx, gy, 4 * dpr, 0, 2 * Math.PI);
        g.stroke();
        g.fillText(`${name} (along beam)`, gx + 8 * dpr, gy + (name === "P" ? 14 : -10) * dpr);
        continue;
      }
      g.beginPath();
      g.moveTo(gx, gy);
      g.lineTo(gx + dx * k, gy + dy * k);
      g.stroke();
      g.fillText(name, gx + dx * k * 1.25 - 4 * dpr, gy + dy * k * 1.25 + 4 * dpr);
    }
  }

  // ---------- render loop ----------
  function layout() {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * renderer.getPixelRatio()) || canvas.height !== Math.round(h * renderer.getPixelRatio())) {
      renderer.setSize(w, h, false);
      dirty = true;
    }
  }
  function viewportOf(el: HTMLElement) {
    const c = canvas.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    return { x: r.left - c.left, y: c.bottom - r.bottom, w: r.width, h: r.height };
  }
  function frame() {
    layout();
    if (simple) {
      // the hero animates (breathing, damping), so it renders every frame; the angiogram only when the pose changed
      if (dirty) { dirty = false; angio.render(carm, data.detectorMm, state.injected, state.alpha * 1000 + state.beta); }
      renderer.setRenderTarget(null);
      renderer.setScissorTest(true);
      renderer.setClearColor(0x0e1117, 1);
      const full = viewportOf($("stage"));
      renderer.setViewport(full.x, full.y, full.w, full.h);
      renderer.setScissor(full.x, full.y, full.w, full.h);
      renderer.clear();
      const h = viewportOf($("hero-panel"));
      hero.camera.aspect = h.w / h.h;
      hero.camera.updateProjectionMatrix();
      renderer.setViewport(h.x, h.y, h.w, h.h);
      renderer.setScissor(h.x, h.y, h.w, h.h);
      hero.render(renderer);
      if (heroView === "split") {
        const s = viewportOf($("hero-angio"));
        const side = Math.min(s.w, s.h);
        const x = s.x + (s.w - side) / 2, y = s.y + (s.h - side) / 2;
        renderer.setViewport(x, y, side, side);
        renderer.setScissor(x, y, side, side);
        renderer.render(blitScene, blitCam);
      }
      renderer.setScissorTest(false);
      requestAnimationFrame(frame);
      return;
    }
    layout();
    if (dirty) {
      dirty = false;
      angio.render(carm, data.detectorMm, state.injected, state.alpha * 1000 + state.beta);
      renderer.setRenderTarget(null);
      renderer.setScissorTest(true);
      renderer.setClearColor(0x0b0d10, 1);
      renderer.clear();
      const a = viewportOf($("angio-panel"));
      renderer.setViewport(a.x, a.y, a.w, a.h);
      renderer.setScissor(a.x, a.y, a.w, a.h);
      renderer.render(blitScene, blitCam);
      const s = viewportOf(scenePanel);
      scene3d.camera.aspect = s.w / s.h;
      scene3d.camera.updateProjectionMatrix();
      renderer.setViewport(s.x, s.y, s.w, s.h);
      renderer.setScissor(s.x, s.y, s.w, s.h);
      renderer.clear();
      scene3d.render(renderer);
      renderer.setScissorTest(false);
      drawOverlay();
    }
    requestAnimationFrame(frame);
  }

  // ---------- simple-mode angle control ----------
  let anim = 0;
  function animatePose(a: number, b: number, ms = 1600) {
    const from = { a: state.alpha, b: state.beta };
    const t0 = performance.now();
    const my = ++anim;
    const step = (now: number) => {
      if (my !== anim) return;
      const t = Math.min(1, (now - t0) / ms);
      const e = t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
      state.alpha = t < 1 ? from.a + e * (a - from.a) : a;
      state.beta = t < 1 ? from.b + e * (b - from.b) : b;
      update();
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
  const heroPreset = $<HTMLSelectElement>("h-preset");
  heroPreset.append(new Option("AP", "0,0,left"), ...PRESETS.map(([n, a, b, t]) => new Option(`${n}`, `${a},${b},${t}`)));
  heroPreset.onchange = () => {
    const [a, b, t] = heroPreset.value.split(",");
    state.injected = t as Tree;
    animatePose(Number(a), Number(b));
  };
  for (const [id, key] of [["h-alpha", "alpha"], ["h-beta", "beta"]] as const) {
    const el = $<HTMLInputElement>(id);
    el.min = String(key === "alpha" ? ALPHA_RANGE[0] : BETA_RANGE[0]);
    el.max = String(key === "alpha" ? ALPHA_RANGE[1] : BETA_RANGE[1]);
    el.oninput = () => { anim++; state[key] = Number(el.value); update(); };
  }
  hero.setView(heroView === "beam" ? "beam" : heroView, carm);
  applyLayout();
  const swing = params.get("swing"); // e.g. "0,0:-30,-25"
  if (swing) {
    const [[a0, b0], [a1, b1]] = swing.split(":").map((p) => p.split(",").map(Number));
    state.alpha = a0; state.beta = b0; update();
    setTimeout(() => animatePose(a1, b1, Number(params.get("swing_ms") ?? 2600)), Number(params.get("swing_delay") ?? 800));
  }

  const dom = data.meta.dominance;
  $("status").innerHTML =
    `${caseId} · centerlines: ${data.meta.centerlines?.source ?? "?"} · ${data.edges.length} segments` +
    (dom ? ` · dominance: <span title="${dom.assessment}">${dom.status}</span>` : "") +
    ` · thickness buffer: ${angio.floatPrecision}`;
  $("label-status").textContent = labelStatus;
  update();
  requestAnimationFrame(frame);

  // test hook (only with ?e2e): read back the path-length image after a render
  if (params.has("e2e")) {
    (window as any).__cpt = {
      setPose(a: number, b: number, tree: Tree = state.injected) {
        Object.assign(state, { alpha: a, beta: b, injected: tree });
        update();
        angio.render(carm, data.detectorMm, state.injected, 0);
        const { thickness, repaired, oddCrossings, signMismatch } = angio.readThickness();
        return { thickness: Array.from(thickness), repaired, oddCrossings, signMismatch };
      },
      select(id: number | null) { select(id === null ? null : { id, idx: Math.floor((edgeById.get(id)?.pts.length ?? 1) / 2) }); },
      frame(what: "patient" | "carm") { scene3d.frame(what, carm); dirty = true; },
      /** client (page) coordinates of an edge's middle sample in the angiogram, for click tests */
      angioClientPoint(id: number) {
        const e = edgeById.get(id)!;
        const p = e.pts[Math.floor(e.pts.length / 2)];
        const [c, row] = screenToPixel(...carm.project(p), data.detectorMm, px);
        const r = overlay.getBoundingClientRect();
        return [r.left + ((c + 0.5) / px) * r.width, r.top + ((row + 0.5) / px) * r.height];
      },
      /** client coordinates of an edge's middle sample in the 3D panel */
      sceneClientPoint(id: number) {
        const e = edgeById.get(id)!;
        const p = new THREE.Vector3(...e.pts[Math.floor(e.pts.length / 2)]).project(scene3d.camera);
        const r = scenePanel.getBoundingClientRect();
        return [r.left + ((p.x + 1) / 2) * r.width, r.top + ((1 - p.y) / 2) * r.height];
      },
      labelEdges(map: Record<number, string>) { for (const [k, v] of Object.entries(map)) labels.set(Number(k), v as LabelName); update(); },
      derivation: () => ({ segments: derivation.segments.map((s) => ({ name: s.name, len: s.lengthMm, complete: s.complete, flags: s.flags })), issues: derivation.issues, notes: derivation.notes, approved: segmentsApproved() }),
      approve: () => { labels.approve(derivation.rcaRule); update(); return segmentsApproved(); },
      selectSample(id: number, idx: number) { select({ id, idx }); },
      rays: () => rays.map((r) => ({ i: r.sampleIndex, overlap: r.overlap ?? null })),
      masks: () => panel.live ? { inter: Array.from(panel.live.m.interMask), self: Array.from(panel.live.m.selfMask) } : null,
      target: () => target?.name ?? null,
      diagnosticRays3D: () => { const s = state.selected !== null ? edgeById.get(state.selected) : null; return s ? projectionRays(carm, s, injectedEdges(), allNodes).map((r) => r.culprits) : []; },
      predict: {
        setMode: (m: State["mode"]) => setMode(m),
        setSeed: (s: number) => predict.setSeed(s),
        setAnimMs: (ms: number) => { predict.animMs = ms; },
        setMirror: (v: boolean) => { predict.useMirror = v; },
        next: () => predict.next(),
        kinds: () => predict.kinds(),
        target: () => predict.target(),
        choose: (i: number) => predict.choose(i),
        summary: () => predict.summary(),
        tile: (i: number) => Array.from(predict.tileImages[i].filter((_, k) => k % 4 === 0)),
        pose: () => ({ alpha: state.alpha, beta: state.beta, tree: state.injected }),
        locked: () => (document.getElementById("alpha") as HTMLInputElement).disabled,
      },
      hero: {
        setView: (v: HeroView) => { heroView = v; hero.setView(v, carm); applyLayout(); },
        animate: (a: number, b: number, ms: number) => animatePose(a, b, ms),
      },
      metrics: () => panel.live ? { F: panel.live.m.F, O_inter: panel.live.m.O_inter, O_self: panel.live.m.O_self, O_any: panel.live.m.O_any, target: panel.live.target.key } : null,
      optimum: () => panel.optimum(),
      scales: () => panel.scales(),
      setFixedScale(v: boolean) { panel.fixedScale = v; panel.redrawMaps(); },
      state: () => ({ ...state, label: state.selected === null ? null : labels.labels.get(state.selected) ?? null }),
      orbit(dx: number, dy: number, dz: number) {
        scene3d.camera.position.set(data.isocenter[0] + dx, data.isocenter[1] + dy, data.isocenter[2] + dz);
        scene3d.controls.update();
        dirty = true;
      },
      edges: data.edges.map((e) => ({ id: e.id, tree: e.tree, length: e.lengthMm })),
      px,
      detectorMm: data.detectorMm,
      isocenter: data.isocenter,
    };
    document.body.dataset.ready = "1";
  }
}

main();
