<!--
FINAL manuscript source (after the Phase 4 cutting pass on draft_v1.md). Built by paper/scripts/build_manuscript.py.
Markup: {{key}} numbers.json; [@key] bib; @@FIG n@@ / @@TABLE n@@ / @@EQ n@@ placement; ^x^ superscript; **bold**.
-->
# TITLE
AngioLens: an open-source, geometry-verified coronary angiography projection simulator for training

# ABSTRACT
**Purpose** Learning coronary angiography means predicting how a three-dimensional coronary tree appears at a given C-arm angle, and the sign conventions invite specific errors: confusing left (LAO) with right anterior oblique (RAO), or cranial with caudal. Simulators exist, but their projection conventions are rarely specified or tested. We present AngioLens, an open-source browser-based simulator, and verify its projection geometry and its misconception-based quiz items.

**Methods** AngioLens renders an atlas coronary tree with a virtual C-arm whose angles follow DICOM. We tested (1) agreement between the browser and a Python reference over a 5° angle grid, for point projections and rendered images; (2) orientation, using a chiral phantom whose expected images were derived from first principles, with mirrored and sign-swapped renders as negative controls; (3) the distractors of the Predict quiz, which encode LAO/RAO, cranial/caudal and mirror errors; and (4) performance.

**Results** Browser and reference projections differed by at most {{e1_vertex_max_px}} pixel; all {{e1b_images}} rendered images matched the exact reference (r ≥ {{e1b_r_min}}). The phantom matched its derivation at {{e2_v2_pass}}/{{e2_v2_views}} named views, and every applicable negative control was rejected. All {{e3_candidates}} options of {{e3_items}} Predict items were the transformation they were labelled as, and no pair of options was a near-duplicate (maximum vessel-mask overlap {{e3_iou_max}}). The app rendered {{e5_igpu_fps_median_median}} frames/s on an integrated graphics processor.

**Conclusion** AngioLens implements explicitly specified, tested projection conventions and verified misconception-based distractors in an open tool. Its educational effect has not been evaluated.

# KEYWORDS
Coronary angiography; C-arm projection; Simulation; Medical education; Software verification; Open-source software

# 1 Introduction
Coronary angiography shows a three-dimensional (3D) arterial tree as two-dimensional projections. Operators choose C-arm angles that separate overlapping branches and limit foreshortening, and trainees learn standard views for each segment [@green2016]. For a known 3D tree, foreshortening and overlap follow from the projection geometry [@dumay1994; @chen2000].

Predicting what a view will show is hard, and the two sign conventions invite two characteristic errors: placing the detector on the wrong side (left anterior oblique, LAO, versus right anterior oblique, RAO) and tilting it the wrong way (cranial versus caudal). Simulation is used to build such skills before patient exposure [@jensen2016; @voelker2016].

Several tools let learners rotate a virtual or physical C-arm around coronary anatomy, including AngioAID 3D [@samtani2024], AngioView [@rahman2026angioview] and 3D-printed models [@sabbak2022]. Such a tool is only as good as its geometry: a mirrored image or a reversed angle sign looks plausible and would teach the very error it should correct. To our knowledge, the projection conventions of these tools have not been published in a form that can be checked.

Multiple-choice items whose distractors encode known misconceptions show which error a learner makes, not only whether they are wrong [@sadler1998; @hestenes1992]. For angiographic views the natural distractors are the LAO/RAO reversal, the cranial/caudal reversal, both together, and a mirror image. Such items are useful only if each distractor really is the labelled error.

We present AngioLens, an open-source browser-based projection simulator, and ask whether it renders what its stated conventions say it should. We specify the conventions, test them against an independent derivation with negative controls, verify the quiz distractors and measure performance. We make no claim about learning.

# 2 Methods
## 2.1 System
AngioLens runs in a web browser (three.js, WebGL) without installation (Fig. 1a). Version 1.1 has six guided scenes, from the heart to a virtual catheterisation laboratory, a live angiogram and a Predict quiz. A study mode with pre- and post-tests exists but was not used, and no learner data are reported. Online Resource 1 is a narrated demonstration.

