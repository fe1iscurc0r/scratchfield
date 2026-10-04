"""antenna_sim MCP 桥（卷122）：模型生成 / 扫描 / 执行 / 状态 / 结果分析。

对齐 material_science 的桥接范式：`handle_handoff(params)` → `{status, message, data}`。
重活（求解）交给 W122-02 的 `sim_runner`，本文件只做参数整形与错误语义。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from . import model_generator

logger = logging.getLogger(__name__)


def _lab_root() -> Path:
    """天线实验室根目录（模型/结果/档案都在这下面）。"""
    try:
        from system.config import get_data_dir

        root = Path(get_data_dir()) / "antenna-lab"
    except Exception:  # noqa: BLE001
        root = Path.home() / ".lumo" / "antenna-lab"
    (root / "models").mkdir(parents=True, exist_ok=True)
    (root / "results").mkdir(parents=True, exist_ok=True)
    return root


class AntennaSimBridge:
    """天线仿真 agent 的 MCP 入口。"""

    def _resolve_out_dir(self, out_dir: str) -> Path:
        return Path(out_dir) if str(out_dir or "").strip() else (_lab_root() / "models")

    # ---- 工具 ----

    def gen_model(self, antenna_type: str, freq_mhz: float, params: Dict[str, Any] | None = None,
                  out_dir: str = "", name: str = "") -> Dict[str, Any]:
        return model_generator.gen_model(
            antenna_type, freq_mhz, params or {}, out_dir=self._resolve_out_dir(out_dir), name=name
        )

    def sweep_params(self, antenna_type: str, freq_mhz: float, sweep: Dict[str, Any],
                     out_dir: str = "") -> Dict[str, Any]:
        target = self._resolve_out_dir(out_dir)
        if str(out_dir or "").strip():
            target = Path(out_dir)
        else:
            target = _lab_root() / "models" / f"{antenna_type}_{int(freq_mhz)}mhz_sweep"
        return model_generator.sweep_params(antenna_type, freq_mhz, sweep or {}, target)

    def sim_run(self, model_path: str, job_id: str = "", dry_run: bool = False,
                timeout_s: float = 0.0) -> Dict[str, Any]:
        from .sim_runner import run_job

        return run_job(model_path, job_id=job_id, dry_run=bool(dry_run),
                       timeout_s=float(timeout_s or 0.0))

    def job_status(self, job_id: str = "") -> Dict[str, Any]:
        from .sim_runner import job_status

        return job_status(job_id)

    def analyze_result(self, job_id: str = "", s11_csv: str = "", synthetic: bool = False) -> Dict[str, Any]:
        from .result_analyzer import analyze_result

        return analyze_result(job_id=job_id, s11_csv=s11_csv, synthetic=bool(synthetic))

    # ---- handoff ----

    _TOOLS = {
        "gen_model": "gen_model",
        "sweep_params": "sweep_params",
        "sim_run": "sim_run",
        "job_status": "job_status",
        "analyze_result": "analyze_result",
    }

    async def handle_handoff(self, task: Dict[str, Any]) -> str:
        import asyncio
        import json

        tool = str((task or {}).get("tool_name") or "")
        fn_name = self._TOOLS.get(tool)
        if fn_name is None:
            return json.dumps(
                {"status": "error", "message": f"未知工具 {tool}，可用: {', '.join(sorted(self._TOOLS))}",
                 "data": {}},
                ensure_ascii=False,
            )
        if isinstance(task.get("params"), dict):
            arguments = dict(task["params"])
        else:
            arguments = {
                k: v for k, v in task.items()
                if not k.startswith("_") and k not in ("tool_name", "agentType", "service_name")
            }
        try:
            data = await asyncio.to_thread(lambda: getattr(self, fn_name)(**arguments))
        except TypeError as e:
            return json.dumps({"status": "error", "message": f"参数错误: {e}", "data": {}}, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            logger.warning("[antenna_sim] %s 执行失败: %s", tool, e)
            return json.dumps({"status": "error", "message": f"{type(e).__name__}: {e}", "data": {}},
                              ensure_ascii=False)
        ok = bool(data.get("ok", True)) and not data.get("error")
        payload = {"status": "success" if ok else "error",
                   "message": "ok" if ok else str(data.get("error") or "failed"),
                   "data": data}
        return json.dumps(payload, ensure_ascii=False, default=str)


__all__ = ["AntennaSimBridge"]
