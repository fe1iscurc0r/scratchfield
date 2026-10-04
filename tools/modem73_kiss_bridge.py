"""MODEM73 KISS TNC 桥接脚本（R54 · radio_suite 数字模式新通道）。

依据 docs/modem73-kiss-tnc-接入方案.md：
- KISS 编解码常量与 RFnexus/modem73 `kiss_tnc.hh` 对齐（FEND/FESC/TFEND/TFESC/CMD_DATA）
- 读 MODEM73 的 KISS over TCP（默认 :8001），按 FEND 定界切帧
- 把数据帧转成 APRS-IS 风格字符串或 JSON 上报
- `--simulate` 自测：本地起假 MODEM73 KISS 服务端 + 注入合成帧，跑通
  「解调 → KISS → 上报」链路，无需真电台/真 MODEM73

纯标准库，主机侧参考实现；供 radio_suite 后端调用或独立运行。

运行：
  python tools/modem73_kiss_bridge.py --simulate
  python tools/modem73_kiss_bridge.py --host 127.0.0.1 --port 8001 --json out.jsonl
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time

# KISS 协议常量（与 RFnexus/modem73 kiss_tnc.hh 一致）
FEND = 0xC0
FESC = 0xDB
TFEND = 0xDC
TFESC = 0xDD
CMD_DATA = 0x00

# 模拟链路用的合成 KISS 帧（模拟 OFDM 解调后的 AX.25 字节流）
SIM_FRAMES = [
    bytes.fromhex("6876828678407a" "f0"),  # 简化示例：目的地/源/路径/控制/信息（占位）
    bytes([0x7E, 0x00, 0x01, 0x02, 0x03, 0x7E]),
    bytes([0x7E, 0x00, 0x0A, 0x0B, 0x0C, 0x7E]),
]


def kiss_escape(data: bytes) -> bytes:
    """KISS 转义：FEND->FESC+TFEND, FESC->FESC+TFESC（仅载荷，不含定界）。"""
    out = bytearray()
    for b in data:
        if b == FEND:
            out += bytes([FESC, TFEND])
        elif b == FESC:
            out += bytes([FESC, TFESC])
        else:
            out.append(b)
    return bytes(out)


def kiss_unescape(data: bytes) -> bytes:
    """KISS 反转义。"""
    out = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b == FESC and i + 1 < len(data):
            nxt = data[i + 1]
            if nxt == TFEND:
                out.append(FEND)
            elif nxt == TFESC:
                out.append(FESC)
            else:  # 非法序列，原样保留
                out.append(b)
                out.append(nxt)
            i += 2
        else:
            out.append(b)
            i += 1
    return bytes(out)


def kiss_encode_frame(payload: bytes, port: int = 0) -> bytes:
    """编码一帧 KISS：FEND | (port<<4 | CMD_DATA) | escaped_payload | FEND。"""
    body = bytes([(port << 4) | CMD_DATA]) + kiss_escape(payload)
    return bytes([FEND]) + body + bytes([FEND])


def kiss_decode_frame(frame: bytes) -> tuple[int, bytes]:
    """解码一帧 KISS（输入含首尾 FEND），返回 (port, payload)。"""
    if len(frame) < 2 or frame[0] != FEND or frame[-1] != FEND:
        raise ValueError("malformed KISS frame")
    inner = frame[1:-1]
    if not inner:
        raise ValueError("empty KISS frame")
    type_byte = inner[0]
    port = (type_byte >> 4) & 0x0F
    cmd = type_byte & 0x0F
    if cmd != CMD_DATA:
        raise ValueError(f"unsupported KISS command 0x{cmd:02x}")
    return port, kiss_unescape(inner[1:])


def iter_kiss_frames(buffer: bytearray) -> list[bytes]:
    """从累积缓冲里切出所有完整 KISS 帧（FEND 定界），返回帧列表并原地消费缓冲。"""
    frames: list[bytes] = []
    while True:
        start = buffer.find(FEND)
        if start == -1:
            break
        end = buffer.find(FEND, start + 1)
        if end == -1:
            break  # 帧未收完，等待更多数据
        frames.append(bytes(buffer[start:end + 1]))
        del buffer[:end + 1]
    return frames


def frame_to_aprs(payload: bytes) -> str:
    """把 KISS 载荷按 AX.25 UI 帧渲染为 APRS-IS 风格字符串。

    标准 AX.25 UI 帧布局：dst(7) + src(7) + control(1=0x03 UI) + pid(1=0xF0) + info。
    info 从第 16 字节开始（跳过 control+pid）；长度不足则十六进制回退。
    桥接用途是上报，不强求完整 L3 解析。
    """
    try:
        if len(payload) >= 16:
            dst = _ax25_callsign(payload[0:7])
            src = _ax25_callsign(payload[7:14])
            info = payload[16:]
            text = info.decode("ascii", errors="replace").rstrip("\x00")
            return f"{src}>{dst}:{text}"
    except Exception:
        pass
    return "RAW:" + payload.hex()


def _ax25_callsign(encoded: bytes) -> str:
    """AX.25 呼号 7 字节（6 字符 + SSID）→ 字符串。"""
    call = "".join(chr(b >> 1) for b in encoded[:6]).strip()
    ssid = (encoded[6] >> 1) & 0x0F
    return call + (f"-{ssid}" if ssid else "")


def report_frame(payload: bytes, out_json, json_handle=None) -> None:
    """上报一帧：APRS 字符串（stdout）或 JSON 行（文件/句柄）。"""
    aprs = frame_to_aprs(payload)
    if out_json and json_handle is not None:
        json_handle.write(json.dumps({"aprs": aprs, "hex": payload.hex(), "ts": time.time()}) + "\n")
    else:
        print(aprs)


class FakeModem73Server:
    """--simulate 用的假 MODEM73：本地 KISS over TCP 服务端，注入合成帧。"""

    def __init__(self, host: str, port: int, frames: list[bytes]):
        self.host, self.port, self.frames = host, port, frames
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((host, port))
        self._sock.listen(1)
        self._sock.settimeout(10)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._sent = 0

    def start(self):
        self._thread.start()

    def _serve(self):
        try:
            conn, _ = self._sock.accept()
        except socket.timeout:
            return
        with conn:
            for payload in self.frames:
                conn.sendall(kiss_encode_frame(payload))
                time.sleep(0.05)
            time.sleep(0.2)  # 留出读取窗口
        self._sent = len(self.frames)


def run_bridge(host: str, port: int, out_json: bool, json_path: str | None) -> int:
    """连 MODEM73 KISS TCP，持续切帧上报，返回收到的帧数。"""
    json_handle = open(json_path, "a", encoding="utf-8") if (out_json and json_path) else None
    received = 0
    try:
        with socket.create_connection((host, port), timeout=5) as sock:
            sock.settimeout(3)
            buf = bytearray()
            while True:
                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    break  # 一段时间无数据即结束（自测场景）
                if not chunk:
                    break
                buf += chunk
                for frame in iter_kiss_frames(buf):
                    try:
                        _, payload = kiss_decode_frame(frame)
                    except ValueError:
                        continue
                    report_frame(payload, out_json, json_handle)
                    received += 1
    finally:
        if json_handle is not None:
            json_handle.close()
    return received


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """精确读取 n 字节。"""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("control port closed early")
        buf += chunk
    return bytes(buf)


def control_get_status(host: str = "127.0.0.1", port: int = 8073, timeout: float = 3.0) -> dict:
    """读 MODEM73 control port 的 get_status，返回状态 JSON dict。

    control port 线格式（CONTROL_PORT.md）：4 字节大端长度前缀 + JSON 载荷。
    用于 radio_suite 状态面板轮询（last_snr/last_ber/rx_frame_count/population）。
    """
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.settimeout(timeout)
        req = json.dumps({"cmd": "get_status"}).encode("utf-8")
        s.sendall(len(req).to_bytes(4, "big") + req)
        n = int.from_bytes(_recv_exact(s, 4), "big")
        body = _recv_exact(s, n)
        return json.loads(body.decode("utf-8"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="MODEM73 KISS TNC 桥接脚本（R54）")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--simulate", action="store_true", help="本地自测：假 MODEM73 注入合成帧")
    ap.add_argument("--json", metavar="PATH", default=None, help="JSONL 上报文件（缺省则 stdout 打印 APRS）")
    args = ap.parse_args(argv)

    if args.simulate:
        server = FakeModem73Server(args.host, args.port, SIM_FRAMES)
        server.start()
        time.sleep(0.1)
        received = run_bridge(args.host, args.port, bool(args.json), args.json)
        print(f"[simulate] decoded {received}/{len(SIM_FRAMES)} synthetic frames")
        return 0 if received == len(SIM_FRAMES) else 1

    received = run_bridge(args.host, args.port, bool(args.json), args.json)
    print(f"[bridge] decoded {received} frames")
    return 0


if __name__ == "__main__":
    sys.exit(main())
