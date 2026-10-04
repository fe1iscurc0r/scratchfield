"""Topics 命名规范（契约 C）—— 整合 caura-memclaw 命名约定。

- 事实：past-participle（已发生）
- 命令：requested / pre-execute（请求干活 / waterfall 门）
- 内部：internal/ 前缀（不触发 internal/dispatch 预通知，防递归）
"""
from __future__ import annotations

from enum import StrEnum


class Topics(StrEnum):
    # ---- 事实（past-participle，已发生） ----
    USER_INPUT_RECEIVED = "lumo.user.input.received"
    ASR_RESULT = "lumo.asr.result"
    TTS_START = "lumo.tts.start"
    TTS_END = "lumo.tts.end"
    MEMORY_CREATED = "lumo.memory.created"
    MEMORY_ARCHIVED = "lumo.memory.archived"
    DECISION_COMPLETED = "lumo.decision.completed"
    SKILL_INVOKED = "lumo.skill.invoked"  # W124-05：技能被加载/注入（回写记录）
    ROUTER_DECISION = "lumo.router.decision"  # W125-04：模型路由决策（surface_router 消费者）

    # ---- 命令（requested，请求干活） ----
    SPEAK_REQUESTED = "lumo.speak.requested"
    EMOTION_REQUESTED = "lumo.emotion.requested"
    MEMORY_EMBED_REQUESTED = "lumo.memory.embed-requested"
    TOOL_PRE_EXECUTE = "lumo.tool.pre-execute"  # waterfall 门

    # ---- 工具三段管道（W124-03：guard → pre-execute → execute → post-execute） ----
    #   TOOL_GUARD：参数合法性校验（不调 next 即拒；被拒不进 pre-execute）
    #   TOOL_POST_EXECUTE：执行完成后的事实广播（审计 / 失败统计 / 结果归一化检查）
    TOOL_GUARD = "lumo.tool.guard"
    TOOL_POST_EXECUTE = "lumo.tool.post-execute"

    # ---- 调度（W120-02：定时任务总线化） ----
    #   Payload: {"interval": "5m", "tick_n": 12, "triggered_at": iso}
    SCHEDULER_TICK = "lumo.scheduler.tick"

    # ---- 内部 ----
    INTERNAL_DISPATCH = "internal/dispatch"  # 所有分发的预通知
    #   Payload: {"topic": str, "mode": str, "args": list}

    # ---- 节点心跳（跨节点状态广播） ----
    NODE_HEARTBEAT = "lumo.node.heartbeat"

    # ---- 设备状态（W131-05：硬件设备进入感知层） ----
    #   Payload: {"device": str, "change": "online"|"offline", "ts": float}
    DEVICE_STATE_CHANGED = "lumo.device.state_changed"

    # ---- 哨兵网格（卷187：LoRaCanary 节点回传 → rf_brain） ----
    #   scan:       {"node_id","ts","n_bins","peak_dbm","event","ts_iso"}
    #   env:        {"node_id","ts","ts_iso","env":{temp_c,hum_pct,...}}
    #   node_online:{"node_id","ts","fw","caps","ts_iso"}
    #   occupation: {"node_id","freq_mhz","start_ts","end_ts","duration_s",
    #                "peak_dbm","mean_dbm","n_samples","kind"}
    SENTINEL_SCAN = "lumo.sentinel.scan"
    SENTINEL_ENV = "lumo.sentinel.env"
    SENTINEL_NODE_ONLINE = "lumo.sentinel.node_online"
    SENTINEL_OCCUPATION = "lumo.sentinel.occupation"

    # ---- 任务流（W119-04 桥 A：mcpserver workflow event_bus → Lumo 提升） ----
    #   workflow 侧 event_type = task_created/task_assigned/task_claimed/task_blocked/
    #   task_done/review_requested/review_approved，对照见 bridge.WORKFLOW_TO_LUMO
    TASK_CREATED = "lumo.task.created"
    TASK_ASSIGNED = "lumo.task.assigned"
    TASK_CLAIMED = "lumo.task.claimed"
    TASK_BLOCKED = "lumo.task.blocked"
    TASK_DONE = "lumo.task.done"
    REVIEW_REQUESTED = "lumo.review.requested"
    REVIEW_APPROVED = "lumo.review.approved"

    # ---- 预留扩展（未来仪器/传感器接入） ----
    RESERVED = "lumo.reserved"
