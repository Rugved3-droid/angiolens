<!--
DRAFT v1 (before the cutting pass). Source format for paper/scripts/build_manuscript.py:
  {{key}}      number from paper/results/numbers.json (unknown key = build error)
  [@a; @b]     citation(s) from paper/references_provided.bib, numbered in order of first appearance
  @@FIG n@@    figure n placed here (caption from the CAPTIONS block)
  @@TABLE n@@  table n placed here
  @@EQ n@@     display equation n (OMML)
  ^x^          superscript
-->
# TITLE
AngioLens: an open-source, geometry-verified coronary angiography projection simulator for training

# ABSTRACT
**Purpose** Learning coronary angiography requires predicting how a three-dimensional coronary tree appears at a given C-arm angle, and the most common errors are sign errors: confusing LAO with RAO or cranial with caudal. Simulators exist, but their projection conventions are rarely specified or tested. We present AngioLens, an open-source browser-based simulator, and report a verification of its projection geometry and of its misconception-based quiz items.

**Methods** AngioLens renders an atlas coronary tree (Z-Anatomy) with a virtual C-arm whose angle conventions follow DICOM. We tested (1) agreement between the browser and a Python reference over a 5° angle grid, for point projections and for rendered images; (2) orientation, using a chiral phantom whose expected images were derived from first principles, with mirrored and sign-swapped renders as negative controls; (3) the distractors of the Predict mode, whose wrong options encode LAO/RAO, cranial/caudal and mirror errors; and (4) performance.

**Results** Browser and reference projections differed by at most {{e1_vertex_max_px}} px; all {{e1b_images}} rendered images matched the exact reference (r ≥ {{e1b_r_min}}). The phantom matched its derivation at {{e2_v2_pass}}/{{e2_v2_views}} named views, and every applicable negative control was rejected. All {{e3_candidates}} options of {{e3_items}} Predict items were the transformation they were labelled as; no option pair was a near-duplicate (maximum vessel-mask IoU {{e3_iou_max}}). The app rendered at {{e5_igpu_fps_median_median}} frames/s on an integrated GPU.

**Conclusion** AngioLens implements explicitly specified, tested projection conventions and verified misconception-based distractors in an open tool. Its educational effect has not been evaluated.

# KEYWORDS
Coronary angiography; C-arm projection; Simulation; Medical education; Software verification; Open-source software

# 1 Introduction
Coronary angiography displays a three-dimensional (3D) arterial tree as two-dimensional (2D) projections. Operators choose C-arm angles that separate overlapping branches and limit foreshortening, and trainees learn a set of standard views for each segment [@green2016]. The choice of view can be framed geometrically: for a known 3D tree, foreshortening and overlap follow from the projection [@dumay1994; @chen2000].

Trainees nevertheless find it hard to predict what a view will show. A recurring error is a sign error: placing the detector on the wrong side (left anterior oblique, LAO, versus right anterior oblique, RAO) or tilting it the wrong way (cranial versus caudal). Simulation-based training is used to build these skills before patient exposure [@jensen2016; @voelker2016].

Several tools now let learners rotate a virtual C-arm around coronary anatomy, including a mobile platform (AngioAID 3D) [@samtani2024], a mobile simulator (AngioView) [@rahman2026angioview] and 3D-printed physical models [@sabbak2022]. A tool of this kind is only as good as its geometry. A mirrored image or a reversed angle sign looks plausible and would teach the very error it is meant to correct. To our knowledge, the projection conventions of such tools have not been published in a form that can be checked independently.

Multiple-choice items whose distractors encode known misconceptions can reveal which error a learner makes, rather than only whether they are wrong [@sadler1998; @hestenes1992]. For angiographic views, the natural distractors are the LAO/RAO reversal, the cranial/caudal reversal, both together, and a mirror image. Such items are useful only if each distractor really is the error it is labelled as.

This paper presents AngioLens, an open-source browser-based projection simulator, and asks one question: does it render what its stated conventions say it should? We specify the conventions, test them against an independent derivation with negative controls, verify the distractors of its quiz mode, and measure its performance. We make no claim about learning outcomes.

# 2 Methods
## 2.1 System
AngioLens runs in a web browser (three.js and WebGL) with no installation (Fig. 1a). Version 1.1 provides six guided scenes, from the heart to a virtual catheterisation laboratory, a live angiogram, and a Predict quiz. A study mode with pre- and post-tests also exists; it was not used here and no learner data are reported. A narrated demonstration is provided as Online Resource 1.

