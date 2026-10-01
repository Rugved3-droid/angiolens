import { describe, expect, it } from "vitest";
import {
  angularDistance, type Attempt, DEGENERATE_DEG, drawPose, makeCandidates, MIN_MOVE_DEG, type PresetPose, rng, summarize,
} from "../src/predict";

const PRESETS: PresetPose[] = [
  { name: "RAO caudal", alpha: -30, beta: -25, tree: "left" },
  { name: "AP cranial", alpha: 0, beta: 35, tree: "left" },
  { name: "LAO 45 (RCA)", alpha: 45, beta: 0, tree: "right" },
];

describe("candidates", () => {
  it("non-degenerate pose: correct, -alpha, -beta, both flipped; exactly one correct; shuffled", () => {
    const seen = new Set<string>();
    for (let s = 0; s < 20; s++) {
      const c = makeCandidates(40, -30, false, rng(s));
      expect(c.map((x) => x.kind).sort()).toEqual(["alpha-flip", "beta-flip", "both-flip", "correct"]);
      const byKind = Object.fromEntries(c.map((x) => [x.kind, x]));
      expect([byKind.correct.alpha, byKind.correct.beta]).toEqual([40, -30]);
      expect([byKind["alpha-flip"].alpha, byKind["alpha-flip"].beta]).toEqual([-40, -30]);
      expect([byKind["beta-flip"].alpha, byKind["beta-flip"].beta]).toEqual([40, 30]);
      expect([byKind["both-flip"].alpha, byKind["both-flip"].beta]).toEqual([-40, 30]);
      expect(c.every((x) => x.kind === "mirror-lr" || !x.mirrorLR)).toBe(true);
      seen.add(c.map((x) => x.kind).join());
    }
    expect(seen.size).toBeGreaterThan(5); // order varies
  });

  it("mirror toggle replaces 'both flipped' with an L-R mirror of the correct view", () => {
    const c = makeCandidates(40, -30, true, rng(1));
    expect(c.map((x) => x.kind).sort()).toEqual(["alpha-flip", "beta-flip", "correct", "mirror-lr"]);
    const m = c.find((x) => x.kind === "mirror-lr")!;
    expect([m.alpha, m.beta, m.mirrorLR, m.mirrorUD]).toEqual([40, -30, true, false]);
  });

  it("degenerate flips (AP, zero tilt) are replaced so all four are distinct", () => {
    expect(() => makeCandidates(0, 0, false, rng(1))).toThrow();
    expect(() => makeCandidates(3, -2, true, rng(1))).toThrow();
    for (const [a, b] of [[0, 35], [45, 0], [-30, 0], [0, -30]]) {
      for (const useMirror of [false, true]) {
        const c = makeCandidates(a, b, useMirror, rng(7));
        const kinds = c.map((x) => x.kind);
        expect(new Set(kinds).size).toBe(4);
        expect(kinds.filter((k) => k === "correct").length).toBe(1);
        if (Math.abs(a) < DEGENERATE_DEG) expect(kinds).not.toContain("alpha-flip");
        if (Math.abs(b) < DEGENERATE_DEG) expect(kinds).not.toContain("beta-flip");
        if (Math.abs(a) < DEGENERATE_DEG || Math.abs(b) < DEGENERATE_DEG) expect(kinds).not.toContain("both-flip");
        // every non-mirror distractor is a genuinely different pose
        for (const x of c.filter((x) => !x.mirrorLR && !x.mirrorUD && x.kind !== "correct"))
          expect(angularDistance(a, b, x.alpha, x.beta)).toBeGreaterThan(2 * DEGENERATE_DEG - 1);
      }
    }
  });
});

describe("pose draws", () => {
  it("presets and random poses, always far enough from the previous pose, within range", () => {
    const r = rng(42);
    let prev = { alpha: 0, beta: 0 };
    const sources = new Set<string>();
    for (let i = 0; i < 300; i++) {
      const p = drawPose(r, PRESETS, prev);
      expect(angularDistance(prev.alpha, prev.beta, p.alpha, p.beta)).toBeGreaterThanOrEqual(MIN_MOVE_DEG);
      expect(Math.abs(p.alpha)).toBeLessThanOrEqual(90);
      expect(Math.abs(p.beta)).toBeLessThanOrEqual(45);
      if (p.source === "random") {
        expect(Math.abs(p.alpha)).toBeGreaterThanOrEqual(10);
        expect(Math.abs(p.beta)).toBeGreaterThanOrEqual(10);
      }
      sources.add(p.source);
      prev = p;
    }
    expect(sources.has("random")).toBe(true);
    expect([...sources].filter((s) => s !== "random").length).toBe(PRESETS.length);
  });

  it("angular distance", () => {
    expect(angularDistance(0, 0, 90, 0)).toBeCloseTo(90, 9);
    expect(angularDistance(0, 0, 0, 30)).toBeCloseTo(30, 9);
    expect(angularDistance(30, 20, 30, 20)).toBeCloseTo(0, 6);
  });
});

describe("summary", () => {
  const att = (to: [number, number], chosen: Attempt["chosen"], offered: Attempt["offered"]): Attempt => ({
    when: "", from: { alpha: 0, beta: 0 }, to: { alpha: to[0], beta: to[1], tree: "left", source: "x" }, chosen, offered,
  });
  it("counts error types, offered denominators, sides and the last 20", () => {
    const all4: Attempt["offered"] = ["correct", "alpha-flip", "beta-flip", "both-flip"];
    const h = [
      att([40, -30], "correct", all4), att([40, -30], "alpha-flip", all4), att([-30, 20], "beta-flip", all4),
      att([-30, 20], "beta-flip", all4), att([0, 35], "mirror-lr", ["correct", "mirror-lr", "beta-flip", "mirror-ud"]),
    ];
    const s = summarize(h);
    expect(s.n).toBe(5);
    expect(s.correct).toBe(1);
    expect(s.errors).toEqual({ "alpha-flip": 1, "beta-flip": 2, "both-flip": 0, "mirror-lr": 1, "mirror-ud": 0 });
    expect(s.offered["mirror-ud"]).toBe(1);
    expect(s.offered["alpha-flip"]).toBe(4);
    expect(s.bySide.LAO).toEqual({ n: 2, correct: 1 });
    expect(s.bySide.RAO).toEqual({ n: 2, correct: 0 });
    expect(s.bySide.CRAN.n).toBe(3); // AP cranial counts for CRAN only
    expect(s.last20).toEqual({ n: 5, correct: 1 });
  });
});
