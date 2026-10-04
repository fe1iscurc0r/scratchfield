"""W59-02 生物质分子势基准原型测试（pytest，≥4 用例）。

运行：python -m pytest tools/test_biomass_mlip_bench.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from biomass_mlip_bench import (
    DATA_DIR,
    MOLECULES,
    MORSE,
    KernelRidge,
    benchmark,
    generate_dataset,
    load_dataset,
    morse_energy,
    morse_force,
)


def test_morse_force_is_negative_energy_gradient():
    r = np.linspace(0.7, 1.3, 50)
    D, a, r0 = MORSE["葡萄糖"]
    f_analytic = morse_force(r, D, a, r0)
    h = 1e-5
    f_numeric = -(morse_energy(r + h, D, a, r0) - morse_energy(r - h, D, a, r0)) / (2 * h)
    assert np.allclose(f_analytic, f_numeric, atol=1e-4)


def test_dataset_files_written():
    generate_dataset(n=20, seed=0, save=True)
    for name in MOLECULES:
        path = os.path.join(DATA_DIR, f"{name}.csv")
        assert os.path.exists(path), f"缺数据集文件: {path}"


def test_krr_beats_mean_baseline_on_energy():
    rows = benchmark()
    krr = {(m, n): (e, f) for m, n, e, f, t in rows}
    for name in MOLECULES:
        assert krr[("KRR基线", name)][0] < krr[("均值基线", name)][0], \
            f"KRR 能量 MAE 未优于均值基线: {name}"


def test_benchmark_table_covers_all_molecules_and_models():
    rows = benchmark()
    keys = {(m, n) for m, n, *_ in rows}
    for name in MOLECULES:
        for model in ("KRR基线", "均值基线"):
            assert (model, name) in keys, f"表格缺 {model}×{name}"


def test_force_mae_finite():
    rows = benchmark()
    for _, _, _, fmae, _ in rows:
        assert np.isfinite(fmae)
