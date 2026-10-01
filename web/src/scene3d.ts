// Right panel: the patient in LPS world coordinates (+z up), an observer camera that orbits
// independently of the C-arm, and the C-arm itself (source, detector, beam, ghost image, rays).
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { CaseData, Edge, Tree } from "./caseData";
import { add, type CArm, scale, type Vec3 } from "./geometry";
import { CULPRIT_COLOR, type LabelStore, SELECT_COLOR } from "./labels";
import type { Ray } from "./rays";

const v3 = (p: Vec3) => new THREE.Vector3(p[0], p[1], p[2]);

function textSprite(text: string, color: string, size = 14): THREE.Sprite {
  const c = document.createElement("canvas");
  c.width = text.length > 2 ? 512 : 128;
  c.height = 64;
  const g = c.getContext("2d")!;
  g.font = `bold ${text.length > 2 ? 34 : 40}px system-ui, sans-serif`;
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.lineWidth = 6;
  g.strokeStyle = "#000000";
  g.strokeText(text, c.width / 2, 32);
  g.fillStyle = color;
  g.fillText(text, c.width / 2, 32);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), depthTest: false }));
  s.scale.set(size * 2, size, 1);
  s.renderOrder = 10;
  return s;
}

export const EXTENSION_COLOR = "#c75cff";
export const SELF_COLOR = "#ff6fb1";

export interface Visibility {
  extension: boolean;
  coronaries: boolean;
  bone: boolean;
  beam: boolean;
  detector: boolean;
  ghost: boolean;
  rays: boolean;
  axes: boolean;
}

export class Scene3D {
  readonly scene = new THREE.Scene();
  readonly camera: THREE.PerspectiveCamera;
  readonly controls: OrbitControls;
  readonly lumen: Record<Tree, THREE.Mesh>;
  private readonly edgeIdAttr: Record<Tree, Float32Array>;
  /** per-vertex nearest sample index on the vertex's own edge (for colouring segments that end mid-edge) */
  private readonly sampleIdx: Record<Tree, Int32Array>;
  private readonly boundaryGroup = new THREE.Group();
  private readonly bone: THREE.Mesh | null;
  private readonly carmGroup = new THREE.Group();
  private readonly beamGroup = new THREE.Group();
  private readonly detector: THREE.Mesh;
  private readonly detectorFrame: THREE.LineLoop;
  private readonly ghost: THREE.Mesh;
  private readonly sourceMesh: THREE.Mesh;
  private readonly rayGroup = new THREE.Group();
  private readonly axes = new THREE.Group();
  /** non-expert layer: tinted translucent tube + dashed centerline, never mixed into the expert meshes */
  readonly extension: THREE.Group | null = null;
  private extensionTube: THREE.Mesh | null = null;
  vis: Visibility = { extension: false, coronaries: true, bone: true, beam: true, detector: true, ghost: true, rays: true, axes: true };

