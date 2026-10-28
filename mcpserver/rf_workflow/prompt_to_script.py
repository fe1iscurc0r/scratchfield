"""prompt/目标 → 可跑 RF 仿真脚本（工单242 任务一）。

分工：

- :func:`parse_goal` 把自然语言里的**可解析参数**（频率 / SF / 带宽 / 功率 / CR / 载荷字节）
  抽成规格字典；抽不到的走 :data:`lora_phy.DEFAULT_SPEC` 默认值，**并在产物里标注哪些是默认**。
- :func:`classify` 判断 goal 属于哪一类可生成的工作流；不认识就**显式报错**（``unsupported_goal``
  + 可用清单），不猜、不静默降级成"随便给个脚本"。
- :func:`build_script` / :func:`generate` 产出**自包含沙箱**：``script.py`` + 同目录
  ``lora_phy.py``（按字节 vendor 自 :mod:`mcpserver.rf_workflow.lora_phy`）。
  用 vendor 副本而不是把公式抄进脚本，是为了让「公式漂移」在结构上不可能发生
  （回归用例断言两份字节相同）。

LLM 通路：``prompt_to_script`` 的**解析**默认用规则（确定、可单测）。若配了
``ANTHROPIC_API_KEY``，可用 :func:`llm_refine_spec` 让模型补全参数——该函数**惰性导入**
``mcpserver.llm_gateway.anthropic_compat``，不可用即返回 ``None`` 并让调用方走规则结果。
"""
from __future__ import annotations

import json
import re
import shutil
import string
from pathlib import Path
from typing import Any

from . import lora_phy

KIND_LORA = "lora_chirp_power_estimator"
SUPPORTED_KINDS: dict[str, str] = {
    KIND_LORA: "LoRa chirp 发射功率估算器（符号时长 / ToA / 能量 / 链路预算 / 频谱占用）",
}
RF_LIBS = ("stdlib", "numpy")
DEFAULT_RF_LIB = "stdlib"
VENDORED_MODULE = "lora_phy.py"
SCRIPT_FILENAME = "script.py"

_FREQ_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:MHz|兆赫|兆)", re.IGNORECASE)
# 允许"扩频因子改成 9""带宽调到 250 kHz"这类中间夹动词的写法（最多夹 10 个非数字字符）
_BW_RE = re.compile(r"(?:BW|带宽)[^\d]{0,10}(\d+(?:\.\d+)?)\s*kHz", re.IGNORECASE)
_SF_RE = re.compile(r"(?:SF|扩频因子|spreading\s*factor)[^\d]{0,10}(\d+)", re.IGNORECASE)
_CR_RE = re.compile(r"CR[^\d]{0,10}4\s*/\s*(\d)", re.IGNORECASE)
_POWER_RE = re.compile(r"(\d+(?:\.\d+)?)\s*dBm", re.IGNORECASE)
_PAYLOAD_RE = re.compile(r"(\d+)\s*(?:字节|bytes|byte)", re.IGNORECASE)

