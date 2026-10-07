"""eis 工具组单测（工单202 任务一验收）。

覆盖：
    - linkk：合成谱（KK 一致）判 pass；破坏谱（实/虚不匹配）判 fail
    - drt：两元件合成谱反演出两个峰，峰位落在真 τ 的对数邻域内
    - 换核接口：注册/切换/注销自定义核；未知核显式报错
    - ecm：两元件拟合回收参数（宽松容差）
    - 总线契约：EisAgent.handle_handoff 分发 + 错误路径
运行：pytest mcpserver/eis/tests -q
"""
from __future__ import annotations

import asyncio
import json
import math

import numpy as np
import pytest

from mcpserver.eis import kernel as K
from mcpserver.eis import tools as T
from mcpserver.eis.agent import EisAgent

# ---- 合成 EIS 数据（R0 + Σ R||C）------------------------------------------

R0, R1, C1, R2, C2 = 10.0, 100.0, 1e-4, 200.0, 1e-2      # τ1=0.01s, τ2=2s
FREQS = np.logspace(-2, 5, 28)


def synth_eis() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    omega = 2 * np.pi * FREQS
    z = np.full_like(omega, R0, dtype=complex)
    z += R1 / (1 + 1j * omega * R1 * C1)
    z += R2 / (1 + 1j * omega * R2 * C2)
    return FREQS, z.real, z.imag


# ---- linkk ----------------------------------------------------------------

def test_linkk_pass_on_kk_consistent_spectrum():
    f, zr, zi = synth_eis()
    out = T.linkk(f, zr, zi)
    assert out["status"] == "ok"
    assert out["verdict"] == "pass", out
    assert out["residual"] < 0.01
    assert out["imag_convention"] == "negative"


def test_linkk_fail_when_kk_violated():
    f, zr, zi = synth_eis()
    good = T.linkk(f, zr, zi)["residual"]
    bad = T.linkk(f, zr, zi * 2.0)          # 虚部与实部不自洽 → 违反 KK
    assert bad["verdict"] == "fail", bad
    assert bad["residual"] > good * 3, (good, bad["residual"])


def test_linkk_positive_imag_convention_detected():
    f, zr, zi = synth_eis()
    out = T.linkk(f, zr, -zi)               # 物理惯例（Z''>0）也能识别
    assert out["imag_convention"] == "positive"
    assert out["verdict"] == "pass"


# ---- drt ------------------------------------------------------------------

def test_drt_resolves_two_peaks_near_true_tau():
    f, zr, zi = synth_eis()
    out = T.drt(f, zr, zi, n_tau=80)
    assert out["status"] == "ok"
    peaks = out["peaks"]
    assert len(peaks) >= 2, out
    taus = sorted(p["tau"] for p in peaks[:2])
    for got, want in zip(taus, (0.01, 2.0)):
        assert 0.3 <= got / want <= 3.0, (taus, want)


def test_drt_kernel_switch_both_run():
    f, zr, zi = synth_eis()
    a = T.drt(f, zr, zi, kernel="tikhonov")
    b = T.drt(f, zr, zi, kernel="hierarchical_bayes")
    for out in (a, b):
        assert out["status"] == "ok"
        assert out["residual"] < 0.1
        assert len(out["tau"]) == len(out["gamma"]) > 0
    assert a["kernel"] != b["kernel"]


# ---- 换核接口 --------------------------------------------------------------

class _ZeroKernel:
    """最小自定义核：返回全零（只为契约测试，不追求数值意义）。"""

    name = "zero_probe"

    def solve(self, matrix, data, **hyperparams):
        n = matrix.shape[1]
        y = np.zeros(n)
        return K.InversionResult(x=np.arange(n, dtype=float), y=y,
                                 residual=1.0, method=self.name)


def test_kernel_registry_register_use_unregister():
    base = K.list_kernels()
    assert "tikhonov" in base and "hierarchical_bayes" in base
    K.register_kernel("zero_probe", _ZeroKernel)
    try:
        assert "zero_probe" in K.list_kernels()
        res = K.invert(np.eye(3), np.ones(3), kernel="zero_probe")
        assert res.method == "zero_probe" and float(res.residual) == 1.0
        assert K.get_kernel("zero_probe").name == "zero_probe"
    finally:
        assert K.unregister_kernel("zero_probe") is True
    assert "zero_probe" not in K.list_kernels()


def test_unknown_kernel_raises_with_available_list():
    with pytest.raises(KeyError) as ei:
        K.get_kernel("no_such_kernel")
    assert "no_such_kernel" in str(ei.value)
    assert "tikhonov" in str(ei.value)


def test_register_kernel_rejects_bad_input():
    with pytest.raises(ValueError):
        K.register_kernel("", _ZeroKernel)
    with pytest.raises(TypeError):
        K.register_kernel("bad", object())      # 不可调用


# ---- ecm ------------------------------------------------------------------

def test_ecm_recovers_parameters():
    f, zr, zi = synth_eis()
    out = T.ecm(f, zr, zi, num_elements=2)
    assert out["status"] == "ok", out
    assert abs(out["R0"] - R0) / R0 < 0.2, out["R0"]
    rs = sorted(e["R"] for e in out["elements"])
    assert abs(rs[0] - R1) / R1 < 0.35, rs
    assert abs(rs[1] - R2) / R2 < 0.35, rs


def test_ecm_linear_response_is_not_crash():
    # 纯电阻（无 CPE）也要给出结果而非崩
    f = np.logspace(-1, 4, 10)
    zr = np.full_like(f, 50.0)
    zi = np.zeros_like(f)
    out = T.ecm(f, zr, zi, num_elements=1)
    assert out["status"] in ("ok", "warn")
    assert "R0" in out


# ---- 总线契约 --------------------------------------------------------------

def _call(tool: str, params: dict | None = None) -> dict:
    payload = {"tool": tool}
    if params is not None:
        payload["params"] = params
    raw = asyncio.run(EisAgent().handle_handoff(payload))
    return json.loads(raw)


def test_agent_lists_tools_and_kernels():
    out = _call("kernels")
    assert out["status"] == "ok"
    assert set(out["available_tools"]) == {"linkk", "drt", "ecm"}
    assert "tikhonov" in out["kernels"]
    assert out["default_kernel"] == "tikhonov"


def test_agent_dispatches_drt_and_linkk():
    f, zr, zi = synth_eis()
    p = {"freqs": list(f), "z_real": list(zr), "z_imag": list(zi)}
    assert _call("linkk", p)["verdict"] == "pass"
    assert _call("drt", p)["status"] == "ok"


def test_agent_unknown_tool_and_missing_spectrum():
    assert _call("nope")["error"].startswith("unknown_tool")
    out = _call("drt", {"freqs": [1.0]})
    assert out["status"] == "error" and out["error"].startswith("missing_spectrum")


def test_agent_bad_shapes_return_structured_error():
    out = _call("drt", {"freqs": [1.0, 2.0], "z_real": [1.0], "z_imag": [1.0, 2.0]})
    assert out["status"] == "error"
    assert out["error"].startswith("bad_input")


def test_agent_flat_call_form_supported():
    f, zr, zi = synth_eis()
    raw = asyncio.run(EisAgent().handle_handoff(
        {"tool_name": "linkk", "freqs": list(f), "z_real": list(zr), "z_imag": list(zi)}))
    assert json.loads(raw)["verdict"] == "pass"