  constructor(dom: HTMLElement, readonly data: CaseData, ghostTexture: THREE.Texture) {
    const iso = v3(data.isocenter);
    this.scene.background = new THREE.Color(0x15181d);
    this.camera = new THREE.PerspectiveCamera(40, 1, 5, 5000);
    this.camera.up.set(0, 0, 1); // superior is up in the observer view
    this.controls = new OrbitControls(this.camera, dom);
    this.frame("patient");

    this.scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const key = new THREE.DirectionalLight(0xffffff, 1.6);
    this.camera.add(key);
    key.position.set(200, 300, 400);
    this.scene.add(this.camera);

    const lumenMat = () => new THREE.MeshPhongMaterial({ vertexColors: true, shininess: 40, transparent: true });
    const mkLumen = (tree: Tree) => {
      const g = data.lumen[tree].clone();
      if (!g.getAttribute("normal")) g.computeVertexNormals();
      const ids = g.getAttribute("_edge_id");
      if (!ids) throw new Error("lumen mesh lacks _EDGE_ID attribute");
      g.setAttribute("color", new THREE.BufferAttribute(new Float32Array(ids.count * 3), 3));
      const m = new THREE.Mesh(g, lumenMat());
      this.scene.add(m);
      return m;
    };
    this.lumen = { left: mkLumen("left"), right: mkLumen("right") };
    this.edgeIdAttr = {
      left: this.lumen.left.geometry.getAttribute("_edge_id").array as Float32Array,
      right: this.lumen.right.geometry.getAttribute("_edge_id").array as Float32Array,
    };
    const edgeById = new Map(data.edges.map((e) => [e.id, e]));
    const nearestIdx = (tree: Tree) => {
      const pos = this.lumen[tree].geometry.getAttribute("position");
      const ids = this.edgeIdAttr[tree];
      const out = new Int32Array(ids.length);
      for (let v = 0; v < ids.length; v++) {
        const e = edgeById.get(ids[v]);
        if (!e) continue;
        let best = 0, bd = Infinity;
        const x = pos.getX(v), y = pos.getY(v), z = pos.getZ(v);
        e.pts.forEach((p, i) => {
          const d = (p[0] - x) ** 2 + (p[1] - y) ** 2 + (p[2] - z) ** 2;
          if (d < bd) { bd = d; best = i; }
        });
        out[v] = best;
      }
      return out;
    };
    this.sampleIdx = { left: nearestIdx("left"), right: nearestIdx("right") };

    if (data.extension) {
      const g = new THREE.Group();
      this.extensionTube = new THREE.Mesh(data.extension.mesh, new THREE.MeshPhongMaterial({
        color: EXTENSION_COLOR, transparent: true, opacity: 0.45, depthWrite: false, shininess: 10,
      }));
      g.add(this.extensionTube);
      for (const e of data.extension.edges) {
        const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(e.pts.map(v3)),
          new THREE.LineDashedMaterial({ color: EXTENSION_COLOR, dashSize: 1.5, gapSize: 1.0, depthTest: false }));
        line.computeLineDistances();
        line.renderOrder = 5;
        g.add(line);
      }
      this.scene.add(g);
      (this as { extension: THREE.Group | null }).extension = g;
    }

    this.bone = data.bone
      ? new THREE.Mesh(data.bone, new THREE.MeshLambertMaterial({
          color: 0xd8cfb8, transparent: true, opacity: 0.22, depthWrite: false, side: THREE.DoubleSide,
        }))
      : null;
    if (this.bone) this.scene.add(this.bone);