@@FIG 1@@

The anatomy is the Z-Anatomy atlas [@zanatomy], derived in part from BodyParts3D. Coronary arteries are tubes around authored centerlines, exported with one rigid transform into the patient frame and closed into one solid per tree. The atlas names the left main, left anterior descending, circumflex and right coronary arteries but not their side branches.

## 2.2 Conventions
Positions are in millimetres in the LPS patient frame (+x left, +y posterior, +z superior). The primary angle α is positive for LAO and the secondary angle β positive for cranial, as in DICOM [@dicom_ps33]. The detector direction from the isocenter is

@@EQ 1@@

so the detector is anterior at α = β = 0 (anteroposterior, AP). The source lies 750 mm from the isocenter and the detector at a source-to-image distance (SID) of 1000 mm. Screen up v is the patient's superior axis projected onto the detector, and screen right is u = v × d. AngioLens states its display convention explicitly: the image is drawn as seen from the detector looking towards the source, so at AP the patient's left appears on the image's right and the patient's head at the top, and the image is never flipped for display. E2 tests that the app follows this convention. A point p projects to

@@EQ 2@@

where S is the source (Fig. 1b, c). The detector is 250 mm wide with 512 pixels ({{pixel_mm}} mm per pixel). Fig. 2 shows one anatomy at four named views.

@@FIG 2@@

The geometry is implemented twice, in TypeScript for the app and in Python as a reference. The app renders vessel path length on the graphics processing unit (GPU) from the entry and exit depths of closed meshes; the reference computes it exactly by intersecting every pixel ray with every triangle.

## 2.3 Predict mode
Each round names a target view and shows four angiograms (Fig. 5): the correct view, LAO/RAO reversed (−α, β), cranial/caudal reversed (α, −β), and both reversed (−α, −β), which a setting can replace with a left-right mirror image. Targets are standard views or random poses at least 15° from the current one. When |α| or |β| is below 5°, reversing it would reproduce the same image, and the app substitutes a mirror image. Mirrored images occur only as distractors.

## 2.4 Verification experiments
Each experiment is a script with a fixed seed that writes raw CSV files, from which all figures and tables are regenerated. Named views were the app's presets: RAO 30, LAO 45, RAO 30/caudal 25, RAO 30/cranial 30, cranial 35, caudal 30, LAO 40/cranial 30, the spider view (LAO 40/caudal 30) and left lateral. The app's classic mode defines the spider view as LAO 45/caudal 30, which was also tested.

**E1 Projection agreement.** We projected all {{e1_points}} atlas centerline samples at {{e1_poses_total}} poses: LAO/RAO −90° to 90° by cranial/caudal −45° to 45° in 5° steps, plus the named views. The app's TypeScript code, run in Chromium, was compared with the Python reference along two paths: the float64 projection used for overlays and the float32 matrix the GPU applies to every vertex. E1 shows that the implementations agree, not that their shared convention is correct.

**E1b Image agreement.** On the same grid, for both coronary trees, we compared the app's rendered path-length image with the exact reference by Pearson r, mean absolute error (MAE), centroid shift and mask intersection over union (IoU), and repeated r after mirroring the app image.

**E2 Orientation.** E2 tests the convention. A synthetic phantom carried three tube letters, L, R and F, at known off-axis positions, drawn to read normally at AP. Expected images were derived without the app's code: from the AP image (detector anterior, patient left on the right), LAO rotates the detector about the long axis toward the patient's left, cranial angulation then tilts it toward the head, and points are projected from a point source. This reproduces Eq. 1–2 and predicts that a mirror reverses each letter, whereas a sign swap moves the letters without reversing them. A render passed if its mask overlapped the expected image with IoU ≥ 0.70, contained three letters each within 2 pixels of its predicted position, and each letter matched its true rather than mirrored shape; the rule was fixed before the first run. Negative controls had to fail: left-right and up-down mirrored renders, and renders with the LAO/RAO or cranial/caudal sign swapped. A swap of a zero angle yields the identical image and was recorded as not applicable. Because two letters of the first phantom overlapped at one view, a second phantom with one letter moved was built; both are reported.

