# Drop the artist heart model here

- Format: **GLB (preferred) or OBJ (+ .mtl and textures)**. FBX cannot be read on this machine (no Blender);
  export to GLB from Blender/your tool, keeping the coronaries as **separate objects**.
- Put the license next to it (`LICENSE.txt`, or the store page text / URL in `SOURCE.txt`).
- Then run:
  `.\.venv\Scripts\python preprocess\scripts\inspect_heart_model.py assets\heart\<file>.glb`
  It reports the license text it found and whether the coronaries are real tube geometry or texture-only.
- This folder is git-ignored until the license is checked and allows committing.
