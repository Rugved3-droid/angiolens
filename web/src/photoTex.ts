// v1.1 PHOTOREAL tissue (feature flag "peel"; display only): Blender-baked seamless tiles (preprocess/blender/
// bake_tissue_textures.py -> build_tissue_textures.py), applied by TRIPLANAR mapping in world (= LPS mm) space at the rest
// position, so no UVs are needed and the atlas meshes stay untouched.
// One PACKED texture per tissue (3 taps per pixel, not 9; the frame-rate budget):
//   RG  tangent normal xy (z rebuilt)   fine fibre / lobule relief
//   B   roughness                        a wet sheen
//   A   colour variation (0.5 = the material's own colour)
import * as THREE from "three";

export interface PhotoSet { pack: THREE.Texture; scale: number; strength: number; colorVar: number; roughMix: number }

const loader = new THREE.TextureLoader();
function tex(url: string) {
  const t = loader.load(url);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.colorSpace = THREE.NoColorSpace;
  t.anisotropy = 4;
  return t;
}
const base = `${import.meta.env.BASE_URL}anatomy/textures/`;
/** tile sizes (mm per repeat) chosen for the scale of the features: fibre relief ~ a few mm, fat lobules ~3 mm */
export const PHOTO = {
  myo: (): PhotoSet => ({ pack: tex(`${base}myo_pack.png`), scale: 1 / 46, strength: 0.22, colorVar: 0.32, roughMix: 0.8 }),
  cor: (): PhotoSet => ({ pack: tex(`${base}cor_pack.png`), scale: 1 / 9, strength: 0.35, colorVar: 0, roughMix: 0 }),
  fat: (): PhotoSet => ({ pack: tex(`${base}fat_pack.png`), scale: 1 / 16, strength: 0.9, colorVar: 0.45, roughMix: 0.8 }),
};

/** GLSL for one photo set: uniforms, a fragment head, and the colour / roughness / normal insertions. */
export function photoChunks(p: PhotoSet) {
  const uniforms: Record<string, THREE.IUniform> = {
    uPhPack: { value: p.pack }, uPhScale: { value: p.scale }, uPhStr: { value: p.strength }, uPhVar: { value: p.colorVar },
    uPhRough: { value: p.roughMix },
  };
  const head = /* glsl */ `
    uniform sampler2D uPhPack; uniform float uPhScale; uniform float uPhStr; uniform float uPhVar; uniform float uPhRough;
    varying vec3 vPhN;
    vec4 phT;     // the blended triplanar sample (colour variation: A, roughness: B)
    vec3 phNw;    // the triplanar world normal`;
  // sampled once, at the colour stage (it runs first); the roughness and normal stages reuse phT / phNw
  const sample = /* glsl */ `
    { vec3 N = normalize(vPhN); vec3 b = pow(abs(N), vec3(4.0)); vec3 w = b / (b.x + b.y + b.z); vec3 pp = vRest * uPhScale;
      vec4 sx = texture2D(uPhPack, pp.zy), sy = texture2D(uPhPack, pp.xz), sz = texture2D(uPhPack, pp.xy);
      phT = sx * w.x + sy * w.y + sz * w.z;
      vec2 nx = (sx.xy * 2.0 - 1.0) * uPhStr, ny = (sy.xy * 2.0 - 1.0) * uPhStr, nz = (sz.xy * 2.0 - 1.0) * uPhStr;
      vec3 tx = vec3(nx + N.zy, N.x), ty = vec3(ny + N.xz, N.y), tz = vec3(nz + N.xy, N.z);   // whiteout blend
      phNw = normalize(tx.zyx * w.x + ty.xzy * w.y + tz.xyz * w.z); }`;
  const albedo = sample + (p.colorVar > 0 ? /* glsl */ `
    diffuseColor.rgb *= 1.0 + (phT.a - 0.5) * 2.0 * uPhVar;` : "");
  const rough = p.roughMix > 0 ? /* glsl */ `
    roughnessFactor = mix(roughnessFactor, phT.b, uPhRough);` : "";
  const normal = /* glsl */ `
    normal = normalize(mix(normal, faceDirection * normalize((viewMatrix * vec4(phNw, 0.0)).xyz), 0.85));`;
  return { uniforms, head, albedo, rough, normal };
}
