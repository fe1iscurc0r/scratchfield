"""结果解释 + 下一步建议（工单242 任务一/任务二）。

两条通路，**默认走规则**（确定、可单测）：

- :func:`explain` ⟶ 规则观测（:func:`observations`）+ 下一步建议（:func:`suggest_next`）
  + 具体候选规格（:func:`suggest_specs`，用 :mod:`lora_phy` 真算出每个变体的预测指标）。
- 若配了 ``ANTHROPIC_API_KEY``，额外让 LLM 把那批**已有数字**改写成叙述
  （:func:`llm_narrate`，惰性导入 ``mcpserver.llm_gateway.anthropic_compat``）；
  失败/不可用一律退回规则文本，并在 ``mode`` 字段如实标注 ``rules`` / ``llm``。

**不许编数字**：LLM 提示词里明确「只能用给定 digits」，且返回的文本不参与任何数值字段，
数值字段全部来自 :mod:`lora_phy` 的实算结果。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import lora_phy

DEFAULT_LLM_MODEL_HINT = "claude-3-5-sonnet-latest"
MAX_EXPLANATION_CHARS = 4000


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def observations(metrics: dict[str, Any]) -> list[str]:
    """把指标翻成人能读的观测项（全部来自实算，不含估猜）。"""
    out: list[str] = []
    out.append(
        f"调制：SF{metrics['sf']} / BW {_fmt(metrics['bw_khz'])} kHz / CR {metrics['cr_ratio']}"
        f"（低速率优化={'开' if metrics['low_data_rate_optimize'] else '关'}）；"
        f"符号时长 {_fmt(metrics['symbol_duration_ms'])} ms，chirp 斜率 {_fmt(metrics['chirp_rate_mhz_s'])} MHz/s，"
        f"码片率 {_fmt(metrics['chip_rate_kchips_s'])} kchips/s。")
    out.append(
        f"时间：前导 {_fmt(metrics['preamble_duration_ms'])} ms + 载荷 {metrics['payload_symbols']} 符号 "
        f"{_fmt(metrics['payload_duration_ms'])} ms = 空中时间 {_fmt(metrics['time_on_air_ms'])} ms；"
        f"标称 {_fmt(metrics['nominal_bitrate_bps'])} bps，含开销的有效速率 {_fmt(metrics['airtime_bitrate_bps'])} bps"
        f"（{_fmt(metrics['bit_efficiency_pct'])}% of 标称）。")
    out.append(
        f"能量：发射 {_fmt(metrics['tx_power_dbm'])} dBm（{_fmt(metrics['tx_power_mw'])} mW）下，"
        f"每符号 {_fmt(metrics['energy_per_symbol_uj'])} µJ，每载荷比特 {_fmt(metrics['energy_per_bit_uj'])} µJ。")
    if "occupied_bw_6db_hz" in metrics:
        out.append(
            f"频谱：合成 chirp 的 -6 dB 带宽 {_fmt(metrics['occupied_bw_6db_hz'])} Hz"
            f"（= {_fmt(metrics['bandwidth_utilisation_pct'])}% × BW，即扫频铺满了调制带宽）；"
            f"99% 能量带宽 {_fmt(metrics['occupied_bw_99pct_hz'])} Hz"
            f"（= {_fmt(metrics['occupied_bw_99pct_over_bw'])} × BW，含矩形截断泄漏）。")
    out.append(
        f"链路：@{_fmt(metrics['distance_m'])} m 自由空间路损 {_fmt(metrics['fsl_db'])} dB → 接收 "
        f"{_fmt(metrics['rx_power_dbm'])} dBm，对灵敏度 {_fmt(metrics['sensitivity_dbm'])} dBm 余量 "
        f"{_fmt(metrics['link_margin_db'])} dB（需最小 SNR {_fmt(metrics['required_snr_db'])} dB）；"
        f"自由空间距离上限 {_fmt(metrics['max_free_space_range_m'])} m —— **理论上限，不含地物/多径/衰落**。")
    out.append(
        f"法规：占空比 {_fmt(metrics['duty_cycle_pct'])}%（周期 {_fmt(metrics.get('tx_period_s', 'n/a'))} s，"
        f"限值 {_fmt(metrics['duty_cycle_limit_pct'])}%，"
        f"{'合规' if metrics['duty_cycle_ok'] else '**超限**'}）；"
        f"传导 {_fmt(metrics['tx_power_dbm'])} dBm → EIRP {_fmt(metrics['eirp_dbm'])} dBm → "
        f"ERP {_fmt(metrics['erp_dbm'])} dBm vs 限值 {_fmt(metrics['erp_limit_dbm'])} dBm："
        f"{'合规' if metrics['erp_ok'] else '**超限**'}"
        f"（合规化的传导功率上限 {_fmt(metrics['max_tx_power_dbm_for_erp'])} dBm）。")
    band = metrics["ism_433_range_mhz"]
    out.append(
        f"频段：{_fmt(metrics['freq_mhz'])} MHz "
        f"{'落在' if metrics['in_ism_433'] else '**不在**'} 433 ISM 子带 "
        f"{_fmt(band[0])}–{_fmt(band[1])} MHz 内"
        + ("" if metrics["in_ism_433"] else "；仓内固件 `firmware/dcp_lora/sx1278_lora.cpp` 取的是子带中心 "
           "433.92 MHz，工程上建议对齐到子带内频点。"))
    out.append(f"口径提示：{metrics['regulatory_note']}")
    out.append(f"口径提示：{metrics['sensitivity_note']}")
    if "spectrum_caveat" in metrics:
        out.append(f"口径提示：{metrics['spectrum_caveat']}")
    return out


def suggest_specs(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """给出 3 个候选变体及其**实算**预测（合规化 / 提升灵敏度 / 换带宽）。"""
    plain = {k: v for k, v in spec.items() if k != "spec_sources"}
    compliant_power = round(lora_phy.max_tx_power_dbm_for_erp(
        tx_gain_dbi=float(plain.get("tx_antenna_gain_dbi", 0.0)),
        loss_db=float(plain.get("cable_loss_db", 0.0))), 2)
    candidates: list[dict[str, Any]] = []
    variants = [
        ("合规化：ERP 压到限值", {"tx_power_dbm": compliant_power},
         "把传导功率降到 ERP 恰好等于限值的水平，看链路余量还剩多少"),
        ("提灵敏度：SF 上调 2 档", {"sf": min(int(plain["sf"]) + 2, lora_phy.SF_MAX)},
         "每 +1 档 SF 约补 2.5~3 dB 灵敏度，代价是 ToA 翻倍"),
        ("换信道带宽：BW ×2", {"bw_hz": float(plain["bw_hz"]) * 2},
         "带宽翻倍可缩短 ToA，但灵敏度按 10log10(2)≈3 dB 变差"),
    ]
    for label, patch, why in variants:
        merged = dict(plain)
        merged.update(patch)
        if merged == plain:
            continue
        try:
            metrics = lora_phy.compute_metrics(merged)
        except ValueError as exc:
            candidates.append({"label": label, "why": why, "patch": patch, "ok": False,
                               "error": str(exc)})
            continue
        candidates.append({
            "label": label,
            "why": why,
            "patch": patch,
            "ok": True,
            "predicted": {
                "time_on_air_ms": metrics["time_on_air_ms"],
                "link_margin_db": metrics["link_margin_db"],
                "energy_per_bit_uj": metrics["energy_per_bit_uj"],
                "sensitivity_dbm": metrics["sensitivity_dbm"],
                "duty_cycle_pct": metrics["duty_cycle_pct"],
                "erp_ok": metrics["erp_ok"],
                "duty_cycle_ok": metrics["duty_cycle_ok"],
            },
        })
    return candidates


def suggest_next(metrics: dict[str, Any], spec: dict[str, Any]) -> str:
    """按「最大缺口优先」给一句可执行的下一步。"""
    plain_spec = {k: v for k, v in spec.items() if k != "spec_sources"}
    if not metrics["erp_ok"]:
        compliant = dict(plain_spec)
        compliant["tx_power_dbm"] = lora_phy.max_tx_power_dbm_for_erp(
            tx_gain_dbi=float(plain_spec.get("tx_antenna_gain_dbi", 0.0)),
            loss_db=float(plain_spec.get("cable_loss_db", 0.0)))
        try:
            after = lora_phy.compute_metrics(compliant)
            tail = (f"把传导功率压到 {_fmt(round(compliant['tx_power_dbm'], 2))} dBm（ERP 恰好顶上限值）后，"
                    f"链路余量仍有 {_fmt(after['link_margin_db'])} dB（@{_fmt(after['distance_m'])} m，"
                    f"自由空间）——合规化不会牺牲这次估算的余量。")
        except ValueError:
            tail = "压到限值后需重跑一次估算确认余量。"
        return (f"先做合规化：当前 ERP {_fmt(metrics['erp_dbm'])} dBm 超过该子带限值 "
                f"{_fmt(metrics['erp_limit_dbm'])} dBm（传导 {_fmt(metrics['tx_power_dbm'])} dBm，"
                f"EIRP {_fmt(metrics['eirp_dbm'])} dBm）。" + tail
                + " 随后用实测 RSSI 替换自由空间路损。")
    sf_variant = next(
        (item for item in suggest_specs(plain_spec) if item.get("label", "").startswith("提灵敏度")),
        None)
    if metrics["link_margin_db"] < 10.0:
        hint = (f"建议 SF 上调 1~2 档（{sf_variant['patch'] if sf_variant else 'sf += 2'}）"
                if sf_variant else "建议 SF 上调 1~2 档")
        return (f"链路余量仅 {_fmt(metrics['link_margin_db'])} dB（<10 dB 经验阈）：" + hint
                + "，或补天线增益/降馈线损耗；同时用实测 RSSI 替换自由空间路损假设。")
    return ("链路余量充裕，下一步建议做**参数扫描**（SF × BW 网格）在『能量/比特』与"
            "『链路余量』之间取折中；并把当前 `tx_antenna_gain_dbi` / `cable_loss_db` 从 0 换成"
            "实物数据（当前为理想值，会把余量算乐观）。")


def llm_narrate(metrics: dict[str, Any], rule_text: str) -> str | None:
    """让 LLM 把已有数字改写成叙述；不可用/失败返回 ``None``。"""
    try:
        from mcpserver.llm_gateway import anthropic_compat
        from mcpserver.llm_gateway.anthropic_compat import AnthropicCompatError
    except Exception:
        return None
    try:
        client = anthropic_compat.get_client()
    except AnthropicCompatError:
        return None
    except Exception:  # noqa: BLE001
        return None
    prompt = (
        "下面是 LoRa 链路估算的**已算好**指标与规则观测。请改写成 3~5 句中文工程结论。\n"
        "硬约束：只能用下面出现的数字，**不得新增/推算任何数值**，不要编造实测数据。\n\n"
        f"指标 JSON：{json.dumps(metrics, ensure_ascii=False, sort_keys=True)}\n\n规则观测：{rule_text}"
    )
    try:
        response = anthropic_compat.messages_create(
            client, messages=[{"role": "user", "content": prompt}], max_tokens=1024)
        text = anthropic_compat.extract_text(response).strip()
    except Exception:  # noqa: BLE001
        return None
    return text[:MAX_EXPLANATION_CHARS] or None


def explain(spec: dict[str, Any], metrics: dict[str, Any] | None = None, *,
            allow_llm: bool = True) -> dict[str, Any]:
    """产出 ``explanation`` + ``next_step_suggestion`` + ``candidates`` + ``mode``。"""
    if metrics is None:
        metrics = lora_phy.compute_metrics({k: v for k, v in spec.items() if k != "spec_sources"})
    notes = observations(metrics)
    rule_text = "\n".join(f"- {line}" for line in notes)
    next_step = suggest_next(metrics, spec)
    candidates = suggest_specs(spec)

    mode = "rules"
    explanation = rule_text
    if allow_llm:
        narrated = llm_narrate(metrics, rule_text)
        if narrated:
            mode = "llm"
            explanation = narrated + "\n\n## 规则观测（数值来源，逐条可核）\n\n" + rule_text

    return {
        "mode": mode,
        "explanation": explanation,
        "next_step_suggestion": next_step,
        "observations": notes,
        "candidates": candidates,
        "metrics": metrics,
    }


def render_markdown(result: dict[str, Any], spec: dict[str, Any]) -> str:
    """把解释结果渲染成 ``explanation.md``（四件套之一）。"""
    lines = [
        "# 结果解释（工单242 PoC）",
        "",
        f"- 解释模式: `{result['mode']}`（规则恒可用；`llm` 仅表示叙述层由模型改写，"
        "数值全部来自 `lora_phy` 实算）",
        "",
        "## 规格",
        "",
        "```json",
        json.dumps({k: v for k, v in spec.items()}, ensure_ascii=False, indent=1, sort_keys=True),
        "```",
        "",
        "## 结论",
        "",
        result["explanation"],
        "",
        "## 下一步建议",
        "",
        result["next_step_suggestion"],
        "",
        "## 候选变体（预测值由 lora_phy 实算）",
        "",
        "| 变体 | 改什么 | ToA ms | 余量 dB | 每比特 µJ | ERP 合规 | 占空比合规 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in result["candidates"]:
        if not item.get("ok"):
            lines.append(f"| {item['label']} | {item['patch']} | — | — | — | — | — |")
            continue
        predicted = item["predicted"]
        patch = ", ".join(f"{k}={v}" for k, v in item["patch"].items())
        lines.append(
            f"| {item['label']} | `{patch}` | {predicted['time_on_air_ms']} | "
            f"{predicted['link_margin_db']} | {predicted['energy_per_bit_uj']} | "
            f"{'✅' if predicted['erp_ok'] else '❌'} | "
            f"{'✅' if predicted['duty_cycle_ok'] else '❌'} |")
    lines += ["", "## 指标全量", "", "```json",
              json.dumps(result["metrics"], ensure_ascii=False, indent=1, sort_keys=True),
              "```", ""]
    return "\n".join(lines)


def write_explanation(workflow_id: str, result: dict[str, Any], spec: dict[str, Any], *,
                      directory: Path | None = None,
                      filename: str = "explanation.md") -> Path:
    """写 ``explanation.md``（LF）。"""
    from .sim_runner import workflow_dir

    target = Path(directory) if directory is not None else workflow_dir(workflow_id)
    if ".." in Path(filename).parts or Path(filename).is_absolute():
        raise ValueError(f"非法文件名: {filename!r}")
    path = target / filename
    path.write_text(render_markdown(result, spec), encoding="utf-8", newline="\n")
    return path


__all__ = ["MAX_EXPLANATION_CHARS", "explain", "llm_narrate", "observations", "render_markdown",
           "suggest_next", "suggest_specs", "write_explanation"]
