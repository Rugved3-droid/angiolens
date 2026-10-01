// Derived coronary segments from hand-labeled BRANCHES (SCCT/AHA-style rules). Pure geometry/topology, no rendering.
//
// Never invents a branch: a split point exists only where a labeled side branch originates on its labeled parent.
// Missing side branches leave the parent unsplit (with the reason); inconsistent labels are reported, not repaired.
//
//   LM                  whole labeled LM
//   LAD prox / mid / dist   LAD start -> D1 origin -> D2 origin -> end
//   LCx prox / dist         LCx start -> OM1 origin -> end
//   RCA prox / mid / dist   SCCT acute-margin rule whenever an RV marginal (acute marginal) is labeled on the RCA:
//                           prox = ostium to half-way to its origin, mid = to its origin, dist = beyond.
//                           Otherwise equal arc-length thirds, marked "approximate (thirds)" and NOT mission-eligible.
//   D1, D2, septal, ramus, OM1, OM2, conus, RV marginal, PDA, PLB: each labeled branch whole
import type { Edge, GraphNode, Tree } from "./caseData";
import { norm, sub, type Vec3 } from "./geometry";
import type { BranchName } from "./labels";

export type RcaRule = "acute-margin" | "approximate-thirds" | "none";

export interface SegmentMember {
  edgeId: number;
  i0: number; // inclusive sample index range on the edge (in edge order)
  i1: number;
}

export interface DerivedSegment {
  name: string;
  branch: BranchName;
  tree: Tree;
  pts: Vec3[];
  radius: number[];
  lengthMm: number;
  members: SegmentMember[];
  bif: Vec3[]; // bifurcation nodes on or at the ends of the segment (metric exclusion)
  complete: boolean; // derived by the full rule (eligible as a mission target)
  flags: string[];
}

export interface Boundary {
  name: string; // e.g. "LAD prox | mid"
  pos: Vec3;
  rule: string;
}

export interface Derivation {
  segments: DerivedSegment[];
  /** which RCA rule the derivation actually used (recorded with an approval) */
  rcaRule: RcaRule;
  boundaries: Boundary[];
  /** label INCONSISTENCIES (block approval) */
  issues: string[];
  /** legitimate absences, e.g. a side branch not present/labeled so a split is not made (do not block approval) */
  notes: string[];
}

interface ChainSample {
  p: Vec3;
  r: number;
  edgeId: number;
  idx: number;
  arc: number;
  node: number | null; // graph node at this sample (chain ends / internal joints)
}

const SIDE_PARENT: Partial<Record<BranchName, BranchName>> = {
  D1: "LAD", D2: "LAD", septal: "LAD", OM1: "LCx", OM2: "LCx",
  conus: "RCA", "RV marginal": "RCA", PDA: "RCA", PLB: "RCA",
};

/** Shortest path distance (mm) from each tree's ostium to every node. */
function nodeDepths(edges: Edge[], nodes: GraphNode[]): Map<number, number> {
  const adj = new Map<number, { to: number; w: number }[]>();
  for (const e of edges) {
    for (const [a, b] of [[e.a, e.b], [e.b, e.a]]) {
      if (!adj.has(a)) adj.set(a, []);
      adj.get(a)!.push({ to: b, w: e.lengthMm });
    }
  }
  const depth = new Map<number, number>();
  const queue = nodes.filter((n) => n.kind === "ostium").map((n) => n.id);
  queue.forEach((id) => depth.set(id, 0));
  while (queue.length) {
    const u = queue.shift()!;
    for (const { to, w } of adj.get(u) ?? []) {
      const d = depth.get(u)! + w;
      if (!depth.has(to) || d < depth.get(to)!) {
        depth.set(to, d);
        queue.push(to);
      }
    }
  }
  return depth;
}