**E3 Distractor validity.** Predict items are generated, not stored. We tested the option logic at every integer target over the full angle range, with the mirror setting off and on, and {{e3_items}} rendered items: every preset target with both settings and {{e3_flow_rounds}} seeded rounds of the real quiz flow. Each correct tile was compared byte by byte with an independent render of the target, and its vessel image with the exact reference. Distinctness was the pairwise IoU of binary vessel masks. A pair was a near-duplicate if its IoU reached the highest IoU between the correct view and the same view moved 5° on one axis, the app's own threshold for an identical image. To confirm labels, each option's vessel image was correlated with exact references of all six hypotheses (correct, three reversals, two mirrors); the label had to match best.

**E5 Performance.** On a laptop ({{hw_cpu}}, {{hw_ram}} GB RAM, {{hw_os}}) serving the production build locally, we measured over {{e5_reps}} repetitions the cold load time of the start and angiography scenes, the frame rate while the C-arm swept continuously for {{e5_seconds}} s with the X-ray re-rendered every frame, and memory, using headless Chromium on the integrated GPU, headless Chromium with software rendering, and a visible window on the discrete GPU.

**Use of AI tools.** Claude Code (Anthropic) was used for software development, analysis scripts, figure generation and manuscript drafting, under the authors' direction. The authors verified all code, results and text and take responsibility for them.

# 3 Results
Table 2 summarises the results; full tables, derivations and per-pose outputs are in Online Resource 2. The repository's own suite passed ({{tests_pytest}} Python tests, {{tests_vitest}} TypeScript tests, {{tests_e2e}} browser suites).

@@TABLE 2@@

**E1.** The float64 browser path differed from the reference by at most {{e1_overlay_max_px}} pixel, and the float32 GPU path by at most {{e1_vertex_max_px}} pixel ({{e1_vertex_max_um}} µm at the detector; Fig. 3a).

**E1b.** All {{e1b_pass}} rendered images met the acceptance rule (r ≥ {{e1b_r_min}}, MAE ≤ {{e1b_mae_max}} mm, centroid shift ≤ {{e1b_centroid_max}} pixel, IoU ≥ {{e1b_iou_min}}; Fig. 3b). Mirrored images reached at most r = {{e1b_mirror_lr_max}} (left-right, at {{e1b_mirror_lr_worst_pose}}) and r = {{e1b_mirror_ud_max}} (up-down), so the comparison detected a mirror at every pose (Fig. 3c).

@@FIG 3@@

**E2.** With the first phantom the correct render passed at {{e2_v1_pass}} of {{e2_v1_views}} views. At the classic spider view (LAO 45/caudal 30) the R and F letters overlapped and formed {{e2_v1_overlap_components}} regions instead of three, so the rule failed although the render agreed with the derivation (IoU {{e2_v1_overlap_iou}}; Fig. 4e), a flaw of the phantom. With the second phantom it passed at {{e2_v2_pass}} of {{e2_v2_views}} views (Fig. 4a, f), with every letter within {{e2_v2_err_max_px}} pixels ({{e2_v2_err_max_mm}} mm) of its predicted position and all {{e2_v2_hand_ok}} non-lateral letters of the predicted handedness. All applicable negative controls were rejected (Table 2; Fig. 4b–d), with IoU against the expected image of at most {{e2_v2_neg_iou_max}}.

@@FIG 4@@

