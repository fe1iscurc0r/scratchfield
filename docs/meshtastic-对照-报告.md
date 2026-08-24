# Meshtastic 协议对照报告（W-08）

> 工单：W-08 · 智能体 A 射频集成组（文档级，不写码）
> 日期：2026-08-23
> 对照对象：
> - 本地实现：[mcpserver/rf_brain/mesh_layer.py](../mcpserver/rf_brain/mesh_layer.py)（HW-01，移植自 `github_haul/radio/MeshRadio`，DJ2RF 的 MeshRadio v7 协议，ESP32/SX127x，ESP-IDF C）
> - 参照标准：[meshtastic/meshtastic](https://github.com/meshtastic)（官方 firmware + protobufs + docs/mesh-algo + encryption）
>
> 目的：对照 meshtastic 的路由 / 加密 / 帧结构设计，查 mesh_layer.py 查漏，输出差异表与改进建议。

---

## 1. 对照对象速览

### 1.1 mesh_layer.py（MeshRadio v7 移植）

- 帧头字段（`MeshPacket`）：`flags / ttl / msg_id(2B) / seq(2B) / src(8B call7) / final_dst(8B) / next_hop(8B) / last_hop(8B) / payload`
- 地址：8 字节定长 ASCII callsign（`call7`，截断 8 + 空格补齐）
- 加密：AES-128-CCM（16B key / 12B nonce / 8B tag），`nonce = src(8) + seq(2 LE) + msg_id(2 LE)`；AAD 含 `magic/version/flags/msg_id/seq/src/final_dst/payload_len`，**刻意不含转发字段** ttl/next_hop/last_hop（中间节点改它们不破坏 MAC）
- 路由：beacon 广播发现邻居 → routeadv 广播学习多跳 → 表驱动 `route_lookup` 定向（无路由退化为广播）
- TTL：`DATA_TTL=4 / BEACON_TTL=2 / ACK_TTL=4 / ADV_TTL=3`（独立显式字段）
- 去重：`seen[(src, msg_id)]` 无容量上限
- ACK：`FLAG_ACKREQ` + `FLAG_ACK`（msg_id 回显），**无自动重传循环**
- 物理层：`MeshNetwork` 直连链路表模拟广播域，无 CSMA/CA、无时隙、无 SNR 退避

### 1.2 meshtastic（官方协议，v2.6+）

- 帧头（PacketHeader，**裸字节不加密**，16B）：`To(4B) / From(4B) / PacketID(4B) / Flags(1B) / ChannelHash(1B) / NextHop(1B) / Relay(1B)` + payload（≤237B，protobuf）
- 地址：4 字节数字 NodeID（取蓝牙 MAC 低 4 字节，`0xFFFFFFFF`=广播）
- Flags 1B：`HopLimit(3bit) + WantAck(1bit) + ViaMQTT(1bit) + HopStart(3bit)`
- 加密：信道级 AES-256-CTR 流密码（密钥 128/256 位，Channel PSK 共享，**无认证**）；PKI 直消息（2.5.0+）用 X25519 ECDH + AES-256-CCM（认证加密）
- 路由（2.6 分治）：广播用 managed flooding（每节点收到未听过即重播，HopLimit 递减，SNR 感知退避）；直消息用 next-hop 路由（NextHop/Relay 字段定向）
- 物理层：LoRa，前导 16 up-chirp、sync word `0x2B`、CSMA/CA + CAD（信道活动检测 + 随机退避窗口）
- 重传：发信超时未确认重传，**最多 3 次**
- 去重：接收端缓存约 30 个包按 PacketID 去重

---

## 2. 差异对照表（≥10 行）

| # | 维度 | mesh_layer.py（MeshRadio v7） | meshtastic | 差异要点 |
|---|------|-------------------------------|------------|----------|
| 1 | 帧结构-头长 | magic(2)+ver(1)+flags(1)+msg_id(2)+seq(2)+src(8)+dst(8)+next(8)+last(8)+ttl(1) ≈ 41B + payload(≤120B) | To(4)+From(4)+ID(4)+Flags(1)+ChHash(1)+NextHop(1)+Relay(1) = 16B + payload(≤237B) | meshtastic 头仅 16B、载荷上限 237B；MeshRadio 头 ~41B、载荷上限 120B（明文 ≤112B），单包空气占用更高、有效载荷更小 |
| 2 | 地址空间 | 8B ASCII callsign（2^64 空间，人类可读） | 4B 数字 NodeID（2^32，MAC 低 4 字节） | meshtastic 地址紧凑省空气；MeshRadio 可读性好但头部开销大，且需全局唯一命名管理 |
| 3 | 广播地址 | `WILDCARD = "*"`（next_hop 字段） | `To = 0xFFFFFFFF` | 语义相同，编码不同（文本 vs 数值全 F） |
| 4 | 协议版本 | 显式 `PROTO_VERSION = 8` + magic `b"MR"` | 无显式版本字段（protobuf 演进 + 头部兼容） | meshtastic 靠 protobuf 字段演进与 1B 头部自描述；MeshRadio 显式 magic+version 更利于异构不兼容检测 |
| 5 | 加密算法 | AES-128-CCM（认证+机密性，8B tag） | 信道层 AES-256-CTR（仅机密性，**无认证**）；PKI DM 才用 AES-256-CCM | MeshRadio 信道层即认证加密，优于 meshtastic 信道 CTR（后者已知社区弱点：密文可篡改、无完整性）；meshtastic 密钥强度 256bit 高于 128bit |
| 6 | nonce/IV 构造 | `src(8B)+seq(2B)+msg_id(2B)`，AAD 含 src/dst/payload_len | `node(从 From 推导) + packet id`，IV = nonce(96bit)+counter(32bit) | 两者都不加密头部（可路由），nonce 都由公开字段构造；meshtastic 显式说明 nonce 存 flash 保证不重复 |
| 7 | 认证数据 AAD | 含 magic/ver/flags/msg_id/seq/src/dst/payload_len，**不含转发字段**（ttl/next/last） | 无（CTR 无 AAD）；CCM（PKI DM）另有构造 | MeshRadio 的设计让中间节点改写转发字段不破坏 MAC——这是对 meshtastic 信道层的重要补强点 |
| 8 | 路由-广播 | 无路由时退化为广播；有路由时表驱动定向 | managed flooding：收到即重播（HopLimit 递减），2.6+ 广播 flood 与 DM 路由分离 | meshtastic 广播不依赖路由表、天然健壮；MeshRadio 依赖 beacon/routeadv 建表，稀疏网络有收敛延迟 |
| 9 | 路由-单播 | beacon 直达 + routeadv 多跳学习，`route_lookup(dst)->next_hop`，条目 180s 超时 | 2.6+ next-hop 路由（NextHop/Relay 字段），邻居表 + 转发决策 | 思路同构（表驱动定向）；meshtastic 2.6 前仅 flood，2.6 后才引入定向，MeshRadio 一开始就是表驱动 |
| 10 | TTL/跳数 | 独立 1B 字段，按类型区分：DATA=4/BEACON=2/ACK=4/ADV=3 | Flags 3bit HopLimit（默认 HopStart=3，≤7）+ 3bit HopStart 回存 | meshtastic HopStart 可让节点感知"初始 TTL"做 SNR 衰减决策；MeshRadio TTL 固定、类型化，粒度更细但无原 TTL 信息 |
| 11 | 邻居发现 | 主动周期 beacon（TTL=2，广播） | 无专用 beacon，靠数据包 From 字段自然学习 + 可选 NeighborInfo 模块 | MeshRadio 主动 beacon 收敛快；meshtastic 被动学习省空气 |
| 12 | 去重 | `seen[(src,msg_id)]` 无容量/时间上限 | 缓存约 30 个包按 PacketID 去重，FIFO 淘汰 | meshtastic 有界防内存膨胀；MeshRadio 无界，长运行内存风险 |
| 13 | ACK 与重传 | ACKREQ 置位 → 目标回 ACK（msg_id 回显）；**无自动重传循环** | WantAck 置位 → 目标回 ACK；超时未确认**重传最多 3 次** | meshtastic 有链路层重传保障送达；MeshRadio 只发不收确认，丢包即丢（上层需自行处理） |
| 14 | 信道接入 | 无（直连链路表模拟，无碰撞概念） | CSMA/CA + CAD：发送前信道活动检测，忙则随机 CW 时隙退避 | meshtastic 物理层行为贴近真实 LoRa 半双工；MeshRadio 模拟层无碰撞/退避，仿真结果偏理想 |
| 15 | 同步/时隙 | 无时隙，无 GPS 时间依赖 | 无 TDMA 时隙；依赖退避随机化（DA 时隙由 CSMA 隐式完成），可用 GPS 时间做位置/遥测 | 两者均非 TDMA；meshtastic 用概率退避替代时隙调度 |
| 16 | 加密密钥管理 | 单一 16B 网络密钥全网共享（`DEFAULT_NET_KEY_HEX`），无密钥轮换/区分 | Channel PSK（128/256bit）+ 1B ChannelHash 提示 + PKI 逐节点密钥（2.5.0+） | meshtastic 支持多频道（最多 8）与逐节点 PKI；MeshRadio 单密钥全网、无频道隔离 |

## 3. 逐项要点说明

### 3.1 帧结构
meshtastic 把路由头压缩到 16B 裸字节（不 protobuf 编码、不加密），`ChannelHash(1B)` 用作解密提示——接收方先用 1B hash 试键，省去逐频道全试。MeshRadio 头部字段更多（8B×4 个地址/转发字段），换来 callsign 可读与显式 TTL 类型，代价是空气占用高、载荷上限低。

### 3.2 加密
- 信道级：meshtastic 用 AES-256-CTR（硬件加速、流密码零填充），但**没有 MAC**——社区评审明确警告"密文可篡改、无完整性"。MeshRadio 用 AES-128-CCM，信道层自带 8B tag 认证，且 AAD 不含转发字段（中间节点改 TTL/next/last 不破坏 MAC），这一设计实际优于 meshtastic 信道层。
- 直消息：meshtastic 2.5.0+ 补了 PKI（X25519 ECDH → SHA256 → AES-256-CCM 会话密钥），MeshRadio 无逐节点密钥。

### 3.3 路由
meshtastic 2.6 分治：广播走 managed flooding（不建表，靠 HopLimit 限制扩散 + SNR 感知退避防风暴），DM 走 next-hop。MeshRadio 全表驱动（beacon/routeadv 建表），无路由才广播。两者都是"去重 + TTL 递减 + 定向优先"骨架，差异在发现机制与退避策略。

### 3.4 重传与 ACK
meshtastic 对 WantAck 包超时重传 3 次；MeshRadio 有 ACK 机制但无重传循环，`ack_ok` 仅统计——这是查漏发现的最明显缺口。

### 3.5 物理层
meshtastic 前导 16 chirp、sync 0x2B、CSMA/CA+CAD、随机 CW 退避，仿真/实机行为一致；mesh_layer.py 用直连链路表，无碰撞与退避，适合逻辑验证但不适合链路级仿真。

---

## 4. 改进建议（3 条）

1. **补自动重传循环（最高优先）**
   MeshRadio 已有 `FLAG_ACKREQ`/`FLAG_ACK` 但无重发机制。建议在 `MeshNode` 增加"待确认队列 + 定时重发（如 3 次、指数退避）"，`send_message(ackreq=True)` 入队，收到 ACK 出队。对齐 meshtastic 的 3 次重传语义，改造成本低、直接提升丢包场景送达率。

2. **seen 去重缓存加有界淘汰**
   `MeshNode.seen` 无容量/时间上限，长运行（真机连续收包）会内存膨胀。建议仿 meshtastic 的约 30 包 FIFO 缓存，或按 `NEIGHBOR_TIMEOUT_MS` 加过期清理；同时把 `msg_id` 从 2B 扩到 4B（meshtastic PacketID 4B），降低长时间运行 ID 碰撞导致误去重的概率。

3. **模拟层引入信道占用与退避（CSMA/CA + CAD 语义）**
   `MeshNetwork.tx` 目前无碰撞概念。建议给每跳加"信道忙模拟 + 随机退避"，并在帧日志中记录 `(发送时刻, 退避时隙, 是否检测到忙)`，使 mesh_layer 的仿真行为向 meshtastic 的 CSMA/CA+CAD 靠拢，为后续接真实 SX127x 驱动提供可对照的链路层基线。

4. **（可选）多频道隔离与密钥轮换**
   meshtastic 支持 8 频道 + ChannelHash 提示 + 逐节点 PKI；MeshRadio 单密钥全网。若 HW-01 面向多组网/多业务域，建议引入 `channel_id → key` 映射与 1B channel hash 字段，密钥升级到 256bit（AES-CCM 支持 32B key），保持 CCM 认证优势同时对齐 meshtastic 的强度与隔离能力。

---

## 5. 结论

- mesh_layer.py 在**认证加密（AES-CCM + AAD 不含转发字段）**与**表驱动定向路由**上优于或持平 meshtastic 信道层；
- 主要差距：**无自动重传**、**seen 无界**、**模拟层无退避/碰撞**、**msg_id 位宽小**、**无频道隔离**；
- 建议优先落实第 1、2 条（成本低、收益直接），第 3 条按仿真精度需求推进。

## 6. 资料来源

- meshtastic official docs：Mesh Broadcast Algorithm（Layer 0-3、PacketHeader 布局、CSMA/CA、前导 16/sync 0x2B）
- meshtastic official docs：Encryption Comments（AES-256-CTR、nonce=node+packet id、IV 构造）
- meshtastic firmware behavior reference（PKI DM：Curve25519 ECDH + AES-256-CCM，会话密钥 SHA256 派生）
- meshtastic-sdk protocol reference（Channel PSK/name/id/hash 字段）
- 本地：`mcpserver/rf_brain/mesh_layer.py`（MeshRadio v7 移植）
