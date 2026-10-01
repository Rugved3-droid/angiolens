"""Non-expert extension: traces a contrast vessel beyond an expert endpoint, never touches expert data."""
import numpy as np

from cpt.extension import trace_extension
from cpt.volume import Volume


def scene():
    sp = 0.4
    n = (160, 120, 60)
    x, y, z = np.meshgrid(*[(np.arange(k) - k / 2) * sp for k in n], indexing="ij")
    hu = np.full(n, 30.0, np.float32) + np.random.default_rng(1).normal(0, 12, n)
    expert = (np.hypot(y, z) < 1.0) & (x < 0)                 # expert-annotated vessel ends at x = 0
    hu[expert] = 480
    cont = (np.hypot(y, z) < 0.7) & (x >= 0) & (x < 20)        # thinner, dimmer unannotated continuation
    hu[cont] = 320
    A = np.diag([sp, sp, sp, 1.0])
    A[:3, 3] = [-n[0] / 2 * sp, -n[1] / 2 * sp, -n[2] / 2 * sp]
    return Volume(hu, A, "LPS"), expert


def test_traces_continuation_and_leaves_expert_mask_untouched():
    ct, expert = scene()
    before = expert.copy()
    r = trace_extension(ct, expert, np.zeros_like(expert), np.array([-0.2, 0.0, 0.0]), threshold=230)
    assert r["traceable"]
    longest = max(b["length_mm"] for b in r["branches"])
    assert 16 <= longest <= 21, longest
    assert all(b["end"][0] > 15 for b in r["branches"] if b["length_mm"] == longest)
    np.testing.assert_array_equal(expert, before)


def test_not_traceable_when_nothing_continues():
    ct, expert = scene()
    ct.data[ct.data == 320] = 30
    r = trace_extension(ct, expert, np.zeros_like(expert), np.array([-0.2, 0.0, 0.0]), threshold=230)
    assert not r["traceable"]
