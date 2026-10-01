// Phase 2 panel: live metrics for the selected segment + angle-space heatmaps (worker-computed).
// All numbers come from geometry (metrics.ts); nothing here reads the rendered angiogram.
import type { Edge, GraphNode } from "./caseData";
import type { CArm, Vec3 } from "./geometry";
import { Heatmap } from "./heatmap";
import type { LabelStore } from "./labels";
import { type AngleMaps, argminCost, combinedCost, packSamples, type Samples, type ViewMetrics, viewMetrics } from "./metrics";

export interface Target {
  key: string;
  name: string;
  edges: Edge[];
  samples: Samples;
  pts: Vec3[];
  bif: Vec3[];
  note: string;
}

/**
 * The metric target for a selected edge: if the edge carries a label, all contiguous edges with the same label
 * forming a simple path (e.g. "LAD mid" spanning 2 edges); otherwise the edge alone.
 */
export function buildTarget(sel: Edge, edges: Edge[], nodes: GraphNode[], labels: LabelStore): Target {
  const name = labels.labels.get(sel.id);
  let chain = [sel];
  let note = "";
  if (name) {
    const group = edges.filter((e) => e.tree === sel.tree && labels.labels.get(e.id) === name);
    // grow a path from sel in both directions through nodes shared with exactly one other group edge
    const used = new Set([sel.id]);
    const extend = (end: number, atStart: boolean) => {
      for (;;) {
        const next = group.filter((e) => !used.has(e.id) && (e.a === end || e.b === end));
        if (next.length !== 1) return;
        const e = next[0];
        used.add(e.id);
        if (atStart) chain = [e, ...chain];
        else chain = [...chain, e];
        end = e.a === end ? e.b : e.a;
      }
    };
    extend(sel.b, false);
    extend(sel.a, true);
    if (used.size < group.length) note = `"${name}" is not one simple path; using the ${chain.length} connected edge(s)`;
  }
  // orient every edge so the chain runs continuously
  const pts: Vec3[] = [];
  const rad: number[] = [];
  let prevEnd: number | null = null;
  for (const e of chain) {
    const fwd: boolean = prevEnd === null ? (chain.length === 1 || e.b === chain[1]?.a || e.b === chain[1]?.b) : e.a === prevEnd;
    const P = fwd ? e.pts : [...e.pts].reverse();
    const R = fwd ? e.radius : [...e.radius].reverse();
    const skip = pts.length ? 1 : 0;
    pts.push(...P.slice(skip));
    rad.push(...R.slice(skip));
    prevEnd = fwd ? e.b : e.a;
  }
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const bif = [...new Set(chain.flatMap((e) => [e.a, e.b]))]
    .map((id) => byId.get(id))
    .filter((n) => n && n.kind === "bifurcation")
    .map((n) => n!.pos);
  return {
    key: chain.map((e) => e.id).join("-"),
    name: name ?? labels.name(sel),
    edges: chain,
    samples: packSamples(pts, rad),
    pts,
    bif,
    note,
  };
}

export class MetricsPanel {
  live: { target: Target; m: ViewMetrics } | null = null;
  private maps: AngleMaps | null = null;
  private mapsKey = "";
  private pending = "";
  private readonly worker = new Worker(new URL("./metricsWorker.ts", import.meta.url), { type: "module" });
  private readonly hm: Record<"F" | "O_inter" | "O_self" | "cost", Heatmap>;
  weights = { wF: 1, wO: 1 };
  /** false = per-map scaling with floors (F and O >= 20%, cost >= 20% of wF + wO); true = fixed full range */
  fixedScale = false;
  showOptimum = true;
  private pose: [number, number] = [0, 0];

  constructor(private readonly iso: Vec3, onPick: (a: number, b: number) => void, private readonly onMaps: () => void) {
    const pct = (v: number) => `${(100 * v).toFixed(0)}%`;
    const fixed = () => this.fixedScale;
    const frac = { vmax: () => 1, floor: () => 0.2, fixed, format: pct, onPick };
    this.hm = {
      F: new Heatmap(document.getElementById("hm-F")!, { title: "Foreshortening", ...frac }),
      O_inter: new Heatmap(document.getElementById("hm-inter")!, { title: "Inter-vessel overlap", ...frac }),
      O_self: new Heatmap(document.getElementById("hm-self")!, { title: "Self-overlap", ...frac }),
      cost: new Heatmap(document.getElementById("hm-cost")!, {
        title: "Combined cost (lower is better)", vmax: () => this.weights.wF + this.weights.wO,
        floor: () => 0.2 * (this.weights.wF + this.weights.wO), fixed, format: (v) => v.toFixed(2), onPick,
      }),
    };
    this.worker.onmessage = (ev) => {
      const d = ev.data;
      if (d.key !== this.pending) return;
      if (d.progress !== undefined) {
        for (const h of Object.values(this.hm)) h.setData([], [], null, `computing ${(100 * d.progress).toFixed(0)}%`);
        return;
      }
      this.maps = d.maps;
      this.mapsKey = d.key;
      this.redrawMaps();
      this.onMaps();
    };
    window.addEventListener("resize", () => this.redrawMaps());
  }

  /** Recompute live metrics; request maps when the target or its context changes. */
  update(carm: CArm, target: Target | null, others: Edge[], contextKey: string) {
    this.pose = [carm.alphaDeg, carm.betaDeg];
    if (!target) {
      this.live = null;
      this.maps = null;
      this.pending = this.mapsKey = "";
      for (const h of Object.values(this.hm)) h.setData([], [], null, "select a segment");
      return;
    }
    const otherSamples = others.map((e) => packSamples(e.pts, e.radius));
    this.live = { target, m: viewMetrics(carm, target.samples, target.bif, otherSamples) };
    const key = `${target.key}|${contextKey}`;
    if (key !== this.mapsKey && key !== this.pending) {
      this.pending = key;
      this.maps = null;
      this.worker.postMessage({ key, iso: this.iso, target: target.samples, bif: target.bif, others: otherSamples, step: 2 });
    }
    for (const h of Object.values(this.hm)) h.setPose(...this.pose);
  }

  /** current colour-scale tops, for tests */
  scales() {
    return Object.fromEntries(Object.entries(this.hm).map(([k, h]) => [k, h.scaleMax()]));
  }

  cost(m: ViewMetrics) {
    return combinedCost(m.F, m.O_any, this.weights.wF, this.weights.wO);
  }

  optimum() {
    return this.maps ? argminCost(this.maps, this.weights.wF, this.weights.wO) : null;
  }

  redrawMaps() {
    const m = this.maps;
    if (!m) return;
    const cost = new Float32Array(m.F.length);
    for (let k = 0; k < cost.length; k++) cost[k] = combinedCost(m.F[k], m.O_any[k], this.weights.wF, this.weights.wO);
    this.hm.F.setData(m.alpha, m.beta, m.F);
    this.hm.O_inter.setData(m.alpha, m.beta, m.O_inter);
    this.hm.O_self.setData(m.alpha, m.beta, m.O_self);
    this.hm.cost.setData(m.alpha, m.beta, cost);
    const o = this.optimum();
    this.hm.cost.setOptimum(this.showOptimum && o ? [o.alpha, o.beta] : null);
    for (const h of Object.values(this.hm)) h.setPose(...this.pose);
  }
}
