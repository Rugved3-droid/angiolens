// PREDICT mode logic (pure; no rendering): pose draws, the 4 candidate views, error tracking.
// Whole-vessel level: independent of labels and derived segments.
//
// Candidates for a target (alpha, beta):  the correct view, alpha sign flipped (-alpha, beta), beta sign flipped
// (alpha, -beta), and both flipped (-alpha, -beta), or, with the toggle, a left-right MIRRORED image of the correct
// view. A flip that would reproduce the same image (|alpha| or |beta| below DEGENERATE_DEG, e.g. AP or zero tilt) is
// replaced by a mirror image so the four candidates are always visually distinct.
// Mirrored images exist ONLY as deliberate wrong answers; no correct view is ever mirrored.
import { ALPHA_RANGE, BETA_RANGE, detectorDirection, dot, viewLabel } from "./geometry";
import type { Tree } from "./caseData";

export const DEGENERATE_DEG = 5;
export const MIN_MOVE_DEG = 15;
export const RANDOM_ALPHA: [number, number] = [-70, 70];
export const RANDOM_BETA: [number, number] = [-40, 40];
export const RANDOM_MIN_ABS = 10;

export type CandidateKind = "correct" | "alpha-flip" | "beta-flip" | "both-flip" | "mirror-lr" | "mirror-ud";

export interface Pose {
  alpha: number;
  beta: number;
  tree: Tree;
  source: string; // preset name or "random"
}

export interface Candidate {
  kind: CandidateKind;
  alpha: number;
  beta: number;
  mirrorLR: boolean; // distractor only
  mirrorUD: boolean; // distractor only
}

export const KIND_TEXT: Record<CandidateKind, string> = {
  correct: "correct",
  "alpha-flip": "LAO/RAO sign flipped",
  "beta-flip": "CRAN/CAUD sign flipped",
  "both-flip": "both signs flipped",
  "mirror-lr": "left-right mirror image",
  "mirror-ud": "up-down mirror image",
};

/** Deterministic PRNG (mulberry32) so rounds are reproducible in tests. */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Angle (deg) between the detector directions of two poses. */
export function angularDistance(a1: number, b1: number, a2: number, b2: number): number {
  const c = Math.min(1, Math.max(-1, dot(detectorDirection(a1, b1), detectorDirection(a2, b2))));
  return (Math.acos(c) * 180) / Math.PI;
}

