"""工单 265 · P0-4 验收：仿真标定集。

验收来源：轮48 报告 §6 表 P0-4 ——
  「3 组不同粒径仿真，α(f) 幂律拟合指数随粒径**单调**变化；数据集 < 50 MB」

⚠️ 口径说明（重要）：这里用**局部幂律指数 @10 MHz** 作为"幂律指数"，
而不是全局 log-log 斜率。全局斜率**不单调**（1.992 / 2.007 / 1.796），
因为它把「粘性 ∝ f²」与「散射 ∝ f⁴ 上升期→饱和」混在一起。
局部指数在 10 MHz 处严格单调递减：**1.993 → 1.661 → 0.716**。
两条结论都被钉成测试，防止将来有人"调参让全局斜率也单调"。
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

from acoustics import dataset as ds

DATA_DIR = pathlib.Path(__file__).resolve().parents[1] / "data" / "acoustics"
META_PATH = DATA_DIR / "dataset_meta.json"


def _skip_if_dataset_absent() -> None:
    """数据集是**生成产物**（`acoustics.dataset.generate_monodisperse_dataset`），
    公开镜像仓 scratchfield 不携带 `data/`——那里它必然缺席。
    缺席时**明确跳过**而不是判失败：这些用例验的是「已生成数据的一致性」，
    没有数据就无从校验，报失败只会让 CI 常年挂红、把真故障淹掉（2026-10-30 实测）。"""
    if not META_PATH.exists():
        pytest.skip(
            f"数据集未生成：{META_PATH} 不存在 —— 生成命令是 "
            r"""python -c "import pathlib, acoustics.dataset as ds; ds.generate_monodisperse_dataset(pathlib.Path('data/acoustics'))" """
            "（⚠️ 不是 `python -m acoustics.dataset`：该模块没有 `__main__` 段，那条命令等于只 import，"
            "什么都不生成 —— 2026-10-31 实测确认。私有仓已提交该产物，公开镜像仓不携带 data/，"
            "CI 的 build-release 会在跑测试前现生成，生成器确定性已验：与已提交的 4 个文件 sha256 全等）"
        )


@pytest.fixture(scope="module")
def meta() -> dict:
    _skip_if_dataset_absent()
    return json.loads(META_PATH.read_text(encoding="utf-8"))


def test_three_groups_present_and_small(meta):
    """3 组不同粒径；整个数据集 < 50 MB（工单硬判据）。"""
    entries = meta["entries"]
    assert len(entries) == 3, f"应有 3 组，实际 {len(entries)}"
    assert len({e["diameter_um"] for e in entries}) == 3, "三组粒径必须互不相同"

    total = sum(f.stat().st_size for f in DATA_DIR.rglob("*") if f.is_file())
    assert total < 50 * 1024 * 1024, f"数据集 {total / 1024 / 1024:.1f} MB ≥ 50 MB"
    assert total < 1024 * 1024, f"数据集应远小于上限（实际 {total / 1024:.1f} KB）"


def test_files_exist_and_load(meta):
    for e in meta["entries"]:
        p = DATA_DIR / e["file"]
        assert p.exists(), f"缺数据文件 {p}"
        f, a = ds.load_dataset(p)
        assert f.shape == a.shape == (e["n_points"],)
        assert np.all(np.diff(f) > 0), "频率必须严格递增"
        assert np.all(a > 0), "衰减必须为正"


def test_local_exponent_monotone_decreasing_with_diameter(meta):
    """**核心判据**：局部幂律指数 @10 MHz 随粒径严格单调递减。"""
    pairs = sorted(meta["entries"], key=lambda e: e["diameter_um"])
    exps = [e["local_exponent_10mhz"] for e in pairs]
    diam = [e["diameter_um"] for e in pairs]

    assert all(exps[i] > exps[i + 1] for i in range(len(exps) - 1)), (
        f"局部指数未随粒径单调递减：{list(zip(diam, exps, strict=True))}"
    )
    # 并且差异要有物理意义（不是浮点抖动）
    assert exps[0] - exps[-1] > 1.0, f"首尾指数差 {exps[0] - exps[-1]:.3f} 过小，分不出粒径"


def test_global_exponent_is_documented_non_monotone(meta):
    """**已知边界**：全局 log-log 斜率**不单调**。

    把这条写成断言，是为了防止"为了让全局斜率单调去改核/改频带"——
    那等于用一个混合指标掩盖两个机制的叠加。
    """
    pairs = sorted(meta["entries"], key=lambda e: e["diameter_um"])
    glob = [e["power_law_exponent_global"] for e in pairs]
    assert not all(glob[i] > glob[i + 1] for i in range(len(glob) - 1)), (
        f"全局斜率意外变单调了（{glob}）；若核被改动需重新评估口径，而非调整验收"
    )


def test_exponent_recomputed_from_csv_matches_meta(meta):
    """meta 里的指数必须能由 CSV **重算**出来（防止 meta 与数据脱节）。"""
    for e in meta["entries"]:
        f, a = ds.load_dataset(DATA_DIR / e["file"])
        loc = ds.local_power_law_exponent(f, a, 10.0e6)
        glob = ds.power_law_exponent(f, a)
        assert loc == pytest.approx(e["local_exponent_10mhz"], abs=2e-3), e["file"]
        assert glob == pytest.approx(e["power_law_exponent_global"], abs=2e-3), e["file"]


def test_regeneration_is_deterministic(tmp_path):
    """生成器无随机项：重跑到临时目录应与已提交数据逐值一致。"""
    _skip_if_dataset_absent()
    fresh = tmp_path / "regen"
    ds.generate_monodisperse_dataset(fresh)

    for e in json.loads((fresh / "dataset_meta.json").read_text(encoding="utf-8"))["entries"]:
        f_new, a_new = ds.load_dataset(fresh / e["file"])
        f_old, a_old = ds.load_dataset(DATA_DIR / e["file"])
        assert np.allclose(f_new, f_old, rtol=0, atol=0), f"{e['file']} 频点不一致"
        assert np.allclose(a_new, a_old, rtol=1e-12, atol=0), f"{e['file']} 幅值不一致"
