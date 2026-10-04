"""Sentinel-Link 节点模拟器 —— 无板子也能跑通全链路（工单卷187 A2）。

模拟 N 个 LoRaCanary 节点：在 433–434.7MHz 区间扫描，RSSI = 底噪
（-110 ± 8 dBm）叠加**周期性信号事件**（某频点 -60dBm 附近尖峰持续 5–20s），
并把 scan/env/hello 帧按 Sentinel-Link v1 编码输出。

三种输出模式（与网关消费端一一对应）::

    python -m mcpserver.rf_brain.sentinel_link.simulator --mode stdout --nodes 3
    python -m mcpserver.rf_brain.sentinel_link.simulator --mode tcp --port 48910 --nodes 3
    python -m mcpserver.rf_brain.sentinel_link.simulator --mode file --out /tmp/canary.ndjson

`--chaos`：注入**丢帧 / 乱序（延迟重发）/ 重复帧**，用于压网关的
去重与乱序重排逻辑（配合 gateway `--chaos` 验收项 3）。

`--duration S`：跑满 S 秒后自动退出（验收脚本用）；缺省则一直跑。
"""
from __future__ import annotations

import argparse
import json
import random
import socket
import sys
import time
from dataclasses import dataclass, field

from .protocol import DEFAULT_FREQ_RANGE, EnvSample, ScanBin, make_hello_frame, make_scan_frame

__all__ = ["NodeModel", "SimConfig", "SentinelSimulator", "main"]

FW_VERSION = "1.1.0"


# ── 模拟参数 ─────────────────────────────────────────────────────────────

@dataclass
class SimConfig:
    """模拟参数。"""

    nodes: int = 3
    freq_lo: float = DEFAULT_FREQ_RANGE[0]      # MHz
    freq_hi: float = DEFAULT_FREQ_RANGE[1]
    step_khz: int = 200
    interval_s: float = 1.0                     # 每节点扫描周期
    noise_floor_dbm: float = -110.0
    noise_jitter_db: float = 8.0
    event_prob: float = 0.06                    # 每轮触发新事件的概率
    event_dur_range: tuple[float, float] = (5.0, 20.0)
    event_peak_dbm: float = -60.0
    chaos: bool = False
    seed: int | None = None


@dataclass
class _ActiveEvent:
    """一个正在进行的信号占用事件。"""

    freq_mhz: float
    peak_dbm: float
    ends_at: float
    duration_s: float


@dataclass
class NodeModel:
    """单节点状态机：底噪 + 占用事件叠加。"""

    node_id: str
    cfg: SimConfig
    rng: random.Random
    t0: float = field(default_factory=time.time)
    _events: list[_ActiveEvent] = field(default_factory=list)
    _bat_mv: float = field(default=3980.0)
    _temp_c: float = field(default=23.0)

    def scan_freqs(self) -> list[float]:
        """本次扫描的频点列表（MHz，升序）。"""
        step_mhz = self.cfg.step_khz / 1000.0
        n = max(1, int(round((self.cfg.freq_hi - self.cfg.freq_lo) / step_mhz)) + 1)
        return [round(self.cfg.freq_lo + i * step_mhz, 4) for i in range(n)]

    def _maybe_spawn_event(self, now: float) -> None:
        if self.rng.random() >= self.cfg.event_prob:
            return
        dur = self.rng.uniform(*self.cfg.event_dur_range)
        peak = self.cfg.event_peak_dbm + self.rng.uniform(-6.0, 6.0)
        self._events.append(_ActiveEvent(
            freq_mhz=self.rng.choice(self.scan_freqs()),
            peak_dbm=peak,
            ends_at=now + dur,
            duration_s=dur,
        ))

    def _expire_events(self, now: float) -> None:
        self._events = [e for e in self._events if e.ends_at > now]

    def _rssi_for(self, freq: float) -> float:
        """底噪 + 活跃事件尖峰（dBm 取较强一方）。

        事件谱形：命中中心（delta=0）时 = peak_dbm；偏离 1.5 个 step 处
        **衰减到 peak_dbm - 30dB**，窗口外不再计入。窗口内线性衰减，
        不存在“越远越强”的反向增益。
        """
        noise = self.rng.gauss(self.cfg.noise_floor_dbm, self.cfg.noise_jitter_db)
        best = noise
        half_width = self.cfg.step_khz / 1000.0 * 1.5
        for ev in self._events:
            delta = abs(freq - ev.freq_mhz)
            if delta >= half_width:
                continue
            frac = 1.0 - (delta / half_width)           # 1.0=中心, 0.0=窗口边缘
            shaped = ev.peak_dbm - (1.0 - frac) * 30.0  # 边缘衰减 30dB
            best = max(best, shaped)
        return best

    def _env(self, now: float) -> EnvSample:
        """环境漂移：温度缓变 + 电池随运行时长线性下降（模拟放电）。"""
        elapsed = now - self.t0
        self._temp_c += self.rng.gauss(0.0, 0.02)
        self._bat_mv = max(3000.0, self._bat_mv - elapsed * 0.004)
        return EnvSample(
            temp_c=round(self._temp_c, 2),
            hum_pct=round(41.0 + self.rng.gauss(0.0, 0.3), 1),
            pres_hpa=round(1008.0 + self.rng.gauss(0.0, 0.1), 2),
            bat_mv=int(self._bat_mv),
        )

    def next_frame(self, now: float) -> str:
        """产出一帧 scan NDJSON（含 CRC）。"""
        self._expire_events(now)
        self._maybe_spawn_event(now)
        sfs = [0, 7, 9, 12]
        bins = [ScanBin(f, self._rssi_for(f), sf=self.rng.choice(sfs))
                for f in self.scan_freqs()]
        peak = max((b.rssi_dbm for b in bins), default=self.cfg.noise_floor_dbm)
        event = "cad_busy" if peak > self.cfg.event_peak_dbm - 6.0 else None
        return make_scan_frame(self.node_id, now, FW_VERSION, bins,
                               env=self._env(now), event=event)

    def hello_frame(self, now: float) -> str:
        caps = {"bands": [433.0], "has_gps": False, "has_env": True,
                "sf_set": [7, 9, 10, 12]}
        return make_hello_frame(self.node_id, now, FW_VERSION, caps)