**E3.** All {{e3_logic_ok}} generated option sets were valid: four distinct options, one correct, each matching its label's angles. The logic declined only the {{e3_logic_threw}} sets with targets within 5° of AP on both axes, which the target generator never produced. The correct option matched the exact reference (IoU ≥ {{e3_correct_iou_cpu_min}}), and every label was its option's best-matching hypothesis (r ≥ {{e3_r_label_min}}; margin ≥ {{e3_margin_min}}). Pairwise IoU had a median of {{e3_iou_median}} and a maximum of {{e3_iou_max}} (Fig. 5e). Item-specific near-duplicate thresholds ranged from {{e3_tau_min}} to {{e3_tau_max}}; no pair reached its threshold, the closest staying {{e3_tau_gap_min}} below. The structural similarity index [@wang2004] did not discriminate, lying between {{e3_ssim_min}} and {{e3_ssim_max}} for every pair because the sparse masks share a large empty background (Online Resource 2).

@@FIG 5@@

The correct tile was byte-identical to an independent render in {{e3_tiles_identical_correct}} of {{e3_items}} items, and all four tiles in {{e3_tiles_identical_all}}; in the other {{e3_tile_diff_items}}, a tile differed by {{e3_tile_diff_min_bytes}}–{{e3_tile_diff_max_bytes}} bytes. In a follow-up, repeated renders of one pose occasionally differed ({{probe_repeats_diff}} of {{probe_repeats}}) in small patches outside the vessels, by up to {{probe_max_dv}} grey levels, and the differences did not recur for the same items. We attribute them to run-to-run nondeterminism of GPU rendering; vessel pixels, positions and labels were unaffected.

**E5.** On the integrated GPU the start and angiography scenes loaded cold in {{e5_igpu_load_scene1_ms_s}} s and {{e5_igpu_load_scene4_ms_s}} s (medians), and rotation ran at {{e5_igpu_fps_median_median}} frames/s with {{e5_igpu_js_heap_mb_after_rotation_median}} MB of JavaScript heap. On the discrete GPU the values were {{e5_dgpu_load_scene1_ms_s}} s, {{e5_dgpu_load_scene4_ms_s}} s and {{e5_dgpu_fps_median_median}} frames/s. Software rendering fell to {{e5_sw_fps_median_median}} frames/s, so a GPU is required.

# 4 Discussion
The image a learner sees is the reference geometry, without rasterisation or precision error at the scale of a pixel, and the shared convention is the intended one: it matches a derivation from the DICOM angle definitions and the app's stated display convention, and each class of sign or mirror error yields an image the test rejects. Every Predict distractor is the error it names.

This matters because a training tool's geometric errors are silent: a mirrored or sign-reversed coronary tree still looks like a coronary tree. Specifying conventions, deriving expected images independently and testing deliberately wrong renders turns "looks right" into a check that can fail, and the harness can be rerun after any code change.

The negative controls also mark what image tests cannot detect. At AP the LAO/RAO swap, and at zero tilt the cranial/caudal swap, leave the image unchanged; no test can see them, and the Predict logic correctly never offers them. A mirror reverses the letters' handedness while a sign swap only moves them, so position is needed to detect swaps.

AngioLens differs from other tools (Table 1) less in features than in being open, running in a browser, and documenting and testing its conventions. AngioView [@rahman2026angioview] offers comparable interactive C-arm control on mobile devices, and 3D-printed models [@sabbak2022] a physical alternative. Their published descriptions do not report projection verification, which says nothing about their correctness.

@@TABLE 1@@

**Limitations.** One atlas anatomy and synthetic phantoms were used; anatomical variation is not represented, and the atlas lacks named diagonal, obtuse marginal and posterior descending branches, so segment-level foreshortening against recommended views was not assessed and is future work. The path-length model has no scatter, motion blur or contrast dynamics, so the images teach geometry, not image quality. The first phantom failed at one view because of its design. A few tiles differed between renders outside the vessels, a cause attributed but not proven. Performance was measured on one laptop. Learning was not evaluated; whether verified geometry and misconception-based distractors improve view selection needs a separate study.

