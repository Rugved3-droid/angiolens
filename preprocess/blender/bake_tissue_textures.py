"""Bake seamless procedural tissue textures (v1.1 item 3b; display only).

    powershell -File preprocess\\blender\\run_blender.ps1 -Empty -MinFreeGB 1 -Script preprocess\\blender\\bake_tissue_textures.py `
      -Log assets\\textures\\bake_log.txt -ScriptArgs "assets\\textures"

Each map is a procedural Blender node tree baked (Cycles, EMIT) on a unit plane. Seamless tiling is exact: the plane's
(u, v) go onto a torus in 4D, (cos 2pi u, sin 2pi u, cos 2pi v) + W = sin 2pi v, fed to the 4D Noise / Voronoi textures, so
the field is periodic in u and v. Outputs (PNG, 1024 square; heights become normal maps in build_tissue_textures.py):
  myo_albedo, myo_height, myo_rough      myocardium: dark red-brown with subtle patchy variation, fine fibre striation
  cor_height                             coronary wall: fine longitudinal ridges + micro-noise
  fat_albedo, fat_height, fat_rough      epicardial fat: ivory-yellow lobules (Voronoi cells), soft
"""
import math
import sys
from pathlib import Path

import bpy

OUT = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = 1024

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 4
scene.cycles.use_denoising = False
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.mesh.primitive_plane_add(size=1.0)
plane = bpy.context.active_object


def torus_coords(nt):
    """(u, v) -> 4D torus: returns (vector socket of (cos 2pi u, sin 2pi u, cos 2pi v), W socket = sin 2pi v)."""
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs[0])

    def trig(src, fn):
        m = nt.nodes.new("ShaderNodeMath"); m.operation = "MULTIPLY"; m.inputs[1].default_value = 2 * math.pi
        nt.links.new(src, m.inputs[0])
        t = nt.nodes.new("ShaderNodeMath"); t.operation = fn
        nt.links.new(m.outputs[0], t.inputs[0])
        return t.outputs[0]
    cu, su = trig(sep.outputs["X"], "COSINE"), trig(sep.outputs["X"], "SINE")
    cv, sv = trig(sep.outputs["Y"], "COSINE"), trig(sep.outputs["Y"], "SINE")
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(cu, comb.inputs[0]); nt.links.new(su, comb.inputs[1]); nt.links.new(cv, comb.inputs[2])
    return comb.outputs[0], sv, cu, su, cv


def noise4(nt, vec, w, scale, detail=4.0, rough=0.55, distortion=0.0):
    n = nt.nodes.new("ShaderNodeTexNoise"); n.noise_dimensions = "4D"
    n.inputs["Scale"].default_value = scale; n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough; n.inputs["Distortion"].default_value = distortion
    nt.links.new(vec, n.inputs["Vector"]); nt.links.new(w, n.inputs["W"])
    return n.outputs["Fac"]


def voronoi4(nt, vec, w, scale, feature="F1", metric="EUCLIDEAN"):
    v = nt.nodes.new("ShaderNodeTexVoronoi"); v.voronoi_dimensions = "4D"; v.feature = feature; v.distance = metric
    v.inputs["Scale"].default_value = scale
    nt.links.new(vec, v.inputs["Vector"]); nt.links.new(w, v.inputs["W"])
    return v.outputs["Distance"]


def math_node(nt, op, a, b=None, clamp=False):
    m = nt.nodes.new("ShaderNodeMath"); m.operation = op; m.use_clamp = clamp
    for i, x in enumerate((a, b)):
        if x is None:
            continue
        if isinstance(x, (int, float)):
            m.inputs[i].default_value = x
        else:
            nt.links.new(x, m.inputs[i])
    return m.outputs[0]


def ramp(nt, fac, stops):
    r = nt.nodes.new("ShaderNodeValToRGB")
    els = r.color_ramp.elements
    while len(els) > 2:
        els.remove(els[-1])
    for i, (pos, col) in enumerate(stops):
        e = els[i] if i < 2 else els.new(pos)
        e.position = pos; e.color = (*col, 1.0)
    nt.links.new(fac, r.inputs["Fac"])
    return r.outputs["Color"]


