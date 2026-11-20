<!--
Medical Science Educator, article type Innovation. Built by paper/mse/source/build_package.py.
Markup: {{key}} = paper/results/numbers.json (numbers come only from result files); [@a; @b] = references_mse.bib (numbered in
order of first citation); @@FIG n@@ / @@TABLE n@@ = placement; ^x^ superscript; **bold**; *italic*.
[VERIFY ...] and [AUTHOR INPUT ...] are placeholders for facts only the authors can supply; they are highlighted in the .docx and
listed in paper/mse/OPEN_ITEMS.md. HARD RULE: no learner outcome data anywhere.
-->
# TITLE
AngioLens: an open-source, browser-based simulator that makes coronary angiography projections visible and testable

# ABSTRACT
Reading coronary angiograms requires trainees to map two-dimensional images back to three-dimensional anatomy, using angle conventions that are easy to reverse: left versus right anterior oblique, and cranial versus caudal. These views are usually learned opportunistically in the catheterization laboratory, and dedicated simulators are costly and seldom teach projection geometry explicitly. We built AngioLens, a free, open-source simulator that runs in a web browser. It places an atlas coronary tree inside a virtual patient with a movable C-arm and shows the simulated angiogram beside the three-dimensional scene. Its Predict mode asks learners to pick the angiogram that matches a named view from four options whose distractors encode the common errors: oblique reversed, tilt reversed, both reversed, or a mirror image. Automated tests compare the projection with an independent reference and confirm that every distractor is the error it names. We used AngioLens in a teaching session for internal medicine residents, with Predict items as prompts for group discussion. Lessons for other programs include stating conventions explicitly, testing for silent mirror errors and checking graphics hardware before teaching. No learner outcomes are reported; a prospective evaluation is planned.

# ABSTRACT_SHORT
AngioLens is a free, open-source browser simulator linking three-dimensional coronary anatomy, a movable C-arm and the resulting angiogram. Its Predict mode uses distractors that encode common orientation errors. We describe its design, automated geometry verification, use in a resident teaching session, and lessons for programs adopting it.

# KEYWORDS
Coronary angiography; Simulation; Medical education; Open-source software; Graduate medical education

# MAIN
## The Problem
Coronary angiography shows a three-dimensional (3D) arterial tree as a series of two-dimensional projections. To choose or read a view, a trainee must work the mapping in both directions: predict which C-arm angle will open a given segment, and reconstruct the 3D course of a vessel from a flat image [@green2016]. The naming conventions add a second difficulty. Left anterior oblique (LAO) and right anterior oblique (RAO) name the side towards which the image detector is rotated, and cranial and caudal name the direction of its tilt. Each convention can be learned the wrong way round, and a mirrored or reversed image looks just as plausible as the correct one.

Most residents and fellows meet these views opportunistically in the catheterization laboratory, on patients, under radiation and contrast, and while the operator is busy. Simulation offers a safer setting. In a randomized trial, adding simulation training to didactic teaching helped trainees interpret coronary angiographic views [@lee2022], and simulator curricula have been built into cardiology fellowships for diagnostic angiography [@schimmel2016; @casey2016]. These programs relied on dedicated high-fidelity simulators, which carry purchase and maintenance costs that many training programs cannot meet, and in which projection geometry is a feature of the platform rather than the subject of teaching. Lower-cost alternatives exist, including a mobile 3D app [@rahman2026angioview], a mobile platform described in abstract form [@samtani2024] and 3D-printed models [@sabbak2022]. To our knowledge, none of them publishes its angle conventions in a form that can be checked. We wanted a free tool that makes the geometry explicit and lets a teacher see whether a learner has each convention the right way round.

## What Was Created
AngioLens is a web application built with three.js and WebGL. It runs in a desktop browser without installation. Six guided scenes lead from the beating heart, through the heart in the chest and a virtual catheterization laboratory, to the X-ray image, catheter engagement with contrast filling, and a cross-section of the vessel wall (Fig. 1). The anatomy is the open Z-Anatomy atlas [@zanatomy]: heart, coronary arteries, skeleton and a translucent body. The learner moves the C-arm to named views or to any angle, and the simulated angiogram updates beside the 3D scene, which can be seen from the room, from behind the detector or side by side. Angles follow the Digital Imaging and Communications in Medicine (DICOM) convention [@dicom_ps33], and the display convention is stated: the image is drawn as seen from the detector, so at the anteroposterior (AP) view the patient's left is on the right of the screen. A separate optional case uses coronary computed tomography angiography from ASOCA, a publicly available, de-identified dataset used under its terms of use [@gharleghi2022; @gharleghi2023]; these data are not redistributed with AngioLens.

@@FIG 1@@

The active-learning component is Predict mode (Fig. 2). Each round names a target view and shows four angiograms: the correct view, LAO/RAO reversed, cranial/caudal reversed, and both reversed or, as an option, a left-right mirror image. Distractors built from known misconceptions show which error a learner makes, not only whether the answer is wrong [@sadler1998; @hestenes1992]. After an answer, every option is labelled with the error it represents, and the C-arm in the 3D scene swings to the target so the reason for the image can be seen. Targets are standard views or random angles at least 15° from the current position. Near the AP view a reversal would reproduce the same image, so the app substitutes a mirror image. Items are generated rather than stored, so there is no fixed bank to memorize.

