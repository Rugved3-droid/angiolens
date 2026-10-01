"""D10 revision rules on a synthetic chest: vertebra with FOV-clipped cortex touching a contrast-filled
descending aorta, an opacified heart, a coronary lumen and dense SVC contrast."""
import numpy as np

from cpt.masks import bone_and_pool
from cpt.volume import Volume


def chest():
    sp = 0.8
    n = (150, 150, 50)
    x, y, z = np.meshgrid(*[(np.arange(k) - k / 2) * sp for k in n], indexing="ij")
    hu = np.full(n, -60.0, np.float32)                      # fat / soft tissue
    hu += np.random.default_rng(0).normal(0, 15, n)          # CT noise
    r_vert = np.hypot(x - 0, y - 40)
    hu[r_vert < 15] = 250                                     # cancellous
    hu[(r_vert >= 13) & (r_vert < 15.5)] = 950                # cortex
    aorta = np.hypot(x - 23.3, y - 30) < 9                    # ~0.8 mm of fat from the vertebral cortex
    hu[aorta] = 450
    heart = np.hypot(x - 5, y + 20) < 25
    hu[heart] = 400
    lumen = (np.hypot(x - 32, y + 20) < 1.8) & (np.abs(z) < 15)
    hu[lumen] = 480
    svc = np.hypot(x + 28, y + 5) < 5
    hu[svc] = 1400                                            # undiluted contrast inflow
    hu[y > 50] = -3024                                        # reconstruction FOV cuts the vertebra open
    A = np.diag([sp, sp, sp, 1.0])
    A[:3, 3] = [-n[0] / 2 * sp, -n[1] / 2 * sp, -n[2] / 2 * sp]
    return Volume(hu, A, "LPS"), lumen, dict(vert=r_vert < 12, aorta=aorta, heart=heart, svc=svc)


def frac(mask, region, inner=slice(5, -5)):
    sel = region[:, :, inner]
    return float(mask[:, :, inner][sel].mean())


def test_bone_and_pool_classification():
    ct, lumen, r = chest()
    bone, pool, rep = bone_and_pool(ct, lumen)
    y = ct.index_to_lps(np.argwhere(np.ones(ct.data.shape[:2] + (1,), bool)))[:, 1].reshape(ct.data.shape[:2])[:, :, None]
    vert_in_fov = r["vert"] & (ct.data > -1000)
    # the last ~2 mm at the FOV edge are smoothed against the -3024 padding and land in NEITHER mask
    # (so they keep their own HU in the DRR); everything deeper must be bone
    assert frac(bone, vert_in_fov & (y <= 48)) == 1.0, "cancellous vertebra (open cortex at FOV edge) must be bone"
    assert frac(pool, vert_in_fov) == 0.0, "no vertebral voxel may be suppressed as blood"
    assert frac(pool, r["aorta"]) > 0.95 and frac(bone, r["aorta"]) < 0.05, "descending aorta must be pool"
    assert frac(pool, r["heart"]) > 0.95
    assert frac(bone, r["svc"]) == 0.0, "dense SVC contrast must never be bone"
    assert frac(pool, r["svc"]) > 0.95, "dense SVC contrast must be suppressed with the pool"
    assert not (bone & lumen).any() and not (pool & lumen).any(), "coronary lumen is handled separately"
    assert not (bone & pool).any()
