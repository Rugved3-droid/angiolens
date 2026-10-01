"""Centerline graph: nodes at ostia, bifurcations and endpoints; edges resampled every 0.5 mm with radius.

Primary source: the official ASOCA centerlines (ostium->endpoint paths sharing their proximal
course). Their file frame differs from the CT header by a pure translation derived from the
header (see `official_to_lps`), validated by lumen containment in `validate_in_lumen`.
Fallback: skeletonization of the lumen (skan), ostium = endpoint nearest the blood pool.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

from .volume import Volume
from .vtp import read_vtp

STEP_MM = 0.5
MERGE_TOL_MM = 1.0


@dataclass
class Graph:
    nodes: list = field(default_factory=list)   # {id, kind, pos, tree}
    edges: list = field(default_factory=list)   # {id, tree, a, b, samples (N,4) x,y,z,r}
    source: str = ""

    def add_node(self, kind, pos, tree):
        self.nodes.append({"id": len(self.nodes), "kind": kind, "pos": np.asarray(pos, float), "tree": tree})
        return self.nodes[-1]["id"]

    def add_edge(self, tree, a, b, samples):
        self.edges.append({"id": len(self.edges), "tree": tree, "a": a, "b": b,
                           "samples": np.asarray(samples, float)})
        return self.edges[-1]["id"]

    def to_json(self) -> dict:
        def L(s):
            return float(np.linalg.norm(np.diff(s[:, :3], axis=0), axis=1).sum())
        return {
            "source": self.source, "step_mm": STEP_MM,
            "nodes": [{"id": n["id"], "kind": n["kind"], "tree": n["tree"],
                       "pos": np.round(n["pos"], 3).tolist()} for n in self.nodes],
            "edges": [{"id": e["id"], "tree": e["tree"], "a": e["a"], "b": e["b"],
                       "length_mm": round(L(e["samples"]), 2),
                       "samples": np.round(e["samples"], 3).tolist()} for e in self.edges],
        }


def resample(poly: np.ndarray, step: float = STEP_MM) -> np.ndarray:
    """Resample (N, 3+k) polyline at uniform arc length; endpoints kept exactly."""
    seg = np.linalg.norm(np.diff(poly[:, :3], axis=0), axis=1)
    s = np.r_[0, np.cumsum(seg)]
    if s[-1] == 0:
        return poly[:1].copy()
    n = max(int(np.ceil(s[-1] / step)), 1)
    t = np.linspace(0, s[-1], n + 1)
    return np.stack([np.interp(t, s, poly[:, j]) for j in range(poly.shape[1])], 1)


def official_to_lps(points: np.ndarray, ct: Volume) -> np.ndarray:
    """ASOCA centerline file frame -> CT LPS: p = P + (2*ox, 2*oy, 0).

    The file was written with the origin's x/y signs in RAS but the axes left in LPS (a common
    VTK image-import artifact), i.e. P = p - 2*(ox, oy, 0). Pure translation, no rotation.
    """
    o = ct.affine[:3, 3]
    return points + np.array([2 * o[0], 2 * o[1], 0.0])


def validate_in_lumen(points: np.ndarray, ct: Volume, lumen: np.ndarray) -> dict:
    dist_out = ndi.distance_transform_edt(~lumen, sampling=ct.spacing)
    d = ndi.map_coordinates(dist_out, ct.lps_to_index(points).T, order=1, cval=99.0)
    return {"mean_mm": float(d.mean()), "max_mm": float(d.max()), "frac_within_0p5mm": float((d <= 0.5).mean())}


def build_from_paths(paths: list[np.ndarray], trees: list[str]) -> Graph:
    """Merge ostium->endpoint paths (each (N,4): x,y,z,r) that share proximal segments into a tree graph."""
    g = Graph()
    by_tree: dict[str, list] = {}
    for p, t in zip(paths, trees):
        by_tree.setdefault(t, []).append(resample(p))
    for tree, ps in by_tree.items():
        ps = sorted(ps, key=lambda p: -len(p))         # longest first
        ost = g.add_node("ostium", ps[0][0, :3], tree)
        end = g.add_node("endpoint", ps[0][-1, :3], tree)
        g.add_edge(tree, ost, end, ps[0])
        for p in ps[1:]:
            pts = np.vstack([e["samples"][:, :3] for e in g.edges if e["tree"] == tree])
            d, _ = cKDTree(pts).query(p[:, :3])
            far = np.flatnonzero(d > MERGE_TOL_MM)
            if len(far) == 0:
                continue                                 # path fully contained in the tree
            dep = max(far[0] - 1, 0)                     # last shared sample
            node = _split_at(g, tree, p[dep, :3])
            tail = np.vstack([np.r_[g.nodes[node]["pos"], p[dep, 3]], p[dep + 1:]])
            e = g.add_node("endpoint", p[-1, :3], tree)
            g.add_edge(tree, node, e, resample(tail))
    return g


def _split_at(g: Graph, tree: str, pos: np.ndarray) -> int:
    """Return a node at the tree sample nearest `pos`, splitting an edge there if needed."""
    best = None
    for e in g.edges:
        if e["tree"] != tree:
            continue
        d = np.linalg.norm(e["samples"][:, :3] - pos, axis=1)
        i = int(d.argmin())
        if best is None or d[i] < best[0]:
            best = (d[i], e, i)
    _, e, i = best
    s = e["samples"]
    if i == 0:
        return e["a"]
    if i == len(s) - 1:
        return e["b"]
    for n in g.nodes:      # reuse an existing bifurcation within half a step
        if n["tree"] == tree and n["kind"] == "bifurcation" and np.linalg.norm(n["pos"] - s[i, :3]) < STEP_MM / 2:
            return n["id"]
    nid = g.add_node("bifurcation", s[i, :3], tree)
    old_b = e["b"]
    e["samples"], tail = s[: i + 1], s[i:]
    e["b"] = nid
    g.add_edge(tree, nid, old_b, tail)
    return nid


def official_graph(vtp_path, ct: Volume, left: np.ndarray, right: np.ndarray) -> tuple[Graph, dict]:
    v = read_vtp(vtp_path)
    P = official_to_lps(v["points"], ct)
    R = v["point_data"]["MaximumInscribedSphereRadius"]
    lumen = left | right
    check = validate_in_lumen(P, ct, lumen)
    paths, trees, info = [], [], []
    for k, cell in enumerate(v["lines"]):
        ijk = np.rint(ct.lps_to_index(P[cell[0]])[0]).astype(int)
        nb = tuple(slice(max(a - 2, 0), a + 3) for a in ijk)
        tree = "left" if left[nb].any() else "right" if right[nb].any() else None
        if tree is None:
            raise ValueError(f"official path {k} does not start inside either tree")
        q = np.c_[P[cell], R[cell]]
        paths.append(q)
        trees.append(tree)
        info.append({"path": k, "tree": tree, "length_mm": round(float(np.linalg.norm(np.diff(q[:, :3], axis=0), axis=1).sum()), 1),
                     "start_lps": q[0, :3].round(1).tolist(), "end_lps": q[-1, :3].round(1).tolist(),
                     "end_radius_mm": round(float(q[-1, 3]), 2)})
    g = build_from_paths(paths, trees)
    g.source = "official ASOCA centerlines (header-derived translation)"
    return g, {"frame_check": check, "paths": info}


def skeleton_graph(ct: Volume, left: np.ndarray, right: np.ndarray, pool: np.ndarray) -> Graph:
    """Fallback: skeletonize each tree; ostium = skeleton endpoint nearest the blood pool."""
    from skan import Skeleton
    from skimage.morphology import skeletonize

    pool_dist = ndi.distance_transform_edt(~pool, sampling=ct.spacing)
    paths, trees = [], []
    for tree, m in (("left", left), ("right", right)):
        sk = Skeleton(skeletonize(m), spacing=1)
        dist_in = ndi.distance_transform_edt(m, sampling=ct.spacing)
        coords = [sk.path_coordinates(i) for i in range(sk.n_paths)]
        ends = [c[j] for c in coords for j in (0, -1)]
        ost = min(ends, key=lambda c: pool_dist[tuple(np.rint(c).astype(int))])
        # ostium->endpoint paths via shortest paths in the skeleton pixel graph
        import networkx as nx
        G = nx.Graph()
        for c in coords:
            for a, b in zip(c[:-1], c[1:]):
                G.add_edge(tuple(a), tuple(b), w=float(np.linalg.norm((a - b) * ct.spacing)))
        deg = dict(G.degree())
        src = tuple(ost)
        for node, dg in deg.items():
            if dg == 1 and node != src:
                idx = np.array(nx.shortest_path(G, src, node, weight="w"))
                r = dist_in[tuple(np.rint(idx).astype(int).T)]
                paths.append(np.c_[ct.index_to_lps(idx), r])
                trees.append(tree)
    g = build_from_paths(paths, trees)
    g.source = "skeleton (skan) fallback"
    return g