SCRIPT_TEMPLATE = string.Template('''#!/usr/bin/env python3
"""$title

由 mcpserver.rf_workflow.prompt_to_script 生成（工单242）—— **自动生成，勿手改**。
goal   : $goal
rf_lib : $rf_lib
真值源 : lora_phy.py（同目录 vendored 副本，字节等同 mcpserver/rf_workflow/lora_phy.py）

产物：result.json（规格 + 指标 + 频谱摘要）；stdout 末尾 __RF_METRICS__ 行供 sim_runner 解析。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SPEC = $spec_literal
RF_LIB = "$rf_lib"
RESULT_FILENAME = "$result_filename"

from lora_phy import compute_metrics, occupied_bandwidth_hz, spectrum_db, synth_chirp_iq


def numpy_spectrum_cross_check(metrics):
    """rf_lib=numpy 时用 numpy.fft 独立复算 -6 dB 带宽，与标准库 FFT 结果对拍。"""
    if RF_LIB != "numpy":
        return {"backend": "stdlib", "note": "rf_lib=stdlib，仅用标准库 FFT"}
    try:
        import numpy as np
    except Exception as exc:  # numpy 缺失 → 显式降级，不静默
        return {"backend": "stdlib(FALLBACK)", "note": "numpy 不可用：%s" % exc}
    samples = synth_chirp_iq(int(SPEC["sf"]), float(SPEC["bw_hz"]),
                             float(SPEC["sample_rate_hz"]),
                             symbols=int(SPEC.get("spectrum_symbols", 1)))
    data = np.asarray(samples, dtype=np.complex128)
    n = 1
    while n < len(data) * 4:
        n <<= 1
    spec = np.fft.fftshift(np.fft.fft(data, n))
    mag = 20.0 * np.log10(np.maximum(np.abs(spec), 1e-12) / float(np.max(np.abs(spec))))
    freqs = (np.arange(n) - n // 2) * float(SPEC["sample_rate_hz"]) / n
    inside = freqs[mag >= float(np.max(mag)) - 6.0]
    obw6 = float(inside.max() - inside.min())
    reference = float(metrics["occupied_bw_6db_hz"])
    return {"backend": "numpy", "bins": int(n),
            "occupied_bw_6db_hz": round(obw6, 1),
            "delta_vs_stdlib_hz": round(obw6 - reference, 1),
            "agrees_within_5pct": abs(obw6 - reference) <= 0.05 * reference}


def main():
    metrics = compute_metrics(SPEC)
    samples = synth_chirp_iq(int(SPEC["sf"]), float(SPEC["bw_hz"]),
                             float(SPEC["sample_rate_hz"]),
                             symbols=int(SPEC.get("spectrum_symbols", 1)))
    freqs, mags = spectrum_db(samples, float(SPEC["sample_rate_hz"]))
    peak_index = max(range(len(mags)), key=lambda i: mags[i])

    payload = {
        "spec": SPEC,
        "rf_lib": RF_LIB,
        "metrics": metrics,
        "spectrum": {
            "bins": len(freqs),
            "peak_freq_hz": round(freqs[peak_index], 1),
            "peak_freq_relative_to_bw": round(freqs[peak_index] / float(SPEC["bw_hz"]), 4),
            "occupied_bw_6db_hz": round(occupied_bandwidth_hz(freqs, mags, drop_db=-6.0), 1),
            "occupied_bw_99pct_hz": round(
                occupied_bandwidth_hz(freqs, mags, energy_fraction=0.99), 1),
        },
        "numpy_cross_check": numpy_spectrum_cross_check(metrics),
    }
    Path(RESULT_FILENAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8", newline="\\n")

    print("=== LoRa chirp 发射功率估算器（工单242 PoC）===")
    print("频率            : %s MHz" % metrics["freq_mhz"])
    print("SF / BW / CR    : SF%s / %s kHz / %s" % (metrics["sf"], metrics["bw_khz"],
                                                    metrics["cr_ratio"]))
    print("发射功率        : %s dBm (%s mW)" % (metrics["tx_power_dbm"],
                                                metrics["tx_power_mw"]))
    print("符号时长 / chirp: %s ms / %s MHz/s" % (metrics["symbol_duration_ms"],
                                                  metrics["chirp_rate_mhz_s"]))
    print("空中时间 ToA    : %s ms（前导 %s + 载荷 %s）" % (
        metrics["time_on_air_ms"], metrics["preamble_duration_ms"],
        metrics["payload_duration_ms"]))
    print("标称 / 有效速率 : %s / %s bps" % (metrics["nominal_bitrate_bps"],
                                              metrics["airtime_bitrate_bps"]))
    print("每比特能量      : %s uJ" % metrics["energy_per_bit_uj"])
    print("灵敏度 / 余量   : %s dBm / %s dB（@%s m）" % (
        metrics["sensitivity_dbm"], metrics["link_margin_db"], metrics["distance_m"]))
    print("占用带宽 -6dB   : %s Hz（%.1f%% of BW）" % (
        metrics["occupied_bw_6db_hz"], metrics["bandwidth_utilisation_pct"]))
    print("占空比          : %s%%（限值 %s%%）" % (metrics["duty_cycle_pct"],
                                                  metrics["duty_cycle_limit_pct"]))
    print("结果文件        : %s" % RESULT_FILENAME)
    print("__RF_METRICS__ " + json.dumps(metrics, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
''')


def classify(goal: str) -> str | None:
    """按关键词判定 goal 属于哪一类工作流；不认识返回 ``None``。"""
    text = str(goal or "").lower()
    if "lora" in text and ("chirp" in text or "功率" in text or "power" in text):
        return KIND_LORA
    return None


