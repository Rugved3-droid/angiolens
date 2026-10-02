"""Write assets/anatomy/CORONARY_REPORT.md from the Blender hierarchy dump (the source of truth).

    python preprocess/coronary_report.py assets/anatomy/inspect/hierarchy.json [assets/anatomy/manifest.json]

Nothing is inferred from shape or position: a vessel is reported present only if a named object exists in the
hierarchy. Branches modelled as extra splines INSIDE an object are counted but stay unnamed.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

EXPECTED = [  # (clinical name, Terminologia Anatomica English name as used by Z-Anatomy, if any)
    ("LCA / left main (LM)", "Left coronary artery"),
    ("LAD (anterior interventricular)", "Anterior interventricular artery"),
    ("Septal branches of LAD", "Septal branches of anterior interventricular artery"),
    ("Diagonal branches (D1, D2)", None),
    ("LCx (circumflex)", "Circumflex artery of heart"),
    ("Obtuse marginal branches (OM1, OM2)", None),
    ("Ramus intermedius", None),
    ("RCA", "Right coronary artery"),
    ("Right inferolateral / posterolateral branch", "Right inferolateral branch of right coronary artery"),
    ("PDA (posterior / inferior interventricular)", None),
    ("Conus branch", None),
    ("Acute marginal / RV marginal", None),
    ("SA nodal branch", None),
    ("AV nodal branch", None),
]
SEARCH = {
    "Diagonal branches (D1, D2)": ["diagonal"],
    "Obtuse marginal branches (OM1, OM2)": ["marginal", "obtuse"],
    "Ramus intermedius": ["intermedi", "ramus"],
    "PDA (posterior / inferior interventricular)": ["posterior interventricular", "inferior interventricular"],
    "Conus branch": ["conus", "conal"],
    "Acute marginal / RV marginal": ["right marginal", "acute marginal"],
    "SA nodal branch": ["sinu-atrial", "sinoatrial", "sinuatrial"],
    "AV nodal branch": ["atrioventricular nod"],
}


def main():
    H = json.loads(Path(sys.argv[1]).read_text())
    man = {}
    if len(sys.argv) > 2 and Path(sys.argv[2]).exists():
        man = {m["exported_node_name"]: m for m in json.loads(Path(sys.argv[2]).read_text())["objects"]}
    O = {o["name"]: o for o in H["objects"]}
    kids = defaultdict(list)
    for o in H["objects"]:
        if o["parent"]:
            kids[o["parent"]].append(o["name"])
    geo = lambda n: [k for k in kids[n] if O[k]["type"] != "FONT" and (O[k].get("evaluated_geometry") or {}).get("triangles")]
    lines = ["# Coronary report: Z-Anatomy Startup.blend", "",
             "Source of truth: the Blender hierarchy (`inspect/hierarchy.json`, every object type). Nothing is inferred from shape.",
             "Each coronary is a bevelled CURVE object; additional branches inside one object are separate *splines* (unnamed).", "",
             "| Clinical vessel | Z-Anatomy object | Type | Independent object | Parent | Child objects (named) | Splines in object | Control points | Triangles (evaluated) | Notes |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for clinical, obj in EXPECTED:
        if obj and obj in O:
            o = O[obj]
            c = o.get("curve") or {}
            sp = c.get("splines")
            notes = []
            if sp and sp > 1:
                notes.append(f"{sp - 1} additional unnamed branch spline(s) MERGED in this object (not separately selectable)")
            if obj == "Left coronary artery":
                notes.append("short stem (1 spline, 3 control points): proximal LM only; LAD and LCx are separate child objects")
            if obj in man:
                notes.append(f"exported as node '{obj}' ({man[obj]['triangle_count']} triangles, from evaluated curve)")
            lines.append(f"| {clinical} | {obj} | {o['type']} | yes | {o['parent']} | {', '.join(geo(obj)) or '-'} | {sp} | "
                         f"{c.get('control_points')} | {(o.get('evaluated_geometry') or {}).get('triangles')} | {'; '.join(notes)} |")
        else:
            terms = SEARCH.get(clinical, [])
            found = [n for n in O if O[n]["type"] in ("CURVE", "MESH") and (O[n].get("evaluated_geometry") or {}).get("triangles")
                     and any(t in n.lower() for t in terms) and ("heart" in json.dumps(O[n]["collections"]).lower() or "cardiovascular" in json.dumps(O[n]["collections"]).lower())
                     and any(a in (O[n]["parent"] or "") for a in ("coronary", "interventricular", "Circumflex", "Arteries of heart"))]
            lines.append(f"| {clinical} | **ABSENT** as a named object | - | - | - | - | - | - | - | searched names for {terms}; "
                         f"{'candidates: ' + ', '.join(found) if found else 'none under the coronary hierarchy'}. If present at all, only as an unnamed spline inside a parent object. NOT inferred. |")
    br = [m for m in man.values() if m.get("parent_vessel")]
    if br:
        lines += ["", "## Exported spline branches (child nodes; unnamed on purpose: label them in Label mode)", "",
                  "| Node | Parent vessel | Spline | Type | Length (mm) | Proximal end attaches to | Gap (mm) |", "|---|---|---|---|---|---|---|"]
        for m in sorted(br, key=lambda m: (m["parent_vessel"], m["spline_index"])):
            a = m.get("attachment") or {}
            lines.append(f"| {m['exported_node_name']} | {m['parent_vessel']} | {m['spline_index']} | {m['spline_type']} | {m['length_mm']} | "
                         f"{a.get('attached_to') or a.get('note', '-')} | {a.get('gap_mm', '-')} |")
    lines += ["", "## Cardiac veins (context; not used for the angiogram)", ""]
    for root in ("Cardiac veins.g",):
        for n in sorted(kids[root]):
            if O[n]["type"] == "CURVE":
                lines.append(f"- {n} (CURVE, {O[n]['curve']['splines']} splines); children: {', '.join(geo(n)) or '-'}")
    odd = [n for n in O if set(n) <= set("?.lr")]
    lines += ["", "## Anomalies", "",
              f"- Objects whose name is only question marks (non-ASCII name lost in the source file): {odd}. "
              "One of them is a CURVE child of the coronary sinus (a cardiac vein); its anatomical identity is unknown from the hierarchy and is NOT guessed.",
              "", "## Summary", "",
              "- Independently selectable named coronary objects: LCA (LM stem), LAD, LAD septal branches, LCx, RCA, right inferolateral branch.",
              "- Merged: side branches inside LAD, LCx and RCA objects are extra unnamed splines (counts above).",
              "- Absent as named objects: diagonals, obtuse marginals, ramus, PDA, conus, RV/acute marginal, SA/AV nodal branches.",
              "- Consequence for the trainer: segment derivation (LAD prox/mid/dist by D1/D2, LCx by OM1, RCA by the acute marginal) is NOT possible "
              "from names alone for this atlas; splitting the merged splines would need hand labeling, as for ASOCA."]
    out = Path(sys.argv[1]).parent.parent / "CORONARY_REPORT.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