/** Ordered proximal->distal chain of the edges labeled `branch`, or an issue. */
function chainOf(branch: BranchName, edges: Edge[], labels: Map<number, BranchName>, depth: Map<number, number>):
  { chain: ChainSample[]; start: number; end: number } | { issue: string } | null {
  const E = edges.filter((e) => labels.get(e.id) === branch);
  if (!E.length) return null;
  const deg = new Map<number, number>();
  for (const e of E) for (const n of [e.a, e.b]) deg.set(n, (deg.get(n) ?? 0) + 1);
  const ends = [...deg].filter(([, d]) => d === 1).map(([n]) => n);
  if ([...deg.values()].some((d) => d > 2) || ends.length !== 2)
    return { issue: `${branch}: labeled edges do not form one simple path (check for gaps or a labeled side branch)` };
  const start = ends.reduce((a, b) => ((depth.get(a) ?? Infinity) <= (depth.get(b) ?? Infinity) ? a : b));
  const end = ends.find((n) => n !== start)!;
  const chain: ChainSample[] = [];
  let at = start;
  const used = new Set<number>();
  while (used.size < E.length) {
    const e = E.find((x) => !used.has(x.id) && (x.a === at || x.b === at));
    if (!e) return { issue: `${branch}: labeled edges are not connected` };
    used.add(e.id);
    const fwd = e.a === at;
    const n = e.pts.length;
    for (let k = chain.length ? 1 : 0; k < n; k++) {
      const idx = fwd ? k : n - 1 - k;
      const prev = chain.at(-1);
      chain.push({
        p: e.pts[idx], r: e.radius[idx], edgeId: e.id, idx,
        arc: prev ? prev.arc + norm(sub(e.pts[idx], prev.p)) : 0,
        node: k === 0 ? at : k === n - 1 ? (fwd ? e.b : e.a) : null,
      });
    }
    at = fwd ? e.b : e.a;
  }
  return { chain, start, end };
}

function slice(name: string, branch: BranchName, tree: Tree, ch: ChainSample[], i0: number, i1: number,
               bifNodes: Set<number>, nodesById: Map<number, GraphNode>, complete: boolean, flags: string[]): DerivedSegment {
  const s = ch.slice(i0, i1 + 1);
  const members: SegmentMember[] = [];
  for (const c of s) {
    const m = members.at(-1);
    if (m && m.edgeId === c.edgeId) { m.i0 = Math.min(m.i0, c.idx); m.i1 = Math.max(m.i1, c.idx); }
    else members.push({ edgeId: c.edgeId, i0: c.idx, i1: c.idx });
  }
  const bif = s.filter((c) => c.node !== null && bifNodes.has(c.node)).map((c) => nodesById.get(c.node!)!.pos);
  return {
    name, branch, tree, pts: s.map((c) => c.p), radius: s.map((c) => c.r),
    lengthMm: s.length ? s.at(-1)!.arc - s[0].arc : 0, members, bif, complete, flags,
  };
}