# 5 Conclusion
AngioLens is an open browser-based coronary angiography projection simulator whose conventions are specified and tested against an independent derivation, and whose quiz distractors are verified to be the errors they name. Its educational effect remains to be studied.

# ONLINE RESOURCES
**Online Resource 1** AngioLens demonstration video: narrated tour of the scenes and Predict mode, recorded from the app source of release v1.1-ijcars; titles and captions are a recording overlay. Rendered from Z-Anatomy models (CC BY-SA 4.0), derived from BodyParts3D (DBCLS).

**Online Resource 2** Full verification tables, derivations and outputs of E1, E1b, E2 (both phantoms), E3 (including the structural similarity index) and E5

# STATEMENTS
**Funding** No funding was received for conducting this study.

**Competing interests** The authors have no competing interests to declare that are relevant to the content of this article.

**Ethics approval** This study did not involve human participants, human data, or animals.

**Consent to participate** Not applicable.

**Consent to publish** Not applicable.

**Data availability** All verification outputs and the scripts that produce them are in the code repository. Atlas renders can be regenerated from Z-Anatomy, available from its original source [@zanatomy].

**Code availability** AngioLens is available at https://github.com/Rugved3-droid/angiolens (MIT licence). This paper describes release tag v1.1-ijcars, commit 198c6d4da1f980cdaa301f5131ccb83ebffb5be1; the verification harness is on the branch paper/ijcars-verification.

**Author contributions** Rugved Parmar: conceptualization, software, methodology, formal analysis, visualization, writing – original draft. Md Fahim: software review, validation, writing – review and editing. Shreya P. Trivedi: supervision, writing – review and editing.

# CAPTIONS
FIG 1: **Fig. 1** Architecture and angle conventions. **a** Data flow from the Z-Anatomy atlas through the C-arm geometry to the rendered angiogram and Predict mode; dashed double arrows mark comparisons E1 (TypeScript versus Python geometry) and E1b (GPU versus exact CPU image). **b** Axial schematic seen from the feet: detector (bar) and beam (arrow) at AP (solid), LAO 40 (dashed) and RAO 30 (dotted). **c** Sagittal schematic seen from the patient's left: AP (solid), cranial 30 (dashed), caudal 25 (dotted). Script: fig1_architecture.py
FIG 2: **Fig. 2** One atlas anatomy at four named views, each as the 3D scene seen from behind the detector (left) beside the rendered angiogram (right). **a** RAO 30/caudal 25, left coronary injection. **b** LAO 40/caudal 30 (spider), left. **c** RAO 30, right coronary injection. **d** LAO 45, right. Rendered from Z-Anatomy models (CC BY-SA 4.0), derived from BodyParts3D (DBCLS). Scripts: fig_capture.mjs, fig2_views.py
FIG 3: **Fig. 3** Agreement over the 5° grid (primary angle horizontal, secondary vertical); circles mark named views. **a** E1: maximum discrepancy between the app's float32 GPU projection and the Python reference over {{e1_points}} centerline points (10^−4^ pixel). **b** E1b: maximum centroid shift between rendered and exact images over both trees (10^−3^ pixel). **c** E1b: correlation of the left-right mirrored app image with the reference (maximum over both trees); low values mean a mirror is detected. Scripts: e1_projection_agreement.py, e1b_render_agreement.py, fig3_agreement.py
FIG 4: **Fig. 4** E2 orientation phantom: rendered path length (dark) with the outline predicted by the first-principles derivation (dashed). **a** Second phantom, correct render, LAO 40/caudal 30. **b** Same render mirrored left-right. **c** LAO/RAO sign swapped. **d** Cranial/caudal sign swapped. **e** First phantom at LAO 45/caudal 30, where two letters overlap. **f** Second phantom at the same view. Panels b–d are negative controls and were rejected. Scripts: e2_orientation.py, fig4_phantom.py
FIG 5: **Fig. 5** Predict mode. **a–d** The four options of one item (target LAO 40/caudal 30, left coronary injection, mirror setting on) as rendered by the app: {{fig5_order}}. **e** Pairwise IoU of binary vessel masks over {{e3_items}} items by pair type (grey: pairs with the correct option; hatched: pairs of distractors); dashed line, smallest item-specific near-duplicate threshold ({{e3_tau_min}}). **a–d** Rendered from Z-Anatomy models (CC BY-SA 4.0), derived from BodyParts3D (DBCLS). Scripts: e3_distractors.py, fig_capture.mjs, fig5_predict.py

