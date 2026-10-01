// PREDICT mode UI: four candidate angiograms for a named target view; pick, reveal, animate the C-arm there.
import type { AngioRenderer } from "./angio";
import type { Tree } from "./caseData";
import { CArm, type Vec3 } from "./geometry";
import {
  type Attempt, type Candidate, drawPose, KIND_TEXT, makeCandidates, type Pose, poseLabel, type PresetPose, rng, summarize,
} from "./predict";

export interface PredictDeps {
  angio: AngioRenderer;
  iso: Vec3;
  detectorMm: number;
  caseId: string;
  presets: PresetPose[];
  getPose: () => { alpha: number; beta: number; tree: Tree };
  setPose: (alpha: number, beta: number, tree: Tree) => void;
  requestRender: () => void;
}

const LETTERS = ["A", "B", "C", "D"];
const ROUND_SEED_NOISE = 7; // same noise pattern on all four tiles, so noise is never a cue

export class PredictMode {
  active = false;
  animMs = 1400;
  useMirror = false;
  private rand = rng((Math.random() * 2 ** 32) >>> 0);
  private round: { from: { alpha: number; beta: number }; to: Pose; cands: Candidate[]; answered: boolean } | null = null;
  private history: Attempt[] = [];
  private readonly key: string;
  private readonly tiles: HTMLCanvasElement[] = [];
  /** last rendered tile pixels (row 0 = top), for tests */
  tileImages: Uint8ClampedArray<ArrayBuffer>[] = [];

  constructor(private readonly d: PredictDeps) {
    this.key = `cpt.predict.history.${d.caseId}`;
    try {
      this.history = JSON.parse(localStorage.getItem(this.key) ?? "[]");
    } catch {
      this.history = [];
    }
    const host = document.getElementById("pr-tiles")!;
    LETTERS.forEach((L, i) => {
      const t = document.createElement("div");
      t.className = "pr-tile";
      t.innerHTML = `<canvas width="${d.angio.px}" height="${d.angio.px}"></canvas><span class="pr-letter">${L}</span><span class="pr-tag"></span>`;
      t.onclick = () => this.choose(i);
      host.appendChild(t);
      this.tiles.push(t.querySelector("canvas")!);
    });
    document.getElementById("pr-next")!.onclick = () => this.next();
    (document.getElementById("pr-mirror") as HTMLInputElement).onchange = (e) => {
      this.useMirror = (e.target as HTMLInputElement).checked;
      if (this.round && !this.round.answered) this.newRound(this.round.from);
    };
    document.getElementById("pr-reset")!.onclick = () => {
      this.history = [];
      this.save();
      this.renderSummary();
    };
    this.renderSummary();
  }

  setSeed(seed: number) { this.rand = rng(seed); }

  enter() {
    this.active = true;
    if (!this.round || this.round.answered) this.next();
    else this.renderSummary();
  }

  exit() { this.active = false; }

  /** Start the next round from the current C-arm pose. */
  next() {
    const p = this.d.getPose();
    this.newRound({ alpha: p.alpha, beta: p.beta });
  }

  private newRound(from: { alpha: number; beta: number }) {
    const to = drawPose(this.rand, this.d.presets, from);
    const cands = makeCandidates(to.alpha, to.beta, this.useMirror, this.rand);
    this.round = { from, to, cands, answered: false };
    this.tileImages = cands.map((c) => this.renderCandidate(c, to.tree));
    this.tileImages.forEach((img, i) => {
      const ctx = this.tiles[i].getContext("2d")!;
      ctx.putImageData(new ImageData(img, this.d.angio.px, this.d.angio.px), 0, 0);
      const tile = this.tiles[i].parentElement!;
      tile.classList.remove("pr-correct", "pr-wrong", "pr-done");
      (tile.querySelector(".pr-tag") as HTMLElement).textContent = "";
    });
    this.d.requestRender(); // the shared angiogram target was used for the tiles
    document.getElementById("pr-prompt")!.innerHTML =
      `Which angiogram is <b>${poseLabel(to)}</b>?<div class="hint">${to.tree === "left" ? "LCA" : "RCA"} injection · ` +
      `${to.source === "random" ? "random view" : to.source} · you are now at ${poseLabel(from)}</div>`;
    document.getElementById("pr-result")!.innerHTML = "<span class='hint'>Pick A, B, C or D.</span>";
    (document.getElementById("pr-next") as HTMLButtonElement).disabled = true;
  }

