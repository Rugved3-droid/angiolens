// Vessel labels assigned by hand in Label mode. No automatic naming anywhere.
// Storage: localStorage (autosave) + export/import of labels.json; a labels.json placed in
// public/cases/<id>/ is loaded when nothing is stored locally.
import { type Edge, edgeSignature, type Tree } from "./caseData";

export const LABEL_NAMES = [
  "LM", "LAD prox", "LAD mid", "LAD dist", "D1", "D2", "septal", "ramus",
  "LCx prox", "LCx dist", "OM1", "OM2",
  "RCA prox", "RCA mid", "RCA dist", "conus", "RV marginal", "PDA", "PLB",
] as const;
export type LabelName = (typeof LABEL_NAMES)[number];

export const LABEL_COLORS: Record<LabelName, string> = {
  LM: "#f0f0f0",
  "LAD prox": "#1f6fd1", "LAD mid": "#4a9ae0", "LAD dist": "#8cc4f5",
  D1: "#17becf", D2: "#7fe0ea", septal: "#b3a2f0", ramus: "#bcbd22",
  "LCx prox": "#2ca02c", "LCx dist": "#6fcf6f", OM1: "#a6e27a", OM2: "#d1f5b0",
  "RCA prox": "#d62728", "RCA mid": "#ff5c5c", "RCA dist": "#ff9e9e",
  conus: "#ff9896", "RV marginal": "#e377c2", PDA: "#ff7f0e", PLB: "#ffbb78",
};
const UNLABELED: Record<Tree, string[]> = {
  left: ["#6f86b5", "#8197c2", "#5d73a0"],
  right: ["#b57a6f", "#c28d81", "#a0665d"],
};
export const SELECT_COLOR = "#ffd400";
export const CULPRIT_COLOR = "#ff8c00";

export interface LabelFile {
  case_id: string;
  version: 1;
  edges_signature: string;
  labels: Record<string, LabelName>;
  updated: string;
}

export class LabelStore {
  labels = new Map<number, LabelName>();
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
    if (raw) return this.apply(JSON.parse(raw), "browser storage");
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
    this.stale = f.edges_signature !== this.sig;
    this.labels = new Map(Object.entries(f.labels).map(([k, v]) => [Number(k), v]));
    return this.stale ? `${from}: WARNING centerline graph changed since labeling; check every label` : from;
  }

  set(edgeId: number, name: LabelName | null) {
    if (name) this.labels.set(edgeId, name);
    else this.labels.delete(edgeId);
    this.save();
  }

  toFile(): LabelFile {
    return {
      case_id: this.caseId,
      version: 1,
      edges_signature: this.sig,
      labels: Object.fromEntries([...this.labels].map(([k, v]) => [String(k), v])),
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
