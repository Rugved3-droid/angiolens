"""Mean vertex colour (COLOR_0) per mesh, decoded from the GLB itself (v1.1 scouting).
    .venv\\Scripts\\python preprocess\\scripts\\scout_colors.py UID ...  -> updates inspect_<uid>.json "parts" with colour families
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scout_inspect import glb  # noqa: E402
from scout_parts import family  # noqa: E402

C = Path(__file__).resolve().parents[2] / "assets" / "candidates"
DT = {5126: np.float32, 5121: np.uint8, 5123: np.uint16}
NC = {"VEC3": 3, "VEC4": 4, "SCALAR": 1}


def read(js, b, ai):
    a = js["accessors"][ai]
    bv = js["bufferViews"][a["bufferView"]]
    n, k, dt = a["count"], NC[a["type"]], DT[a["componentType"]]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", 0) or k * np.dtype(dt).itemsize
    raw = np.frombuffer(b, dtype=np.uint8, count=stride * (n - 1) + k * np.dtype(dt).itemsize, offset=off)
    arr = np.lib.stride_tricks.as_strided(raw.view(dt) if stride % np.dtype(dt).itemsize == 0 else raw, shape=(n, k),
                                          strides=(stride, np.dtype(dt).itemsize))
    x = np.array(arr, dtype=np.float64)
    if dt == np.uint8:
        x /= 255.0
    elif dt == np.uint16:
        x /= 65535.0
    return x


for uid in sys.argv[1:]:
    js, b = glb(C / uid / "model.glb")
    fams = {}
    rows = []
    for mi, m in enumerate(js["meshes"]):
        cols, tri, P = [], 0, []
        for p in m["primitives"]:
            if "COLOR_0" in p["attributes"]:
                cols.append(read(js, b, p["attributes"]["COLOR_0"])[:, :3])
            P.append(read(js, b, p["attributes"]["POSITION"]))
            tri += (js["accessors"][p["indices"]]["count"] if "indices" in p else len(P[-1])) // 3
        col = np.vstack(cols).mean(0) if cols else None
        if col is not None and col.max() <= 1.0:
            col = col ** (1 / 2.2)                               # glTF vertex colours are linear: display-encode for the guess
        fam = family(col) if col is not None else "no colour"
        fams.setdefault(fam, [0, 0])
        fams[fam][0] += 1; fams[fam][1] += tri
        rows.append((m.get("name", f"mesh {mi}"), tri, None if col is None else col.round(2).tolist(), fam))
    f = C / "_scout" / f"inspect_{uid}.json"
    d = json.loads(f.read_text())
    d["colour_families"] = {k: {"meshes": v[0], "triangles": v[1]} for k, v in fams.items()}
    d["mesh_colours"] = rows
    f.write_text(json.dumps(d, indent=1))
    print(uid[:8], {k: tuple(v) for k, v in fams.items()})
    for r in sorted(rows, key=lambda r: -r[1])[:8]:
        print("    ", str(r[0])[:22].ljust(22), str(r[1]).rjust(8), r[2], r[3])