def parse_goal(goal: str) -> dict[str, Any]:
    """从自然语言里抽参数；抽不到的保留默认并记进 ``spec_sources``。"""
    text = str(goal or "")
    spec: dict[str, Any] = dict(lora_phy.DEFAULT_SPEC)
    spec["kind"] = classify(text) or KIND_LORA
    sources: dict[str, str] = {key: "default" for key in (
        "freq_hz", "bw_hz", "sf", "cr", "tx_power_dbm", "payload_bytes")}

    freq = _FREQ_RE.search(text)
    if freq:
        spec["freq_hz"] = float(freq.group(1)) * 1e6
        sources["freq_hz"] = "goal"
    bw = _BW_RE.search(text)
    if bw:
        spec["bw_hz"] = float(bw.group(1)) * 1e3
        sources["bw_hz"] = "goal"
    sf = _SF_RE.search(text)
    if sf:
        spec["sf"] = int(sf.group(1))
        sources["sf"] = "goal"
    cr = _CR_RE.search(text)
    if cr:
        spec["cr"] = int(cr.group(1)) - 4
        sources["cr"] = "goal"
    power = _POWER_RE.search(text)
    if power:
        spec["tx_power_dbm"] = float(power.group(1))
        sources["tx_power_dbm"] = "goal"
    payload = _PAYLOAD_RE.search(text)
    if payload:
        spec["payload_bytes"] = int(payload.group(1))
        sources["payload_bytes"] = "goal"
    spec["spec_sources"] = sources
    return spec


def llm_refine_spec(goal: str, spec: dict[str, Any]) -> dict[str, Any] | None:
    """可选：用 LLM 补全规格。不可用时返回 ``None``（调用方继续用规则结果）。

    惰性导入 ``mcpserver.llm_gateway.anthropic_compat``：没装 SDK / 没配 key 时
    抛 :class:`AnthropicCompatError`，这里一律吞成 ``None``——LLM 是**增强**不是**前置条件**。
    """
    try:
        from mcpserver.llm_gateway import anthropic_compat
        from mcpserver.llm_gateway.anthropic_compat import AnthropicCompatError
    except Exception:
        return None
    try:
        client = anthropic_compat.get_client()
    except AnthropicCompatError:
        return None
    except Exception:  # noqa: BLE001 - 任何 SDK 侧异常都视为"LLM 不可用"
        return None
    prompt = (
        "把下面的 RF 需求补成 JSON 规格，键限定于 sf/bw_hz/freq_hz/cr/tx_power_dbm/"
        "payload_bytes；只输出 JSON。\n需求：" + str(goal) + "\n现有：" + json.dumps(spec, ensure_ascii=False)
    )
    try:
        response = anthropic_compat.messages_create(
            client, messages=[{"role": "user", "content": prompt}], max_tokens=512)
        text = anthropic_compat.extract_text(response).strip()
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        patch = json.loads(text[start:end + 1])
    except Exception:  # noqa: BLE001 - 网络/解析失败都退回规则结果
        return None
    if not isinstance(patch, dict):
        return None
    refined = dict(spec)
    refined.update({k: v for k, v in patch.items() if k in ("sf", "bw_hz", "freq_hz", "cr",
                                                           "tx_power_dbm", "payload_bytes")})
    sources = dict(spec.get("spec_sources") or {})
    sources.update({k: "llm" for k in patch})
    refined["spec_sources"] = sources
    return refined


def spec_literal(spec: dict[str, Any], indent: int = 4) -> str:
    """把规格渲染成**合法 Python 字面量**（脚本里直接赋值）。

    不能直接 `json.dumps`：脚本会带上 ``null/true/false`` 三个 Python 里不存在的名字
    （本模块首版真跑踩到，见 README「踩坑」）。这里用 ``repr`` 递归渲染 + 键排序，
    保证产物可复现且是合法 Python。
    """
    body = {k: v for k, v in spec.items() if k != "spec_sources"}

    def render(value: Any, level: int) -> str:
        pad_inner = " " * (indent * (level + 1))
        pad_outer = " " * (indent * level)
        if isinstance(value, dict):
            if not value:
                return "{}"
            rows = [f"{pad_inner}{key!r}: {render(value[key], level + 1)}" for key in sorted(value)]
            return "{\n" + ",\n".join(rows) + f",\n{pad_outer}}}"
        if isinstance(value, list):
            if not value:
                return "[]"
            rows = [f"{pad_inner}{render(item, level + 1)}" for item in value]
            return "[\n" + ",\n".join(rows) + f",\n{pad_outer}]"
        return repr(value)

    return render(body, 0)