# ── 多节点模拟器 + chaos 注入 + sink ─────────────────────────────────────

class SentinelSimulator:
    """N 节点模拟 + chaos 注入 + 三种输出 sink。"""

    #: chaos 注入概率（丢帧 / 重复 / 延迟乱序）
    CHAOS_DROP = 0.05
    CHAOS_DUP = 0.05
    CHAOS_DELAY = 0.08

    def __init__(self, cfg: SimConfig) -> None:
        self.cfg = cfg
        seed = cfg.seed if cfg.seed is not None else random.randrange(1 << 30)
        self.seed = seed
        self.rng = random.Random(seed)
        self.nodes = [
            NodeModel(f"canary-{i + 1:02d}", cfg, random.Random(seed + i))
            for i in range(cfg.nodes)
        ]
        self.stats = {"sent": 0, "dropped": 0, "duplicated": 0, "reordered": 0}
        self._pending: list[tuple[float, str]] = []   # 延迟队列（乱序用）
        self._sock: socket.socket | None = None
        self._conns: list[socket.socket] = []
        self._fh = None

    # ── sink ──
    def open_sink(self, mode: str, *, host: str, port: int, out_path: str) -> None:
        if mode == "tcp":
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((host, port))
            srv.listen(4)
            srv.settimeout(0.05)
            self._sock = srv
            print(f"[sim] TCP 监听 {host}:{port}（等待网关连接…，Ctrl-C 退出）",
                  file=sys.stderr, flush=True)
        elif mode == "file":
            self._fh = open(out_path, "a", encoding="utf-8")
            print(f"[sim] 写入文件 {out_path}", file=sys.stderr, flush=True)

    def close_sink(self) -> None:
        for c in self._conns:
            try:
                c.close()
            except OSError:
                pass
        if self._sock:
            self._sock.close()
        if self._fh:
            self._fh.close()

    def _accept(self) -> None:
        if not self._sock:
            return
        try:
            conn, addr = self._sock.accept()
            conn.setblocking(True)
            self._conns.append(conn)
            print(f"[sim] 网关接入 {addr[0]}:{addr[1]}", file=sys.stderr, flush=True)
        except (socket.timeout, OSError):
            pass

    def _emit(self, mode: str, line: str) -> None:
        if mode == "stdout":
            print(line, flush=True)
            return
        if mode == "file":
            if self._fh:
                self._fh.write(line + "\n")
                self._fh.flush()
            return
        dead: list[socket.socket] = []
        for c in self._conns:
            try:
                c.sendall((line + "\n").encode("utf-8"))
            except OSError:
                dead.append(c)
        for c in dead:
            self._conns.remove(c)

    def _chaos_route(self, mode: str, line: str, now: float) -> None:
        """chaos：按概率丢帧 / 重复 / 延迟（造成乱序）。"""
        self.stats["sent"] += 1
        if self.rng.random() < self.CHAOS_DROP:
            self.stats["dropped"] += 1
            return
        if self.rng.random() < self.CHAOS_DUP:
            self._emit(mode, line)          # 同 ts 同内容重复一份
            self.stats["duplicated"] += 1
        if self.rng.random() < self.CHAOS_DELAY:
            self._pending.append((now + self.rng.uniform(0.2, 1.5), line))
            self.stats["reordered"] += 1
            return
        self._emit(mode, line)

    def _flush_pending(self, mode: str, now: float) -> None:
        ready = [p for p in self._pending if p[0] <= now]
        self._pending = [p for p in self._pending if p[0] > now]
        for _, line in ready:
            self._emit(mode, line)

    def run(self, mode: str, *, duration: float | None = None) -> dict[str, int]:
        """主循环：逐节点按周期产帧，返回 chaos 统计。"""
        t_start = time.time()
        next_at = {n.node_id: time.time() for n in self.nodes}
        for n in self.nodes:                       # 上线：每节点先发 hello
            self._emit(mode, n.hello_frame(time.time()))
        try:
            while True:
                now = time.time()
                if duration is not None and now - t_start >= duration:
                    break
                if mode == "tcp":
                    self._accept()
                for n in self.nodes:
                    if now < next_at[n.node_id]:
                        continue
                    line = n.next_frame(now)
                    if self.cfg.chaos:
                        self._chaos_route(mode, line, now)
                    else:
                        self._emit(mode, line)
                    next_at[n.node_id] = now + self.cfg.interval_s
                if self.cfg.chaos:
                    self._flush_pending(mode, now)
                time.sleep(0.05)
        except KeyboardInterrupt:
            print("\n[sim] 收到中断，退出", file=sys.stderr, flush=True)
        return dict(self.stats)


