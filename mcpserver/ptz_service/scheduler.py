"""云台任务编排（卷130 W130-03）。

工单原文：「云台任务编排【落地 · TLE 跟踪/扇扫/记忆位】」——`mcpserver/ptz_service/scheduler.py`：
任务模型 `{task_id, type, params, schedule}`（type = `track` / `scan` / `goto_mem`）。

三个任务类型：

| type | 干什么 | 关键约束 |
|---|---|---|
| `track` | 按 TLE + 站点坐标算 az/el，周期性 `ptz_move_to` 跟踪 | 节流 1–5 s；出界不追；中断要**可配置地**保持或平滑回 HOME |
| `scan` | 扇扫**循环**（起/止/步/驻留），供频谱/目标模式联动 | 与 W130-01 的一次性 `ptz_scan` 不同：这是循环任务 |
| `goto_mem` | 走记忆位（JSON 持久化） | 同 `goto_memory` |

## 三条设计纪律

**1. 任务不自己发命令，只产生"该发什么"。**
`scheduler.tick()` 返回 `MoveInstruction` 列表，由 `PTZService` 真正下发。
这样任务编排**不持有链路**，也就不可能绕过仲裁、审计、看门狗、锁机。
编排层拿到指令后走的仍是普通命令路径——**没有特权通道**。

**2. 冲突 last-wins，与 W130-02 同一套语义。**
手动与自动冲突时按时间戳，谁后到谁生效。为此自动任务在
`tick()` 里也调 `arbiter.claim("local", ...)`：手动命令一旦落下，
自动任务**自己让位**，而不是互相对抗。

**3. 安全优先级的顺序是硬的：锁机 > 看门狗 > 手动 > 自动。**
急停锁机时 `tick()` 直接返回空指令——**自动任务绝不能把云台从锁机里"开回去"**。
这条不是可配置项，写死在代码里。
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .tracking import SiteLocation, Tle, make_propagator, sgp4_available

logger = logging.getLogger(__name__)

TASK_TRACK = "track"
TASK_SCAN = "scan"
TASK_GOTO_MEM = "goto_mem"
TASK_TYPES = (TASK_TRACK, TASK_SCAN, TASK_GOTO_MEM)

STATE_PENDING = "pending"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_ABORTED = "aborted"
STATE_FAILED = "failed"

#: 跟踪中断时的处置（工单要求**可配置**）
FAIL_HOLD = "hold"        # 原地保持（默认：望远镜/天线停在当前指向，便于人接管）
FAIL_HOME = "home"        # 平滑回 HOME

#: 来源标记：自动任务用 `local`，与 `serial`/`lora` 同表参与仲裁
SOURCE_AUTO = "local"


@dataclass
class MoveInstruction:
    """一条"该发什么"的描述——**不是命令本身**。由 service 负责下发。"""

    az: float
    el: float
    speed: float | None = None
    task_id: str = ""
    reason: str = ""
    kind: str = "move"

    def as_dict(self) -> Dict[str, Any]:
        return {"az": self.az, "el": self.el, "speed": self.speed,
                "task_id": self.task_id, "reason": self.reason, "kind": self.kind}


@dataclass
class Task:
    """工单规定的任务模型：`{task_id, type, params, schedule}`。"""

    task_id: str
    type: str
    params: Dict[str, Any] = field(default_factory=dict)
    schedule: Dict[str, Any] = field(default_factory=dict)
    state: str = STATE_PENDING
    created_at: float = 0.0
    started_at: float | None = None
    finished_at: float | None = None
    error: str = ""
    #: 运行统计
    ticks: int = 0
    moves: int = 0
    errors: int = 0
    points: int = 0
    loops_done: int = 0
    max_track_error_deg: float = 0.0
    _last_emit_at: float | None = None
    _cursor: int = 0
    _direction: int = 1
    _last_point: tuple | None = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id, "type": self.type, "params": self.params,
            "schedule": self.schedule, "state": self.state,
            "created_at": round(self.created_at, 3),
            "started_at": round(self.started_at, 3) if self.started_at else None,
            "finished_at": round(self.finished_at, 3) if self.finished_at else None,
            "error": self.error, "ticks": self.ticks, "moves": self.moves,
            "errors": self.errors, "points": self.points,
            "loops_done": self.loops_done,
            "max_track_error_deg": round(self.max_track_error_deg, 4),
        }


# ---------------------------------------------------------------------------
# 记忆位持久化
# ---------------------------------------------------------------------------


class MemoryStore:
    """记忆位：`ptz_memory <id>` 存到本地 JSON（工单要求）。

    **为什么不放内存**：记忆位是"安装时标定的固定指向"（例如某颗星的方标、
    某个中继的方向），断电丢失等于每次开机都要重新标定。
    """

    def __init__(self, path: Any = None):
        self.path = Path(path) if path else None
        self._slots: Dict[str, Dict[str, Any]] = {}
        self.load_errors = 0
        self.save_errors = 0
        self.load()

    def load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            slots = raw.get("slots", raw) if isinstance(raw, dict) else {}
            if isinstance(slots, dict):
                clean: Dict[str, Dict[str, Any]] = {}
                for key, val in slots.items():
                    if isinstance(val, dict) and "az" in val and "el" in val:
                        clean[str(key)] = {"az": float(val["az"]), "el": float(val["el"]),
                                           **(val.get("meta") or {})}
                self._slots = clean
        except (OSError, ValueError) as exc:
            # 坏文件不阻断服务启动——记忆位丢了是麻烦，起不来是事故
            self.load_errors += 1
            logger.warning("[ptz_memory] 记忆位文件读取失败（忽略）: %s", exc)

    def save(self) -> bool:
        if self.path is None:
            return True
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"version": 1, "slots": self._slots,
                       "updated_at": datetime.now(timezone.utc).isoformat()}
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            tmp.replace(self.path)          # 原子替换：写坏也不会毁掉旧文件
            return True
        except (OSError, ValueError) as exc:
            self.save_errors += 1
            logger.warning("[ptz_memory] 记忆位落盘失败（内存仍有效）: %s", exc)
            return False

    def set(self, slot: str, az: float, el: float, **meta: Any) -> Dict[str, Any]:
        key = str(slot or "").strip()
        if not key:
            raise ValueError("slot 不能为空")
        entry = {"az": float(az), "el": float(el)}
        if meta:
            entry["meta"] = meta
        self._slots[key] = entry
        saved = self.save()
        return {"slot": key, "az": float(az), "el": float(el), "persisted": saved}

    def get(self, slot: str) -> Dict[str, Any] | None:
        entry = self._slots.get(str(slot or "").strip())
        return dict(entry) if entry else None

    def delete(self, slot: str) -> bool:
        key = str(slot or "").strip()
        if key not in self._slots:
            return False
        del self._slots[key]
        self.save()
        return True

    def list_slots(self) -> List[str]:
        return sorted(self._slots)

    def snapshot(self) -> Dict[str, Any]:
        return {"slots": {k: dict(v) for k, v in self._slots.items()},
                "count": len(self._slots),
                "path": str(self.path) if self.path else None,
                "load_errors": self.load_errors, "save_errors": self.save_errors}


# ---------------------------------------------------------------------------
# 调度器
# ---------------------------------------------------------------------------


class PTZScheduler:
    """任务编排器：把任务列表 + 时钟推进 → 一串 `MoveInstruction`。"""

    def __init__(self, *, clock: Callable[[], float] = time.time,
                 wall_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 site: SiteLocation | None = None,
                 tracking_period_s: float = 3.0,
                 tracking_source: str = "sgp4",
                 track_fail_action: str = FAIL_HOLD,
                 memory: MemoryStore | None = None,
                 az_min: float = 0.0, az_max: float = 360.0,
                 el_min: float = 0.0, el_max: float = 180.0,
                 min_el_deg: float = 0.0,
                 arbiter: Any = None):
        self.clock = clock
        self.wall_clock = wall_clock
        self.site = site or SiteLocation()
        self.tracking_period_s = max(1.0, min(5.0, float(tracking_period_s)))
        self.tracking_source = str(tracking_source or "sgp4")
        self.track_fail_action = (str(track_fail_action or FAIL_HOLD).strip().lower()
                                  if str(track_fail_action).strip().lower() in (FAIL_HOLD, FAIL_HOME)
                                  else FAIL_HOLD)
        self.memory = memory or MemoryStore()
        self.az_min, self.az_max = float(az_min), float(az_max)
        self.el_min, self.el_max = float(el_min), float(el_max)
        #: 最低跟踪仰角：低于它就不追（追地平线目标既无意义又容易撞限位）
        self.min_el_deg = float(min_el_deg)
        self.arbiter = arbiter

        self._lock = threading.RLock()
        self._tasks: Dict[str, Task] = {}
        self._order: List[str] = []
        self._propagators: Dict[str, Any] = {}
        self._tles: Dict[str, Tle] = {}
        self.tick_count = 0
        self.last_tick_at = 0.0

    # ---- 任务生命周期 ----

    def add_task(self, type: str, params: Dict[str, Any] | None = None,
                 schedule: Dict[str, Any] | None = None,
                 task_id: str = "") -> Dict[str, Any]:
        kind = str(type or "").strip().lower()
        if kind not in TASK_TYPES:
            return {"ok": False, "error": "bad_type",
                    "hint": f"type 需为 {'/'.join(TASK_TYPES)}，收到 {type!r}"}
        params = dict(params or {})
        schedule = dict(schedule or {})
        if schedule.get("start_at") and not schedule.get("immediate", False):
            # 定时启动：先把 start_at 解析好，tick 时比较
            try:
                schedule["_start_ts"] = _parse_when(schedule["start_at"]).timestamp()
            except (ValueError, TypeError) as exc:
                return {"ok": False, "error": "bad_schedule", "detail": str(exc)}
        if schedule.get("duration_s") is not None:
            try:
                schedule["_duration_s"] = max(0.0, float(schedule["duration_s"]))
            except (TypeError, ValueError):
                return {"ok": False, "error": "bad_schedule", "detail": "duration_s 需为数字"}

        task = Task(task_id=str(task_id or f"ptz-{uuid.uuid4().hex[:8]}"),
                    type=kind, params=params, schedule=schedule,
                    created_at=self.clock())

        # 类型专有校验推迟到启动时（add 要快；校验失败在 start 报明确错误）
        with self._lock:
            self._tasks[task.task_id] = task
            self._order.append(task.task_id)
        return {"ok": True, "task": task.as_dict()}

    def start_task(self, task_id: str) -> Dict[str, Any]:
        with self._lock:
            task = self._tasks.get(str(task_id))
            if task is None:
                return {"ok": False, "error": "task_not_found", "task_id": task_id}
            if task.state == STATE_RUNNING:
                return {"ok": True, "task": task.as_dict(), "already_running": True}
            check = self._prepare(task)
            if check is not None:
                task.state = STATE_FAILED
                task.error = check.get("error", "prepare_failed")
                task.finished_at = self.clock()
                return {**check, "task": task.as_dict()}
            task.state = STATE_RUNNING
            task.started_at = self.clock()
            task.finished_at = None
            task.error = ""
        return {"ok": True, "task": task.as_dict()}

    def stop_task(self, task_id: str, reason: str = "stopped") -> Dict[str, Any]:
        with self._lock:
            task = self._tasks.get(str(task_id))
            if task is None:
                return {"ok": False, "error": "task_not_found", "task_id": task_id}
            if task.state != STATE_RUNNING:
                return {"ok": True, "task": task.as_dict(), "not_running": True}
            task.state = STATE_ABORTED
            task.error = str(reason or "")
            task.finished_at = self.clock()
        return {"ok": True, "task": task.as_dict()}

    def stop_all(self, reason: str = "stopped_all") -> Dict[str, Any]:
        """停掉所有在跑的任务。**锁机/看门狗兜底时调它**。"""
        stopped: List[str] = []
        with self._lock:
            for task in self._tasks.values():
                if task.state == STATE_RUNNING:
                    task.state = STATE_ABORTED
                    task.error = str(reason or "")
                    task.finished_at = self.clock()
                    stopped.append(task.task_id)
        return {"ok": True, "stopped": stopped, "count": len(stopped)}

    def remove_task(self, task_id: str) -> bool:
        with self._lock:
            key = str(task_id)
            if key not in self._tasks:
                return False
            del self._tasks[key]
            self._order = [t for t in self._order if t != key]
            self._propagators.pop(key, None)
            self._tles.pop(key, None)
            return True

    # ---- 推进 ----

    def tick(self, *, locked: bool = False, link_up: bool = True,
             current: Dict[str, Any] | None = None) -> List[MoveInstruction]:
        """推进一步。返回"该发什么"。

        `locked`：急停锁机中 → **直接返回空**。自动任务绝不能把云台从锁机里开回去。
        `link_up`：链路断了 → 不下发（发了也白发）；跟踪任务记一次错误。
        """
        out: List[MoveInstruction] = []
        self.tick_count += 1
        self.last_tick_at = self.clock()
        if locked:
            return out

        with self._lock:
            tasks = [self._tasks[t] for t in self._order if t in self._tasks]
        for task in tasks:
            if task.state != STATE_RUNNING:
                continue
            try:
                out.extend(self._step(task, link_up=link_up, current=current))
            except Exception as exc:  # noqa: BLE001 - 单个任务崩了不能拖垮整轮
                task.errors += 1
                logger.warning("[ptz_scheduler] 任务 %s 步进异常: %s", task.task_id, exc)
                out.extend(self._on_task_error(task, str(exc)))
        return out

    def _step(self, task: Task, *, link_up: bool,
              current: Dict[str, Any] | None) -> List[MoveInstruction]:
        task.ticks += 1
        # 定时启动未到 → 不动
        start_ts = task.schedule.get("_start_ts")
        if start_ts is not None and self.clock() < start_ts:
            return []
        # 时长到期 → 正常结束
        duration = task.schedule.get("_duration_s")
        if duration is not None and task.started_at is not None:
            if self.clock() - task.started_at >= duration:
                self._finish(task, STATE_DONE)
                return []

        if task.type == TASK_TRACK:
            return self._step_track(task, link_up=link_up)
        if task.type == TASK_SCAN:
            return self._step_scan(task, link_up=link_up)
        if task.type == TASK_GOTO_MEM:
            return self._step_goto_mem(task)
        task.state = STATE_FAILED
        task.error = f"unknown_task_type:{task.type}"
        return []

    # ---- 跟踪 ----

    def _prepare(self, task: Task) -> Dict[str, Any] | None:
        """启动前校验。返回非 None 即失败（错误字典）。"""
        if task.type == TASK_TRACK:
            if not task.params.get("tle_line1") or not task.params.get("tle_line2"):
                return {"ok": False, "error": "missing_tle",
                        "hint": "track 任务需要 params.tle_line1 / tle_line2"}
            try:
                tle = Tle.parse(str(task.params.get("name") or "TARGET"),
                                f"{task.params['tle_line1']}\n{task.params['tle_line2']}",
                                source="task")
            except ValueError as exc:
                return {"ok": False, "error": "bad_tle", "detail": str(exc)}
            prop = make_propagator(tle, self.tracking_source)
            if not prop.available:
                # **宁可拒绝启动，也不返回假角度**
                return {"ok": False, "error": "no_propagator",
                        "detail": getattr(prop, "error", ""),
                        "hint": ("安装 sgp4（MIT 许可）后可精确跟踪：pip install sgp4；"
                                 "或显式用 tracking_source='simple' 走简化模型（仅自测）")}
            self._tles[task.task_id] = tle
            self._propagators[task.task_id] = prop
            if tle.stale:
                logger.warning("[ptz_scheduler] TLE 已 %.1f 天未更新，跟踪误差会明显偏大",
                               tle.age_days or 0.0)
            return None
        if task.type == TASK_SCAN:
            start = task.params.get("start_az")
            end = task.params.get("end_az")
            step = task.params.get("step")
            if start is None or end is None or step is None:
                return {"ok": False, "error": "missing_scan_params",
                        "hint": "scan 需要 start_az / end_az / step"}
            try:
                if abs(float(step)) <= 0:
                    return {"ok": False, "error": "bad_step", "hint": "step 需为正数"}
            except (TypeError, ValueError):
                return {"ok": False, "error": "bad_step"}
            return None
        if task.type == TASK_GOTO_MEM:
            slot = str(task.params.get("slot") or "").strip()
            if not slot:
                return {"ok": False, "error": "bad_slot", "hint": "goto_mem 需要 params.slot"}
            if self.memory.get(slot) is None:
                return {"ok": False, "error": "slot_not_found",
                        "hint": f"已存位：{', '.join(self.memory.list_slots()) or '（空）'}"}
            return None
        return {"ok": False, "error": "unknown_task_type"}

    def _step_track(self, task: Task, *, link_up: bool) -> List[MoveInstruction]:
        prop = self._propagators.get(task.task_id)
        if prop is None:
            task.state = STATE_FAILED
            task.error = "no_propagator"
            return []
        if not link_up:
            task.errors += 1
            if task.errors >= int(task.params.get("max_link_errors", 3)):
                return self._on_track_fail(task, "link_down")
            return []

        # 节流：跟踪周期（工单 1–5 s 可配）。
        # `_last_emit_at is None` = 还没发过 → **立刻发第一条**，不等一个周期。
        # （踩过：用 0.0 当"没发过"，若时钟也从 0 起就把第一条吞了。）
        now = self.clock()
        if task._last_emit_at is not None and (now - task._last_emit_at) < self.tracking_period_s:
            return []

        try:
            az, el, rng = prop.look_angles(self.site, self.wall_clock())
        except Exception as exc:  # noqa: BLE001
            task.errors += 1
            logger.warning("[ptz_scheduler] TLE 传播失败: %s", exc)
            if task.errors >= int(task.params.get("max_prop_errors", 3)):
                return self._on_track_fail(task, f"tle_failure:{exc}")
            return []

        # 出界不追（低于最低仰角 = 目标在地平线下，追它既无意义又容易撞限位）
        if el < self.min_el_deg:
            if task.params.get("fail_on_below_horizon", False):
                return self._on_track_fail(task, f"below_min_el:{el:.2f}")
            task.points += 1
            return []

        # 跟踪误差：与"上一指令"比——量的是"机构跟不跟得上"，不是"算得准不准"
        if task._last_point is not None:
            prev_az, prev_el = task._last_point
            err = max(abs(_wrap180(az - prev_az)), abs(el - prev_el))
            task.max_track_error_deg = max(task.max_track_error_deg, err)

        task._last_emit_at = now
        task.points += 1
        task._last_point = (az, el)
        if not self._claim(task.task_id):
            return []                       # 让位给手动，本次不下发
        task.moves += 1
        return [MoveInstruction(az=round(az, 3), el=round(el, 3),
                                speed=task.params.get("speed"),
                                task_id=task.task_id,
                                reason=f"track:{task.params.get('name') or 'target'}",
                                kind="track")]

    def _on_track_fail(self, task: Task, detail: str) -> List[MoveInstruction]:
        """跟踪中断（TLE 源失败）：**可配置**地保持或平滑回 HOME。"""
        task.error = detail
        if self.track_fail_action == FAIL_HOME:
            task.state = STATE_DONE
            task.finished_at = self.clock()
            self._claim(task.task_id)
            return [MoveInstruction(az=0.0, el=0.0, task_id=task.task_id,
                                    reason=f"track_interrupted->home:{detail}",
                                    kind="home")]
        # hold：原地保持，任务结束但机构不动
        task.state = STATE_DONE
        task.finished_at = self.clock()
        return []

    # ---- 扇扫循环 ----

    def _step_scan(self, task: Task, *, link_up: bool) -> List[MoveInstruction]:
        if not link_up:
            task.errors += 1
            return []
        start = float(task.params["start_az"])
        end = float(task.params["end_az"])
        step = abs(float(task.params["step"]))
        dwell = max(0.0, float(task.params.get("dwell", 1.0)))
        el = float(task.params.get("el", 0.0))
        loops = task.params.get("loops")
        max_loops = int(loops) if loops else 0     # 0 = 无限循环（工单要求"循环"）

        # 驻留：每点停 dwell 秒（`None` = 第一个点，立刻走）
        if task._last_emit_at is not None and (self.clock() - task._last_emit_at) < dwell:
            return []

        span = end - start
        count = int(abs(span) / step) + 1
        if task._cursor >= count:
            # 一轮走完：回到起点准备下一轮。**这里不产指令、也不计 moves**
            # ——"折返"是记账动作，不是机械动作。
            task._cursor = 0
            task._direction = -task._direction if task.params.get("boustrophedon") else 1
            task.points = 0
            task.loops_done += 1
            if max_loops and task.loops_done >= max_loops:
                self._finish(task, STATE_DONE)      # 已完成 max_loops 轮
                return []

        az = start + (step * task._cursor if span >= 0 else -step * task._cursor)
        task._cursor += 1
        task._last_emit_at = self.clock()
        task.points += 1
        if not self._claim(task.task_id):
            return []                       # 让位给手动，本次不下发
        task.moves += 1
        return [MoveInstruction(az=round(az, 3), el=round(el, 3),
                                speed=task.params.get("speed"),
                                task_id=task.task_id,
                                reason=f"scan:loop{task.loops_done + 1}",
                                kind="scan")]

    # ---- 记忆位 ----

    def _step_goto_mem(self, task: Task) -> List[MoveInstruction]:
        slot = str(task.params["slot"]).strip()
        entry = self.memory.get(slot)
        if entry is None:
            # 运行中记忆位被删了 → 任务失败，不猜坐标
            task.state = STATE_FAILED
            task.error = f"slot_disappeared:{slot}"
            return []
        if not self._claim(task.task_id):
            return []                       # 让位给手动
        task.moves += 1
        self._finish(task, STATE_DONE)
        return [MoveInstruction(az=float(entry["az"]), el=float(entry["el"]),
                                speed=task.params.get("speed"),
                                task_id=task.task_id, reason=f"goto_mem:{slot}",
                                kind="goto")]

    # ---- 内部 ----

    def _claim(self, task_id: str) -> bool:
        """自动任务也走仲裁：手动一旦落下，自动任务自己让位（last-wins 同语义）。

        返回 False 表示**当前不该动**——让位给手动。调用方必须据此放弃本次下发，
        否则"仲裁"就只是个日志装饰。注意 `priority` 模式下手动优先于自动
        （`PRIORITY_ORDER` 里 `local` 档低于 `serial`），这正是想要的：
        调试口/手动操作永远压得住自动跟踪。
        """
        if self.arbiter is None:
            return True
        try:
            verdict = self.arbiter.claim(SOURCE_AUTO, f"task:{task_id}")
        except Exception as exc:  # noqa: BLE001 - 仲裁异常不该阻断任务
            logger.warning("[ptz_scheduler] 仲裁调用失败（放行，不阻断）: %s", exc)
            return True
        if not verdict.accepted:
            logger.info("[ptz_scheduler] 仲裁拒绝自动任务 %s，本轮让位: %s",
                        task_id, verdict.reason)
            return False
        return True

    def _on_task_error(self, task: Task, detail: str) -> List[MoveInstruction]:
        if task.errors >= 5:
            task.state = STATE_FAILED
            task.error = detail
            task.finished_at = self.clock()
        return []

    def _finish(self, task: Task, state: str) -> None:
        task.state = state
        task.finished_at = self.clock()

    # ---- 查询 ----

    def get_task(self, task_id: str) -> Dict[str, Any] | None:
        with self._lock:
            task = self._tasks.get(str(task_id))
            return task.as_dict() if task else None

    def list_tasks(self, state: str = "") -> List[Dict[str, Any]]:
        with self._lock:
            tasks = [self._tasks[t] for t in self._order if t in self._tasks]
        if state:
            tasks = [t for t in tasks if t.state == state]
        return [t.as_dict() for t in tasks]

    def report(self, task_id: str) -> Dict[str, Any]:
        """跟踪误差报告（工单要求：「跟踪误差上报」）。"""
        with self._lock:
            task = self._tasks.get(str(task_id))
            if task is None:
                return {"ok": False, "error": "task_not_found", "task_id": task_id}
            tle = self._tles.get(task.task_id)
            out = {"ok": True, "task_id": task.task_id, "type": task.type,
                   "state": task.state, "points": task.points, "moves": task.moves,
                   "errors": task.errors,
                   "max_track_error_deg": round(task.max_track_error_deg, 4),
                   "duration_s": (round(task.finished_at - task.started_at, 3)
                                  if task.started_at and task.finished_at else None),
                   "tle": tle.as_dict() if tle else None,
                   "propagator": (self._propagators[task.task_id].kind
                                  if task.task_id in self._propagators else None),
                   "site": self.site.as_dict(),
                   "tracking_period_s": self.tracking_period_s,
                   "fail_action": self.track_fail_action}
            if tle is not None:
                out["tle_age_days"] = round(tle.age_days, 3) if tle.age_days is not None else None
                out["tle_stale"] = tle.stale
            return out

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            tasks = [self._tasks[t] for t in self._order if t in self._tasks]
            running = [t.task_id for t in tasks if t.state == STATE_RUNNING]
        return {"tasks": len(tasks), "running": running, "running_count": len(running),
                "tick_count": self.tick_count,
                "tracking_period_s": self.tracking_period_s,
                "tracking_source": self.tracking_source,
                "sgp4_available": sgp4_available(),
                "track_fail_action": self.track_fail_action,
                "site": self.site.as_dict(),
                "memory_slots": self.memory.list_slots()}


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def _wrap180(deg: float) -> float:
    """归一到 (−180, 180]——方位角跨界（359° → 1°）不该算成 358° 的误差。"""
    d = (float(deg) + 180.0) % 360.0 - 180.0
    return d


def _parse_when(text: Any) -> datetime:
    """解析 `start_at`：ISO 8601 或 Unix 时间戳。"""
    if isinstance(text, (int, float)):
        return datetime.fromtimestamp(float(text), tz=timezone.utc)
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("start_at 为空")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        except ValueError as exc:
            raise ValueError(f"无法解析时间：{raw!r}（用 ISO 8601 或 Unix 时间戳）") from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


__all__ = [
    "PTZScheduler", "Task", "MoveInstruction", "MemoryStore",
    "TASK_TRACK", "TASK_SCAN", "TASK_GOTO_MEM", "TASK_TYPES",
    "STATE_PENDING", "STATE_RUNNING", "STATE_DONE", "STATE_ABORTED", "STATE_FAILED",
    "FAIL_HOLD", "FAIL_HOME", "SOURCE_AUTO",
]
