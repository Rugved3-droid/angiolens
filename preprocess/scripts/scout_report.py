"""Writes assets/candidates/SCOUTING.md (v1.1 item 4; report only) from the scouting data in assets/candidates/_scout/.
    .venv\\Scripts\\python preprocess\\scripts\\scout_report.py
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
C = ROOT / "assets" / "candidates"
S = C / "_scout"
REV = ROOT / "out" / "review" / "scouting"

# the ten most realistic of the shortlist, ranked by looking at the large thumbnails (contact_sheet.png numbers in brackets)
TOP10 = [
    (23, "photo-real sculpt; superficial vessels sculpted in relief", "sculpted relief (fused)"),
    (1, "photo-real texture (wet, glossy); the best surface look", "painted in the texture"),
    (3, "clean anatomical illustration; arteries red, veins blue", "separate coloured geometry (see inspection)"),
    (6, "the same model as #1 under another account and licence", "painted in the texture"),
    (22, "anatomical; coronaries drawn as red tubes on the surface", "red tubes (likely separate)"),
    (7, "anatomical, ivory/brown; a teaching series (Groningen)", "not visible on the thumbnail"),
    (11, "Dundee coronary-artery view (same series as #3)", "coloured geometry"),
    (18, "textured, saturated red; moderately realistic", "painted"),
    (15, "glossy, pink-red; stylised lighting", "painted"),
    (12, "heart with lungs (Groningen series)", "not visible"),
]
TOP3 = ["2edbedffae6b49ee97f919a8528329ba", "3f8072336ce94d18b3d0d055a1ece089", "a3f0ea2030214a6bbaa97e7357eebd58"]


def main():
    sj = json.loads((S / "search.json").read_text())
    sl = sj["shortlist"]
    REV.mkdir(parents=True, exist_ok=True)
    shutil.copy(S / "contact_sheet.png", C / "SCOUTING_contact_sheet.png")
    lines = [
        "# Photoreal heart scouting (v1.1 item 4): report only, nothing integrated",
        "",
        f"Date: {sj['date']}. Source: the official Sketchfab Data API v3 only (`/v3/search?type=models&downloadable=true`,",
        "`/v3/models/{uid}/download`); no HTML scraping, no login bypass, at most one call per 1.1 s. Downloads used the",
        "`SKETCHFAB_TOKEN` environment variable; it was never printed, stored or committed. Script:",
        "`preprocess/scripts/sketchfab_scout.py` (+ `scout_inspect.py`, `scout_parts.py`, `scout_colors.py`, `e2e/scout_render.mjs`).",
        "",
        "## Search",
        f"- Queries: {', '.join(repr(q) for q in sj['queries'])}; each sorted by likes and by views (24 per query and sort).",
        f"- {sj['unique']} unique models. Filters: licence in {{CC BY, CC BY-SA, CC BY-NC, CC BY-NC-SA, CC0}}; not age-restricted;",
        "  the name or a tag names the heart; no stylized / cartoon / low-poly / game / icon / emoji words.",
        f"  {sj.get('filters_pass', '?')} passed; the 30 most popular were kept with their largest thumbnails.",
        "- Contact sheet of those 30: `SCOUTING_contact_sheet.png` (numbers below refer to it).",
        "- Removed by eye after the keyword filter: a steampunk sculpture (#2), a whole-body angiology model (#4), a silver",
        "  ZBrush sculpt (#5), an untextured white sculpt (#9), a wireframe-look heart (#10), full skeletons (#16, #20), a thorax",
        "  (#17), echo-plane cut models (#14, #21, #24, #25, #27-#29) and a conduction-system model (#30).",
        "",
        "## The ten most realistic (ranked by eye on the thumbnails: photorealism, then visible coronaries)",
        "",
        "| Rank | # | Title | Author | Licence | Likes | Triangles | Look | Coronaries (thumbnail) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for rank, (n, look, cor) in enumerate(TOP10, 1):
        m = sl[n - 1]
        lic = m["license"].replace("CC Attribution", "CC BY").replace("-NonCommercial", "-NC").replace("-ShareAlike", "-SA")
        title = m["name"].replace("|", "/")                      # a "|" would break the table
        lines.append(f"| {rank} | {n} | [{title}]({m['url']}) | {m['author']} | {lic} | {m['likes']} | {m['faces']:,} | {look} | {cor} |")
    lines += ["", "## The top 3: downloaded and inspected", "",
              "Each is in `assets/candidates/<uid>/` (git-ignored) with `LICENSE.txt` (title, author, URL, licence and URL,",
              "attribution, date). `inspect_heart_model.py` reports are in `out/review/scouting/<uid>/`; the glTF details below",
              "come from each file's own JSON (`_scout/inspect_<uid>.json`).", ""]
    notes = {
        "2edbedffae6b49ee97f919a8528329ba": [
            "Parts: ONE fused surface. The 20 meshes are buffer-size chunks (~100 k triangles each, all spanning most of the heart), not anatomical parts; no chambers, appendages, aorta or PA as separate objects; no fat layer.",
            "Coronaries: SCULPTED RELIEF fused into the surface (visible as raised vessels in the render), not separate geometry; no colour difference (one muscle-tone vertex colour everywhere).",
            "Textures: none; colour is per-vertex (COLOR_0), one material.",
        ],
        "3f8072336ce94d18b3d0d055a1ece089": [
            "Parts: ONE mesh (ZBrush export, 22.6 k triangles). Nothing is separate.",
            "Coronaries: PAINTED in the texture (with normal-map relief); no vessel geometry.",
            "Textures: base colour, metal/roughness and normal, each 1024 x 1024. The most photoreal surface of the three.",
            "Note: the same model is listed again as #6 'heart' under CC BY-NC by another account; the CC BY original was taken.",
        ],
        "a3f0ea2030214a6bbaa97e7357eebd58": [
            "Parts: 41 meshes, but with generic names (Object_N) and buffer-size chunks (~120 k triangles); colour groups are separate meshes: muscle-tone 24 meshes (1.77 M triangles), red 9 (0.62 M: aorta and coronary arteries), blue 4 (0.38 M: veins), neutral 4 (0.24 M).",
            "Coronaries: SEPARATE COLOURED GEOMETRY (red meshes distinct from the muscle), but the aorta and the arteries share the red meshes; branch-level separation would need splitting by connectivity. Chambers / appendages / PA are not named; no fat layer.",
            "Textures: none (per-vertex colour, one grey material). Very heavy: 3.0 M triangles, 121 MB.",
            "Licence: CC BY-NC-SA (non-commercial, share-alike).",
        ],
    }
    for uid in TOP3:
        d = json.loads((S / f"inspect_{uid}.json").read_text())
        m = next(x for x in sl if x["uid"] == uid)
        lic = (C / uid / "LICENSE.txt").read_text().splitlines()[3].replace("License: ", "")
        imgs = ", ".join(f"{i['size'][0]}x{i['size'][1]}" for i in d["images"] if i["size"]) or "none"
        lines += [f"### [{m['name']}]({m['url']}) ({m['author']}), {lic}", "",
                  f"- File: {d['file_MB']} MB GLB; {d['triangles_total']:,} triangles in {d['mesh_count']} meshes; materials: "
                  f"{', '.join(x['material'] or '-' for x in d['materials'])}; texture images: {imgs}."]
        lines += [f"- {t}" for t in notes[uid]]
        lines.append("")
    lines += ["## Side by side", "",
              "`out/review/scouting/scout_compare.png`: the three rendered in our three.js viewer with the atlas lighting (warm key,",
              "cool rim, soft fill, hemisphere, RoomEnvironment), from the front like the Z-Anatomy close-up, next to our heart.",
              "The candidates' orientation is the file's own (+Y up, facing +Z); it was not aligned to the patient frame.", "",
              "## For the decision (no winner picked)", "",
              "- None of the three has the parts peel mode needs (chambers, appendages, aorta, PA, fat as separate objects) or",
              "  coronaries as separate, branch-level geometry; only the Dundee model separates artery-coloured geometry at all.",
              "- Every heart uses its own coronaries: using any of these for the X-ray would mean extracting ITS coronaries (only",
              "  feasible for the Dundee model) and re-validating; using one as display only would put a different heart's surface",
              "  over our atlas coronaries, which the project rules forbid.",
              "- Licences: the photoreal options are CC BY; the anatomical Dundee series is CC BY-NC-SA."]
    (C / "SCOUTING.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    shutil.copy(C / "SCOUTING.md", REV / "SCOUTING.md")
    print("wrote", C / "SCOUTING.md")


if __name__ == "__main__":
    main()