@@FIG 2@@

A mirrored or sign-reversed coronary tree still looks like a coronary tree, so we treated the geometry as something to test rather than to inspect (Table 1). The projection is implemented twice: in TypeScript for the app and in Python as a reference. Across {{e1_poses_total}} C-arm poses, the app's projection of {{e1_points}} centerline points differed from the reference by at most {{e1_vertex_max_px}} pixel. All {{e1b_images}} rendered angiograms matched an exact reference renderer, and mirrored images were detected at every pose. A synthetic phantom of letters, whose expected images were derived without the app's code, matched at {{e2_v2_pass}} of {{e2_v2_views}} named views, and every applicable mirrored or sign-swapped render was rejected. All {{e3_candidates}} options of {{e3_items}} generated Predict items were the error they were labelled as. AngioLens was developed with an artificial intelligence (AI) coding assistant, Claude Code (Anthropic), running the Claude Opus 5.5 model, from specifications written by the first author. The authors directed the work, reviewed and tested all code, and verified the geometry with the tests above, including a derivation of expected images made independently of the app's code. [VERIFY: no other AI tool was used for the software]

@@TABLE 1@@

## How It Was Implemented
AngioLens needs only a current desktop browser with WebGL and a graphics processor. There are no licence fees, accounts or plug-ins. The production build is a set of static files, which a program can serve from a laptop or from any static web host. The atlas meshes are generated once from Z-Anatomy with a scripted export, because third-party anatomy files are not stored in the repository. On a laptop with integrated graphics, the scenes loaded in about {{e5_igpu_load_scene1_ms_s}} s, and the angiogram was re-rendered at {{e5_igpu_fps_median_median}} frames per second while the C-arm rotated continuously. Without a graphics processor, software rendering fell to {{e5_sw_fps_median_median}} frames per second.

We used AngioLens in a teaching session for internal medicine residents at [VERIFY: institution and setting, e.g. noon conference or academic half-day] in [VERIFY: month and year]. The session lasted about [VERIFY: minutes] and was run by [VERIFY: which author] using a laptop and a projected screen [VERIFY]. The instructor first used the guided scenes to show how C-arm rotation and tilt move the detector around the patient, with the 3D scene and the angiogram side by side. Predict mode was then run as a group exercise: the instructor displayed an item, asked residents to commit to one of the four images before revealing the answer, and used the labelled distractors to discuss which convention each wrong image reverses while the C-arm swung to the target view [VERIFY: confirm this sequence matches the session]. This report includes no learner responses or assessment data. AngioLens also contains a study mode intended for a future formal evaluation; no data from it are reported here.

## What We Learned
First, a plausible image is not a correct one. A mirrored or sign-reversed angiogram is as convincing as the correct image, and the projection AngioLens uses is mirror-handed with respect to common graphics defaults, so code that relied on those defaults would draw plausible but wrong images. Writing the convention down and requiring deliberately mirrored and reversed renders to fail the tests were what made such errors detectable. Any program that modifies AngioLens should rerun its test suite, which passes at the cited release ({{tests_pytest}} Python tests, {{tests_vitest}} TypeScript tests and {{tests_e2e}} browser suites).

Second, the wrong options taught more than the right one. Because every distractor is a named error, the discussion after an answer could address which convention had been reversed rather than only what the correct view was. [AUTHOR INPUT: one or two sentences, from the authors' own observation, on how Predict items worked as discussion prompts in the session. Authors' observations only; no learner data.]

Third, interface details matter in a group setting. [AUTHOR INPUT: what the authors saw cause confusion at the interface level during the session, e.g. a control, label or camera view, and what was changed or would be changed.] Before teaching, the instructor should open AngioLens on the room computer and confirm that it is using the graphics processor, because software rendering is too slow for live rotation.

Fourth, an atlas has limits. The single atlas anatomy does not show variation in coronary dominance or branching, and the atlas does not name diagonal, obtuse marginal or posterior descending branches, so the instructor must supply segment-level teaching. The simulated angiogram shows vessel path length without scatter, motion or contrast dynamics. It teaches geometry, not image quality.

**Limitations** AngioLens has not been formally evaluated with learners, and nothing here demonstrates an effect on knowledge, skills or patient care. The anatomy is a simplified, single atlas. The catheter scenes are illustrative animations: there is no haptic feedback, vascular access or catheter manipulation. Performance was measured on one laptop. Software development was assisted by an AI coding tool; this is mitigated, but not removed, by the authors' review and by automated tests.

## Why It Is Useful to Others
AngioLens removes the two barriers that keep projection teaching in the catheterization laboratory: cost and the need for a dedicated simulator. Any program with a projector and a laptop can use it, and because the source code is open under the MIT licence, educators can add anatomy, change the preset views or translate the interface. The verification suite lets them check that their changes have not broken the geometry. Predict mode can be used in small-group teaching, by individuals for self-study, or as a warm-up before a catheterization laboratory rotation. Our next step is a prospective, ethics-approved evaluation of view recognition on previously unseen projections, with immediate and delayed tests, followed by use across several training sites.

