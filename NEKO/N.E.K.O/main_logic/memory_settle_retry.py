# Copyright 2025-2026 Project N.E.K.O. Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""WO-272 / P0-18 —— session end 记忆结算失败后的待重试队列。

调用方（``main_logic/cross_server.py``）原来在结算失败时只打一条 warning，然后照旧
``chat_history.clear()``：那段对话既没进 memory_server，本地副本又被丢掉，永久消失。
本模块把失败的载荷接住，落盘一份，按指数退避重试，重试成功后回调通知连接器清理尾部。

载荷在这里是唯一的事实来源，所以这个文件本身不能重蹈 P0-19 的覆辙：读失败时它被记为
``failed``，此时禁止任何全量覆盖写——否则「重试队列读不出来」会先变成「重试队列是空的」，
再把还没结算的那几段一起抹掉。
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

from utils.config_manager import get_config_manager
from utils.file_utils import atomic_write_json, read_json
from utils.logger_config import get_module_logger

logger = get_module_logger(__name__, "Main")

SIDECAR_FILENAME = "memory_settle_retry.json"
SCHEMA_VERSION = 1

# 退避：30s 起步、每次翻倍、封顶 30 分钟。打满次数后停止自动重试但**保留载荷**，
# 把「有 N 条记忆未结算」交给 UI 侧，由人来决定丢弃还是补投。
INITIAL_BACKOFF_S = 30.0
MAX_BACKOFF_S = 1800.0
MAX_ATTEMPTS = 8
# 落盘条目上限：memory_server 长期不可用时，载荷不能无限堆积把磁盘吃穿。超限先丢
# 最老的「已打满次数」条目（那已经是人工处置过的死数据），仍超限再丢最老的普通条目。
MAX_ENTRIES = 20


def _should_log_repeated_failure(count: int) -> bool:
    return count <= 3 or count % 50 == 0


def _backoff_for(attempts: int) -> float:
    return min(INITIAL_BACKOFF_S * (2 ** max(0, attempts - 1)), MAX_BACKOFF_S)


