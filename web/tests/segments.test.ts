import { describe, expect, it } from "vitest";
import type { Edge, GraphNode } from "../src/caseData";
import { add, norm, scale, sub, type Vec3 } from "../src/geometry";
import type { BranchName } from "../src/labels";
import { deriveSegments } from "../src/segments";

// Synthetic tree. Left: ostium 0 -LM-> 1; 1 -LAD-> 2 -LAD-> 4 -LAD-> 5; D1 2->6; D2 4->7; 1 -LCx-> 3 -LCx-> 8; OM1 3->9.
// Right: ostium 10 -RCA-> 11 -RCA-> 12; RV marginal 11->13.
const P: Record<number, Vec3> = {
  0: [0, 0, 0], 1: [10, 0, 0], 2: [20, -10, -5], 4: [35, -20, -15], 5: [50, -30, -35], 6: [30, -5, -5], 7: [45, -15, -15],
  3: [20, 10, -5], 8: [30, 30, -30], 9: [35, 15, -5],
  10: [-10, -10, 0], 11: [-25, -15, -20], 12: [-20, 5, -60], 13: [-35, -25, -25],
};
const kinds: Record<number, GraphNode["kind"]> = { 0: "ostium", 10: "ostium", 1: "bifurcation", 2: "bifurcation", 3: "bifurcation", 4: "bifurcation", 11: "bifurcation" };
const nodes: GraphNode[] = Object.entries(P).map(([id, pos]) => ({
  id: Number(id), pos, kind: kinds[Number(id)] ?? "endpoint", tree: Number(id) >= 10 ? "right" : "left",
}));
let nextId = 0;
function edge(a: number, b: number, tree: "left" | "right" = "left"): Edge {
  const L = norm(sub(P[b], P[a]));
  const n = Math.ceil(L / 0.5);
  const pts = [...Array(n + 1).keys()].map((k) => add(P[a], scale(sub(P[b], P[a]), k / n)));
  return { id: nextId++, tree, a, b, lengthMm: L, pts, radius: pts.map(() => 1) };
}
const E = {
  LM: edge(0, 1), LAD1: edge(1, 2), LCx1: edge(1, 3), LAD2: edge(2, 4), D1: edge(2, 6), LAD3: edge(4, 5), D2: edge(4, 7),
  LCx2: edge(3, 8), OM1: edge(3, 9), RCA1: edge(10, 11, "right"), RCA2: edge(11, 12, "right"), RVM: edge(11, 13, "right"),
};
const edges = Object.values(E);
const full = new Map<number, BranchName>([
  [E.LM.id, "LM"], [E.LAD1.id, "LAD"], [E.LAD2.id, "LAD"], [E.LAD3.id, "LAD"], [E.D1.id, "D1"], [E.D2.id, "D2"],
  [E.LCx1.id, "LCx"], [E.LCx2.id, "LCx"], [E.OM1.id, "OM1"], [E.RCA1.id, "RCA"], [E.RCA2.id, "RCA"], [E.RVM.id, "RV marginal"],
]);
const opts = { rcaDistalTruncated: true };
const seg = (d: ReturnType<typeof deriveSegments>, n: string) => d.segments.find((s) => s.name === n);
const close = (a: Vec3, b: Vec3) => expect(norm(sub(a, b))).toBeLessThan(1e-9);