def build_script(goal: str, spec: dict[str, Any], rf_lib: str = DEFAULT_RF_LIB, *,
                 result_filename: str = "result.json") -> str:
    """渲染脚本源码；``rf_lib`` 不在 :data:`RF_LIBS` 里抛 ``ValueError``。"""
    if rf_lib not in RF_LIBS:
        raise ValueError(f"rf_lib 必须是 {list(RF_LIBS)} 之一，收到 {rf_lib!r}")
    title = SUPPORTED_KINDS.get(str(spec.get("kind")), "RF 工作流脚本")
    return SCRIPT_TEMPLATE.substitute(
        title=f"{title}（rf_lib={rf_lib}）",
        goal=str(goal).replace('"""', "'''"),
        rf_lib=rf_lib,
        result_filename=str(result_filename),
        spec_literal=spec_literal(spec),
    )


def vendor_module_source() -> bytes:
    """返回要 vendor 进沙箱的 ``lora_phy.py`` 字节（= 仓内真字节）。"""
    return Path(lora_phy.__file__).read_bytes()


def render_prompt_md(goal: str, spec: dict[str, Any], rf_lib: str = DEFAULT_RF_LIB) -> str:
    """渲染 ``prompt.md``（四件套之一）：goal + 解析出的规格 + 字段来源。"""
    kind = str(spec.get("kind") or KIND_LORA)
    title = SUPPORTED_KINDS.get(kind, "RF 工作流")
    return "\n".join([
        f"# {title}",
        "",
        f"- goal: {goal}",
        f"- rf_lib: {rf_lib}",
        f"- 生成器: mcpserver.rf_workflow.prompt_to_script（模板 {kind}）",
        "",
        "## 解析出的规格（`spec_sources` 标注每个字段来自 goal / llm / default）",
        "",
        "```json",
        json.dumps(spec, ensure_ascii=False, indent=1, sort_keys=True),
        "```",
        "",
    ])


def generate(goal: str, out_dir: Path | str, *, rf_lib: str = DEFAULT_RF_LIB,
             spec: dict[str, Any] | None = None, script_filename: str = SCRIPT_FILENAME,
             result_filename: str = "result.json",
             prompt_filename: str = "prompt.md") -> dict[str, Any]:
    """写 ``<out_dir>/<script_filename>`` + vendor ``lora_phy.py``；返回产物路径与规格。"""
    kind = classify(goal)
    if kind is None:
        return {"ok": False, "error": "unsupported_goal", "goal": str(goal),
                "supported": sorted(SUPPORTED_KINDS),
                "hint": "当前只支持 LoRa chirp 功率估算；其它 RF 工作流需先在工作流注册表登记模板"}
    resolved = spec if spec is not None else parse_goal(goal)
    resolved.setdefault("kind", kind)
    problems = lora_phy.validate_spec(resolved)
    if problems:
        return {"ok": False, "error": "invalid_spec", "problems": problems, "spec": resolved}

    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    script_path = target / script_filename
    script_path.write_text(
        build_script(goal, resolved, rf_lib, result_filename=result_filename),
        encoding="utf-8", newline="\n")
    shutil.copyfile(lora_phy.__file__, target / VENDORED_MODULE)
    (target / prompt_filename).write_text(
        render_prompt_md(goal, resolved, rf_lib), encoding="utf-8", newline="\n")

    return {"ok": True, "kind": kind, "rf_lib": rf_lib, "spec": resolved,
            "script_path": str(script_path), "vendored_path": str(target / VENDORED_MODULE),
            "prompt_path": str(target / prompt_filename)}


__all__ = [
    "DEFAULT_RF_LIB", "KIND_LORA", "RF_LIBS", "SCRIPT_FILENAME", "SCRIPT_TEMPLATE",
    "SUPPORTED_KINDS", "VENDORED_MODULE", "build_script", "classify", "generate",
    "llm_refine_spec", "parse_goal", "render_prompt_md", "spec_literal", "vendor_module_source",
]
