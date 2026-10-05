// STUDY (v1.1 assessment module; pure, no rendering): the fixed pre/post question sets on the ASOCA heart, the four answer
// tiles per question, the session record, the summary and the per-participant CSV.
//
// Design (v1.1 brief):
//   pre-test  10 Predict questions on the ASOCA real-patient heart
//   training  the atlas (guided tour + free Predict on the atlas)
//   post-test 10 NEW questions on the ASOCA heart (different poses: transfer to unseen views of unseen anatomy)
// The two sets are fixed (every participant answers the same 20 poses) and counterbalanced: the participant code decides
// whether set A or set B comes first. Each set is balanced: 5 LAO / 5 RAO, 5 CRAN / 5 CAUD, 5 LCA / 5 RCA; every pair of the
// 20 poses is >= 11 degrees apart (searched, then checked in tests/study.test.ts).
//
// Wrong-answer kinds (the error types recorded):
//   alpha-flip  LAO <-> RAO sign flipped            (-a, b)
//   beta-flip   CRAN <-> CAUD sign flipped           (a, -b)
//   mirror      the correct image mirrored left-right (a deliberate wrong answer only; no correct tile is ever mirrored)
//   axis-swap   axis confusion: the two magnitudes exchanged between the axes, each axis keeps its side
//               (LAO 25 / CAUD 40 -> LAO 40 / CAUD 25)
// Every pose has 15 <= |a|, |b| <= 45 and | |a| - |b| | >= 15, so all four wrong answers are distinct views.
// Each question shows the correct tile plus three of the four kinds; the left-out kind rotates with the question number,
// so each kind is offered in 7 or 8 of the 10 questions of a set.
import type { Tree } from "../caseData";
import { viewLabel } from "../geometry";
import { rng } from "../predict";

export type ErrorKind = "alpha-flip" | "beta-flip" | "mirror" | "axis-swap";
export type TileKind = "correct" | ErrorKind;
export const ERROR_KINDS: ErrorKind[] = ["alpha-flip", "beta-flip", "mirror", "axis-swap"];
export const ERROR_TEXT: Record<ErrorKind, string> = {
  "alpha-flip": "LAO/RAO flip",
  "beta-flip": "CRAN/CAUD flip",
  mirror: "left-right mirror",
  "axis-swap": "axis confusion",
};

export interface StudyPose { alpha: number; beta: number; tree: Tree }

export const SET_A: StudyPose[] = [
  { alpha: -45, beta: -15, tree: "left" },
  { alpha: -40, beta: -25, tree: "right" },
  { alpha: -30, beta: 15, tree: "left" },
  { alpha: -45, beta: 15, tree: "right" },
  { alpha: -40, beta: 25, tree: "left" },
  { alpha: 15, beta: -30, tree: "right" },
  { alpha: 25, beta: -40, tree: "left" },
  { alpha: 30, beta: -15, tree: "right" },
  { alpha: 15, beta: 30, tree: "left" },
  { alpha: 25, beta: 40, tree: "right" },
];
export const SET_B: StudyPose[] = [
  { alpha: -25, beta: -40, tree: "left" },
  { alpha: -15, beta: -30, tree: "right" },
  { alpha: -30, beta: -15, tree: "left" },
  { alpha: -25, beta: 40, tree: "right" },
  { alpha: -15, beta: 30, tree: "left" },
  { alpha: 45, beta: -30, tree: "right" },
  { alpha: 45, beta: -15, tree: "left" },
  { alpha: 30, beta: 15, tree: "right" },
  { alpha: 40, beta: 25, tree: "left" },
  { alpha: 45, beta: 15, tree: "right" },
];

export interface Tile { kind: TileKind; alpha: number; beta: number; mirrorLR: boolean }

/** The tile for one kind (the view that answer would show). */
export function tileFor(p: StudyPose, kind: TileKind): Tile {
  const { alpha: a, beta: b } = p;
  switch (kind) {
    case "correct": return { kind, alpha: a, beta: b, mirrorLR: false };
    case "alpha-flip": return { kind, alpha: -a, beta: b, mirrorLR: false };
    case "beta-flip": return { kind, alpha: a, beta: -b, mirrorLR: false };
    case "mirror": return { kind, alpha: a, beta: b, mirrorLR: true };
    case "axis-swap": return { kind, alpha: Math.sign(a) * Math.abs(b), beta: Math.sign(b) * Math.abs(a), mirrorLR: false };
  }
}

/** The four tiles of question q (0-based) in display order, shuffled with the participant's seed. */
export function tilesFor(p: StudyPose, q: number, seed: number): Tile[] {
  const left = ERROR_KINDS[q % 4];
  const kinds: TileKind[] = ["correct", ...ERROR_KINDS.filter((k) => k !== left)];
  const r = rng((seed ^ Math.imul(q + 1, 0x9e3779b1)) >>> 0);
  for (let i = kinds.length - 1; i > 0; i--) {
    const j = Math.floor(r() * (i + 1));
    [kinds[i], kinds[j]] = [kinds[j], kinds[i]];
  }
  return kinds.map((k) => tileFor(p, k));
}