def bake(name, build):
    """build(nt, vec, w, cu, su, cv) -> color socket; bakes it to OUT/name.png."""
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    vec, w, cu, su, cv = torus_coords(nt)
    nt.links.new(build(nt, vec, w, cu, su, cv), em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    img = bpy.data.images.new(name, RES, RES, float_buffer=False)
    img.colorspace_settings.name = "sRGB" if name.endswith("albedo") else "Non-Color"
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = img
    nt.nodes.active = tex
    plane.data.materials.clear(); plane.data.materials.append(mat)
    bpy.context.view_layer.objects.active = plane; plane.select_set(True)
    bpy.ops.object.bake(type="EMIT", margin=0)
    img.filepath_raw = str(OUT / f"{name}.png"); img.file_format = "PNG"; img.save()
    print("baked", name)


# ---- myocardium ----
def myo_albedo(nt, vec, w, *_):
    patch = noise4(nt, vec, w, 2.2, 3, 0.5)                  # large, soft patches
    fine = noise4(nt, vec, w, 18.0, 6, 0.6)
    f = math_node(nt, "ADD", math_node(nt, "MULTIPLY", patch, 0.75), math_node(nt, "MULTIPLY", fine, 0.25))
    return ramp(nt, f, [(0.25, (0.20, 0.055, 0.04)), (0.55, (0.30, 0.085, 0.06)), (0.85, (0.38, 0.12, 0.085))])


def fibre(nt, vec, w, cu, su, cv, freq=12.0, warp=1.3):
    """Fine striation: a sine of the torus angle along one axis, warped by noise (fibres are never straight)."""
    n = noise4(nt, vec, w, 2.0, 3, 0.55)
    ang = nt.nodes.new("ShaderNodeMath"); ang.operation = "ARCTAN2"
    nt.links.new(su, ang.inputs[0]); nt.links.new(cu, ang.inputs[1])
    a = math_node(nt, "ADD", math_node(nt, "MULTIPLY", ang.outputs[0], freq), math_node(nt, "MULTIPLY", n, warp * 2 * math.pi))
    return math_node(nt, "MULTIPLY", math_node(nt, "ADD", math_node(nt, "SINE", a), 1.0), 0.5)


def myo_height(nt, vec, w, cu, su, cv):
    s = fibre(nt, vec, w, cu, su, cv)
    micro = noise4(nt, vec, w, 40.0, 4, 0.6)
    blot = noise4(nt, vec, w, 7.0, 5, 0.6)                   # irregular relief dominates; the fibre is only a hint
    h = math_node(nt, "ADD", math_node(nt, "ADD", math_node(nt, "MULTIPLY", s, 0.22), math_node(nt, "MULTIPLY", micro, 0.3)),
                  math_node(nt, "MULTIPLY", blot, 0.48))
    return ramp(nt, h, [(0.0, (0, 0, 0)), (1.0, (1, 1, 1))])


def myo_rough(nt, vec, w, *_):
    n = noise4(nt, vec, w, 6.0, 4, 0.55)                     # wet: mostly smooth, with a little variation
    return ramp(nt, n, [(0.3, (0.26, 0.26, 0.26)), (0.75, (0.46, 0.46, 0.46))])


# ---- coronary wall ----
def cor_height(nt, vec, w, cu, su, cv):
    s = fibre(nt, vec, w, cu, su, cv, freq=18.0, warp=0.8)
    micro = noise4(nt, vec, w, 60.0, 3, 0.5)
    return ramp(nt, math_node(nt, "ADD", math_node(nt, "MULTIPLY", s, 0.5), math_node(nt, "MULTIPLY", micro, 0.5)),
                [(0.0, (0, 0, 0)), (1.0, (1, 1, 1))])


# ---- epicardial fat ----
def fat_cells(nt, vec, w):
    f1 = voronoi4(nt, vec, w, 5.5, "F1")
    f2 = voronoi4(nt, vec, w, 5.5, "F2")
    edge = math_node(nt, "SUBTRACT", f2, f1)                 # 0 on a lobule border, larger inside
    return f1, edge


def fat_albedo(nt, vec, w, *_):
    f1, edge = fat_cells(nt, vec, w)
    tint = noise4(nt, vec, w, 4.0, 3, 0.5)
    e = math_node(nt, "MULTIPLY", math_node(nt, "POWER", math_node(nt, "MINIMUM", math_node(nt, "MULTIPLY", edge, 6.0), 1.0), 0.6), 0.75)
    f = math_node(nt, "ADD", e, math_node(nt, "MULTIPLY", tint, 0.25))
    return ramp(nt, f, [(0.15, (0.62, 0.46, 0.20)), (0.55, (0.86, 0.73, 0.42)), (0.95, (0.95, 0.87, 0.62))])


def fat_height(nt, vec, w, *_):
    f1, edge = fat_cells(nt, vec, w)
    dome = math_node(nt, "SUBTRACT", 1.0, math_node(nt, "MULTIPLY", f1, 1.6), clamp=True)   # each lobule a soft dome
    border = math_node(nt, "MINIMUM", math_node(nt, "MULTIPLY", edge, 5.0), 1.0)
    return ramp(nt, math_node(nt, "MULTIPLY", math_node(nt, "POWER", dome, 0.7), border), [(0.0, (0, 0, 0)), (1.0, (1, 1, 1))])


def fat_rough(nt, vec, w, *_):
    f1, edge = fat_cells(nt, vec, w)
    return ramp(nt, math_node(nt, "MINIMUM", math_node(nt, "MULTIPLY", edge, 4.0), 1.0), [(0.0, (0.55, 0.55, 0.55)), (1.0, (0.3, 0.3, 0.3))])


for name, fn in [("myo_albedo", myo_albedo), ("myo_height", myo_height), ("myo_rough", myo_rough), ("cor_height", cor_height),
                 ("fat_albedo", fat_albedo), ("fat_height", fat_height), ("fat_rough", fat_rough)]:
    bake(name, fn)
print("done")