# TABLE 1
CAPTION: **Table 1** Interactive coronary angiography training tools as documented in their published descriptions
HEADER: Tool | Platform | 3D coronary anatomy | User-set C-arm angles | Misconception-based distractors | Projection verification reported | Source code
ROW: AngioAID 3D [@samtani2024] | Mobile^a^ | NR | NR | NR | NR | NR
ROW: AngioView [@rahman2026angioview] | iPhone, iPad^b^ | Yes^b^ | Yes^b^ | NR | NR | NR
ROW: 3D-printed models [@sabbak2022] | Physical model^a^ | Yes^a^ | NR | NR | NR | Not applicable
ROW: AngioLens (this work) | Web browser | Yes | Yes | Yes | Yes (E1–E3) | Open (MIT)
FOOT: NR, not reported in the cited description. ^a^ From the title of the conference abstract; the abstract text was not available to the authors. ^b^ From the app store description (version 1.0.4, accessed 14 November 2026).

# TABLE 2
CAPTION: **Table 2** Summary of the verification experiments
HEADER: Experiment | Scope | Result
ROW: E1 projection agreement | {{e1_poses_total}} poses × {{e1_points}} points | Max discrepancy {{e1_overlay_max_px}} pixel (float64), {{e1_vertex_max_px}} pixel (float32 GPU path)
ROW: E1b image agreement | {{e1b_images}} images, 2 trees | r ≥ {{e1b_r_min}}; MAE ≤ {{e1b_mae_max}} mm; centroid shift ≤ {{e1b_centroid_max}} pixel; mirrored r ≤ {{e1b_mirror_lr_max}}
ROW: E2 orientation, phantom 1^a^ | {{e2_v1_views}} named views | Correct render passed {{e2_v1_pass}}/{{e2_v1_views}}
ROW: E2 orientation, phantom 2 | {{e2_v2_views}} named views | Passed {{e2_v2_pass}}/{{e2_v2_views}}; negative controls rejected {{e2_v2_mirror_lr_det}}/{{e2_v2_mirror_lr_app}}, {{e2_v2_swap_lao_rao_det}}/{{e2_v2_swap_lao_rao_app}}, {{e2_v2_swap_cran_caud_det}}/{{e2_v2_swap_cran_caud_app}}, {{e2_v2_mirror_ud_det}}/{{e2_v2_mirror_ud_app}}^b^
ROW: E3 option logic | {{e3_logic_ok}} option sets | All valid
ROW: E3 rendered items | {{e3_items}} items, {{e3_candidates}} options | Labels confirmed {{e3_label_ok}}/{{e3_candidates}}; near-duplicates {{e3_flagged}}/{{e3_pairs}} pairs; max IoU {{e3_iou_max}}
ROW: E5 performance, integrated GPU | {{e5_reps}} runs | Cold load {{e5_igpu_load_scene1_ms_s}} s; {{e5_igpu_fps_median_median}} frames/s
ROW: E5 performance, discrete GPU | {{e5_reps}} runs | Cold load {{e5_dgpu_load_scene1_ms_s}} s; {{e5_dgpu_fps_median_median}} frames/s
ROW: E5 performance, software rendering | {{e5_reps}} runs | {{e5_sw_fps_median_median}} frames/s
FOOT: MAE, mean absolute error of path length. ^a^ Failed at one view because two phantom letters overlapped in projection. ^b^ Left-right mirror, LAO/RAO swap, cranial/caudal swap, up-down mirror; swaps of a zero angle are not applicable.