# ONLINE RESOURCES
**Online Resource 1** AngioLens demonstration video (3 min 40 s): narrated tour of the scenes and Predict mode, recorded from the app. Also available at https://youtu.be/Bb-A4pW2P1M. Rendered from Z-Anatomy models (CC BY-SA 4.0), derived from BodyParts3D (DBCLS)

# STATEMENTS
**Funding** The authors did not receive support from any organization for the submitted work. [VERIFY]

**Competing interests** The authors have no relevant financial or non-financial interests to disclose. [VERIFY]

**Ethics approval** This article describes the development, technical verification and implementation of an educational tool. No data from human participants are reported. An optional case uses a publicly available, de-identified coronary computed tomography angiography dataset (ASOCA), used under its terms of use [@gharleghi2022; @gharleghi2023].

**Consent to participate** Not applicable.

**Consent to publish** Not applicable.

**Data availability** The verification scripts and their outputs are in the code repository on the branch paper/ijcars-verification (folder paper/results; commit ab82d63fe8a4fb3892097a2965e3a04a3f3acbff), whose application code is identical to the cited release tag.

**Code availability** AngioLens is available at https://github.com/Rugved3-droid/angiolens under the MIT licence (an Open Source Initiative-approved licence). This article describes release tag v1.1-ijcars, commit 198c6d4da1f980cdaa301f5131ccb83ebffb5be1. Third-party anatomy assets keep their own licences and are not in the repository.

**Author contributions** Rugved Parmar: conceptualization, software, verification, writing – original draft, writing – review and editing. Md Fahim: software, testing, writing – review and editing. Adam Budzikowski: supervision, writing – review and editing. All authors read and approved the final manuscript. [VERIFY]

**Use of AI** AngioLens was developed with Claude Code (Anthropic; Claude Opus 5.5 model) for software development, including the verification scripts and the figure-generation scripts. Claude Code with the same model was used to draft and edit this manuscript, all its sections, the figure layouts and the cover letter, under the authors' direction. The authors reviewed and edited all text, checked every reference against Crossref or PubMed, and take full responsibility for the content of this article. [VERIFY: model versions used over the whole project, and any other AI tool]

# CAPTIONS
FIG 1: **Fig. 1** The AngioLens atlas experience at the same right anterior oblique (RAO) caudal view. **a** Room view: the C-arm, its beam and the image detector around a translucent virtual patient, with the simulated angiogram in the inset (lower left). **b** Side-by-side view: the 3D heart and coronary arteries (left) beside the angiogram formed on the detector (right). The toolbar (top) steps through the six scenes. Screenshots of AngioLens; anatomy rendered from Z-Anatomy models (CC BY-SA 4.0), derived from BodyParts3D (DBCLS)
FIG 2: **Fig. 2** Predict mode. **a** A question: which of four angiograms is RAO 53/cranial 35 (right coronary injection). **b** After the answer, each option is labelled with its angles and the error it encodes (both signs reversed; correct; LAO/RAO sign reversed; cranial/caudal sign reversed), the chosen option is outlined and marked as correct in text, and the C-arm swings to the target view. Screenshots of AngioLens; anatomy rendered from Z-Anatomy models (CC BY-SA 4.0), derived from BodyParts3D (DBCLS)

# TABLE 1
CAPTION: **Table 1** Technical verification of AngioLens (release v1.1-ijcars)
HEADER: Check | What was compared | Result
ROW: Projection agreement | App projection versus an independent Python reference; {{e1_poses_total}} C-arm poses × {{e1_points}} centerline points | Maximum difference {{e1_vertex_max_px}} pixel
ROW: Image agreement | App angiogram versus an exact reference renderer; {{e1b_images}} images over a 5° angle grid | All matched (Pearson r ≥ {{e1b_r_min}}); mirrored images detected at every pose
ROW: Orientation | Letter phantom versus expected images derived without the app's code; {{e2_v2_views}} named views | Correct at {{e2_v2_pass}}/{{e2_v2_views}}^a^; all applicable mirrored and sign-swapped renders rejected
ROW: Predict distractors | {{e3_items}} generated items, {{e3_candidates}} options | Every option was the error it was labelled as; no near-duplicate options (maximum vessel overlap {{e3_iou_max}})
ROW: Performance | Laptop with integrated graphics, {{e5_reps}} runs | {{e5_igpu_fps_median_median}} frames/s; {{e5_sw_fps_median_median}} frames/s with software rendering
ROW: Test suite | Repository unit and browser tests | {{tests_pytest}} Python and {{tests_vitest}} TypeScript tests, {{tests_e2e}} browser suites passed
FOOT: ^a^ A first phantom was correct at {{e2_v1_pass}}/{{e2_v1_views}} views; at the remaining view two of its letters overlapped in projection, a flaw of the phantom, so one letter was moved. Full methods and outputs are in the code repository