@@FIG 1@@

The anatomy is the Z-Anatomy atlas [@zanatomy], which is derived in part from BodyParts3D. Coronary arteries are tubes around authored centerlines. They were exported with a single rigid transform into the patient frame and closed into one solid per tree, so that path length through a vessel is well defined. Nothing else is moved or rescaled. The atlas has named left main, left anterior descending (LAD), circumflex and right coronary arteries, but unnamed side branches.

## 2.2 Conventions
Positions are in millimetres in the LPS patient frame: +x patient left, +y posterior, +z superior. The primary angle α is positive for LAO, and the secondary angle β is positive for cranial, as in DICOM [@dicom_ps33]. The detector direction from the isocenter is

@@EQ 1@@

so that at α = β = 0 (anteroposterior, AP) the detector is anterior. The source lies at a source-to-isocenter distance of 750 mm and the detector at a source-to-image distance (SID) of 1000 mm. Screen up v is the projection of the patient's superior axis onto the detector plane, and screen right is u = v × d. The image is therefore viewed from the detector, so that at AP the patient's left appears on the right, and no image is flipped for display. A point p projects to

@@EQ 2@@

where S is the source (Fig. 1b, c). The detector is 250 mm wide with 512 pixels ({{pixel_mm}} mm per pixel). Fig. 2 shows the same anatomy at four named views.

@@FIG 2@@

The geometry is implemented twice: in TypeScript for the app and in Python as a reference. The app renders vessel path length on the GPU by summing ray entry and exit depths of closed meshes. The Python reference computes the same quantity exactly by intersecting every pixel ray with every triangle.

## 2.3 Predict mode
Each Predict round shows four angiograms and names a target view (Fig. 5). The target is a standard view or a random pose at least 15° from the current one. The options are the correct view and three distractors: LAO/RAO reversed (−α, β), cranial/caudal reversed (α, −β), and both reversed (−α, −β). An optional setting replaces the last with a left-right mirror image. When |α| or |β| is below 5°, reversing that angle would reproduce the same image, so the app substitutes a mirror image. Mirrored images occur only as distractors.

## 2.4 Verification experiments
Each experiment is a script with a fixed seed that writes raw CSV files. All figures and tables are regenerated from these files. The named views were the app's presets: RAO 30, LAO 45, RAO caudal (RAO 30/caudal 25), RAO cranial (RAO 30/cranial 30), AP cranial (cranial 35), AP caudal (caudal 30), LAO cranial (LAO 40/cranial 30), spider (LAO 40/caudal 30) and left lateral (LAO 90). The classic mode of the app defines the spider view as LAO 45/caudal 30, which was also tested; named-view angles vary in practice.

**E1 Projection agreement.** We projected all {{e1_points}} atlas centerline samples at {{e1_poses_total}} poses: a grid of LAO/RAO −90° to 90° by cranial/caudal −45° to 45° in 5° steps, plus the named views. We compared the app's TypeScript code, run in Chromium, with the Python reference. Two browser paths were compared: the float64 projection used for overlays, and the float32 clip-space matrix used by the GPU for every vertex. E1 shows that the two implementations agree; it cannot show that the shared convention is correct.

**E1b Image agreement.** At the same grid, for both coronary trees ({{e1b_images}} images), we compared the app's rendered path-length image with the exact Python reference. We computed Pearson r, mean absolute error, centroid shift, and mask intersection over union (IoU), and repeated the correlation after mirroring the app image left-right and up-down.

**E2 Orientation.** E2 is the test of the convention. A synthetic phantom carried three tube letters, L, R and F, placed off-axis at known positions and drawn so that each reads normally at AP. Expected images at each named view were derived from first principles, without the app's code. Starting from the AP image (detector anterior, patient left on the screen right), LAO rotates the detector about the patient's long axis toward the patient's left, and cranial angulation then tilts it toward the head; points are projected through a point source. This construction reproduces the closed form above, and it predicts that a mirror reverses each letter whereas an angle-sign swap moves the letters without reversing them. A render passed if its vessel mask overlapped the expected image with IoU ≥ 0.70, it contained three letters each within 2 pixels of its expected position, and each letter matched its true rather than its mirrored shape. The rule was fixed before the first run. Negative controls, which had to fail, were left-right and up-down mirrored renders and renders with the LAO/RAO or cranial/caudal sign swapped. A swap of an angle that is zero yields the identical image and was recorded as not applicable. After the first phantom showed two letters overlapping at one view, a second phantom with one letter moved was built; both are reported.

