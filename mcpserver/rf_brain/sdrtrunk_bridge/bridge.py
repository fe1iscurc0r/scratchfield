"""sdrtrunk sidecar · JVM 子进程桥（W-01）

职责：把 sdrtrunk（JVM 独立进程）解码输出桥接到统一 JSON schema。

两种工作模式：
1. live  —— 启动真实 sdrtrunk JVM 子进程，解析其 stdout 事件流
           （依赖：云服/真机需安装 Java 21+ 与 sdrtrunk 发行包，见 README）
2. simulate —— 内置模拟器：读入 WAV 音频文件，按 P25/DMR 帧特征产出
           与 sdrtrunk 同构的事件（本仓库 CI/无 JVM 环境验收用）

统一 schema 定义见 schema.py。桥输出为 NDJSON（每行一个 SdrtrunkEvent），
mcpserver 工具总线按行消费——天然支持管道 / 子进程 stdout 两种传输。

硬约束：本模块不触碰 NEKO/apiserver 主流程，仅提供独立可导入的桥。
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Iterator

import numpy as np

from .schema import REQUIRED_FIELDS, SdrtrunkEvent, parse_json_line, validate_event

# sdrtrunk 日志行样例（真实事件行由 JVM sidecar 适配器输出为 NDJSON 到 stdout）
# 桥本身只消费 NDJSON；非 NDJSON 行（INFO 日志等）一律跳过。


class SdrtrunkBridgeError(RuntimeError):
    """桥层错误（JVM 缺失 / 启动失败 / 事件非法）。"""


class SdrtrunkBridge:
    """JVM 独立进程桥。

    live 模式参数:
        java_bin: java 可执行文件路径
        sdrtrunk_jar: sdrtrunk 发行包 main jar 或启动器
        extra_args: 传给 sdrtrunk 的附加参数
    simulate 模式参数:
        audio_path: WAV 音频文件路径（P25/DMR 帧的模拟过桥输入）
    """

    def __init__(
        self,
        mode: str = "simulate",
        *,
        java_bin: str = "java",
        sdrtrunk_jar: str | None = None,
        extra_args: list[str] | None = None,
        audio_path: str | Path | None = None,
        sample_rate: int = 48000,
        max_events: int | None = None,
    ):
        if mode not in ("live", "simulate"):
            raise SdrtrunkBridgeError(f"未知桥模式: {mode!r}（仅支持 live/simulate）")
        self.mode = mode
        self.java_bin = java_bin
        self.sdrtrunk_jar = sdrtrunk_jar
        self.extra_args = list(extra_args or [])
        self.audio_path = Path(audio_path) if audio_path else None
        self.sample_rate = sample_rate
        self.max_events = max_events
        self._proc: subprocess.Popen | None = None
        self._stdout_lock = threading.Lock()

    # ---- 生命周期 --------------------------------------------------
    def start(self) -> None:
        if self.mode == "live":
            self._start_jvm()
        else:
            self._check_audio()

    def _check_audio(self) -> None:
        if self.audio_path is None or not self.audio_path.is_file():
            raise SdrtrunkBridgeError(
                f"simulate 模式需要存在 WAV 音频文件: {self.audio_path}")

    def _start_jvm(self) -> None:
        if not self.sdrtrunk_jar:
            raise SdrtrunkBridgeError("live 模式必须提供 sdrtrunk_jar")
        cmd = [self.java_bin, "-jar", self.sdrtrunk_jar, *self.extra_args]
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
            )
        except FileNotFoundError as e:
            raise SdrtrunkBridgeError(
                f"JVM 未就绪（java 不可执行: {self.java_bin}）。"
                f"真机/云服运行前提：安装 Java 21+ 并下载 sdrtrunk 发行包。"
            ) from e

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None

    # ---- 事件流 ----------------------------------------------------
    def iter_events(self) -> Iterator[SdrtrunkEvent]:
        """产出统一 schema 事件；逐行跳过非 NDJSON 噪音。"""
        if self.mode == "live":
            yield from self._iter_live()
        else:
            yield from self._iter_simulate()

    def _iter_live(self) -> Iterator[SdrtrunkEvent]:
        if self._proc is None:
            raise SdrtrunkBridgeError("live 桥未 start()")
        assert self._proc.stdout is not None
        count = 0
        for line in self._proc.stdout:
            ev = parse_json_line(line)
            if ev is None:
                continue
            ok, err = validate_event(ev.to_dict())
            if not ok:
                raise SdrtrunkBridgeError(f"事件字段不完整: {err}")
            yield ev
            count += 1
            if self.max_events and count >= self.max_events:
                break

    def _iter_simulate(self) -> Iterator[SdrtrunkEvent]:
        if self.audio_path is None:
            raise SdrtrunkBridgeError("simulate 桥未配置 audio_path")
        events = simulate_decode(self.audio_path, sample_rate=self.sample_rate)
        for ev in events:
            ok, err = validate_event(ev.to_dict())
            if not ok:
                raise SdrtrunkBridgeError(f"事件字段不完整: {err}")
            yield ev

    # ---- 便捷入口 --------------------------------------------------
    def decode_all(self) -> list[SdrtrunkEvent]:
        """一次性过桥：全部事件 → 列表（验收脚本/工具总线用）。"""
        try:
            self.start()
            return list(self.iter_events())
        finally:
            self.stop()


def simulate_decode(audio_path: str | Path, *, sample_rate: int = 48000) -> list[SdrtrunkEvent]:
    """模拟 sdrtrunk 解码：读 WAV 音频文件 → 产出 P25/DMR 同构事件。

    真实 sdrtrunk 会对 P25/DMR 帧解出 NAC/TG/Unit 等信息；此处模拟器
    从音频文件的时域特征（能量包络）推断帧存在性，产出与 sdrtrunk
    事件语义一致的统一 JSON（用于无 JVM 环境验收桥链路）。
    """
    path = Path(audio_path)
    try:
        with wave.open(str(path), "rb") as wf:
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
            fs = wf.getframerate()
    except (wave.Error, OSError) as e:
        raise SdrtrunkBridgeError(f"无法读取音频文件 {path}: {e}") from e

    data = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if data.size == 0:
        raise SdrtrunkBridgeError(f"音频文件为空: {path}")
    # 能量包络 → 有效帧占比（模拟解码成功判定）
    frame_ms = 20  # P25 语音帧 20ms
    frame_len = max(1, int(fs * frame_ms / 1000))
    n_full = data.size // frame_len
    if n_full == 0:
        raise SdrtrunkBridgeError(f"音频过短（<{frame_ms}ms）: {path}")
    frames = data[: n_full * frame_len].reshape(n_full, frame_len)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    active = int(np.count_nonzero(rms > 0.05))
    total = n_full
    ts_base = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    events: list[SdrtrunkEvent] = [
        SdrtrunkEvent(
            protocol="P25P1",
            event_type="call_start",
            frequency_hz=855_000_000,
            ts=ts_base,
            details=f"模拟 P25P1 呼叫开始（音频 {path.name}，{total} 帧）",
            talkgroup=12345,
            from_radio=67890,
            payload={"nac": 0x293, "modulation": "C4FM", "frame_count": total},
        ),
        SdrtrunkEvent(
            protocol="P25P1",
            event_type="frame",
            frequency_hz=855_000_000,
            ts=ts_base,
            details=f"P25P1 语音帧（active={active}/{total}）",
            talkgroup=12345,
            from_radio=67890,
            payload={"frame_type": "voice", "active_frames": active, "total_frames": total},
        ),
        SdrtrunkEvent(
            protocol="P25P1",
            event_type="call_end",
            frequency_hz=855_000_000,
            ts=ts_base,
            details=f"模拟 P25P1 呼叫结束（有效帧率 {100 * active / max(total, 1):.1f}%）",
            talkgroup=12345,
            from_radio=67890,
            payload={"duration_ms": n_full * frame_ms, "active_ratio": round(active / max(total, 1), 3)},
        ),
    ]
    # 校验必填字段，缺了就抛（验收断言前置）
    for ev in events:
        ok, err = validate_event(ev.to_dict())
        if not ok:
            raise SdrtrunkBridgeError(f"模拟事件字段不完整: {err}")
    return events


def validate_required_fields(events: list[SdrtrunkEvent]) -> tuple[bool, list[str]]:
    """验收断言：全部事件必填字段完整（grep/assert 目标）。"""
    bad: list[str] = []
    for i, ev in enumerate(events):
        d = ev.to_dict()
        missing = [f for f in REQUIRED_FIELDS if f not in d]
        if missing:
            bad.append(f"event#{i}: 缺失 {missing}")
    return (not bad), bad
