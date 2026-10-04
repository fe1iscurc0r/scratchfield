"""仿真执行桥（卷122 W122-02）：模型 → 执行后端 → 结果拉回。

状态机：`pending → pushed → running → done / failed`（落 `jobs.json`，串行执行，一次只跑一个）。

后端与触发条件：

| 后端 | 触发条件 | 做什么 |
| --- | --- | --- |
| `openems` | 找到 openEMS.exe | 用 CSX XML 模型直接算（免 Python 绑定） |
| `openems_py` | 配了 `antenna_sim.openems_python` | 用装了官方 wheel 的解释器跑 Python 模型脚本 |
| `kali` | 配了 `antenna_sim.kali_endpoint` | 推送 → 远端跑 → 拉回（Kali 侧脚本见 README） |
| `dry_run` | 显式指定 | 只走状态机与目录准备，产出占位结果并标注 |

安全与纪律：

- **路径收敛**：`check_model_path()` 拒 `..` 段 → `resolve(strict=True)` → 必须落在
  `allowed_model_roots()` 内；执行时工作目录固定在「模型所在目录/结果目录」，argv 只带文件名
- **job_id 收敛**：`safe_job_id()` 只允许 `[A-Za-z0-9_-]{1,64}`（会拼进结果目录名）
- **不并发**：串行队列；**不静默失败**：无后端/桥不通返回明确错误码
- **超时**：默认 1800s；**大文件不入 git**（结果落 <user_data>/antenna-lab/results/<job_id>/）
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_PUSHED = "pushed"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_running: str | None = None


def _cfg() -> Any:
    try:
        from system.config import get_config

        return getattr(get_config(), "antenna_sim", None)
    except Exception:  # noqa: BLE001
        return None


def _cfg_str(name: str) -> str:
    cfg = _cfg()
    return str(getattr(cfg, name, "") or "").strip() if cfg is not None else ""


def lab_root() -> Path:
    configured = _cfg_str("lab_root")
    if configured:
        root = Path(configured).expanduser()
    else:
        try:
            from system.config import get_data_dir

            root = Path(get_data_dir()) / "antenna-lab"
        except Exception:  # noqa: BLE001
            root = Path.home() / ".lumo" / "antenna-lab"
    for sub in ("models", "results", "logs"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def jobs_path() -> Path:
    configured = _cfg_str("jobs_path")
    return Path(configured).expanduser() if configured else (lab_root() / "jobs.json")


def default_timeout_s() -> float:
    cfg = _cfg()
    return float(getattr(cfg, "timeout_s", 1800.0) or 1800.0) if cfg is not None else 1800.0


def allowed_model_roots() -> List[Path]:
    """允许的模型目录（默认 <lab_root>/models，可加 `antenna_sim.extra_model_dirs`）。"""
    roots = [(lab_root() / "models").resolve()]
    cfg = _cfg()
    extras = (getattr(cfg, "extra_model_dirs", None) or []) if cfg is not None else []
    for extra in extras:
        text = str(extra).strip()
        if not text:
            continue
        try:
            roots.append(Path(text).expanduser().resolve())
        except Exception:  # noqa: BLE001
            continue
    return roots


def check_model_path(model_path: str) -> Tuple[Path | None, str | None]:
    """路径校验：拒 `..` 段 → 必须 resolve 到真实文件 → 必须落在允许目录内。

    返回 `(resolved, None)` 或 `(None, 错误码)`。
    """
    raw = str(model_path or "").strip()
    if not raw:
        return None, "empty_path"
    if ".." in Path(raw).parts:
        return None, "path_traversal_denied"
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = lab_root() / "models" / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError:
        return None, "model_not_found"
    except OSError as e:  # noqa: BLE001
        return None, f"path_error: {e}"
    if not resolved.is_file():
        return None, "not_a_file"
    for root in allowed_model_roots():
        try:
            resolved.relative_to(root)
            return resolved, None
        except ValueError:
            continue
    return None, "path_outside_models"


def safe_model_path(model_path: str) -> Tuple[Path | None, str | None]:
    """`check_model_path` 的同义公开名（供外部与测试调用）。"""
    return check_model_path(model_path)


def safe_job_id(job_id: str) -> Tuple[str | None, str | None]:
    """校验 job_id（会拼进结果目录名）：只允许 `[A-Za-z0-9_-]{1,64}`；空则自动生成。"""
    raw = str(job_id or "").strip()
    if not raw:
        return _new_job_id(), None
    if not _JOB_ID_RE.match(raw):
        return None, "invalid_job_id"
    return raw, None


def _new_job_id() -> str:
    return f"ant-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"


def contained_workdir(model: Path) -> Path:
    """子进程工作目录：模型所在目录（因为 model 已过校验，必然落在允许根内）。"""
    base = model.parent.resolve()
    for root in allowed_model_roots():
        if base == root or root in base.parents:
            return base
    raise ValueError("模型目录不在允许范围内")


# ---------------------------------------------------------------------------
# 任务表（JSON；量大了再换 SQLite）
# ---------------------------------------------------------------------------


def _load_jobs() -> Dict[str, Any]:
    path = jobs_path()
    if not path.exists():
        return {"jobs": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and "jobs" in data else {"jobs": {}}
    except Exception as e:  # noqa: BLE001 - 损坏则重建
        logger.warning("[antenna_sim] jobs.json 解析失败，重建: %s", e)
        return {"jobs": {}}


def _save_jobs(data: Dict[str, Any]) -> None:
    jobs_path().write_bytes(json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))


def _update_job(job_key: str, **fields: Any) -> Dict[str, Any]:
    data = _load_jobs()
    job = data["jobs"].setdefault(job_key, {"job_id": job_key, "created_at": time.time()})
    job.update(fields)
    job["updated_at"] = time.time()
    _save_jobs(data)
    return job


# ---------------------------------------------------------------------------
# 后端探测
# ---------------------------------------------------------------------------


def openems_dir() -> Path | None:
    """OpenEMS 安装目录（含 openEMS.exe）：环境变量 → 配置 → 常见路径。"""
    candidates: List[Path] = []
    env = os.environ.get("ANTENNA_SIM_OPENEMS_DIR", "").strip()
    if env:
        candidates.append(Path(env))
    configured = _cfg_str("openems_dir")
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates += [Path.home() / "openems-win" / "extracted" / "openEMS", Path(r"C:\openEMS")]
    exe_names = ("openEMS.exe", "openEMS")
    for candidate in candidates:
        if not candidate.exists():
            continue
        for exe in exe_names:
            if (candidate / exe).is_file():
                return candidate
        try:
            for sub in candidate.iterdir():
                if sub.is_dir():
                    for exe in exe_names:
                        if (sub / exe).is_file():
                            return sub
        except OSError:
            continue
    return None


def openems_available() -> bool:
    return openems_dir() is not None


def openems_python() -> str:
    """装了 openEMS/CSXCAD wheel 的解释器路径（跑 Python 模型脚本用，可选）。"""
    configured = _cfg_str("openems_python")
    if configured and Path(configured).is_file():
        return configured
    return ""


def kali_endpoint() -> str:
    return _cfg_str("kali_endpoint")


def pick_backend(dry_run: bool = False, suffix: str = "") -> str:
    """按模型类型与可用环境选后端。

    `.py` 模型 → `openems_py`（Python 绑定，可做后处理）；`.xml` 模型 → `openems`（CLI）。
    其它类型走 kali 桥；都没有则 `unavailable`（调用方给明确错误）。
    """
    if dry_run:
        return "dry_run"
    kind = str(suffix or "").lower()
    if kind == ".py":
        if openems_python():
            return "openems_py"
        if kali_endpoint():
            return "kali"
        return "unavailable"
    if kind == ".xml":
        if openems_available():
            return "openems"
        if kali_endpoint():
            return "kali"
        return "unavailable"
    if openems_available():
        return "openems"
    if openems_python():
        return "openems_py"
    if kali_endpoint():
        return "kali"
    return "unavailable"


def _prepare_result_dir(job_key: str) -> Path:
    clean, err = safe_job_id(job_key)
    if clean is None:
        raise ValueError(f"非法 job_id: {err}")
    base = (lab_root() / "results").resolve()
    target = (base / clean).resolve()
    if target != base and base not in target.parents:
        raise ValueError("结果目录越界")
    target.mkdir(parents=True, exist_ok=True)
    return target


# ---------------------------------------------------------------------------
# 执行（子进程细节集中在 sim_exec，便于审计与替换）
# ---------------------------------------------------------------------------


def _execute(backend: str, model: Path, result_dir: Path, job_key: str,
             timeout: float) -> Dict[str, Any]:
    """按后端执行；子进程调用全部走 `sim_exec`（argv 只带文件名，cwd 已限定）。"""
    from . import sim_exec

    if backend == "openems":
        return sim_exec.run_openems_xml(model, result_dir, timeout)
    if backend == "openems_py":
        return sim_exec.run_openems_python(model, result_dir, timeout)
    if backend == "kali":
        endpoint = kali_endpoint()
        if not endpoint:
            return {"ok": False, "error": "kali_unreachable", "hint": "未配置 antenna_sim.kali_endpoint"}
        try:
            from . import kali_bridge
        except Exception as e:  # noqa: BLE001 - 桥未部署时明确报错，不静默
            return {"ok": False, "error": f"kali_bridge_missing: {e}",
                    "hint": "kali 桥未部署：见 README「Kali 桥接入」"}
        return kali_bridge.run_remote(model, job_id=job_key, result_dir=result_dir,
                                      endpoint=endpoint, timeout=timeout)
    return sim_exec.run_dry(result_dir)


def run_job(model_path: str, *, job_id: str = "", dry_run: bool = False,
            timeout_s: float = 0.0) -> Dict[str, Any]:
    """跑一个仿真任务（串行）。返回任务记录。"""
    global _running

    path, path_error = check_model_path(model_path)
    if path is None:
        return {"ok": False, "error": path_error or "model_not_found", "model_path": str(model_path),
                "hint": "模型需放在 <user_data>/antenna-lab/models/ 下（或用 antenna_sim.extra_model_dirs 放开）"}
    job_key, jid_error = safe_job_id(job_id)
    if job_key is None:
        return {"ok": False, "error": jid_error,
                "hint": "job_id 只允许字母/数字/下划线/连字符（最长 64）"}
    if _running:
        return {"ok": False, "error": "busy", "running": _running,
                "hint": "仿真串行执行：等当前任务结束再提交（资源纪律）"}

    result_dir = _prepare_result_dir(job_key)
    backend = pick_backend(dry_run=bool(dry_run), suffix=path.suffix)
    # 注意：参数名 timeout_s 会遮蔽同名模块函数，这里用 default_timeout_s()
    budget = float(timeout_s) if timeout_s else default_timeout_s()
    _update_job(job_key, job_id=job_key, status=STATUS_PENDING, model=str(path),
                backend=backend, result_dir=str(result_dir))

    if backend == "unavailable":
        _update_job(job_key, status=STATUS_FAILED, error="no_backend")
        return {"ok": False, "job_id": job_key, "status": STATUS_FAILED, "error": "no_backend",
                "hint": "设 ANTENNA_SIM_OPENEMS_DIR / antenna_sim.openems_python，或配 kali_endpoint"}

    _running = job_key
    try:
        _update_job(job_key, status=STATUS_PUSHED if backend == "kali" else STATUS_RUNNING)
        outcome = _execute(backend, path, result_dir, job_key, budget)
        status = STATUS_DONE if outcome.get("ok") else STATUS_FAILED
        _update_job(job_key, status=status, error=outcome.get("error", ""),
                    outcome={k: v for k, v in outcome.items() if k != "currents"})
        logger.info("[antenna_sim] 任务 %s 结束：%s（backend=%s）", job_key, status, backend)
        return {"ok": bool(outcome.get("ok")), "job_id": job_key, "status": status,
                "backend": backend, "result_dir": str(result_dir), **outcome}
    finally:
        _running = None


def job_status(job_id: str = "") -> Dict[str, Any]:
    """查任务状态；空 job_id 返回最近 10 个任务摘要。"""
    data = _load_jobs()
    jobs = data.get("jobs") or {}
    if job_id:
        key, err = safe_job_id(job_id)
        if key is None:
            return {"ok": False, "error": err}
        job = jobs.get(key)
        if not job:
            return {"ok": False, "error": "job_not_found", "job_id": key}
        return {"ok": True, "job": job}
    recent = sorted(jobs.values(), key=lambda j: float(j.get("updated_at") or 0), reverse=True)[:10]
    return {"ok": True, "count": len(jobs), "recent": recent,
            "backends": {"openems": openems_available(), "openems_python": bool(openems_python()),
                         "kali": bool(kali_endpoint())},
            "jobs_path": str(jobs_path()), "openems_dir": str(openems_dir() or "")}


def reset_for_tests() -> None:
    """测试用：清掉「正在跑」标记。"""
    global _running
    _running = None


__all__ = ["run_job", "job_status", "openems_available", "openems_dir", "openems_python",
           "kali_endpoint", "pick_backend", "lab_root", "jobs_path", "reset_for_tests",
           "check_model_path", "safe_model_path", "safe_job_id", "allowed_model_roots",
           "contained_workdir", "default_timeout_s",
           "STATUS_PENDING", "STATUS_PUSHED", "STATUS_RUNNING", "STATUS_DONE", "STATUS_FAILED"]
