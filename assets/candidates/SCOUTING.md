# Photoreal heart scouting (v1.1 item 4): report only, nothing integrated

Date: 2026-10-05. Source: the official Sketchfab Data API v3 only (`/v3/search?type=models&downloadable=true`,
`/v3/models/{uid}/download`); no HTML scraping, no login bypass, at most one call per 1.1 s. Downloads used the
`SKETCHFAB_TOKEN` environment variable; it was never printed, stored or committed. Script:
`preprocess/scripts/sketchfab_scout.py` (+ `scout_inspect.py`, `scout_parts.py`, `scout_colors.py`, `e2e/scout_render.mjs`).

## Search
- Queries: 'human heart', 'heart anatomy', 'realistic heart', 'heart coronary arteries', 'anatomical heart', 'cardiac anatomy'; each sorted by likes and by views (24 per query and sort).
- 132 unique models. Filters: licence in {CC BY, CC BY-SA, CC BY-NC, CC BY-NC-SA, CC0}; not age-restricted;
  the name or a tag names the heart; no stylized / cartoon / low-poly / game / icon / emoji words.
  78 passed; the 30 most popular were kept with their largest thumbnails.
- Contact sheet of those 30: `SCOUTING_contact_sheet.png` (numbers below refer to it).
- Removed by eye after the keyword filter: a steampunk sculpture (#2), a whole-body angiology model (#4), a silver
  ZBrush sculpt (#5), an untextured white sculpt (#9), a wireframe-look heart (#10), full skeletons (#16, #20), a thorax
  (#17), echo-plane cut models (#14, #21, #24, #25, #27-#29) and a conduction-system model (#30).

## The ten most realistic (ranked by eye on the thumbnails: photorealism, then visible coronaries)

| Rank | # | Title | Author | Licence | Likes | Triangles | Look | Coronaries (thumbnail) |
|---|---|---|---|---|---|---|---|---|
| 1 | 23 | [Human Heart](https://sketchfab.com/3d-models/none-2edbedffae6b49ee97f919a8528329ba) | Rudy | CC BY | 41 | 1,981,158 | photo-real sculpt; superficial vessels sculpted in relief | sculpted relief (fused) |
| 2 | 1 | [Realistic Human Heart](https://sketchfab.com/3d-models/none-3f8072336ce94d18b3d0d055a1ece089) | neshallads | CC BY | 1661 | 22,562 | photo-real texture (wet, glossy); the best surface look | painted in the texture |
| 3 | 3 | [Cardiac Anatomy: External view of human heart](https://sketchfab.com/3d-models/none-a3f0ea2030214a6bbaa97e7357eebd58) | HannahNewey | CC BY-NC-SA | 182 | 3,003,486 | clean anatomical illustration; arteries red, veins blue | separate coloured geometry (see inspection) |
| 4 | 6 | [heart](https://sketchfab.com/3d-models/none-764e3bbc71664221bb123eef5c47fee8) | rbproduction160 | CC BY-NC | 210 | 22,562 | the same model as #1 under another account and licence | painted in the texture |
| 5 | 22 | [Anatomical heart - codominance](https://sketchfab.com/3d-models/none-42d07ac1517748ea82bb05b0a362b298) | E-learning UMCG | CC BY-NC-SA | 49 | 186,065 | anatomical; coronaries drawn as red tubes on the surface | red tubes (likely separate) |
| 6 | 7 | [Cardiac Anatomy: external view](https://sketchfab.com/3d-models/none-e8e8c6685e82474d8393693fd0646dc7) | E-learning UMCG | CC BY-NC-SA | 179 | 248,695 | anatomical, ivory/brown; a teaching series (Groningen) | not visible on the thumbnail |
| 7 | 11 | [Cardiac Anatomy: Coronary arteries of the heart](https://sketchfab.com/3d-models/none-00b5f4ec0b984325b453f8df07cd0cb5) | HannahNewey | CC BY-NC-SA | 70 | 2,747,730 | Dundee coronary-artery view (same series as #3) | coloured geometry |
| 8 | 18 | [Human Heart 3D Model / Anatomy / Medical Project](https://sketchfab.com/3d-models/none-5da08bb137014f0392c69f9997f777cd) | Mesh-Magnet | CC BY | 53 | 20,395 | textured, saturated red; moderately realistic | painted |
| 9 | 15 | [Human heart](https://sketchfab.com/3d-models/none-3342c8c438904ee2b3b6b68fedf30531) | Freddan755 | CC BY | 66 | 54,452 | glossy, pink-red; stylised lighting | painted |
| 10 | 12 | [Healthy heart and lungs](https://sketchfab.com/3d-models/none-5c62cd4d4ba04243be1062d2263d3ef0) | E-learning UMCG | CC BY-NC-SA | 85 | 371,915 | heart with lungs (Groningen series) | not visible |

## The top 3: downloaded and inspected

Each is in `assets/candidates/<uid>/` (git-ignored) with `LICENSE.txt` (title, author, URL, licence and URL,
attribution, date). `inspect_heart_model.py` reports are in `out/review/scouting/<uid>/`; the glTF details below
come from each file's own JSON (`_scout/inspect_<uid>.json`).

### [Human Heart](https://sketchfab.com/3d-models/none-2edbedffae6b49ee97f919a8528329ba) (Rudy), CC BY 4.0 (CC Attribution)

- File: 74.9 MB GLB; 1,981,158 triangles in 20 meshes; materials: material_0; texture images: none.
- Parts: ONE fused surface. The 20 meshes are buffer-size chunks (~100 k triangles each, all spanning most of the heart), not anatomical parts; no chambers, appendages, aorta or PA as separate objects; no fat layer.
- Coronaries: SCULPTED RELIEF fused into the surface (visible as raised vessels in the render), not separate geometry; no colour difference (one muscle-tone vertex colour everywhere).
- Textures: none; colour is per-vertex (COLOR_0), one material.

### [Realistic Human Heart](https://sketchfab.com/3d-models/none-3f8072336ce94d18b3d0d055a1ece089) (neshallads), CC BY 4.0 (CC Attribution)

- File: 3.3 MB GLB; 22,562 triangles in 1 meshes; materials: Heart_Tex; texture images: 1024x1024, 1024x1024, 1024x1024.
- Parts: ONE mesh (ZBrush export, 22.6 k triangles). Nothing is separate.
- Coronaries: PAINTED in the texture (with normal-map relief); no vessel geometry.
- Textures: base colour, metal/roughness and normal, each 1024 x 1024. The most photoreal surface of the three.
- Note: the same model is listed again as #6 'heart' under CC BY-NC by another account; the CC BY original was taken.

### [Cardiac Anatomy: External view of human heart](https://sketchfab.com/3d-models/none-a3f0ea2030214a6bbaa97e7357eebd58) (HannahNewey), CC BY-NC-SA 4.0 (CC Attribution-NonCommercial-ShareAlike)

- File: 121.5 MB GLB; 3,003,484 triangles in 41 meshes; materials: defaultMat; texture images: none.
- Parts: 41 meshes, but with generic names (Object_N) and buffer-size chunks (~120 k triangles); colour groups are separate meshes: muscle-tone 24 meshes (1.77 M triangles), red 9 (0.62 M: aorta and coronary arteries), blue 4 (0.38 M: veins), neutral 4 (0.24 M).
- Coronaries: SEPARATE COLOURED GEOMETRY (red meshes distinct from the muscle), but the aorta and the arteries share the red meshes; branch-level separation would need splitting by connectivity. Chambers / appendages / PA are not named; no fat layer.
- Textures: none (per-vertex colour, one grey material). Very heavy: 3.0 M triangles, 121 MB.
- Licence: CC BY-NC-SA (non-commercial, share-alike).

## Side by side

`out/review/scouting/scout_compare.png`: the three rendered in our three.js viewer with the atlas lighting (warm key,
cool rim, soft fill, hemisphere, RoomEnvironment), from the front like the Z-Anatomy close-up, next to our heart.
The candidates' orientation is the file's own (+Y up, facing +Z); it was not aligned to the patient frame.

## For the decision (no winner picked)

- None of the three has the parts peel mode needs (chambers, appendages, aorta, PA, fat as separate objects) or
  coronaries as separate, branch-level geometry; only the Dundee model separates artery-coloured geometry at all.
- Every heart uses its own coronaries: using any of these for the X-ray would mean extracting ITS coronaries (only
  feasible for the Dundee model) and re-validating; using one as display only would put a different heart's surface
  over our atlas coronaries, which the project rules forbid.
- Licences: the photoreal options are CC BY; the anatomical Dundee series is CC BY-NC-SA.