**E3 Distractor validity.** Predict items are generated, not stored. We therefore tested (a) the option logic at every integer target over the full angle range, with the mirror setting off and on, and (b) {{e3_items}} rendered items: every preset target with the mirror setting off and on, and {{e3_flow_rounds}} seeded rounds of the real quiz flow. For each item we checked that the correct tile was byte-identical to an independent render of the target, and that its vessel image matched the exact reference. Distinctness was measured as pairwise IoU of binary vessel masks. A pair was flagged as a near-duplicate if its IoU reached the highest IoU between the correct view and the same view moved 5° on one axis, the app's own threshold for an identical image. To confirm labels, each option's vessel image was correlated with exact references of all six hypotheses (correct, the three reversals, and the two mirrors), and the label had to be the best match.

**E5 Performance.** On a laptop ({{hw_cpu}}, {{hw_ram}} GB RAM, {{hw_os}}) we served the production build locally and measured, over {{e5_reps}} repetitions each, the cold load time of the start scene and of the angiography scene, the frame rate while the C-arm swept continuously for {{e5_seconds}} s with the X-ray re-rendered every frame, and memory. Configurations were headless Chromium on the integrated GPU, headless Chromium with software rendering, and a visible window on the discrete GPU.

**Use of AI tools.** Claude Code (Anthropic) was used for software development, analysis scripts, figure generation and manuscript drafting, under the authors' direction. The authors verified all code, results and text and take responsibility for them.

# 3 Results
Table 2 summarises the results; the full tables, derivations and per-pose outputs are in Online Resource 2.

@@TABLE 2@@

**Existing tests.** The repository's own test suite passed: {{tests_pytest}} Python tests, {{tests_vitest}} TypeScript tests and {{tests_e2e}} browser suites.

**E1.** Over {{e1_grid_poses}} grid poses and {{e1_points}} points, the float64 browser path differed from the reference by at most {{e1_overlay_max_px}} px, and the float32 GPU path by at most {{e1_vertex_max_px}} px ({{e1_vertex_max_um}} µm at the detector; Fig. 3a; Table 2).

**E1b.** All {{e1b_pass}} of {{e1b_images}} rendered images met the acceptance rule. The minimum r was {{e1b_r_min}}, the maximum mean absolute error {{e1b_mae_max}} mm, the maximum centroid shift {{e1b_centroid_max}} px and the minimum IoU {{e1b_iou_min}} (Fig. 3b). Mirrored images correlated with the reference at most r = {{e1b_mirror_lr_max}} (left-right, at {{e1b_mirror_lr_worst_pose}}) and r = {{e1b_mirror_ud_max}} (up-down), so the comparison could tell a mirrored image at every pose (Fig. 3c).

@@FIG 3@@

**E2.** With the first phantom, the correct render passed at {{e2_v1_pass}} of {{e2_v1_views}} views. At the classic spider view (LAO 45/caudal 30) the R and F letters overlapped in projection and formed {{e2_v1_overlap_components}} connected regions instead of three, so the rule failed, although the render agreed with the derivation (IoU {{e2_v1_overlap_iou}}; Fig. 4e). This was a flaw of the phantom. With the second phantom, the correct render passed at {{e2_v2_pass}} of {{e2_v2_views}} views (Fig. 4a, f), with IoU ≥ {{e2_v2_iou_min}} and every letter within {{e2_v2_err_max_px}} px ({{e2_v2_err_max_mm}} mm) of its predicted position. All {{e2_v2_hand_ok}} letters at non-lateral views had the predicted handedness. Every applicable negative control was rejected: {{e2_v2_mirror_lr_det}}/{{e2_v2_mirror_lr_app}} left-right mirrors, {{e2_v2_swap_lao_rao_det}}/{{e2_v2_swap_lao_rao_app}} LAO/RAO swaps, {{e2_v2_swap_cran_caud_det}}/{{e2_v2_swap_cran_caud_app}} cranial/caudal swaps and {{e2_v2_mirror_ud_det}}/{{e2_v2_mirror_ud_app}} up-down mirrors (Fig. 4b–d). Their IoU with the expected image was at most {{e2_v2_neg_iou_max}}.

