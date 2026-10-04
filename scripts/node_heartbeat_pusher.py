#!/usr/bin/env python3
"""节点心跳推送脚本 —— 部署在各节点上，定期向云服 apiserver 上报状态。

用法（crontab 示例）：
    */1 * * * * /usr/bin/python3 /path/to/scripts/node_heartbeat_pusher.py

部署位置：
    云服：/home/ubuntu/scratchpad/scripts/
    Kali/K40/天选7：同步到对应机器的 ~/scripts/ 或通过 rsync 推送

依赖：requests / psutil（二选一，纯 shell 方案可只用 df/free/top 输出解析）
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Optional

# ---- 配置 ----
APISERVER_URL = os.environ.get(
    "HERMES_HEARTBEAT_URL",
    "http://localhost:8000/api/status/heartbeat",
)
NODE_ID = os.environ.get("HERMES_NODE_ID", socket.gethostname())
NODE_TYPE = os.environ.get("HERMES_NODE_TYPE", "cloud-server")
TIMEOUT = 5  # 秒


# ---- 数据采集（纯标准库，无 psutil 依赖） ----
def _cmd(cmd: str) -> str:
    try:
        return subprocess.check_output(cmd, shell=True, text=True, timeout=3).strip()
    except Exception:
        return ""


def get_metrics() -> dict:
    """采集本节点指标（无 psutil 依赖，纯 shell）。"""
    # CPU
    try:
        idle_cmd = subprocess.check_output(
            "top -bn1 | grep 'Cpu(s)' | awk '{print $8}' | sed 's/id,//'",
            shell=True, text=True, timeout=3,
        )
        cpu_idle = float(idle_cmd.strip())
        cpu_percent = round(100 - cpu_idle, 1)
    except Exception:
        cpu_percent = None

    # 内存
    try:
        free_cmd = subprocess.check_output("free -m", shell=True, text=True, timeout=3)
        lines = free_cmd.strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            total_mb = float(parts[1])
            used_mb = float(parts[2])
            memory_percent = round(used_mb / total_mb * 100, 1) if total_mb else None
        else:
            memory_percent = None
    except Exception:
        memory_percent = None

    # 磁盘
    try:
        df_cmd = subprocess.check_output(
            "df -BG / | tail -1 | awk '{print $5}'", shell=True, text=True, timeout=3
        )
        disk_percent = float(df_cmd.strip().replace("G", ""))
    except Exception:
        disk_percent = None

    # 网络速率（差分，秒级精度，首次调用差值会偏大）
    try:
        rx1 = int(subprocess.check_output(
            "cat /proc/net/dev | grep eth0 | awk '{print $2}'", shell=True, text=True, timeout=3
        ))
        time.sleep(0.5)
        rx2 = int(subprocess.check_output(
            "cat /proc/net/dev | grep eth0 | awk '{print $2}'", shell=True, text=True, timeout=3
        ))
        network_rx_mbps = round((rx2 - rx1) * 8 / 1e6 * 2, 2)  # bits/s → Mbps
    except Exception:
        network_rx_mbps = None

    return {
        "cpu_percent": cpu_percent,
        "memory_percent": memory_percent,
        "disk_percent": disk_percent,
        "api_quota_percent": None,  # 各节点自行填充（云服通过 API 查询）
        "queue_depth": 0,
        "network_rx_mbps": network_rx_mbps,
        "network_tx_mbps": None,
    }


# ---- 推送 ----
def push(url: str, payload: dict, timeout: int = TIMEOUT) -> bool:
    import urllib.error
    import urllib.request

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode())
            return result.get("ok", False)
    except urllib.error.URLError as e:
        print(f"[heartbeat] 推送失败 {url}: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[heartbeat] 未知错误: {e}", file=sys.stderr)
        return False


def build_payload() -> dict:
    return {
        "node_id": NODE_ID,
        "node_type": NODE_TYPE,
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
        "status": "online",
        "metrics": get_metrics(),
        "alerts": [],
    }


def main() -> int:
    payload = build_payload()
    ok = push(APISERVER_URL, payload)
    if ok:
        print(f"[heartbeat] {NODE_ID} 上报成功")
    else:
        print(f"[heartbeat] {NODE_ID} 上报失败（HTTP 层）", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
