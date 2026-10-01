"""Minimal glTF 2.0 binary writer/reader. Vertices are written VERBATIM in LPS mm.

No axis conversion is applied (glTF's nominal +Y-up is ignored on purpose); the viewer
treats +z as up. One mesh, one primitive, POSITION + optional NORMAL + optional custom
`_EDGE_ID` (float32 per vertex, nearest centerline edge).
"""
from __future__ import annotations

import json
import struct

import numpy as np

_FLOAT, _UINT = 5126, 5125
_ARRAY_BUFFER, _ELEMENT_ARRAY_BUFFER = 34962, 34963


def write_glb(path, vertices, faces, normals=None, edge_id=None, name="mesh", extras=None):
    v = np.ascontiguousarray(vertices, np.float32)
    f = np.ascontiguousarray(faces, np.uint32)
    chunks, views, accessors, attrs = [], [], [], {}
    offset = 0

    def add(arr, target, acc):
        nonlocal offset
        b = arr.tobytes()
        pad = (-len(b)) % 4
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(b), "target": target})
        acc["bufferView"] = len(views) - 1
        accessors.append(acc)
        chunks.append(b + b"\0" * pad)
        offset += len(b) + pad
        return len(accessors) - 1

    attrs["POSITION"] = add(v, _ARRAY_BUFFER, {"componentType": _FLOAT, "count": len(v), "type": "VEC3",
                                                "min": v.min(0).tolist(), "max": v.max(0).tolist()})
    if normals is not None:
        attrs["NORMAL"] = add(np.ascontiguousarray(normals, np.float32), _ARRAY_BUFFER,
                              {"componentType": _FLOAT, "count": len(v), "type": "VEC3"})
    if edge_id is not None:
        attrs["_EDGE_ID"] = add(np.ascontiguousarray(edge_id, np.float32), _ARRAY_BUFFER,
                                {"componentType": _FLOAT, "count": len(v), "type": "SCALAR"})
    ind = add(f.ravel(), _ELEMENT_ARRAY_BUFFER, {"componentType": _UINT, "count": f.size, "type": "SCALAR"})
    gltf = {
        "asset": {"version": "2.0", "generator": "cpt.glb (LPS mm, no axis conversion)"},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": name}],
        "meshes": [{"name": name, "primitives": [{"attributes": attrs, "indices": ind, "mode": 4}],
                    "extras": {"frame": "LPS", "units": "mm", **(extras or {})}}],
        "buffers": [{"byteLength": offset}], "bufferViews": views, "accessors": accessors,
    }
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * ((-len(js)) % 4)
    binb = b"".join(chunks)
    total = 12 + 8 + len(js) + 8 + len(binb)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, total))
        fh.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        fh.write(struct.pack("<II", len(binb), 0x004E4942) + binb)


def read_glb(path) -> dict:
    data = open(path, "rb").read()
    magic, ver, total = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67 and ver == 2 and total == len(data)
    jl, _ = struct.unpack_from("<II", data, 12)
    gltf = json.loads(data[20:20 + jl])
    bl, _ = struct.unpack_from("<II", data, 20 + jl)
    binb = data[28 + jl:28 + jl + bl]
    prim = gltf["meshes"][0]["primitives"][0]
    comps = {"SCALAR": 1, "VEC3": 3}

    def get(i):
        acc = gltf["accessors"][i]
        bv = gltf["bufferViews"][acc["bufferView"]]
        dt = np.float32 if acc["componentType"] == _FLOAT else np.uint32
        a = np.frombuffer(binb, dt, acc["count"] * comps[acc["type"]], bv["byteOffset"])
        return a.reshape(-1, comps[acc["type"]]) if comps[acc["type"]] > 1 else a

    out = {k: get(i) for k, i in prim["attributes"].items()}
    out["indices"] = get(prim["indices"]).reshape(-1, 3)
    out["extras"] = gltf["meshes"][0].get("extras", {})
    return out