export function makeCandidates(alpha: number, beta: number, useMirror: boolean, rand: () => number): Candidate[] {
  const aOk = Math.abs(alpha) >= DEGENERATE_DEG;
  const bOk = Math.abs(beta) >= DEGENERATE_DEG;
  // near (0,0) both flips reproduce the image: only 3 distinct views exist. drawPose never produces such a target.
  if (!aOk && !bOk) throw new Error(`target ${alpha},${beta} is too close to AP/zero tilt for four distinct candidates`);
  const c = (kind: CandidateKind): Candidate => ({
    kind,
    alpha: kind === "alpha-flip" || kind === "both-flip" ? -alpha : alpha,
    beta: kind === "beta-flip" || kind === "both-flip" ? -beta : beta,
    mirrorLR: kind === "mirror-lr",
    mirrorUD: kind === "mirror-ud",
  });
  const kinds: CandidateKind[] = ["correct"];
  const want: CandidateKind[] = [aOk ? "alpha-flip" : "mirror-lr", bOk ? "beta-flip" : "mirror-ud",
    useMirror ? "mirror-lr" : aOk && bOk ? "both-flip" : "mirror-lr"];
  for (const k of want) {
    if (!kinds.includes(k)) { kinds.push(k); continue; }
    const alt = (["mirror-lr", "mirror-ud", "both-flip"] as CandidateKind[])
      .find((x) => !kinds.includes(x) && (x !== "both-flip" || (aOk && bOk)));
    kinds.push(alt ?? "mirror-ud");
  }
  const out = kinds.map(c);
  for (let i = out.length - 1; i > 0; i--) {             // Fisher-Yates
    const j = Math.floor(rand() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

export interface PresetPose { name: string; alpha: number; beta: number; tree: Tree }

/** Next target: a standard preset or a random pose, at least MIN_MOVE_DEG away from the previous pose. */
export function drawPose(rand: () => number, presets: PresetPose[], prev: { alpha: number; beta: number } | null): Pose {
  for (let attempt = 0; attempt < 200; attempt++) {
    let p: Pose;
    if (rand() < 0.5) {
      const q = presets[Math.floor(rand() * presets.length)];
      p = { alpha: q.alpha, beta: q.beta, tree: q.tree, source: q.name };
    } else {
      const pick = (lo: number, hi: number) => {
        const sign = rand() < 0.5 ? -1 : 1;
        const lim = sign < 0 ? -lo : hi;
        return sign * Math.round(RANDOM_MIN_ABS + rand() * (lim - RANDOM_MIN_ABS));
      };
      p = { alpha: pick(...RANDOM_ALPHA), beta: pick(...RANDOM_BETA), tree: rand() < 0.5 ? "left" : "right", source: "random" };
    }
    p.alpha = Math.min(ALPHA_RANGE[1], Math.max(ALPHA_RANGE[0], p.alpha));
    p.beta = Math.min(BETA_RANGE[1], Math.max(BETA_RANGE[0], p.beta));
    if (!prev || angularDistance(prev.alpha, prev.beta, p.alpha, p.beta) >= MIN_MOVE_DEG) return p;
  }
  throw new Error("could not draw a pose far enough from the previous one");
}

export interface Attempt {
  when: string;
  from: { alpha: number; beta: number };
  to: Pose;
  chosen: CandidateKind;
  offered: CandidateKind[];
}

export interface Summary {
  n: number;
  correct: number;
  /** wrong answers by kind */
  errors: Record<Exclude<CandidateKind, "correct">, number>;
  /** how often each kind was offered (denominator for error rates) */
  offered: Record<Exclude<CandidateKind, "correct">, number>;
  last20: { n: number; correct: number };
  /** accuracy split by the target's sides: LAO vs RAO targets, CRAN vs CAUD targets */
  bySide: Record<"LAO" | "RAO" | "CRAN" | "CAUD", { n: number; correct: number }>;
}

export function summarize(history: Attempt[]): Summary {
  const zero = () => ({ "alpha-flip": 0, "beta-flip": 0, "both-flip": 0, "mirror-lr": 0, "mirror-ud": 0 });
  const s: Summary = {
    n: history.length, correct: 0, errors: zero(), offered: zero(), last20: { n: 0, correct: 0 },
    bySide: { LAO: { n: 0, correct: 0 }, RAO: { n: 0, correct: 0 }, CRAN: { n: 0, correct: 0 }, CAUD: { n: 0, correct: 0 } },
  };
  history.forEach((h, i) => {
    const ok = h.chosen === "correct";
    if (ok) s.correct++;
    else s.errors[h.chosen as Exclude<CandidateKind, "correct">]++;
    for (const k of h.offered) if (k !== "correct") s.offered[k]++;
    if (i >= history.length - 20) { s.last20.n++; if (ok) s.last20.correct++; }
    const sides: ("LAO" | "RAO" | "CRAN" | "CAUD")[] = [];
    if (Math.abs(h.to.alpha) >= DEGENERATE_DEG) sides.push(h.to.alpha > 0 ? "LAO" : "RAO");
    if (Math.abs(h.to.beta) >= DEGENERATE_DEG) sides.push(h.to.beta > 0 ? "CRAN" : "CAUD");
    for (const side of sides) { s.bySide[side].n++; if (ok) s.bySide[side].correct++; }
  });
  return s;
}

export const poseLabel = (p: { alpha: number; beta: number }) => viewLabel(p.alpha, p.beta);
