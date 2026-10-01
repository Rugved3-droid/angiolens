"""Minimal reader for VTK XML PolyData (.vtp) with inline binary, optionally zlib-compressed.

Only what the ASOCA centerline files use: Points, PointData arrays, Lines.
"""
from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
import zlib

import numpy as np

_DT = {"Float32": "<f4", "Float64": "<f8", "Int32": "<i4", "Int64": "<i8",
       "UInt32": "<u4", "UInt64": "<u8", "UInt8": "<u1", "Int8": "<i1"}


def _b64len(nbytes: int) -> int:
    return 4 * ((nbytes + 2) // 3)


def _decode(text: str, dtype: str, header_type: str, compressed: bool) -> np.ndarray:
    text = "".join(text.split())
    hdt = np.dtype(_DT[header_type])
    if not compressed:
        raw = base64.b64decode(text)
        n = int(np.frombuffer(raw[:hdt.itemsize], hdt)[0])
        return np.frombuffer(raw[hdt.itemsize:hdt.itemsize + n], _DT[dtype]).copy()
    first = base64.b64decode(text[:_b64len(3 * hdt.itemsize)])
    nblocks = int(np.frombuffer(first[:hdt.itemsize], hdt)[0])
    hlen = (3 + nblocks) * hdt.itemsize
    h = np.frombuffer(base64.b64decode(text[:_b64len(hlen)])[:hlen], hdt)
    sizes = h[3:].astype(int)
    payload = base64.b64decode(text[_b64len(hlen):])
    out, pos = [], 0
    for s in sizes:
        out.append(zlib.decompress(payload[pos:pos + s]))
        pos += s
    return np.frombuffer(b"".join(out), _DT[dtype]).copy()


def read_vtp(path) -> dict:
    root = ET.parse(str(path)).getroot()
    if root.get("byte_order", "LittleEndian") != "LittleEndian":
        raise ValueError("big-endian VTP not supported")
    htype = root.get("header_type", "UInt32")
    comp = root.get("compressor") is not None
    piece = root.find("PolyData/Piece")

    def arr(el):
        if el.get("format") != "binary":
            raise ValueError(f"unsupported DataArray format {el.get('format')}")
        a = _decode(el.text or "", el.get("type"), htype, comp)
        nc = int(el.get("NumberOfComponents", "1"))
        return a.reshape(-1, nc) if nc > 1 else a

    points = arr(piece.find("Points/DataArray")).astype(float)
    point_data = {el.get("Name"): arr(el) for el in piece.findall("PointData/DataArray")}
    lines = piece.find("Lines")
    conn = arr(lines.find("DataArray[@Name='connectivity']")).astype(int)
    offs = arr(lines.find("DataArray[@Name='offsets']")).astype(int)
    starts = np.r_[0, offs[:-1]]
    cells = [conn[s:e] for s, e in zip(starts, offs)]
    return {"points": points, "point_data": point_data, "lines": cells}