export const promptFor = (p: StudyPose) => `${viewLabel(p.alpha, p.beta)}, ${p.tree === "left" ? "left (LCA)" : "right (RCA)"} injection`;

// ---------------- participant, session ----------------
/** An anonymous participant code: letters/digits/hyphen, 3-16 characters, with at least one digit (so it cannot be a name). */
export const CODE_RE = /^(?=.*\d)[A-Za-z0-9-]{3,16}$/;
export function newCode(rand: () => number = Math.random): string {
  const A = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let s = "P-";
  for (let i = 0; i < 5; i++) s += A[Math.floor(rand() * A.length)];
  return /\d/.test(s) ? s : s.slice(0, -1) + "7";
}
/** Stable 32-bit hash of the code: the tile-order seed and the set order. */
export function hashCode(code: string): number {
  let h = 2166136261 >>> 0;
  for (const ch of code.toUpperCase()) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619) >>> 0; }
  return h >>> 0;
}
/** Counterbalancing: even hash -> A first, odd -> B first. */
export const setOrder = (code: string): ["A", "B"] | ["B", "A"] => (hashCode(code) % 2 === 0 ? ["A", "B"] : ["B", "A"]);
export const setPoses = (s: "A" | "B") => (s === "A" ? SET_A : SET_B);

export type Phase = "pre" | "post";
export interface Answer {
  phase: Phase;
  set: "A" | "B";
  q: number;                 // 0-9
  pose: StudyPose;
  offered: TileKind[];       // tile order A-D
  chosen: TileKind;
  rtMs: number;              // from the tiles appearing to the click
  at: string;                // ISO time of the answer
}
export interface Session {
  version: 1;
  code: string;              // anonymous participant code; no names are ever stored
  started: string;
  order: ["A", "B"] | ["B", "A"];
  answers: Answer[];
  training: { started?: string; ended?: string; tourCompleted: boolean; practiceAnswers: number; practiceCorrect: number;
    histStart?: number };
  finished?: string;
}
export function newSession(code: string, now = new Date()): Session {
  return { version: 1, code, started: now.toISOString(), order: setOrder(code), answers: [],
    training: { tourCompleted: false, practiceAnswers: 0, practiceCorrect: 0 } };
}

export interface PhaseSummary {
  n: number;
  correct: number;
  errors: Record<ErrorKind, number>;
  offered: Record<ErrorKind, number>;
  medianRtMs: number;
  totalMs: number;
}
export function summarizePhase(s: Session, phase: Phase): PhaseSummary {
  const a = s.answers.filter((x) => x.phase === phase);
  const zero = () => ({ "alpha-flip": 0, "beta-flip": 0, mirror: 0, "axis-swap": 0 });
  const out: PhaseSummary = { n: a.length, correct: 0, errors: zero(), offered: zero(), medianRtMs: 0, totalMs: 0 };
  for (const x of a) {
    if (x.chosen === "correct") out.correct++;
    else out.errors[x.chosen]++;
    for (const k of x.offered) if (k !== "correct") out.offered[k]++;
    out.totalMs += x.rtMs;
  }
  const rts = a.map((x) => x.rtMs).sort((p, q) => p - q);
  out.medianRtMs = rts.length ? (rts.length % 2 ? rts[(rts.length - 1) / 2] : (rts[rts.length / 2 - 1] + rts[rts.length / 2]) / 2) : 0;
  return out;
}

// ---------------- CSV (one file per participant, one row per question) ----------------
export const CSV_COLUMNS = ["participant", "phase", "set", "question", "view", "alpha_deg", "beta_deg", "tree",
  "tile_A", "tile_B", "tile_C", "tile_D", "chosen", "correct", "error_type", "rt_ms", "answered_at",
  "training_minutes", "tour_completed", "practice_answers", "practice_correct", "session_started"] as const;
const esc = (v: string | number | boolean) => {
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};
export function sessionCsv(s: Session): string {
  const t = s.training;
  const trainMin = t.started && t.ended ? ((Date.parse(t.ended) - Date.parse(t.started)) / 60000).toFixed(1) : "";
  const rows = s.answers.map((a) => [s.code, a.phase, a.set, a.q + 1, viewLabel(a.pose.alpha, a.pose.beta), a.pose.alpha, a.pose.beta,
    a.pose.tree === "left" ? "LCA" : "RCA", ...a.offered, a.chosen, a.chosen === "correct" ? 1 : 0,
    a.chosen === "correct" ? "" : a.chosen, Math.round(a.rtMs), a.at, trainMin, t.tourCompleted ? 1 : 0, t.practiceAnswers,
    t.practiceCorrect, s.started].map(esc).join(","));
  return [CSV_COLUMNS.join(","), ...rows].join("\r\n") + "\r\n";
}
