"""Scouting detail for the downloaded candidates (v1.1 item 4; report only): reads each model.glb's own glTF JSON and images.

    .venv\\Scripts\\python preprocess\\scripts\\scout_inspect.py UID ...   -> assets/candidates/_scout/inspect_<uid>.json
"""
import io
import json
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

C = Path(__file__).resolve().parents[2] / "assets" / "candidates"


def glb(path):
    data = path.read_bytes()
    assert struct.unpack_from("<I", data, 0)[0] == 0x46546C67
    off, js, binc = 12, None, None
    while off < len(data):
        n, typ = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + n]
        if typ == 0x4E4F534A:
            js = json.loads(chunk)
        elif typ == 0x004E4942:
            binc = chunk
        off += 8 + n
    return js, binc


def main(uids):
    for uid in uids:
        p = C / uid / "model.glb"
        js, binc = glb(p)
        acc = js.get("accessors", [])
        meshes = []
        for mi, m in enumerate(js.get("meshes", [])):
            tri = 0
            mats = set()
            for pr in m["primitives"]:
                if "indices" in pr:
                    tri += acc[pr["indices"]]["count"] // 3
                else:
                    tri += acc[pr["attributes"]["POSITION"]]["count"] // 3
                if "material" in pr:
                    mats.add(js["materials"][pr["material"]].get("name", f"material {pr['material']}"))
            meshes.append({"mesh": m.get("name", f"mesh {mi}"), "primitives": len(m["primitives"]), "triangles": tri, "materials": sorted(mats)})
        nodes = [n.get("name", "") for n in js.get("nodes", []) if "mesh" in n]
        imgs = []
        for ii, im in enumerate(js.get("images", [])):
            bv = js["bufferViews"][im["bufferView"]] if "bufferView" in im else None
            size = None
            if bv is not None:
                raw = binc[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]]
                try:
                    size = Image.open(io.BytesIO(raw)).size
                except Exception:
                    size = None
            imgs.append({"image": im.get("name", f"image {ii}"), "mime": im.get("mimeType"), "size": size,
                         "bytes": bv["byteLength"] if bv else None})
        mats = []
        for m in js.get("materials", []):
            pbr = m.get("pbrMetallicRoughness", {})
            slots = [k for k in ("baseColorTexture", "metallicRoughnessTexture") if k in pbr]
            slots += [k for k in ("normalTexture", "occlusionTexture", "emissiveTexture") if k in m]
            mats.append({"material": m.get("name", ""), "maps": slots})
        out = {"uid": uid, "file_MB": round(p.stat().st_size / 1e6, 1), "triangles_total": sum(x["triangles"] for x in meshes),
               "mesh_count": len(meshes), "node_names": nodes[:60], "meshes": meshes[:60], "materials": mats, "images": imgs,
               "extensions_used": js.get("extensionsUsed", []), "generator": js.get("asset", {}).get("generator")}
        (C / "_scout" / f"inspect_{uid}.json").write_text(json.dumps(out, indent=1))
        print(json.dumps({k: out[k] for k in ("uid", "file_MB", "triangles_total", "mesh_count", "generator")}))
        print("   nodes:", nodes[:20])
        print("   materials:", [(m["material"], m["maps"]) for m in mats][:12])
        print("   images:", [(i["image"], i["size"]) for i in imgs][:12])


if __name__ == "__main__":
    main(sys.argv[1:])
