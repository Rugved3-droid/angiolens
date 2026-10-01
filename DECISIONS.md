# Decisions log

Newest at the bottom. Status: DECIDED (by Rugved), DEFAULT (my call, open to change), OPEN (needs Rugved).

## 2026-09-30 (Phase 0)

**D1 Location.** DECIDED. `D:\coronary-projection-trainer\`, its own git repo. A Python venv in `.venv`,
with versions pinned in `requirements.txt` (system Python 3.12; not the stEVE conda env).

**D2 Data source.** DECIDED. `D:\coronav\data\anatomy\` holds only VMR 0066 (CoroNav-processed), so it is not used.
The original ASOCA distribution is `D:\ASOCADataAccess.zip` (8.3 GB, dataset's own
`ASOCADataAccess/Normal/{CTCA,Annotations,Centerlines,SurfaceMeshes}` layout). `Normal_12` CTCA and its
annotation were **extracted (read-only) from that zip** into `data/raw/Normal_12/` and renamed
`CTCA_Normal_12.nrrd` and `Annotation_Normal_12.nrrd`. Byte content is unchanged; the SHA-256 of each file is in
`out/phase0/Normal_12/case_meta.json`. Nothing in the CoroNav or stEVE folders was moved or modified. No CoroNav or stEVE meshes or centerlines are used.
Headers: `space: left-posterior-superior`, identity directions (0.369, 0.369, 0.625 mm), gzip, both files on the same grid.
The CT is int32 HU; outside the circular reconstruction FOV it is padded at −3024.

**D3 Uninjected tree in the DRR.** DECIDED. Every voxel in the expert lumen segmentation (both trees,
dilated ~1 voxel) is set to soft-tissue HU (~40), on top of the blood-pool mask. Only the
selected tree is added back as contrast. (To implement in Phase 1.5.)

**D4 Isocenter.** DECIDED. One fixed point per case: the centroid of all lumen voxels of both trees.
For Normal_12 it is (25.2, −3.3, −106.7) mm LPS. `CArm.table_offset` is reserved for table pan.

**D5 Left/right split.** DEFAULT. The annotation must have exactly two 26-connected components. Left = the larger
one AND the one with the more patient-left centroid; if these disagree, loading stops for manual review.
Normal_12 left: 1670 mm³, centroid x +42. Right: 690 mm³, centroid x −15, y −22 (anterior).
This names *trees* only, never branches (branch labels come from Label mode).

**D6 Spine in FOV.** DECIDED (marker rule) / measured. In Normal_12 the vertebral bodies are present through the whole
z range (−193 to −65 mm, ~129 mm) at y ≈ +45…+90 mm. The circular reconstruction FOV
clips the posterior elements. So no approximate spine marker is needed for this case; the rule still applies to
future cases with sparse vertebral bone.

**D7 Image raster and viewing side.** DEFAULT (follows from the spec). Row 0 = +v (top), column 0 = −u.
Because u × v = d, the image is viewed from the detector side. This is the standard angiographic view
(AP: patient left on screen right).

**D8 Phase 0 renderer.** DEFAULT. The CPU reference renderer integrates path length through the expert voxel
annotation along true source→pixel rays (trilinear, 0.2 mm steps), I = exp(−0.35·t). The detector is 250 mm and 500 px.
It deliberately does not use a mesh, so it is an independent ground truth for the Phase 1 mesh and GPU renderers.

**D9 View readout.** DEFAULT. A zero component is omitted: `LAO 45`, not `LAO 45 / 0`. AP is `AP`.

**D10 Blood-pool mask as specified leaks into the spine.** OPEN. Rule: 200–700 HU, the component containing the aortic root.
In Normal_12 that component (443 mL) also contains the vertebral bodies (cancellous bone around 200–300 HU touches
the contrast-filled descending aorta). That would erase the spine from the bone mesh and from the DRR.
With a 1-voxel opening before connectivity, the spine separates (pool 289 mL). However, the FOV ends at
z = −65, below the arch, so the descending aorta is then a *separate* component and would be classed as "bone"
(HU > 250) and stay opacified in the DRR. Needs a decision before Phase 1 (bone mesh) and 1.5 (DRR).