@@FIG 4@@

**E3.** All {{e3_logic_ok}} option sets generated over the full angle grid were valid: four distinct options, one correct, each matching its label's angles. The logic declined only the {{e3_logic_threw}} sets whose target lay within 5° of AP on both axes, a zone the target generator never produced. In the rendered items, the correct option's vessel image matched the exact reference (IoU ≥ {{e3_correct_iou_cpu_min}}), and the label of all {{e3_label_ok}} of {{e3_candidates}} options was its best-matching hypothesis (r ≥ {{e3_r_label_min}}; margin over the next hypothesis ≥ {{e3_margin_min}}). Pairwise IoU between options had a median of {{e3_iou_median}} and a maximum of {{e3_iou_max}} (Fig. 5e). The item-specific near-duplicate threshold ranged from {{e3_tau_min}} to {{e3_tau_max}}, and {{e3_flagged}} of {{e3_pairs}} pairs reached it; the closest pair stayed {{e3_tau_gap_min}} below its threshold. The structural similarity index [@wang2004] did not discriminate between options: it lay between {{e3_ssim_min}} and {{e3_ssim_max}} for every pair, because the sparse vessel masks share a large empty background (Online Resource 2).

@@FIG 5@@

The correct tile was byte-identical to an independent render in {{e3_tiles_identical_correct}} of {{e3_items}} items, and all four tiles in {{e3_tiles_identical_all}}. In the remaining {{e3_tile_diff_items}} items a tile differed by {{e3_tile_diff_min_bytes}}–{{e3_tile_diff_max_bytes}} bytes. A follow-up showed that repeated renders of the same pose occasionally differ ({{probe_repeats_diff}} of {{probe_repeats}}) in small patches outside the vessels, by up to {{probe_max_dv}} grey levels, and that these differences do not recur for the same items. We attribute them to run-to-run nondeterminism of the GPU rendering; vessel pixels, positions and labels were unaffected.

**E5.** On the integrated GPU, the start scene loaded cold in {{e5_igpu_load_scene1_ms_s}} s and the angiography scene in {{e5_igpu_load_scene4_ms_s}} s (medians). The app held {{e5_igpu_fps_median_median}} frames/s during continuous rotation, with a 95th-percentile frame time of {{e5_igpu_frame_p95_ms_median}} ms and {{e5_igpu_js_heap_mb_after_rotation_median}} MB of JavaScript heap. On the discrete GPU in a visible window the values were {{e5_dgpu_load_scene1_ms_s}} s, {{e5_dgpu_load_scene4_ms_s}} s and {{e5_dgpu_fps_median_median}} frames/s. With software rendering the frame rate fell to {{e5_sw_fps_median_median}} frames/s, so a GPU is required (Table 2).

# 4 Discussion
AngioLens renders what its stated conventions say it should. E1 and E1b show that what the learner sees is the reference geometry, without rasterisation or precision errors that matter at the scale of a pixel. E2 shows that the shared convention is the intended one: positions and handedness match a derivation from the DICOM angle definitions and the usual display convention, and each class of sign or mirror error produces an image the test rejects. E3 shows that every Predict distractor is the error it names and is clearly different from the correct image.

These properties matter for a training tool because its errors are silent. A mirrored or sign-reversed image of a coronary tree still looks like a coronary tree. Specifying the conventions, deriving expected images independently and testing deliberately wrong renders turns "looks right" into a check that can fail. The same harness can be rerun after any change to the code.

The negative controls also show what an image test can and cannot detect. At AP the LAO/RAO swap, and at zero tilt the cranial/caudal swap, leave the image unchanged; no test can distinguish them, and the Predict logic correctly avoids offering such options. A mirror reverses the handedness of the phantom letters, whereas angle-sign swaps do not; position is therefore needed to detect swaps.

Compared with other tools (Table 1), AngioLens is distinguished less by its features than by being open, running in a browser, and documenting and testing its conventions. AngioView [@rahman2026angioview] offers comparable interactive C-arm control on mobile devices, and 3D-printed models [@sabbak2022] offer a physical alternative. Publicly available descriptions of these tools do not report verification of projection geometry; this is a statement about reporting, not about their correctness.

@@TABLE 1@@

