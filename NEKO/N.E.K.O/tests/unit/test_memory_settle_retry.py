"""WO-272 / P0-18 —— session end 记忆结算失败的「保留 + 重试」验收。

工单验收项（原文）：
  1. 注入失败（mock 结算返回非 2xx）跑一次 session end：断言 ``chat_history`` 长度不变、
     待重试队列 +1。
  2. 恢复 mock 为成功再触发重试：断言队列清空、``chat_history`` 清空、记忆文件里出现该段。
  3. 进程重启后队列仍在（落盘文件读取断言）。

连接器里的 ``chat_history`` 是协程局部变量，测试从外面读不到，所以第 1、2 条用连接器
自己在会话结束时打的计数日志（``会话结束：聊天历史 N 条，增量 M 条``）当作「本地尾部还在
不在」的观测面；「记忆文件里出现该段」这一腿钉的是投递给 memory_server 的载荷逐条相等
（见 ``poster.captured``）——真实 memory_server 落盘要 LLM，unit 层跑不动，施工记录里已注明。
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from types import SimpleNamespace

import pytest

from main_logic import cross_server
from main_logic import memory_settle_retry as retry

pytestmark = pytest.mark.unit


class _Poster:
    """假 ``_post_memory_server``：记录每次投递的载荷，按 ``fail`` 决定成功还是非 2xx。"""

    def __init__(self, *, fail: bool = True) -> None:
        self.fail = fail
        self.captured: list[dict] = []

    async def __call__(
        self,
        endpoint,
        lanlan_name,
        payload,
        *,
        timeout_s,
        language=None,
        render_language=None,
    ):
        self.captured.append(
            {
                "endpoint": endpoint,
                "lanlan_name": lanlan_name,
                "payload": [dict(item) for item in payload],
                "language": language,
            }
        )
        if self.fail:
            return False, "HTTP 503 (body_len=0)", {}
        return True, "", {"status": "ok"}


@pytest.fixture
def store(monkeypatch, tmp_path):
    """把待重试队列的落盘根指到 tmp_path，并保证角色队列字典不跨用例残留。"""
    monkeypatch.setattr(
        retry, "get_config_manager", lambda: SimpleNamespace(memory_dir=tmp_path)
    )
    retry._QUEUES.clear()
    yield tmp_path
    retry._QUEUES.clear()


def _sidecar(root, lanlan_name: str = "Yui"):
    return root / lanlan_name / retry.SIDECAR_FILENAME


def _sidecar_entries(root) -> list[dict]:
    return json.loads(_sidecar(root).read_text(encoding="utf-8"))["entries"]


def _session_end_counts(infos: list[str]) -> tuple[int, int]:
    """从「会话结束：聊天历史 N 条，增量 M 条」取最近一次的 (N, M)。"""
    for line in reversed(infos):
        if "会话结束：聊天历史" in line:
            numbers = re.findall(r"\d+", line.split("会话结束：")[1])
            return int(numbers[0]), int(numbers[1])
    raise AssertionError(f"没有会话结束日志：{infos}")


def _session_end_lines(infos: list[str]) -> int:
    return len([line for line in infos if "会话结束：聊天历史" in line])


@pytest.fixture
def connector(monkeypatch, store):
    """返回「起连接器」的工厂；连接器 task 要在测试自己的事件循环里取消。"""
    poster = _Poster()
    infos: list[str] = []
    statuses: list[str] = []

    monkeypatch.setattr(cross_server, "_post_memory_server", poster)
    monkeypatch.setattr(
        cross_server,
        "_publish_analyze_request_with_fallback",
        lambda **kwargs: asyncio.sleep(0, result=True),
    )
    monkeypatch.setattr(cross_server.logger, "info", lambda msg, *a, **k: infos.append(str(msg)))

    async def build():
        message_queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(
            cross_server.run_sync_connector(
                message_queue,
                "Yui",
                config={"monitor": False, "bullet": False},
                status_callback=statuses.append,
            )
        )

        async def send(*messages: dict) -> None:
            for item in messages:
                await message_queue.put(item)

        async def stop() -> None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        async def wait_until(predicate, *, timeout: float = 3.0) -> None:
            deadline = asyncio.get_running_loop().time() + timeout
            while not predicate():
                if asyncio.get_running_loop().time() > deadline:
                    raise AssertionError(f"超时未满足条件；日志={infos}")
                await asyncio.sleep(0.01)

        return SimpleNamespace(
            poster=poster, infos=infos, statuses=statuses, task=task,
            send=send, stop=stop, wait_until=wait_until,
        )

    return build


async def _drive_failing_session_end(harness) -> tuple[int, int]:
    """一条用户转录 + 一次 session end：本地尾部 1 条，结算被注入成非 2xx。"""
    await harness.send(
        {"type": "user", "data": {"data": "今天陪我聊了这么久", "input_type": "transcript"}},
        {"type": "system", "data": "session end"},
    )
    await harness.wait_until(lambda: _session_end_lines(harness.infos) >= 1)
    # 计数日志在结算投递之前，入队在其之后：只等日志会读到还没落进队列的中间态
    await harness.wait_until(lambda: retry.peek("Yui")["pending"] >= 1)
    # 入队是「内存先、磁盘后」：peek 涨了不代表 sidecar 已写完（落盘走 asyncio.to_thread）。
    # 等显式屏障，而不是 sleep 猜时间，也别在这里 poll 文件名（那是实现细节）。
    queue = await retry.queue_for("Yui")
    assert await queue.wait_saved(), "入队后 sidecar 未在超时内落盘"
    counts = _session_end_counts(harness.infos)
    assert counts == (1, 1), "本地尾部必须原样留着"
    return counts


async def test_failed_settlement_keeps_the_local_tail_and_queues_the_payload(connector, store):
    """验收 1：结算失败 ⇒ 历史不清、队列 +1、sidecar 落盘一份。"""
    harness = await connector()
    try:
        assert await _drive_failing_session_end(harness) == (1, 1), "本地尾部必须原样留着"

        assert retry.peek("Yui")["pending"] == 1
        on_disk = _sidecar_entries(store)
        assert len(on_disk) == 1
        entry = on_disk[0]
        assert entry["endpoint"] == "process"
        assert entry["attempts"] == 0
        assert entry["exhausted"] is False
        assert entry["session_id"]
        assert entry["lanlan_name"] == "Yui"
        assert entry["payload"] == harness.poster.captured[0]["payload"]
        assert entry["next_retry_at"] > entry["enqueued_at"]
    finally:
        await harness.stop()


async def test_retry_success_drains_queue_and_clears_tail_in_one_step(connector, store):
    """验收 2：mock 改回成功后补投 ⇒ 队列清空、本地尾部一次性清掉、载荷逐条到达。"""
    harness = await connector()
    try:
        await _drive_failing_session_end(harness)
        failed_payload = harness.poster.captured[0]["payload"]

        queue = await retry.queue_for("Yui")
        assert queue.pending_count() == 1
        # 首次退避（30s）没到之前不许重试，否则退避语义被抹平
        assert await queue.drain_once(harness.poster, now=0.0) == 0

        harness.poster.fail = False
        settled = await queue.drain_once(
            harness.poster, now=queue.entries[0]["next_retry_at"]
        )
        assert settled == 1
        assert queue.pending_count() == 0
        assert _sidecar_entries(store) == []

        delivered = harness.poster.captured[-1]
        assert delivered["endpoint"] == "process"
        assert delivered["payload"] == failed_payload, "补投的必须是当初那一段，逐条相等"

        # 补投成功后本地尾部应该已经清掉：下一次会话结束应该看到 0 条历史
        await harness.send({"type": "system", "data": "session end"})
        await harness.wait_until(lambda: _session_end_lines(harness.infos) >= 2)
        assert _session_end_counts(harness.infos) == (0, 0)
    finally:
        await harness.stop()


async def test_queue_survives_process_restart_by_reading_the_sidecar(store):
    """验收 3：换一个全新队列对象（= 重启后的进程）读盘，条目仍在，并能补投成功。"""
    queue = await retry.queue_for("Yui")
    await queue.enqueue(
        endpoint="process",
        payload=[{"role": "user", "content": [{"type": "text", "text": "重启前那段对话"}]}],
        language="zh",
        render_language=None,
        origin="session_end",
        connector_key="old-process",
    )
    assert len(_sidecar_entries(store)) == 1

    reopened = retry.SettleRetryQueue("Yui")  # 新进程：内存一无所有
    assert reopened.pending_count() == 0
    assert await reopened._ensure_loaded_unlocked() is True
    assert reopened.pending_count() == 1, "落盘的那段必须从盘上读回来"
    assert reopened.entries[0]["payload"][0]["content"][0]["text"] == "重启前那段对话"

    poster = _Poster(fail=False)
    settled = await reopened.drain_once(poster, now=time.time() + 3600)
    assert settled == 1
    assert reopened.pending_count() == 0
    assert poster.captured[0]["payload"][0]["content"][0]["text"] == "重启前那段对话"
    assert poster.captured[0]["language"] == "zh"
    assert _sidecar_entries(store) == []


async def test_exhausted_entries_are_surfaced_to_the_ui(connector, store, monkeypatch):
    """打满次数后必须在 UI 侧报「有 N 条记忆未结算」，不能只剩日志。"""
    monkeypatch.setattr(retry, "MAX_ATTEMPTS", 2)
    harness = await connector()
    try:
        await _drive_failing_session_end(harness)
        queue = await retry.queue_for("Yui")
        # 每次都用条目上当前的 next_retry_at：退避是逐次翻倍的，写死 +1 秒会永远不到期
        assert await queue.drain_once(harness.poster, now=queue.entries[0]["next_retry_at"]) == 0
        assert queue.exhausted_count() == 0
        assert await queue.drain_once(harness.poster, now=queue.entries[0]["next_retry_at"]) == 0
        assert queue.exhausted_count() == 1
        assert queue.entries[0]["exhausted"] is True
        assert queue.entries[0]["next_retry_at"] is None
        assert len(_sidecar_entries(store)) == 1, "载荷仍然留在盘上等人处理"

        await harness.send({"type": "system", "data": "session end"})
        await harness.wait_until(lambda: any("未结算" in line for line in harness.statuses))
        assert any("有 1 条记忆未结算" in line for line in harness.statuses)
    finally:
        await harness.stop()


async def test_a_later_success_drops_the_entry_it_superseded(connector, store):
    """成功的结算覆盖了队列里的旧前缀 ⇒ 摘掉它，同一段不能被 memory_server 记两遍。"""
    harness = await connector()
    try:
        await _drive_failing_session_end(harness)
        queue = await retry.queue_for("Yui")
        assert queue.pending_count() == 1
        first_payload = queue.entries[0]["payload"]

        harness.poster.fail = False
        await harness.send(
            {"type": "user", "data": {"data": "再来一句", "input_type": "transcript"}},
            {"type": "system", "data": "session end"},
        )
        await harness.wait_until(lambda: _session_end_lines(harness.infos) >= 2)
        assert queue.pending_count() == 0, "被这次投递覆盖的旧条目应该被摘掉"
        # 摘除也要落盘才算数：等屏障，否则会在 sidecar 还没重写时读到旧内容
        assert await queue.wait_saved(), "摘除旧条目后 sidecar 未在超时内重写"
        assert _sidecar_entries(store) == []
        delivered = harness.poster.captured[-1]["payload"]
        assert delivered[: len(first_payload)] == first_payload
    finally:
        await harness.stop()


async def test_corrupt_sidecar_is_not_mistaken_for_an_empty_queue(store):
    """新文件自己不能重蹈 P0-19：读不出来 = failed，禁止用「空队列」覆盖它。"""
    path = _sidecar(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"version": 1, "entries": [{"session_id": "abc"', encoding="utf-8")
    broken = path.read_bytes()

    queue = retry.SettleRetryQueue("Yui")
    assert await queue._ensure_loaded_unlocked() is False
    assert queue.load_state == "failed"

    await queue.enqueue(
        endpoint="process",
        payload=[{"role": "user", "content": [{"type": "text", "text": "新的"}]}],
        origin="session_end",
        connector_key="k",
    )
    assert path.read_bytes() == broken, "failed 态下磁盘必须一个字节都不动"
    assert queue.write_refusals >= 1
    assert queue.pending_count() == 1, "内存里那条仍然要继续重试，不能丢"