export function deriveSegments(edges: Edge[], nodes: GraphNode[], labels: Map<number, BranchName>,
                               opts: { rcaDistalTruncated: boolean }): Derivation {
  const expert = edges.filter((e) => !e.nonExpert); // the non-expert layer never takes part in segmentation
  const depth = nodeDepths(expert, nodes);
  const nodesById = new Map(nodes.map((n) => [n.id, n]));
  const bifNodes = new Set(nodes.filter((n) => n.kind === "bifurcation").map((n) => n.id));
  const issues: string[] = [];
  const notes: string[] = [];
  const segments: DerivedSegment[] = [];
  const boundaries: Boundary[] = [];
  const chains = new Map<BranchName, { chain: ChainSample[]; start: number; end: number }>();
  for (const e of expert) {
    const l = labels.get(e.id);
    if (l && e.tree !== (["RCA", "conus", "RV marginal", "PDA", "PLB"].includes(l) ? "right" : "left"))
      issues.push(`edge #${e.id} is in the ${e.tree} tree but labeled ${l}`);
  }
  const branches = [...new Set([...labels.values()])];
  for (const b of branches) {
    const c = chainOf(b, expert, labels, depth);
    if (c && "issue" in c) issues.push(c.issue);
    else if (c) chains.set(b, c);
  }

  /** arc-index on the parent chain where side branch `side` originates, or null (with an issue). */
  const originOn = (side: BranchName, parent: BranchName): number | null => {
    const s = chains.get(side), p = chains.get(parent);
    if (!s || !p) return null;
    const i = p.chain.findIndex((c) => c.node === s.start);
    if (i < 0) { issues.push(`${side} does not originate on the labeled ${parent}`); return null; }
    return i;
  };

  // side branches must hang off their parent (report, never fix)
  for (const [side, parent] of Object.entries(SIDE_PARENT) as [BranchName, BranchName][])
    if (chains.has(side) && chains.has(parent!)) originOn(side, parent!);
    else if (chains.has(side) && !chains.has(parent!)) issues.push(`${side} is labeled but its parent ${parent} is not`);

  // LM and the LAD / LCx starts
  const lm = chains.get("LM");
  if (lm) segments.push(slice("LM", "LM", "left", lm.chain, 0, lm.chain.length - 1, bifNodes, nodesById, true, []));
  for (const b of ["LAD", "LCx"] as const)
    if (lm && chains.has(b) && chains.get(b)!.start !== lm.end) issues.push(`${b} does not start at the distal end of LM`);

  /** Split a parent at the origins of its labeled side branches; stop at the first one that is missing. */
  const splitBranch = (b: "LAD" | "LCx", parts: [string, BranchName | null][]) => {
    const c = chains.get(b);
    if (!c) return;
    const cuts = [0];
    let k = 0;
    for (; k < parts.length - 1; k++) {
      const side = parts[k][1]!;
      if (!chains.has(side)) { notes.push(`${b}: the ${parts[k][0]} | ${parts[k + 1][0]} split needs ${side} labeled`); break; }
      const i = originOn(side, b);
      if (i === null) break;
      if (i <= cuts.at(-1)!) { issues.push(`${b}: ${side} origin is not distal to the previous split`); break; }
      cuts.push(i);
      boundaries.push({ name: `${parts[k][0]} | ${parts[k + 1][0]}`, pos: c.chain[i].p, rule: `${side} origin` });
    }
    const fullySplit = k === parts.length - 1;
    cuts.push(c.chain.length - 1);
    for (let j = 0; j + 1 < cuts.length; j++) {
      const lastPartial = j + 2 === cuts.length && !fullySplit;
      const name = lastPartial ? `${b} ${parts.slice(j).map((p) => p[0].split(" ")[1]).join("+")} (unsplit)` : parts[j][0];
      segments.push(slice(name, b, "left", c.chain, cuts[j], cuts[j + 1], bifNodes, nodesById, !lastPartial,
        lastPartial ? ["not split: a required side branch is not labeled"] : []));
    }
  };
  splitBranch("LAD", [["LAD prox", "D1"], ["LAD mid", "D2"], ["LAD dist", null]]);
  splitBranch("LCx", [["LCx prox", "OM1"], ["LCx dist", null]]);

  let rcaRule: RcaRule = "none";
  const rca = chains.get("RCA");
  if (rca) {
    const ch = rca.chain;
    const L = ch.at(-1)!.arc;
    const at = (arc: number) => ch.findIndex((c) => c.arc >= arc - 1e-9);
    // SCCT acute-margin rule when the RV marginal is labeled ON the RCA; otherwise approximate thirds
    const i = chains.has("RV marginal") ? originOn("RV marginal", "RCA") : null;
    let cuts: number[];
    let rule: string;
    let approx = false;
    if (i !== null && i > 0) {
      cuts = [0, at(ch[i].arc / 2), i, ch.length - 1];
      rule = "SCCT acute margin (RV marginal origin); prox = half-way to it";
      rcaRule = "acute-margin";
    } else {
      cuts = [0, at(L / 3), at((2 * L) / 3), ch.length - 1];
      rule = "approximate: equal arc-length thirds (RV marginal not labeled on the RCA)";
      rcaRule = "approximate-thirds";
      approx = true;
      if (!chains.has("RV marginal")) notes.push("RCA split by approximate thirds: label the RV marginal (acute marginal) for the SCCT acute-margin rule");
    }
    const trunc = opts.rcaDistalTruncated ? ["distal RCA truncated: expert annotation ends before the crux"] : [];
    ["RCA prox", "RCA mid", "RCA dist"].forEach((n, k) => {
      const flags = [...(approx ? ["approximate (thirds)"] : []), ...(n === "RCA dist" ? trunc : [])];
      segments.push(slice(n, "RCA", "right", ch, cuts[k], cuts[k + 1], bifNodes, nodesById, !approx, flags));
    });
    boundaries.push({ name: "RCA prox | mid", pos: ch[cuts[1]].p, rule }, { name: "RCA mid | dist", pos: ch[cuts[2]].p, rule });
  }

  for (const b of ["D1", "D2", "septal", "ramus", "OM1", "OM2", "conus", "RV marginal", "PDA", "PLB"] as BranchName[]) {
    const c = chains.get(b);
    if (!c) continue;
    const tree = expert.find((e) => e.id === c.chain[0].edgeId)!.tree;
    segments.push(slice(b, b, tree, c.chain, 0, c.chain.length - 1, bifNodes, nodesById, true, []));
  }
  return { segments, rcaRule, boundaries, issues: [...new Set(issues)], notes: [...new Set(notes)] };
}
