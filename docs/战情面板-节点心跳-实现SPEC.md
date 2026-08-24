# 战情面板 —— 节点心跳广播系统 SPEC

> 工单：盲区①-1 | 日期：2026-08-23 | 状态：写码中
> 目标：四节点（云服/Kali/K40/天选7）心跳状态通过 EventBus 广播

---

## 一、架构设计

### 现状
- `apiserver/routes/system.py` 有 `/health`（仅本进程 WebSocket 统计）和 `/health/full`（查 agent_server）
- `apiserver/event_bus/` 已有 InProcessEventBus（emit/parallel/serial/bail/waterfall 五种 dispatch）
- `apiserver/event_bus/topics.py` 的 Topics 枚举中已有 `RESERVED` 槽位
- **缺口**：无跨节点状态汇聚，无 heartbeat topic

### 方案
```
各节点（定时脚本） → POST /api/status/heartbeat → apiserver 内存存储（TTL 淘汰）
                                                        ↓
                                              EventBus.emit(NODE_HEARTBEAT, payload)
                                                        ↓
                                              订阅者（战情面板/告警/监控）收到
                                                        ↓
                                        GET /api/status/nodes → 各节点最新状态
```

---

## 二、EventBus Topic 扩展

### 新增 Topics（topics.py）

```python
# ---- 节点心跳（事实）----
NODE_HEARTBEAT = "lumo.node.heartbeat"   # 每台节点定期推送状态
```

---

## 三、接口设计

### POST /api/status/heartbeat（节点上报）

**路径**：`/api/status/heartbeat`
**鉴权**：免鉴权（节点在内网，定向 IP 白名单由网络层控制）
**请求体**：
```json
{
  "node_id": "cloud-server",          // 节点标识（hostname 或自定义名）
  "node_type": "cloud-server",        // cloud-server | kali | k40 | tianxuan7
  "timestamp": "2026-08-23T17:00:00+08:00",
  "status": "online",                 // online | degraded | offline
  "metrics": {
    "cpu_percent": 45.2,
    "memory_percent": 62.8,
    "disk_percent": 38.5,
    "api_quota_percent": 87.3,        // 模型 API 余额（tokenrhythm 等）
    "queue_depth": 0,                  // 待处理任务队列深度
    "network_rx_mbps": 12.4,
    "network_tx_mbps": 8.7
  },
  "alerts": []                         // 安全告警列表，如 ["rate_limit_near", "disk_warning"]
}
```

**响应**：`{"ok": true, "received": "<node_id>", "ttl": 120}`

### GET /api/status/nodes（查所有节点）

**路径**：`/api/status/nodes`
**鉴权**：免鉴权（同 /health）
**响应**：
```json
{
  "nodes": {
    "cloud-server": { ...最后一次心跳payload... },
    "kali": { ... },
    "k40": { ... },
    "tianxuan7": { ... }
  },
  "timestamp": 1787476800
}
```
**TTL**：节点超过 120s 未上报则从响应中剔除（内存淘汰）

---

## 四、存储设计

```python
# apiserver/routes/status_heartbeat.py

from datetime import datetime, timedelta
from threading import RLock

_HEARTBEAT_TTL = 120  # 秒
_node_heartbeats: dict[str, dict] = {}
_heartbeat_lock = RLock()

def _purge_expired():
    now = datetime.now()
    expired = [k for k, v in _node_heartbeats.items()
               if (now - v["_received_at"]).total_seconds() > _HEARTBEAT_TTL]
    for k in expired:
        _node_heartbeats.pop(k, None)
```

---

## 五、EventBus 集成

```python
from apiserver.event_bus import get_bus, Topics

bus = get_bus()

# 上报时：
bus.emit(Topics.NODE_HEARTBEAT, payload)   # fire-and-forget

# 订阅示例（战情面板 UI）：
d = bus.on(Topics.NODE_HEARTBEAT, handler)
```

---

## 六、文件清单

| 文件 | 操作 |
|------|------|
| `apiserver/event_bus/topics.py` | 追加 `NODE_HEARTBEAT` 枚举值 |
| `apiserver/routes/status_heartbeat.py` | 新建：心跳接收+查询路由 |
| `apiserver/api_server.py` | 注册新路由 `status_heartbeat_router` |
| `scripts/node_heartbeat_pusher.py` | 新建：各节点部署的推送脚本（crontab 调用） |

---

## 七、验收标准

1. `grep -r "heartbeat" apiserver/` 命中 ≥3 个文件
2. `curl -s http://localhost:8000/api/status/nodes` 返回节点状态 JSON（启动后）
3. `curl -s -X POST http://localhost:8000/api/status/heartbeat -H "Content-Type: application/json" -d '{"node_id":"test","node_type":"cloud-server","status":"online","metrics":{}}'` 返回 `{"ok": true}`
4. EventBus topic `NODE_HEARTBEAT` 存在于 Topics 枚举
5. 超过 TTL 未上报的节点在 GET 响应中自动消失
