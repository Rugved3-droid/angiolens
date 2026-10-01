import * as THREE from "three";
import "./style.css";
import { AngioRenderer } from "./angio";
import { type CaseData, type Edge, loadCase, type Tree } from "./caseData";
import { ALPHA_RANGE, BETA_RANGE, CArm, screenToPixel, pixelToScreen, type Vec3, add, scale } from "./geometry";
import { CULPRIT_COLOR, LABEL_NAMES, type LabelName, LabelStore, SELECT_COLOR } from "./labels";
import { nearestEdge, pickInAngio, projectionRays, type Ray } from "./rays";
import { Scene3D } from "./scene3d";

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
  labelMode: boolean;
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
    labelMode: false,
  };

  const canvas = $("gl") as HTMLCanvasElement;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: params.has("e2e") });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.autoClear = false;

  const px = Number(params.get("px") ?? 512);
  const angio = new AngioRenderer(renderer, { left: data.lumen.left, right: data.lumen.right, bone: data.bone }, px);
  const scene3d = new Scene3D($("scene-panel"), data, angio.angioRT.texture);
  const labels = new LabelStore(caseId, data.edges);
  const labelStatus = await labels.init();

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
  let dirty = true;
  const edgeById = new Map(data.edges.map((e) => [e.id, e]));
  const injectedEdges = () => data.edges.filter((e) => e.tree === state.injected);

  function update() {
    carm = new CArm(state.alpha, state.beta, data.isocenter);
    const sel = state.selected !== null ? edgeById.get(state.selected)! : null;
    rays = sel && sel.tree === state.injected ? projectionRays(carm, sel, injectedEdges(), data.nodes) : [];
    culprits = new Set(rays.flatMap((r) => r.culprits));
    scene3d.setCArm(carm, data.detectorMm);
    scene3d.setRays(carm, rays);
    scene3d.recolor(labels, data.edges, state.injected, state.selected, culprits);
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

  function select(id: number | null) {
    state.selected = id;
    update();
  }

  function syncControls() {
    alphaIn.value = String(state.alpha);
    betaIn.value = String(state.beta);
    $("alpha-val").textContent = state.alpha === 0 ? "0" : `${state.alpha > 0 ? "LAO" : "RAO"} ${Math.abs(state.alpha)}`;
    $("beta-val").textContent = state.beta === 0 ? "0" : `${state.beta > 0 ? "CRAN" : "CAUD"} ${Math.abs(state.beta)}`;
    $<HTMLInputElement>(`inject-${state.injected}`).checked = true;
    $("readout").textContent = carm.label;
    $("inject-badge").textContent = state.injected === "left" ? "LCA injection" : "RCA injection";
    const sel = state.selected !== null ? edgeById.get(state.selected)! : null;
    const info = $("selection");
    if (!sel) {
      info.innerHTML = "Click a vessel in either panel.";
    } else {
      const overl = rays.filter((r) => r.culprits.length).length;
      const names = [...culprits].map((id) => labels.name(edgeById.get(id)!)).join(", ");
      info.innerHTML =
        `<b style="color:${SELECT_COLOR}">${labels.name(sel)}</b> · ${sel.tree === "left" ? "LCA" : "RCA"} tree · ${sel.lengthMm.toFixed(1)} mm` +
        (sel.tree !== state.injected
          ? `<br><i>Not injected: switch to ${sel.tree === "left" ? "LCA" : "RCA"} injection to see it in the angiogram.</i>`
          : `<br>${overl}/${rays.length} rays pass through another vessel` +
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
    select(pickInAngio(carm, x, y, injectedEdges()));
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
    select(nearestEdge(hitP, data.edges));
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
    for (const id of culprits) drawEdge(edgeById.get(id)!, CULPRIT_COLOR, 1.5);
    const sel = state.selected !== null ? edgeById.get(state.selected)! : null;
    if (sel && sel.tree === state.injected) drawEdge(sel, SELECT_COLOR, 2);
    for (const ray of rays) {
      const [x, y] = toCanvas(ray.p);
      g.fillStyle = ray.culprits.length ? CULPRIT_COLOR : SELECT_COLOR;
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
        const { thickness, repaired } = angio.readThickness();
        return { thickness: Array.from(thickness), repaired };
      },
      select(id: number | null) { select(id); },
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