def _digest(payload: list[dict]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


class SettleRetryQueue:
    """一个角色的待重试队列：内存一份 + 角色目录下 sidecar 一份。"""

    def __init__(self, lanlan_name: str) -> None:
        self.lanlan_name = lanlan_name
        self.entries: list[dict[str, Any]] = []
        self.load_state: str = "unloaded"
        self.read_failures = 0
        self.write_refusals = 0
        self.write_failures = 0
        self.dropped_entries = 0
        self._lock = asyncio.Lock()
        self._callbacks: dict[str, Callable[[list], None]] = {}
        # 最近一次成功落盘时**覆盖到的条目数**。用于 `wait_saved()`：内存先于磁盘是设计
        # （先保证不丢，再异步落盘），所以「内存里已有 N 条」不等于「磁盘上已有 N 条」。
        self._saved_count = 0

    # ---------- 路径与持久化 ----------

    def _file_path(self) -> Path:
        memory_dir = str(get_config_manager().memory_dir)
        character_dir = os.path.join(memory_dir, self.lanlan_name)
        from memory import _is_within_memory_root, ensure_character_dir

        # 名字解析到记忆根之外（"." / ".." / "a/b"）就不能建目录，否则 sidecar 会写到
        # 整棵记忆树旁边甚至上面。宁可放弃落盘（内存里照样重试），也不越界写。
        if not _is_within_memory_root(memory_dir, self.lanlan_name, character_dir):
            raise ValueError(f"character name escapes the memory root: {self.lanlan_name!r}")
        return Path(ensure_character_dir(memory_dir, self.lanlan_name)) / SIDECAR_FILENAME

    async def _ensure_loaded_unlocked(self) -> bool:
        """只在还没读过（unloaded / failed）时读盘；成功后不再重读，避免用磁盘内容
        覆盖掉本进程刚接住、可能还没写成功的条目。"""
        if self.load_state in ("loaded", "missing"):
            return True
        return await self._load_unlocked()

    async def _load_unlocked(self) -> bool:
        try:
            path = self._file_path()
        except Exception as exc:
            logger.warning("[%s] 待重试队列路径不可用，仅内存重试: %s", self.lanlan_name, exc)
            self.load_state = "missing"
            return False
        try:
            data = await asyncio.to_thread(read_json, path)
        except FileNotFoundError:
            # 首次启动 / 从没失败过 —— 合法空队列，下次入队会建文件
            self.entries = []
            self.load_state = "missing"
            self.read_failures = 0
            return True
        except Exception as exc:
            self.read_failures += 1
            if _should_log_repeated_failure(self.read_failures):
                logger.warning(
                    "[%s] %s 读取失败（连续第 %d 次）%s: %s —— 记为 failed，"
                    "内存里已有的条目原样保留，磁盘那份在恢复可读前不会被覆盖",
                    self.lanlan_name,
                    SIDECAR_FILENAME,
                    self.read_failures,
                    type(exc).__name__,
                    exc,
                )
            self.load_state = "failed"
            return False
        entries = data.get("entries") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            # 结构不认识 ≠ 「空队列」。当成空并覆盖，就是 P0-19 的同一个错误。
            self.read_failures += 1
            logger.warning(
                "[%s] %s 结构异常（entries 不是列表），记为 failed，不落盘",
                self.lanlan_name,
                SIDECAR_FILENAME,
            )
            self.load_state = "failed"
            return False
        self.entries = [dict(entry) for entry in entries if isinstance(entry, dict)]
        self.load_state = "loaded"
        self.read_failures = 0
        return True

    async def _save_unlocked(self) -> bool:
        if self.load_state == "failed":
            self.write_refusals += 1
            if _should_log_repeated_failure(self.write_refusals):
                logger.warning(
                    "[%s] 拒绝写 %s（连续第 %d 次）：那份文件现在读不出来，覆盖它会把"
                    "还没结算的载荷一起丢掉",
                    self.lanlan_name,
                    SIDECAR_FILENAME,
                    self.write_refusals,
                )
            return False
        try:
            path = self._file_path()
        except Exception as exc:
            logger.warning("[%s] 待重试队列路径不可用，仅内存重试: %s", self.lanlan_name, exc)
            return False
        try:
            await asyncio.to_thread(
                atomic_write_json,
                path,
                {
                    "version": SCHEMA_VERSION,
                    "lanlan_name": self.lanlan_name,
                    "entries": self.entries,
                },
                indent=2,
                ensure_ascii=False,
            )
        except Exception as exc:
            self.write_failures += 1
            logger.warning(
                "[%s] 写 %s 失败（内存那份仍然会继续重试）: %s: %s",
                self.lanlan_name,
                SIDECAR_FILENAME,
                type(exc).__name__,
                exc,
            )
            return False
        self._saved_count = len(self.entries)
        return True

    async def wait_saved(self, timeout: float = 5.0) -> bool:
        """等「磁盘上的 sidecar 已经覆盖内存里的全部条目」。

        为什么需要它：`enqueue()` 的顺序是 `entries.append(...)` → `await _save_unlocked()`
        → `await asyncio.to_thread(atomic_write_json, ...)`。内存先于磁盘是**设计**
        （先保证不丢，落盘失败也只是下次会话结束重发）。但如果调用方在**后台 task** 里入队，
        外部只能看到"内存里 pending 涨了"，此时磁盘那份可能还没写完。

        测试/优雅退出应当等这个屏障，而不是 `sleep` 猜时间，也不要直接 poll 文件
        （那会把"文件名与位置"这种实现细节写进调用方）。

        返回：True = 已落盘；False = 超时（调用方可据此决定是否继续等）。
        """
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            async with self._lock:
                if self._saved_count >= len(self.entries):
                    return True
            if asyncio.get_running_loop().time() > deadline:
                return False
            await asyncio.sleep(0.005)

    # ---------- 条目 ----------

    def _drop_superseded_unlocked(self, payload: list[dict]) -> int:
        """新载荷是旧条目的延长线（同一段对话后来又失败了）时，旧条目并入新的，
        避免同一前缀被重试两次。"""
        if not self.entries:
            return 0
        victims = {
            id(entry)
            for entry in self.entries
            if _as_payload(entry) and _as_payload(entry) == payload[: len(_as_payload(entry))]
        }
        if not victims:
            return 0
        self.entries = [e for e in self.entries if id(e) not in victims]
        return len(victims)

    async def enqueue(
        self,
        *,
        endpoint: str,
        payload: list[dict],
        language: str | None = None,
        render_language: str | None = None,
        origin: str = "session_end",
        connector_key: str = "",
        on_settled: Callable[[list], None] | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        """接住一段没结算成功的载荷。同一段重复入队只刷新退避，不复制第二份。"""
        now = time.time() if now is None else now
        async with self._lock:
            await self._ensure_loaded_unlocked()
            if on_settled is not None and connector_key:
                self._callbacks[connector_key] = on_settled
            digest = _digest(payload)
            for entry in self.entries:
                if entry.get("digest") == digest:
                    entry["attempts"] = int(entry.get("attempts", 0)) + 1
                    entry["next_retry_at"] = now + _backoff_for(entry["attempts"])
                    entry["last_error"] = f"re-queued from {origin}"
                    entry["origin"] = origin
                    entry["connector_key"] = connector_key or str(entry.get("connector_key", ""))
                    await self._save_unlocked()
                    return entry
            merged = self._drop_superseded_unlocked(payload)
            entry = {
                "session_id": uuid.uuid4().hex,
                "lanlan_name": self.lanlan_name,
                "endpoint": endpoint,
                "payload": list(payload),
                "digest": digest,
                "size": len(payload),
                "language": language,
                "render_language": render_language,
                "origin": origin,
                "connector_key": connector_key,
                "attempts": 0,
                "enqueued_at": now,
                "next_retry_at": now + INITIAL_BACKOFF_S,
                "exhausted": False,
                "last_error": "",
            }
            self.entries.append(entry)
            self._trim_if_needed()
            await self._save_unlocked()
            logger.warning(
                "[%s] 记忆结算未成功，%d 条对话已交给待重试队列"
                "（session_id=%s, endpoint=%s, origin=%s%s）",
                self.lanlan_name,
                len(payload),
                entry["session_id"][:8],
                endpoint,
                origin,
                f", 合并了 {merged} 条被它覆盖的旧条目" if merged else "",
            )
            return entry

    def _trim_if_needed(self) -> None:
        while len(self.entries) > MAX_ENTRIES:
            victim = next((e for e in self.entries if e.get("exhausted")), self.entries[0])
            self.entries.remove(victim)
            self.dropped_entries += 1
            logger.error(
                "[%s] 待重试队列超过 %d 条上限，丢弃最老的一段（session_id=%s, %d 条消息, "
                "attempts=%s）——这段记忆确实没了",
                self.lanlan_name,
                MAX_ENTRIES,
                str(victim.get("session_id", ""))[:8],
                int(victim.get("size", 0)),
                victim.get("attempts"),
            )

    def register_callback(self, connector_key: str, callback: Callable[[list], None]) -> None:
        if connector_key:
            self._callbacks[connector_key] = callback

    def unregister_callback(self, connector_key: str) -> None:
        self._callbacks.pop(connector_key, None)

    def pending_count(self) -> int:
        return len(self.entries)

    def exhausted_count(self) -> int:
        return sum(1 for entry in self.entries if entry.get("exhausted"))

    def snapshot(self) -> dict[str, Any]:
        return {
            "lanlan_name": self.lanlan_name,
            "load_state": self.load_state,
            "pending": len(self.entries),
            "exhausted": self.exhausted_count(),
            "dropped": self.dropped_entries,
            "read_failures": self.read_failures,
            "write_refusals": self.write_refusals,
            "write_failures": self.write_failures,
            "messages_pending": sum(int(entry.get("size", 0)) for entry in self.entries),
        }

    async def drain_once(
        self,
        poster: Callable[..., Awaitable[tuple[bool, str, dict]]],
        *,
        now: float | None = None,
    ) -> int:
        """重发所有到期的条目，返回本轮成功的条数。

        失败就写回 attempts / next_retry_at 等下一轮；打满 ``MAX_ATTEMPTS`` 的条目转为
        ``exhausted``：不再自动重试，但载荷仍然留在磁盘上等人处理。
        """
        now = time.time() if now is None else now
        async with self._lock:
            await self._ensure_loaded_unlocked()
            due = [
                entry
                for entry in self.entries
                if not entry.get("exhausted")
                and float(entry.get("next_retry_at") or 0.0) <= now
            ]
            if not due:
                return 0
            succeeded: list[dict[str, Any]] = []
            for entry in due:
                entry["attempts"] = int(entry.get("attempts", 0)) + 1
                try:
                    ok, err_detail, _ = await poster(
                        str(entry.get("endpoint") or "process"),
                        self.lanlan_name,
                        list(entry.get("payload") or []),
                        timeout_s=30.0,
                        language=entry.get("language"),
                        render_language=entry.get("render_language"),
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    ok, err_detail = False, f"{type(exc).__name__}: {exc}"
                if ok:
                    succeeded.append(entry)
                    continue
                entry["last_error"] = str(err_detail)
                if entry["attempts"] >= MAX_ATTEMPTS:
                    entry["exhausted"] = True
                    entry["next_retry_at"] = None
                    logger.error(
                        "[%s] 待重试队列 session_id=%s（%d 条消息）已重试 %d 次仍失败：%s"
                        " —— 停止自动重试，载荷仍留在 %s 里等人处理",
                        self.lanlan_name,
                        str(entry.get("session_id", ""))[:8],
                        int(entry.get("size", 0)),
                        entry["attempts"],
                        err_detail,
                        SIDECAR_FILENAME,
                    )
                else:
                    entry["next_retry_at"] = now + _backoff_for(entry["attempts"])
            if succeeded:
                digests = {entry.get("digest") for entry in succeeded}
                self.entries = [e for e in self.entries if e.get("digest") not in digests]
            await self._save_unlocked()
            for entry in succeeded:
                callback = self._callbacks.get(str(entry.get("connector_key") or ""))
                if not callable(callback):
                    continue
                try:
                    callback(list(entry.get("payload") or []))
                except Exception as exc:
                    logger.warning(
                        "[%s] 重试成功后的本地尾部清理回调失败: %s: %s",
                        self.lanlan_name,
                        type(exc).__name__,
                        exc,
                    )
            return len(succeeded)

    async def drop_covered(self, payload: list[dict]) -> int:
        """一次成功的结算覆盖了这些消息：把队列里作为它前缀的旧条目摘掉，免得同一段
        被 memory_server 记两遍。

        摘掉之后必须落盘：只在内存里删，进程一重启就会从 sidecar 把这段读回来再投一次
        —— 那是重复结算，正是要靠这个方法避免的东西。
        """
        if not payload:
            return 0
        async with self._lock:
            await self._ensure_loaded_unlocked()
            dropped = self._drop_superseded_unlocked(payload)
            if dropped:
                await self._save_unlocked()
            return dropped


def _as_payload(entry: dict[str, Any]) -> list[dict]:
    payload = entry.get("payload")
    return list(payload) if isinstance(payload, list) else []


_QUEUES: dict[str, SettleRetryQueue] = {}


async def queue_for(lanlan_name: str) -> SettleRetryQueue:
    """每个角色一个队列。字典的读写全在事件循环的同步段里完成，不需要额外的锁。"""
    queue = _QUEUES.get(lanlan_name)
    if queue is None:
        queue = SettleRetryQueue(lanlan_name)
        _QUEUES[lanlan_name] = queue
    return queue


def peek(lanlan_name: str) -> dict[str, Any]:
    """非阻塞健康快照；还没建过队列时返回 pending=0。"""
    queue = _QUEUES.get(lanlan_name)
    if queue is None:
        return {"lanlan_name": lanlan_name, "pending": 0, "exhausted": 0, "load_state": "unloaded"}
    return queue.snapshot()


async def run_retry_loop(
    lanlan_name: str,
    poster: Callable[..., Awaitable[tuple[bool, str, dict]]],
    *,
    check_interval_s: float = 15.0,
    should_stop: Callable[[], bool] = lambda: False,
) -> None:
    """到期条目的一条后台巡检线；由连接器创建并随连接器取消。"""
    queue = await queue_for(lanlan_name)
    while not should_stop():
        try:
            await asyncio.sleep(check_interval_s)
        except asyncio.CancelledError:
            raise
        if should_stop():
            return
        try:
            settled = await queue.drain_once(poster)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "[%s] 待重试队列巡检异常: %s: %s", lanlan_name, type(exc).__name__, exc
            )
            continue
        if settled:
            logger.info(
                "[%s] 待重试队列补投成功 %d 段，剩余 %d 段",
                lanlan_name,
                settled,
                queue.pending_count(),
            )
