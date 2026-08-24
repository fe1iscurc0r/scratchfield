"""射频大脑 · LoRa Mesh 层（HW-01，模拟 3 节点组网）

协议移植自 github_haul/radio/MeshRadio（DJ2RF，ESP32/SX127x LoRa mesh，ESP-IDF C）：

- mr_proto_v7.h   → 帧结构、标志位、TTL、路由常量
- mr_sec_ccm.h    → AES-CCM 载荷加密（AES-128：16B key / 12B nonce / 8B tag）
- main.c          → 邻居表（beacon 发现）、路由表（beacon 直达 + routeadv 多跳学习）、
                    消息转发（TTL 递减 + seen 去重 + 路由表定向，无路由退化为广播）

设计对齐点（与固件一致的语义）：
- nonce  = src(8B) + seq(2B LE) + msg_id(2B LE)
- AAD    = magic/version/flags/msg_id/seq/src/final_dst/payload_len
           —— 刻意不含转发字段 ttl/next_hop/last_hop，中间节点改它们不破坏 MAC
- 加密后 payload = 密文 + 8B tag（payload_len = plain_len + SEC_TAG_LEN）
- 转发时 last_hop 改写为转发者，next_hop 由路由表重定向

模拟物理层：MeshNetwork 用「直连链路表」模拟 LoRa 广播域，next_hop=* 广播给全部
直连邻居，非 * 只投给指定直连节点（听不到就丢包，帧日志可审计）。
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESCCM

# ------------------------------ 协议常量（与 mr_proto_v7.h / config_meshradio.h 对齐）--
PROTO_VERSION = 8
MAGIC = b"MR"

FLAG_DATA = 0x10
FLAG_BEACON = 0x20
FLAG_ACK = 0x40
FLAG_ROUTEADV = 0x80
FLAG_ACKREQ = 0x01
FLAG_SEC = 0x08

DATA_TTL = 4
BEACON_TTL = 2
ACK_TTL = 4
ADV_TTL = 3

MAX_PAYLOAD = 120
SEC_KEY_LEN = 16
SEC_NONCE_LEN = 12
SEC_TAG_LEN = 8
MAX_PLAINTEXT = MAX_PAYLOAD - SEC_TAG_LEN

ROUTE_TIMEOUT_MS = 180_000          # 路由条目活跃时限
NEIGHBOR_TIMEOUT_MS = 60_000        # 邻居条目活跃时限
ADV_TOPN = 8                        # routeadv 最多携带的路由条数

WILDCARD = "*"                      # 广播地址（对应 mr_proto_v7.h 的 call7_is_wild）

# 默认网络密钥（与 config_meshradio.h MR_NET_KEY_HEX 同值，16 字节 hex16）
DEFAULT_NET_KEY_HEX = "00112233445566778899AABBCCDDEEFF"


def call7(s: str) -> bytes:
    """callsign → 8 字节定长（截断到 8 + 空格补齐），与 mr_call7.h call7_set 等价。"""
    return s.encode("utf-8")[:8].ljust(8, b" ")


def parse_key_hex16(hex_str: str) -> bytes:
    """hex16 字符串 → 16 字节网络密钥，与 mr_sec_ccm.h parse_key_hex16 等价。"""
    hex_str = hex_str.strip()
    assert len(hex_str) >= 32, "network key must be at least 32 hex chars (16 bytes)"
    return bytes(int(hex_str[i:i + 2], 16) for i in range(0, 32, 2))


# ------------------------------ 帧结构（对应 mr_hdr_v7_t）------------------------------
@dataclass
class MeshPacket:
    """MeshRadio v7 帧：头部字段 + payload（SEC 时 payload = 密文+8B tag）。"""
    flags: int = FLAG_DATA
    ttl: int = DATA_TTL
    msg_id: int = 0
    seq: int = 0
    src: str = ""
    final_dst: str = ""
    next_hop: str = WILDCARD
    last_hop: str = ""
    payload: bytes = b""

    def make_nonce(self) -> bytes:
        """nonce = src(8) + seq(2 LE) + msg_id(2 LE)，与 mr_sec_ccm.h sec_make_nonce 一致。"""
        return (
            call7(self.src)
            + int(self.seq & 0xFFFF).to_bytes(2, "little")
            + int(self.msg_id & 0xFFFF).to_bytes(2, "little")
        )

    def make_aad(self) -> bytes:
        """AAD：固定头字段（不含 ttl/next_hop/last_hop），与 mr_aad_v7_t 一致。"""
        return (
            MAGIC
            + bytes([PROTO_VERSION])
            + bytes([self.flags])
            + int(self.msg_id & 0xFFFF).to_bytes(2, "little")
            + int(self.seq & 0xFFFF).to_bytes(2, "little")
            + call7(self.src)
            + call7(self.final_dst)
            + bytes([len(self.payload) & 0xFF])
        )


def encrypt_payload(pkt: MeshPacket, plain: bytes, net_key: bytes) -> bytes:
    """AES-CCM 加密载荷（返回 密文+8B tag），等价 sec_encrypt_payload。

    加密时 payload 尚未填充，AAD 的 payload_len 按最终长度（plain+tag）计算。
    """
    assert len(plain) <= MAX_PLAINTEXT, f"plaintext too long: {len(plain)}"
    payload_len = len(plain) + SEC_TAG_LEN
    aad = _make_aad(pkt, payload_len)
    ccm = AESCCM(net_key, tag_length=SEC_TAG_LEN)
    return ccm.encrypt(pkt.make_nonce(), plain, aad)


def decrypt_payload(pkt: MeshPacket, net_key: bytes) -> bytes | None:
    """AES-CCM 认证解密（payload = 密文+8B tag）。MAC 失败或密钥错误 → None。

    等价 sec_decrypt_payload；转发只改 ttl/next_hop/last_hop 不破坏完整性，
    因为 AAD 不含这三个转发字段。
    """
    if len(pkt.payload) < SEC_TAG_LEN:
        return None
    ccm = AESCCM(net_key, tag_length=SEC_TAG_LEN)
    try:
        return ccm.decrypt(pkt.make_nonce(), pkt.payload, pkt.make_aad())
    except Exception:
        return None


def _make_aad(pkt: MeshPacket, payload_len: int) -> bytes:
    """构造 AAD（payload_len 显式传入，加密/解密一致）。"""
    return (
        MAGIC
        + bytes([PROTO_VERSION])
        + bytes([pkt.flags])
        + int(pkt.msg_id & 0xFFFF).to_bytes(2, "little")
        + int(pkt.seq & 0xFFFF).to_bytes(2, "little")
        + call7(pkt.src)
        + call7(pkt.final_dst)
        + bytes([payload_len & 0xFF])
    )


# ------------------------------ 邻居 / 路由条目（对应 main.c 的 neighbor_t / route_t）----
@dataclass
class NeighborEntry:
    """一跳邻居（由 beacon 发现）。"""
    rssi: int = -127
    t_ms: float = 0.0
    tx_attempts: int = 0
    ack_ok: int = 0


@dataclass
class RouteEntry:
    """路由条目：dst → next_hop（带 seq 版本 + 跳数 + 活跃时间）。"""
    dst: str
    next: str
    seq: int = 0
    hop_count: int = 1
    t_ms: float = 0.0


# ------------------------------ 网格节点（对应 mesh node 固件）--------------------------
class MeshNode:
    """单个 LoRa mesh 节点：beacon 发现邻居、routeadv 学习多跳路由、TTL 转发、AES 载荷。"""

    def __init__(self, callsign: str, network: "MeshNetwork", net_key: bytes,
                 rssi_db: int = -80) -> None:
        self.callsign = callsign
        self.network = network
        self.net_key = net_key
        self.rssi_db = rssi_db

        self._seq = 0
        self._msg_id = 0
        self.routeadv_seq = 0

        self.neighbors: dict[str, NeighborEntry] = {}
        self.routes: dict[str, RouteEntry] = {}
        self.seen: dict[tuple[str, int], float] = {}
        self.delivered: list[tuple[str, str, bytes]] = []  # (src, final_dst, 明文)

        self.tx_count = 0            # 本节点发出帧数
        self.tx_forward_count = 0    # 其中转发帧数（final_dst != me）
        self.rx_drop_duplicate = 0
        self.rx_drop_auth = 0

    # ---- 计数器 / 时钟 ----
    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def next_msg_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    @staticmethod
    def now_ms() -> float:
        return time.monotonic() * 1000.0

    # ---- 邻居 / 路由表（与 main.c neighbor_* / route_* 同构）----
    def neighbor_update(self, call: str, rssi: int | None = None) -> None:
        t = self.now_ms()
        e = self.neighbors.get(call)
        if e is None:
            self.neighbors[call] = NeighborEntry(rssi=rssi if rssi is not None else self.rssi_db, t_ms=t)
        else:
            if rssi is not None:
                e.rssi = rssi
            e.t_ms = t

    def neighbor_expire(self) -> None:
        t = self.now_ms()
        for call in [c for c, e in self.neighbors.items() if t - e.t_ms > NEIGHBOR_TIMEOUT_MS]:
            del self.neighbors[call]

    def route_update(self, dst: str, next_hop: str, seq: int, hop_count: int) -> None:
        """学习/刷新路由。seq 更新（主）或跳数更优（次）时替换 next_hop。"""
        if next_hop == self.callsign:
            return
        t = self.now_ms()
        r = self.routes.get(dst)
        if r is None:
            self.routes[dst] = RouteEntry(dst=dst, next=next_hop, seq=seq,
                                          hop_count=hop_count, t_ms=t)
            return
        if seq > r.seq or (seq == r.seq and hop_count < r.hop_count):
            r.next = next_hop
            r.seq = seq
            r.hop_count = hop_count
        r.t_ms = t

    def route_lookup(self, dst: str) -> str | None:
        """查路由表取 next_hop；条目超时（ROUTE_TIMEOUT_MS）视为无路由。"""
        r = self.routes.get(dst)
        if r is None:
            return None
        if self.now_ms() - r.t_ms > ROUTE_TIMEOUT_MS:
            del self.routes[dst]
            return None
        return r.next

    # ---- 去重缓存（与 main.c seen_before / remember_msg 同构）----
    def seen_before(self, src: str, msg_id: int) -> bool:
        return (src, msg_id) in self.seen

    def remember_msg(self, src: str, msg_id: int) -> None:
        self.seen[(src, msg_id)] = self.now_ms()

    # ---- 发送路径 ----
    def send_message(self, dst: str, text: str, ackreq: bool = False) -> MeshPacket:
        """发送用户消息：AES-128 加密载荷 → 路由表定向（无路由广播）→ 交给物理层。"""
        plain = text.encode("utf-8")
        assert len(plain) <= MAX_PLAINTEXT
        pkt = MeshPacket(
            flags=FLAG_DATA | FLAG_SEC | (FLAG_ACKREQ if ackreq else 0),
            ttl=DATA_TTL,
            msg_id=self.next_msg_id(),
            seq=self.next_seq(),
            src=self.callsign,
            final_dst=dst,
            last_hop=self.callsign,
        )
        pkt.payload = encrypt_payload(pkt, plain, self.net_key)
        nxt = self.route_lookup(dst)
        pkt.next_hop = nxt if nxt else WILDCARD
        self.network.tx(self, pkt)
        return pkt

    def broadcast_beacon(self) -> MeshPacket:
        """节点发现：广播 beacon，邻居收到后记录「到达 src 的直达路由」。"""
        pkt = MeshPacket(
            flags=FLAG_BEACON, ttl=BEACON_TTL,
            msg_id=self.next_msg_id(), seq=self.next_seq(),
            src=self.callsign, final_dst=WILDCARD,
            next_hop=WILDCARD, last_hop=self.callsign,
        )
        self.network.tx(self, pkt)
        return pkt

    def broadcast_routeadv(self) -> MeshPacket | None:
        """广播路由广告（topn 条），让邻居学到「经我到达 dst」的多跳路由。

        payload 紧凑编码：dst(8) + next(8) + hop_count(1)，对应 ROUTEADV_PL_LEN。
        """
        if not self.routes:
            return None
        self.routeadv_seq += 1
        body = bytearray()
        for dst, r in sorted(self.routes.items())[:ADV_TOPN]:
            body += call7(dst) + call7(r.next) + bytes([r.hop_count & 0xFF])
        pkt = MeshPacket(
            flags=FLAG_ROUTEADV, ttl=ADV_TTL,
            msg_id=self.next_msg_id(), seq=self.routeadv_seq,
            src=self.callsign, final_dst=WILDCARD,
            next_hop=WILDCARD, last_hop=self.callsign,
            payload=bytes(body),
        )
        self.network.tx(self, pkt)
        return pkt

    # ---- 接收路径（与 main.c handle_rx 同构）----
    def receive(self, pkt: MeshPacket) -> None:
        """收帧入口：去重 → 更新邻居/直达路由 → 按类型分流（beacon/routeadv/ack/data）。

        拷贝入帧：广播时多接收者共享同一 pkt 对象，转发者会原地改写
        ttl/next_hop/last_hop，必须隔离，避免互相污染。
        """
        pkt = copy.copy(pkt)
        if pkt.src == self.callsign:
            return
        if self.seen_before(pkt.src, pkt.msg_id):
            self.rx_drop_duplicate += 1
            return
        self.remember_msg(pkt.src, pkt.msg_id)

        # 任何合法帧都刷新 last_hop 邻居与「到达 src 的直达路由」
        self.neighbor_update(pkt.last_hop)
        self.route_update(pkt.src, pkt.last_hop, seq=pkt.seq, hop_count=1)

        if pkt.flags & FLAG_BEACON:
            return
        if pkt.flags & FLAG_ROUTEADV:
            self._absorb_routeadv(pkt)
            return
        if pkt.flags & FLAG_ACK:
            return
        if pkt.flags & FLAG_DATA:
            self._handle_data(pkt)

    def _absorb_routeadv(self, pkt: MeshPacket) -> None:
        """吸收邻居广播的路由广告：dst 经 pkt.last_hop 可达，跳数 +1。"""
        body = pkt.payload
        i = 0
        while i + 17 <= len(body):
            dst = body[i:i + 8].decode("ascii", "ignore").rstrip()
            _nxt = body[i + 8:i + 16].decode("ascii", "ignore").rstrip()
            hop = body[i + 16]
            i += 17
            if not dst or dst == self.callsign:
                continue
            self.route_update(dst, pkt.last_hop, seq=pkt.seq, hop_count=hop + 1)

    def _handle_data(self, pkt: MeshPacket) -> None:
        if pkt.final_dst == self.callsign:
            self._deliver(pkt)
            return
        self._forward(pkt)

    def _deliver(self, pkt: MeshPacket) -> None:
        """目的地投递：SEC 载荷先认证解密，失败丢弃；ACKREQ 则回 ACK。"""
        if pkt.flags & FLAG_SEC:
            plain = decrypt_payload(pkt, self.net_key)
            if plain is None:
                self.rx_drop_auth += 1
                return
        else:
            plain = pkt.payload
        self.delivered.append((pkt.src, pkt.final_dst, plain))
        if pkt.flags & FLAG_ACKREQ:
            ack = MeshPacket(
                flags=FLAG_ACK, ttl=ACK_TTL,
                msg_id=pkt.msg_id, seq=self.next_seq(),
                src=self.callsign, final_dst=pkt.last_hop,
                next_hop=WILDCARD, last_hop=self.callsign,
            )
            self.network.tx(self, ack)

    def _forward(self, pkt: MeshPacket) -> None:
        """中间节点转发：TTL 递减 → last_hop 改写为自身 → 路由表定向（无路由广播）。"""
        if pkt.ttl <= 1:
            return
        pkt.ttl -= 1
        pkt.last_hop = self.callsign
        nxt = self.route_lookup(pkt.final_dst)
        pkt.next_hop = nxt if nxt else WILDCARD
        self.tx_forward_count += 1
        self.network.tx(self, pkt)


# ------------------------------ 物理层模拟（LoRa 广播域）-------------------------------
class MeshNetwork:
    """模拟共享 LoRa 信道：links 表定义可直连（互相听得到）的节点对。

    - next_hop == "*" → 广播给所有直连邻居
    - next_hop == X   → 只投给 X；若 X 不在直连范围内则丢包（真实：听不到）
    frames_tx 记录每一次空中发送，供测试审计转发路径。
    """

    def __init__(self) -> None:
        self.nodes: dict[str, MeshNode] = {}
        self.links: set[frozenset[str]] = set()
        self.frames_tx: list[tuple[str, MeshPacket]] = []
        self.frames_dropped: list[tuple[str, MeshPacket, str]] = []

    def add_node(self, node: MeshNode) -> None:
        self.nodes[node.callsign] = node

    def add_link(self, a: str, b: str) -> None:
        """a、b 直连（同一 LoRa 频率/扩频因子，互相可听）。"""
        self.links.add(frozenset((a, b)))

    def can_hear(self, a: str, b: str) -> bool:
        return frozenset((a, b)) in self.links

    def tx(self, src_node: MeshNode, pkt: MeshPacket) -> None:
        src_node.tx_count += 1
        self.frames_tx.append((src_node.callsign, pkt))
        if pkt.next_hop == WILDCARD:
            for call in sorted(self.nodes):
                if call != src_node.callsign and self.can_hear(src_node.callsign, call):
                    self.nodes[call].receive(pkt)
        else:
            dst_node = self.nodes.get(pkt.next_hop)
            if dst_node is None or not self.can_hear(src_node.callsign, pkt.next_hop):
                self.frames_dropped.append((src_node.callsign, pkt, pkt.next_hop))
                return
            dst_node.receive(pkt)