# ── CLI ──────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="simulator",
        description="Sentinel-Link 节点模拟器（LoRaCanary 无板调试）",
    )
    p.add_argument("--mode", choices=["stdout", "tcp", "file"], default="stdout",
                   help="输出模式（默认 stdout）")
    p.add_argument("--nodes", type=int, default=3, help="模拟节点数（默认 3）")
    p.add_argument("--host", default="127.0.0.1", help="TCP 监听地址")
    p.add_argument("--port", type=int, default=48910, help="TCP 监听端口")
    p.add_argument("--out", default="canary.ndjson", help="file 模式的输出路径")
    p.add_argument("--interval", type=float, default=1.0, help="每节点扫描周期秒")
    p.add_argument("--freq-lo", type=float, default=DEFAULT_FREQ_RANGE[0])
    p.add_argument("--freq-hi", type=float, default=DEFAULT_FREQ_RANGE[1])
    p.add_argument("--step-khz", type=int, default=200, help="频率步进 kHz")
    p.add_argument("--event-prob", type=float, default=0.06,
                   help="每轮触发占用事件概率")
    p.add_argument("--chaos", action="store_true",
                   help="注入丢帧/乱序/重复（压网关健壮性）")
    p.add_argument("--duration", type=float, default=None,
                   help="跑满 N 秒后自动退出（缺省一直跑）")
    p.add_argument("--seed", type=int, default=None, help="随机种子（可复现）")
    p.add_argument("--quiet", action="store_true", help="不打印收尾统计")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.nodes < 1:
        print("[sim] --nodes 必须 >= 1", file=sys.stderr)
        return 2
    cfg = SimConfig(nodes=args.nodes, freq_lo=args.freq_lo, freq_hi=args.freq_hi,
                    step_khz=args.step_khz, interval_s=args.interval,
                    event_prob=args.event_prob, chaos=args.chaos, seed=args.seed)
    sim = SentinelSimulator(cfg)
    sim.open_sink(args.mode, host=args.host, port=args.port, out_path=args.out)
    try:
        stats = sim.run(args.mode, duration=args.duration)
    finally:
        sim.close_sink()
    if not args.quiet:
        print(f"[sim] 统计: {json.dumps(stats, ensure_ascii=False)}", file=sys.stderr)
    return 0


if __name__ == "__main__":                    # pragma: no cover
    raise SystemExit(main())