**Limitations.** The verification uses one atlas anatomy and synthetic phantoms. Anatomical variation, such as dominance or anomalous origins, is not represented, and the atlas lacks named diagonal, obtuse marginal and posterior descending branches. Segment-level foreshortening against recommended views was therefore not assessed; this is future work. The rendering is a path-length model without scatter, motion blur or contrast dynamics, so the images teach geometry, not image quality. The first phantom had overlapping letters at one view; the second phantom resolved this, and both are reported. A few tiles differed by some bytes between renders, outside the vessels, and the cause was attributed but not proven. Performance was measured on one laptop. Finally, we did not evaluate learning: whether verified geometry and misconception-based distractors improve trainees' view selection requires a separate study.

# 5 Conclusion
AngioLens is an open, browser-based coronary angiography projection simulator whose conventions are specified and tested against an independent derivation, and whose quiz distractors are verified to be the errors they name. Its educational effect remains to be studied.

# ONLINE RESOURCES
**Online Resource 1** AngioLens demonstration video (narrated tour of the six scenes and Predict mode)

**Online Resource 2** Full verification tables, derivations and per-experiment outputs (E1, E1b, E2 with both phantoms, E3 including the structural similarity index, E5)

# STATEMENTS
**Funding** No funding was received for conducting this study.

**Competing interests** The authors have no competing interests to declare that are relevant to the content of this article.

**Ethics approval** This study did not involve human participants, human data, or animals.

**Consent to participate** Not applicable.

**Consent to publish** Not applicable.

**Data availability** All verification outputs (CSV and JSON) and the scripts that produce them are in the code repository. Renders of the Z-Anatomy atlas can be regenerated from the atlas, which is available from its original source [@zanatomy].

**Code availability** AngioLens is available at https://github.com/Rugved3-droid/angiolens under the MIT licence. This paper describes release tag v1.1, commit 198c6d4da1f980cdaa301f5131ccb83ebffb5be1. The verification harness is on the branch paper/ijcars-verification.

**Author contributions** Rugved Parmar: conceptualization, software, methodology, formal analysis, visualization, writing – original draft. Md Fahim: software review, validation, writing – review and editing. Shreya P. Trivedi: supervision, writing – review and editing.

# CAPTIONS
FIG 1: **Fig. 1** AngioLens architecture and angle conventions. **a** Data flow from the Z-Anatomy atlas through the C-arm geometry to the GPU-rendered angiogram and Predict mode; dashed double arrows mark the comparisons of experiments E1 (TypeScript versus Python geometry) and E1b (GPU versus exact CPU image). **b** Axial schematic seen from the feet: detector (dark bar) and beam (arrow) at AP (solid), LAO 40 (dashed) and RAO 30 (dotted). **c** Sagittal schematic seen from the patient's left: AP (solid), cranial 30 (dashed) and caudal 25 (dotted). Script: fig1_architecture.py
FIG 2: **Fig. 2** The same atlas coronary anatomy at four named views of the app, each shown as the 3D scene from behind the detector (left half) beside the rendered angiogram (right half). **a** RAO 30/caudal 25, left coronary injection. **b** LAO 40/caudal 30 (spider), left coronary injection. **c** RAO 30, right coronary injection. **d** LAO 45, right coronary injection. Anatomy: Z-Anatomy (CC BY-SA 4.0), derived in part from BodyParts3D. Script: fig_capture.mjs, fig2_views.py
FIG 3: **Fig. 3** Agreement over the 5° angle grid (primary angle horizontal, secondary angle vertical); circles mark the named views. **a** E1: maximum discrepancy between the app's float32 GPU projection and the Python reference over {{e1_points}} centerline points, in units of 10^−4^ pixel. **b** E1b: maximum centroid shift between the app's rendered image and the exact reference over the two coronary trees, in units of 10^−3^ pixel. **c** E1b: correlation of the left-right mirrored app image with the reference (maximum over the two trees); low values show the comparison detects a mirror. Scripts: e1_projection_agreement.py, e1b_render_agreement.py, fig3_agreement.py
FIG 4: **Fig. 4** E2 orientation phantom. Rendered path length (dark) with the outline expected from the first-principles derivation (dashed). **a** Second phantom, correct render at LAO 40/caudal 30. **b** The same render mirrored left-right. **c** Render with the LAO/RAO sign swapped. **d** Render with the cranial/caudal sign swapped. **e** First phantom at LAO 45/caudal 30, where two letters overlap. **f** Second phantom at the same view. Panels b–d are negative controls and were rejected. Scripts: e2_orientation.py, fig4_phantom.py
FIG 5: **Fig. 5** Predict mode. **a–d** The four options of one item (target LAO 40/caudal 30, left coronary injection, mirror setting on) exactly as rendered by the app: correct view, LAO/RAO reversed, cranial/caudal reversed and left-right mirror, in the order {{fig5_order}}. **e** Pairwise IoU of binary vessel masks between options over {{e3_items}} items, by pair type (grey boxes: pairs including the correct option; hatched: pairs of distractors). Dashed line: smallest item-specific near-duplicate threshold ({{e3_tau_min}}). Scripts: e3_distractors.py, fig_capture.mjs, fig5_predict.py

