import { describe, expect, it } from "vitest";
import { angularDistance } from "../src/predict";
import {
  CODE_RE, CSV_COLUMNS, ERROR_KINDS, hashCode, newCode, newSession, SET_A, SET_B, sessionCsv, setOrder, summarizePhase, tileFor,
  tilesFor, type Session,
} from "../src/study/studyCore";
import { rng } from "../src/predict";

const all = [...SET_A, ...SET_B];

describe("study question sets", () => {
  it("each set: 10 poses, 5 LAO / 5 RAO, 5 CRAN / 5 CAUD, 5 LCA / 5 RCA", () => {
    for (const S of [SET_A, SET_B]) {
      expect(S.length).toBe(10);
      expect(S.filter((p) => p.alpha > 0).length).toBe(5);
      expect(S.filter((p) => p.beta > 0).length).toBe(5);
      expect(S.filter((p) => p.tree === "left").length).toBe(5);
    }
  });
  it("all 20 poses are pairwise >= 11 degrees apart (the post-test views are new)", () => {
    for (let i = 0; i < all.length; i++)
      for (let j = i + 1; j < all.length; j++)
        expect(angularDistance(all[i].alpha, all[i].beta, all[j].alpha, all[j].beta)).toBeGreaterThanOrEqual(11);
  });
  it("every pose keeps all four wrong answers distinct views (>= 15 deg magnitudes, >= 15 deg apart between axes)", () => {
    for (const p of all) {
      expect(Math.abs(p.alpha)).toBeGreaterThanOrEqual(15);
      expect(Math.abs(p.beta)).toBeGreaterThanOrEqual(15);
      expect(Math.abs(p.alpha)).toBeLessThanOrEqual(45);
      expect(Math.abs(p.beta)).toBeLessThanOrEqual(45);
      expect(Math.abs(Math.abs(p.alpha) - Math.abs(p.beta))).toBeGreaterThanOrEqual(15);
      const views = (["correct", "alpha-flip", "beta-flip", "axis-swap"] as const).map((k) => tileFor(p, k));
      for (let i = 0; i < views.length; i++)
        for (let j = i + 1; j < views.length; j++)
          expect(angularDistance(views[i].alpha, views[i].beta, views[j].alpha, views[j].beta)).toBeGreaterThan(14);
    }
  });
  it("axis confusion exchanges the magnitudes and keeps each axis's side", () => {
    expect(tileFor({ alpha: 25, beta: -40, tree: "left" }, "axis-swap")).toMatchObject({ alpha: 40, beta: -25, mirrorLR: false });
    expect(tileFor({ alpha: -45, beta: 15, tree: "left" }, "axis-swap")).toMatchObject({ alpha: -15, beta: 45 });
  });
});

describe("tiles", () => {
  it("one correct tile + three different error kinds; the left-out kind rotates; only the mirror tile is mirrored", () => {
    const seen = Object.fromEntries(ERROR_KINDS.map((k) => [k, 0]));
    SET_A.forEach((p, q) => {
      const t = tilesFor(p, q, 1234);
      expect(t.length).toBe(4);
      expect(t.filter((x) => x.kind === "correct").length).toBe(1);
      expect(new Set(t.map((x) => x.kind)).size).toBe(4);
      expect(t.some((x) => x.kind === ERROR_KINDS[q % 4])).toBe(false);
      for (const x of t) {
        expect(x.mirrorLR).toBe(x.kind === "mirror");
        if (x.kind !== "correct") seen[x.kind]++;
      }
    });
    for (const k of ERROR_KINDS) expect([7, 8]).toContain(seen[k]);
  });
  it("tile order is reproducible per participant and differs between participants", () => {
    const a = tilesFor(SET_A[0], 0, hashCode("P-AB12C")).map((t) => t.kind).join();
    expect(tilesFor(SET_A[0], 0, hashCode("P-AB12C")).map((t) => t.kind).join()).toBe(a);
    const orders = new Set(Array.from({ length: 30 }, (_, i) => tilesFor(SET_A[0], 0, hashCode(`P-${i}X`)).map((t) => t.kind).join()));
    expect(orders.size).toBeGreaterThan(5);
  });
});

describe("participant and session", () => {
  it("codes are anonymous: generated codes match, names do not", () => {
    const r = rng(5);
    for (let i = 0; i < 50; i++) expect(CODE_RE.test(newCode(r))).toBe(true);
    for (const name of ["John", "Rugved Parmar", "a", "jane.doe@x.org"]) expect(CODE_RE.test(name)).toBe(false);
    expect(CODE_RE.test("R07")).toBe(true);
  });
  it("counterbalancing: set order follows the code, both orders occur", () => {
    const orders = new Set(Array.from({ length: 40 }, (_, i) => setOrder(`P-${i}Q`).join("")));
    expect(orders).toEqual(new Set(["AB", "BA"]));
    expect(setOrder("P-AB12C")).toEqual(setOrder("p-ab12c"));
  });
  it("summary and CSV: one row per question, columns fixed, error type blank when correct", () => {
    const s: Session = newSession("P-TEST1", new Date("2026-10-05T10:00:00Z"));
    SET_A.forEach((p, q) => {
      const offered = tilesFor(p, q, 7).map((t) => t.kind);
      const chosen = q < 6 ? "correct" : offered.find((k) => k !== "correct")!;
      s.answers.push({ phase: "pre", set: "A", q, pose: p, offered, chosen, rtMs: 1000 + q * 100, at: "2026-10-05T10:01:00Z" });
    });
    s.training = { started: "2026-10-05T10:05:00Z", ended: "2026-10-05T10:15:30Z", tourCompleted: true, practiceAnswers: 9, practiceCorrect: 6 };
    const sum = summarizePhase(s, "pre");
    expect(sum).toMatchObject({ n: 10, correct: 6, medianRtMs: 1450, totalMs: 14500 });
    expect(Object.values(sum.errors).reduce((a, b) => a + b, 0)).toBe(4);
    const lines = sessionCsv(s).trim().split("\r\n");
    expect(lines[0].split(",")).toEqual([...CSV_COLUMNS]);
    expect(lines.length).toBe(11);
    const first = lines[1].split(",");
    expect(first[0]).toBe("P-TEST1");
    expect(first[13]).toBe("1");
    expect(first[14]).toBe("");
    expect(first[17]).toBe("10.5");
    expect(lines[10].split(",")[13]).toBe("0");
  });
});