  /** Render one candidate into pixels. Mirroring is applied ONLY to deliberate wrong answers. */
  private renderCandidate(c: Candidate, tree: Tree): Uint8ClampedArray<ArrayBuffer> {
    const { angio } = this.d;
    angio.render(new CArm(c.alpha, c.beta, this.d.iso), this.d.detectorMm, tree, ROUND_SEED_NOISE);
    const img = angio.readImage();
    if (!c.mirrorLR && !c.mirrorUD) return img;
    const px = angio.px;
    const out = new Uint8ClampedArray(img.length);
    for (let r = 0; r < px; r++)
      for (let col = 0; col < px; col++) {
        const sr = c.mirrorUD ? px - 1 - r : r;
        const sc = c.mirrorLR ? px - 1 - col : col;
        out.set(img.subarray((sr * px + sc) * 4, (sr * px + sc) * 4 + 4), (r * px + col) * 4);
      }
    return out;
  }

  choose(i: number) {
    const R = this.round;
    if (!this.active || !R || R.answered) return;
    R.answered = true;
    const chosen = R.cands[i];
    this.history.push({ when: new Date().toISOString(), from: R.from, to: R.to, chosen: chosen.kind, offered: R.cands.map((c) => c.kind) });
    this.save();
    R.cands.forEach((c, k) => {
      const tile = this.tiles[k].parentElement!;
      tile.classList.add("pr-done");
      if (c.kind === "correct") tile.classList.add("pr-correct");
      else if (k === i) tile.classList.add("pr-wrong");
      (tile.querySelector(".pr-tag") as HTMLElement).textContent =
        c.kind === "correct" ? poseLabel(c) : c.mirrorLR || c.mirrorUD ? KIND_TEXT[c.kind] : `${poseLabel(c)} (${KIND_TEXT[c.kind]})`;
    });
    const ok = chosen.kind === "correct";
    document.getElementById("pr-result")!.innerHTML = ok
      ? `<b class="ok">Correct.</b> Watch the C-arm move to ${poseLabel(R.to)}.`
      : `<b class="bad">Not quite:</b> you picked the <b>${KIND_TEXT[chosen.kind]}</b>` +
        (chosen.mirrorLR || chosen.mirrorUD ? "" : ` view (${poseLabel(chosen)})`) + `. Watch the C-arm move to ${poseLabel(R.to)}.`;
    this.renderSummary();
    this.animateTo(R.to).then(() => ((document.getElementById("pr-next") as HTMLButtonElement).disabled = false));
  }

  /** Move the C-arm from its current pose to the target, interpolating the angles (the 3D panel follows). */
  animateTo(to: Pose): Promise<void> {
    const from = this.d.getPose();
    if (this.animMs <= 0) {
      this.d.setPose(to.alpha, to.beta, to.tree);
      return Promise.resolve();
    }
    return new Promise((resolve) => {
      const t0 = performance.now();
      const step = (now: number) => {
        const t = Math.min(1, (now - t0) / this.animMs);
        const e = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
        const a = from.alpha + e * (to.alpha - from.alpha);
        const b = from.beta + e * (to.beta - from.beta);
        this.d.setPose(t < 1 ? a : to.alpha, t < 1 ? b : to.beta, to.tree);
        if (t < 1) requestAnimationFrame(step);
        else resolve();
      };
      requestAnimationFrame(step);
    });
  }

  summary() { return summarize(this.history); }
  kinds() { return this.round?.cands.map((c) => c.kind) ?? []; }
  target() { return this.round?.to ?? null; }

  private save() {
    try {
      localStorage.setItem(this.key, JSON.stringify(this.history));
    } catch {
      /* per-viewer convenience only */
    }
  }

  private renderSummary() {
    const s = summarize(this.history);
    const pct = (a: number, b: number) => (b ? `${Math.round((100 * a) / b)}%` : "–");
    const row = (k: keyof typeof s.errors, name: string) =>
      `<tr><td>${name}</td><td>${s.errors[k]}</td><td>${s.offered[k]}</td><td>${pct(s.errors[k], s.offered[k])}</td></tr>`;
    const side = (k: keyof typeof s.bySide) => `${k} ${pct(s.bySide[k].correct, s.bySide[k].n)} (${s.bySide[k].n})`;
    document.getElementById("pr-summary")!.innerHTML = s.n === 0 ? "<span class='hint'>No answers yet.</span>" :
      `<div><b>${s.correct}/${s.n}</b> correct (${pct(s.correct, s.n)}); last ${s.last20.n}: ${pct(s.last20.correct, s.last20.n)}</div>` +
      `<table class="mt pr-conf"><tr><td><i>picked instead of correct</i></td><td>times</td><td>offered</td><td>rate</td></tr>` +
      row("alpha-flip", "LAO/RAO sign flip") + row("beta-flip", "CRAN/CAUD sign flip") + row("both-flip", "both flipped") +
      row("mirror-lr", "L-R mirror") + row("mirror-ud", "U-D mirror") + `</table>` +
      `<div class="hint">accuracy by target side: ${side("LAO")} · ${side("RAO")} · ${side("CRAN")} · ${side("CAUD")}</div>`;
  }
}