# TABLE 1
CAPTION: **Table 1** Interactive coronary angiography training tools, as documented in their published descriptions
HEADER: Tool | Platform | 3D coronary anatomy | User-set C-arm angles | Misconception-based distractors | Projection verification reported | Source code
ROW: AngioAID 3D [@samtani2024] | Mobile^a^ | NR | NR | NR | NR | NR
ROW: AngioView [@rahman2026angioview] | iPhone, iPad^b^ | Yes^b^ | Yes^b^ | NR | NR | NR
ROW: 3D-printed models [@sabbak2022] | Physical model^a^ | Yes^a^ | NR | NR | NR | Not applicable
ROW: AngioLens (this work) | Web browser | Yes | Yes | Yes | Yes (E1–E3) | Open (MIT)
FOOT: NR, not reported in the cited description. ^a^ From the title of the conference abstract; the abstract text was not available to the authors. ^b^ From the app store description (version 1.0.4, accessed 14 November 2026).

# TABLE 2
CAPTION: **Table 2** Summary of the verification experiments
HEADER: Experiment | Scope | Result
ROW: E1 projection agreement | {{e1_poses_total}} poses × {{e1_points}} points | Max discrepancy {{e1_overlay_max_px}} px (float64), {{e1_vertex_max_px}} px (float32 GPU path)
ROW: E1b image agreement | {{e1b_images}} images (2 trees) | r ≥ {{e1b_r_min}}; MAE ≤ {{e1b_mae_max}} mm; centroid shift ≤ {{e1b_centroid_max}} px; mirrored r ≤ {{e1b_mirror_lr_max}}
ROW: E2 orientation, phantom 1^a^ | {{e2_v1_views}} named views | Correct render passed {{e2_v1_pass}}/{{e2_v1_views}}
ROW: E2 orientation, phantom 2 | {{e2_v2_views}} named views | Passed {{e2_v2_pass}}/{{e2_v2_views}}; negative controls rejected {{e2_v2_mirror_lr_det}}/{{e2_v2_mirror_lr_app}}, {{e2_v2_swap_lao_rao_det}}/{{e2_v2_swap_lao_rao_app}}, {{e2_v2_swap_cran_caud_det}}/{{e2_v2_swap_cran_caud_app}}, {{e2_v2_mirror_ud_det}}/{{e2_v2_mirror_ud_app}}^b^
ROW: E3 option logic | {{e3_logic_ok}} option sets | All valid
ROW: E3 rendered items | {{e3_items}} items, {{e3_candidates}} options | Labels confirmed {{e3_label_ok}}/{{e3_candidates}}; near-duplicates {{e3_flagged}}/{{e3_pairs}} pairs; max IoU {{e3_iou_max}}
ROW: E5 performance, integrated GPU | {{e5_reps}} runs | Cold load {{e5_igpu_load_scene1_ms_s}} s; {{e5_igpu_fps_median_median}} frames/s
ROW: E5 performance, discrete GPU | {{e5_reps}} runs | Cold load {{e5_dgpu_load_scene1_ms_s}} s; {{e5_dgpu_fps_median_median}} frames/s
ROW: E5 performance, software rendering | {{e5_reps}} runs | {{e5_sw_fps_median_median}} frames/s
FOOT: MAE, mean absolute error of path length. ^a^ Failed at one view because two phantom letters overlapped in projection. ^b^ Left-right mirror, LAO/RAO swap, cranial/caudal swap, up-down mirror; swaps of a zero angle are not applicable.