describe("derived segments", () => {
  it("full labeling: SCCT/AHA splits at the labeled side-branch origins", () => {
    const d = deriveSegments(edges, nodes, full, opts);
    expect(d.issues).toEqual([]);
    expect(d.notes).toEqual([]);
    const names = d.segments.map((s) => s.name).sort();
    expect(names).toEqual(["D1", "D2", "LAD dist", "LAD mid", "LAD prox", "LCx dist", "LCx prox", "LM", "OM1",
      "RCA dist", "RCA mid", "RCA prox", "RV marginal"].sort());
    close(seg(d, "LAD prox")!.pts[0], P[1]);
    close(seg(d, "LAD prox")!.pts.at(-1)!, P[2]);                // D1 origin
    close(seg(d, "LAD mid")!.pts.at(-1)!, P[4]);                 // D2 origin
    close(seg(d, "LAD dist")!.pts.at(-1)!, P[5]);
    close(seg(d, "LCx prox")!.pts.at(-1)!, P[3]);                // OM1 origin
    expect(d.segments.every((s) => s.complete)).toBe(true);
  });

  it("no RV marginal: approximate thirds, flagged, not mission-eligible; distal flagged as truncated", () => {
    const l = new Map(full);
    l.delete(E.RVM.id);
    const d = deriveSegments(edges, nodes, l, opts);
    expect(d.rcaRule).toBe("approximate-thirds");
    expect(["RCA prox", "RCA mid", "RCA dist"].every((n) => seg(d, n)!.flags.includes("approximate (thirds)") && !seg(d, n)!.complete)).toBe(true);
    expect(d.notes.join()).toMatch(/approximate thirds/);
    const L = ["RCA prox", "RCA mid", "RCA dist"].map((n) => seg(d, n)!.lengthMm);  // equal thirds
    const total = E.RCA1.lengthMm + E.RCA2.lengthMm;
    L.forEach((l) => expect(Math.abs(l - total / 3)).toBeLessThan(0.6));
    expect(seg(d, "RCA dist")!.flags.join()).toMatch(/truncated/);
    expect(seg(d, "RCA prox")!.flags).toEqual(["approximate (thirds)"]);
  });

  it("RV marginal labeled: SCCT acute-margin rule is used automatically and segments are complete", () => {
    const d = deriveSegments(edges, nodes, full, { rcaDistalTruncated: false });
    expect(d.rcaRule).toBe("acute-margin");
    expect(seg(d, "RCA prox")!.complete && seg(d, "RCA mid")!.complete).toBe(true);
    expect(seg(d, "RCA prox")!.flags).toEqual([]);
    close(seg(d, "RCA mid")!.pts.at(-1)!, P[11]);
    expect(Math.abs(seg(d, "RCA prox")!.lengthMm - E.RCA1.lengthMm / 2)).toBeLessThan(0.6);
  });

  it("missing D2: LAD prox is derived, the rest stays unsplit and is not mission-eligible", () => {
    const l = new Map(full);
    l.delete(E.D2.id);
    const d = deriveSegments(edges, nodes, l, opts);
    expect(seg(d, "LAD prox")!.complete).toBe(true);
    const rest = seg(d, "LAD mid+dist (unsplit)")!;
    expect(rest.complete).toBe(false);
    close(rest.pts[0], P[2]);
    close(rest.pts.at(-1)!, P[5]);
    expect(d.notes.join()).toMatch(/D2/);
    expect(d.issues).toEqual([]);       // a missing side branch is a note, not an inconsistency
    expect(d.segments.find((s) => s.name === "D2")).toBeUndefined();
  });

  it("missing D1: whole LAD unsplit", () => {
    const l = new Map(full);
    l.delete(E.D1.id);
    const d = deriveSegments(edges, nodes, l, opts);
    expect(seg(d, "LAD prox+mid+dist (unsplit)")).toBeDefined();
    expect(seg(d, "LAD prox")).toBeUndefined();
  });

  it("never invents: unlabeled edges produce no segment, names come only from labels", () => {
    const l = new Map<number, BranchName>([[E.LM.id, "LM"], [E.LAD1.id, "LAD"]]);
    const d = deriveSegments(edges, nodes, l, opts);
    expect(d.segments.map((s) => s.name).sort()).toEqual(["LAD prox+mid+dist (unsplit)", "LM"]);
  });

  it("a side branch on the wrong parent is reported, not repaired", () => {
    const l = new Map(full);
    l.set(E.OM1.id, "D1");     // second D1 hangs off LCx: D1 is no longer one path
    l.delete(E.D1.id);
    const d = deriveSegments(edges, nodes, l, opts);
    expect(d.issues.join()).toMatch(/D1 does not originate on the labeled LAD/);
    expect(seg(d, "LAD prox")).toBeUndefined();
  });

  it("a gap in a labeled branch is reported", () => {
    const l = new Map(full);
    l.delete(E.LAD2.id);
    const d = deriveSegments(edges, nodes, l, opts);
    expect(d.issues.join()).toMatch(/LAD: labeled edges do not form one simple path/);
  });

  it("non-expert edges never take part, even if labeled", () => {
    const ext: Edge = { ...edge(12, 13, "right"), id: 1000, nonExpert: true };
    const l = new Map(full);
    l.set(1000, "PDA");
    const d = deriveSegments([...edges, ext], nodes, l, opts);
    expect(d.segments.find((s) => s.name === "PDA")).toBeUndefined();
  });

  it("segments carry their bifurcations for the metric exclusion", () => {
    const d = deriveSegments(edges, nodes, full, opts);
    const mid = seg(d, "LAD mid")!;
    expect(mid.bif.length).toBe(2);   // D1 and D2 origins at its ends
  });
});
