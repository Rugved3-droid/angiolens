// Branch labels assigned by hand in Label mode. No automatic naming anywhere: segments (LAD prox/mid/dist, ...)
// are DERIVED from these branch labels by fixed rules in segments.ts and need a separate human approval.
// Storage: localStorage (autosave) + export/import of labels.json; a labels.json placed in
// public/cases/<id>/ is loaded when nothing is stored locally.
import { type Edge, edgeSignature, type Tree } from "./caseData";

export const BRANCH_NAMES = [
  "LM", "LAD", "D1", "D2", "septal", "ramus", "LCx", "OM1", "OM2",
  "RCA", "conus", "RV marginal", "PDA", "PLB",
] as const;
export type BranchName = (typeof BRANCH_NAMES)[number];
/** kept for older imports: a label is a branch name */
export const LABEL_NAMES = BRANCH_NAMES;
export type LabelName = BranchName;

export const BRANCH_TREE: Record<BranchName, Tree> = {
  LM: "left", LAD: "left", D1: "left", D2: "left", septal: "left", ramus: "left", LCx: "left", OM1: "left", OM2: "left",
  RCA: "right", conus: "right", "RV marginal": "right", PDA: "right", PLB: "right",
};

export const LABEL_COLORS: Record<BranchName, string> = {
  LM: "#f0f0f0", LAD: "#4a9ae0", D1: "#17becf", D2: "#7fe0ea", septal: "#b3a2f0", ramus: "#bcbd22",
  LCx: "#2ca02c", OM1: "#a6e27a", OM2: "#d1f5b0",
  RCA: "#ff5c5c", conus: "#ff9896", "RV marginal": "#e377c2", PDA: "#ff7f0e", PLB: "#ffbb78",
};
const UNLABELED: Record<Tree, string[]> = {
  left: ["#6f86b5", "#8197c2", "#5d73a0"],
  right: ["#b57a6f", "#c28d81", "#a0665d"],
};
export const SELECT_COLOR = "#ffd400";
export const CULPRIT_COLOR = "#ff8c00";

export interface SegmentApproval {
  labels_hash: string;
  rca_rule: string;
  approved: string;
}

export interface LabelFile {
  case_id: string;
  version: 2;
  edges_signature: string;
  labels: Record<string, BranchName>;
  segments_approval?: SegmentApproval | null;
  updated: string;
}

export class LabelStore {
  labels = new Map<number, BranchName>();
  approval: SegmentApproval | null = null;
  stale = false;
  private readonly key: string;
  private readonly sig: string;

  constructor(readonly caseId: string, edges: Edge[]) {
    this.key = `cpt.labels.${caseId}`;
    this.sig = edgeSignature(edges);
  }

  async init(): Promise<string> {
    let raw: string | null = null;
    try {
      raw = localStorage.getItem(this.key);
    } catch {
      /* storage unavailable */
    }
    try {
      if (raw) return this.apply(JSON.parse(raw), "browser storage");
    } catch (e) {
      return `stored labels ignored: ${e}`;
    }
    try {
      const r = await fetch(`${import.meta.env.BASE_URL}cases/${this.caseId}/labels.json`);
      if (r.ok && r.headers.get("content-type")?.includes("json")) return this.apply(await r.json(), "labels.json");
    } catch {
      /* none */
    }
    return "no labels yet";
  }

  apply(f: LabelFile, from: string): string {
    if (f.case_id !== this.caseId) throw new Error(`labels are for ${f.case_id}, not ${this.caseId}`);
    if (f.version !== 2) throw new Error("labels file is version 1 (segment names); relabel with branch names");
    for (const v of Object.values(f.labels))
      if (!(BRANCH_NAMES as readonly string[]).includes(v)) throw new Error(`unknown branch name "${v}"`);
    this.stale = f.edges_signature !== this.sig;
    this.labels = new Map(Object.entries(f.labels).map(([k, v]) => [Number(k), v]));
    this.approval = f.segments_approval ?? null;
    return this.stale ? `${from}: WARNING centerline graph changed since labeling; check every label` : from;
  }

  set(edgeId: number, name: BranchName | null) {
    if (name) this.labels.set(edgeId, name);
    else this.labels.delete(edgeId);
    this.save();
  }

  /** Stable hash of the branch labels; an approval of derived segments is valid only for this hash. */
  labelsHash(): string {
    const s = [...this.labels].sort((a, b) => a[0] - b[0]).map(([k, v]) => `${k}=${v}`).join(";") + "|" + this.sig;
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
    return (h >>> 0).toString(16).padStart(8, "0");
  }

  approvalValid(rcaRule: string): boolean {
    return !!this.approval && this.approval.labels_hash === this.labelsHash() && this.approval.rca_rule === rcaRule;
  }

  approve(rcaRule: string | null) {
    this.approval = rcaRule === null ? null : { labels_hash: this.labelsHash(), rca_rule: rcaRule, approved: new Date().toISOString() };
    this.save();
  }

  toFile(): LabelFile {
    return {
      case_id: this.caseId,
      version: 2,
      edges_signature: this.sig,
      labels: Object.fromEntries([...this.labels].map(([k, v]) => [String(k), v])),
      segments_approval: this.approval,
      updated: new Date().toISOString(),
    };
  }

  save() {
    try {
      localStorage.setItem(this.key, JSON.stringify(this.toFile()));
    } catch {
      /* storage unavailable: export still works */
    }
  }

  name(e: Edge): string {
    return this.labels.get(e.id) ?? `unlabeled ${e.tree} #${e.id}`;
  }

  color(e: Edge): string {
    const l = this.labels.get(e.id);
    return l ? LABEL_COLORS[l] : UNLABELED[e.tree][e.id % 3];
  }
}