    // C-arm parts; geometry is rebuilt from the pose in setCArm()
    this.sourceMesh = new THREE.Mesh(new THREE.SphereGeometry(10, 16, 12), new THREE.MeshBasicMaterial({ color: 0xffe066 }));
    this.detector = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshBasicMaterial({
      color: 0x8899aa, transparent: true, opacity: 0.12, side: THREE.DoubleSide, depthWrite: false,
    }));
    this.ghost = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshBasicMaterial({
      map: ghostTexture, transparent: true, opacity: 0.85, side: THREE.DoubleSide, depthWrite: false,
    }));
    this.detectorFrame = new THREE.LineLoop(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: 0x9fb4c8 }));
    this.carmGroup.add(this.sourceMesh, this.detector, this.ghost, this.detectorFrame, this.beamGroup);
    this.scene.add(this.carmGroup, this.rayGroup, this.axes, this.boundaryGroup);
    this.buildAxes(iso);
  }

  private buildAxes(iso: THREE.Vector3) {
    const L = 60;
    for (const [dir, name, color] of [
      [[1, 0, 0], "L", "#ff5c5c"],
      [[0, 1, 0], "P", "#5cdc5c"],
      [[0, 0, 1], "S", "#6aa8ff"],
    ] as [Vec3, string, string][]) {
      this.axes.add(new THREE.ArrowHelper(v3(dir), iso, L, new THREE.Color(color).getHex(), 10, 6));
      const s = textSprite(name, color);
      s.position.copy(iso).add(v3(scale(dir, L + 14)));
      this.axes.add(s);
    }
  }

  /** Move the observer (never the C-arm): "patient" = heart fills the view, "carm" = whole C-arm visible.
   *  Keeps the current viewing direction; the first call looks from anterior-left-superior. */
  frame(what: "patient" | "carm", carm?: CArm) {
    const iso = v3(this.data.isocenter);
    // look from beside the beam (screen-right side, slightly superior) so neither the
    // detector plate nor the source sits between the observer and the heart
    const dir = carm
      ? v3(add(carm.u, scale([0, 0, 1], 0.45))).normalize()
      : new THREE.Vector3(0.55, -0.75, 0.37).normalize();
    const radius = what === "patient" ? 110 : 650;
    const dist = radius / Math.sin(THREE.MathUtils.degToRad(this.camera.fov / 2));
    this.controls.target.copy(iso);
    this.camera.position.copy(iso).addScaledVector(dir, dist);
    this.controls.update();
  }

  setCArm(carm: CArm, detectorMm: number) {
    const h = detectorMm / 2;
    const D = carm.detectorCenter;
    // corners in (u,v) order: (-,-), (+,-), (+,+), (-,+); uv follows u right / v up exactly
    const corners = [[-h, -h], [h, -h], [h, h], [-h, h]].map(([x, y]) => add(D, add(scale(carm.u, x), scale(carm.v, y))));
    const uvs = [0, 0, 1, 0, 1, 1, 0, 1];
    const quad = new THREE.BufferGeometry();
    quad.setAttribute("position", new THREE.Float32BufferAttribute(corners.flat(), 3));
    quad.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
    quad.setIndex([0, 1, 2, 0, 2, 3]);
    this.detector.geometry.dispose();
    this.detector.geometry = quad;
    this.ghost.geometry.dispose();
    this.ghost.geometry = quad.clone();
    // ghost sits a hair in front of the plate (toward the patient) to avoid z-fighting
    this.ghost.position.copy(v3(scale(carm.d, -0.5)));
    this.detectorFrame.geometry.dispose();
    this.detectorFrame.geometry = new THREE.BufferGeometry().setFromPoints(corners.map(v3));
    this.sourceMesh.position.copy(v3(carm.source));

    this.beamGroup.clear();
    const S = v3(carm.source);
    const beamMat = new THREE.LineBasicMaterial({ color: 0xffe066, transparent: true, opacity: 0.35 });
    for (const c of corners) this.beamGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([S, v3(c)]), beamMat));
    this.beamGroup.add(new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([S, v3(D)]),
      new THREE.LineDashedMaterial({ color: 0xffe066, dashSize: 12, gapSize: 8 }),
    ));
    (this.beamGroup.children.at(-1) as THREE.Line).computeLineDistances();
  }

  setRays(carm: CArm, rays: Ray[]) {
    this.rayGroup.clear();
    const S = v3(carm.source);
    for (const r of rays) {
      const hit = !!r.overlap;
      const color = r.overlap === "inter" ? CULPRIT_COLOR : r.overlap === "self" ? SELF_COLOR : SELECT_COLOR;
      const pre = new THREE.Line(new THREE.BufferGeometry().setFromPoints([S, v3(r.p)]),
        new THREE.LineBasicMaterial({ color, transparent: true, opacity: hit ? 0.55 : 0.18 }));
      const post = new THREE.Line(new THREE.BufferGeometry().setFromPoints([v3(r.p), v3(r.q)]),
        new THREE.LineBasicMaterial({ color, transparent: true, opacity: hit ? 0.95 : 0.6 }));
      const dot = new THREE.Mesh(new THREE.SphereGeometry(hit ? 2.2 : 1.6, 8, 6), new THREE.MeshBasicMaterial({ color }));
      dot.position.copy(v3(r.q));
      this.rayGroup.add(pre, post, dot);
    }
  }

  /** Recolor lumen vertices from labels / selection / culprits; dim the uninjected tree. */
  recolor(labels: LabelStore, edges: Edge[], injected: Tree, selected: number | null, culprits: Set<number>,
          segColor?: (edgeId: number, idx: number) => string | null, selectedSeg?: (edgeId: number, idx: number) => boolean) {
    const colorOf = new Map<number, THREE.Color>();
    for (const e of edges) {
      const c = e.id === selected && !selectedSeg ? SELECT_COLOR : culprits.has(e.id) ? CULPRIT_COLOR : labels.color(e);
      colorOf.set(e.id, new THREE.Color(c));
    }
    for (const tree of ["left", "right"] as Tree[]) {
      const mesh = this.lumen[tree];
      const col = mesh.geometry.getAttribute("color") as THREE.BufferAttribute;
      const ids = this.edgeIdAttr[tree];
      const idx = this.sampleIdx[tree];
      const tmp = new THREE.Color();
      for (let i = 0; i < ids.length; i++) {
        let c = colorOf.get(ids[i]) ?? new THREE.Color(0x888888);
        if (segColor) {
          if (selectedSeg?.(ids[i], idx[i])) c = tmp.set(SELECT_COLOR);
          else if (!culprits.has(ids[i])) {
            const sc = segColor(ids[i], idx[i]);
            if (sc) c = tmp.set(sc);
          }
        }
        col.setXYZ(i, c.r, c.g, c.b);
      }
      col.needsUpdate = true;
      (mesh.material as THREE.MeshPhongMaterial).opacity = tree === injected ? 1 : 0.35;
      (mesh.material as THREE.MeshPhongMaterial).depthWrite = tree === injected;
    }
    if (this.extensionTube && this.data.extension) {
      const ids = this.data.extension.edges.map((e) => e.id);
      const mat = this.extensionTube.material as THREE.MeshPhongMaterial;
      const sel = selected !== null && ids.includes(selected);
      mat.color.set(sel ? SELECT_COLOR : ids.some((i) => culprits.has(i)) ? CULPRIT_COLOR : EXTENSION_COLOR);
      mat.opacity = injected === "right" ? (sel ? 0.8 : 0.45) : 0.2;
    }
  }

  /** White markers + names at derived-segment boundaries. */
  setBoundaries(list: { name: string; pos: Vec3 }[]) {
    this.boundaryGroup.clear();
    for (const b of list) {
      const m = new THREE.Mesh(new THREE.SphereGeometry(1.6, 12, 8), new THREE.MeshBasicMaterial({ color: 0xffffff, depthTest: false }));
      m.renderOrder = 6;
      m.position.copy(v3(b.pos));
      const s = textSprite(b.name, "#ffffff", 5);
      s.scale.set(28, 7, 1);
      s.position.copy(v3(b.pos)).add(new THREE.Vector3(0, 0, 6));
      this.boundaryGroup.add(m, s);
    }
  }

  applyVisibility() {
    this.lumen.left.visible = this.lumen.right.visible = this.vis.coronaries;
    if (this.extension) this.extension.visible = this.vis.coronaries && this.vis.extension;
    if (this.bone) this.bone.visible = this.vis.bone;
    this.beamGroup.visible = this.vis.beam;
    this.detector.visible = this.detectorFrame.visible = this.vis.detector;
    this.ghost.visible = this.vis.ghost;
    this.rayGroup.visible = this.vis.rays;
    this.axes.visible = this.vis.axes;
  }

  /** Edge id under a pointer position (NDC within the right viewport), via the lumen surfaces. */
  pick(ndc: THREE.Vector2, trees: Tree[]): THREE.Vector3 | null {
    const rc = new THREE.Raycaster();
    rc.setFromCamera(ndc, this.camera);
    const targets: THREE.Object3D[] = trees.map((t) => this.lumen[t]).filter((m) => m.visible);
    if (this.extensionTube && this.extension?.visible && trees.includes("right")) targets.push(this.extensionTube);
    const hits = rc.intersectObjects(targets, false);
    return hits.length ? hits[0].point : null;
  }

  render(r: THREE.WebGLRenderer) {
    this.controls.update();
    r.render(this.scene, this.camera);
  }
}
