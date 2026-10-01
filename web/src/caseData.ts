// Loading per-case assets from public/cases/<id>/ (built by preprocess/scripts/build_case.py).
// All coordinates are LPS mm, verbatim; nothing is recentred or rotated here.
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import type { Vec3 } from "./geometry";

export type Tree = "left" | "right";

export interface Edge {
  id: number;
  tree: Tree;
  a: number;
  b: number;
  lengthMm: number;
  pts: Vec3[];
  radius: number[];
}

export interface GraphNode {
  id: number;
  kind: "ostium" | "bifurcation" | "endpoint";
  tree: Tree;
  pos: Vec3;
}

export interface CaseData {
  id: string;
  meta: any;
  isocenter: Vec3;
  detectorMm: number;
  nodes: GraphNode[];
  edges: Edge[];
  lumen: Record<Tree, THREE.BufferGeometry>;
  bone: THREE.BufferGeometry | null;
}

async function loadGeometry(url: string): Promise<THREE.BufferGeometry> {
  const gltf = await new GLTFLoader().loadAsync(url);
  let geom: THREE.BufferGeometry | null = null;
  gltf.scene.traverse((o) => {
    if ((o as THREE.Mesh).isMesh) {
      const m = o as THREE.Mesh;
      // loaders may attach node transforms; ours must be identity (verbatim LPS)
      m.updateMatrixWorld(true);
      if (!m.matrixWorld.equals(new THREE.Matrix4())) throw new Error(`${url}: non-identity node transform`);
      geom = m.geometry as THREE.BufferGeometry;
    }
  });
  if (!geom) throw new Error(`${url}: no mesh`);
  return geom;
}

export async function loadCase(id: string): Promise<CaseData> {
  const base = `${import.meta.env.BASE_URL}cases/${id}/`;
  const meta = await (await fetch(base + "case.json")).json();
  const cl = await (await fetch(base + "centerlines.json")).json();
  const files: string[] = meta.files ?? [];
  const [left, right, bone] = await Promise.all([
    loadGeometry(base + "lumen_left.glb"),
    loadGeometry(base + "lumen_right.glb"),
    files.includes("bone.glb") ? loadGeometry(base + "bone.glb") : Promise.resolve(null),
  ]);
  const edges: Edge[] = cl.edges.map((e: any) => ({
    id: e.id,
    tree: e.tree,
    a: e.a,
    b: e.b,
    lengthMm: e.length_mm,
    pts: e.samples.map((s: number[]) => [s[0], s[1], s[2]] as Vec3),
    radius: e.samples.map((s: number[]) => s[3]),
  }));
  return {
    id,
    meta,
    isocenter: meta.isocenter_lps_mm,
    detectorMm: meta.c_arm.detector_mm,
    nodes: cl.nodes,
    edges,
    lumen: { left, right },
    bone,
  };
}

/** Stable signature of the edge set so stale labels are detected after a rebuild. */
export function edgeSignature(edges: Edge[]): string {
  return edges
    .map((e) => `${e.id}:${e.tree}:${e.pts[0].map((x) => x.toFixed(1)).join(",")}>${e.pts[e.pts.length - 1].map((x) => x.toFixed(1)).join(",")}`)
    .join("|");
}
