# LoRaCanary Mesh 弹性路由 · APC-RLNC 分层网络编码（R50）方案

> 2026-08-31 · 沈遥线 · 来源：digest-g8-3a APC-RLNC 授粉点 + SPEC-20 v1.6（EWMA 分组 + XOR 冗余）
> 现状基线：`tools/link_reliability.py`（v1.6 EWMA+XOR 已验）+ `mcpserver/rf_brain/rlnc/`（GF(2^8) 分层 RLNC）
> 状态：方案 + 原型（`mcpserver/rf_brain/rlnc/apc_mesh_routing.py`，验收已过）

## 〇、一句话定位

**把 v1.6 的「弱链路 XOR 冗余」升级为「分层 RLNC 网络编码」下沉到 Mesh 多跳路由**：每条链路按 EWMA 可靠度聚类定冗余率，弱链路自动加 RLNC 冗余；中继/目的任意收到 k 个编码块即可解码；节点断电丢解码缓冲但 RTC 保留世代/epoch，唤醒即重同步——不破坏 v1/v1.5 帧格式兼容层。

## 一、现状与差距

| # | 现状（v1.6） | 差距 |
|---|-------------|------|
| 1 | 星型单跳，节点→网关直发 | 无 Mesh 多跳，弱链路（楼宇遮挡/距离拉远）仍丢 |
| 2 | XOR FEC（k 数据 + m 校验） | XOR 只恢复「恰好 1 个缺失包」，抗随机丢包但恢复能力有限 |
| 3 | 固定分组（A/B/C）单跳冗余 | 未按「端到端路径上最弱一跳」做冗余决策 |
| 4 | 深度睡眠 RTC 保 seq/node_id | 断电后 Mesh 中继的解码缓冲（易失）未纳入重同步协议 |

## 二、分层网络编码设计

### 2.1 链路可靠度 EWMA（沿用 v1.6）

```
R_n = α·ack_n + (1-α)·R_{n-1}        # α=0.3，初始 R_0=1.0
分组阈值（与 v1.6 / rlnc/clustering 一致）：
  R ≥ 0.8          → high：零冗余（factor=0.0）
  0.5 ≤ R < 0.8    → mid ：factor=0.3
  R < 0.5          → low ：factor=0.6
```

### 2.2 分层 RLNC 编码（rlnc 模块承接）

- **系统式编码**：k 原始块 → n = k + r 编码块，前 k 块是原始块（单位系数向量），后 r 块是 GF(2^8) 随机系数线性组合；`r = ⌊k × factor⌋`。
- **按链路分组编码冗余**：源端取「端到端路径上最弱一跳的冗余率」编码——弱链路 r 大、强链路 r=0 零冗余（不浪费带宽）。
- **任意 k 块可解**：目的/中继用增量高斯消元（RREF），收到任意 k 个线性无关块即还原，比 XOR 的「恰好 1 个缺失」恢复能力更强。

### 2.3 Mesh 路由与断电重同步

- **路由**：沿用 `mesh_layer.py` 的 MeshNode/MeshNetwork（beacon 邻居发现 + routeadv 多跳学习 + TTL 转发）；编码在 payload 层做，帧头（magic/flags/seq/msg_id/路由字段）不变。
- **断电重同步**：节点断电只清易失解码缓冲，`epoch+1` 与 `generation` 走 RTC 持久化；唤醒后凭世代头（generation, epoch）向源端请求重发当前世代——MagPie「无主控锚点」思想，无中心广播分组表。

### 2.4 帧兼容（不破坏 v1/v1.5）

- 编码是 **payload 层**的：系统式编码前 k 块 = 原始数据块，旧 v1/v1.5 接收端不识别冗余块时丢弃即可，仍能用系统块还原原始数据。
- 帧头字段（`mr_proto_v7` 的 magic/version/flags/msg_id/seq/src/final_dst）完全不动，AES-CCM 载荷加密照旧。

## 三、量化验收（解析模型）

单跳 PER=p、k 原始块、r 冗余块：

```
无编码交付率  = (1-p)^k
分层 RLNC      = Σ_{j=k}^{k+r} C(k+r, j)·(1-p)^j·p^{k+r-j}
```

**PER=30%（k=10）**：

| 方案 | 冗余 | 交付率 | 相对无编码 |
|------|------|--------|-----------|
| 无编码 | 0 | 2.8% | 1× |
| 分层 RLNC（low, factor=0.6） | r=6 | 82.5% | **≈29×** |

验收「弱链路交付率较无编码提升 ≥50%（≥1.5×）」成立且余量充足（≈29×）。

## 四、原型与测试

- 原型：`mcpserver/rf_brain/rlnc/apc_mesh_routing.py`
  - `delivery_probability` / `delivery_gain`：解析交付率模型
  - `HierarchicalMeshRouter`：EWMA 聚类 → 冗余率 → 系统式 RLNC 编码 → 断电重同步
  - `simulate_mesh`：Monte Carlo 多跳交付率（与解析自洽）
- 测试：`mcpserver/rf_brain/rlnc/test_apc_mesh_routing.py`（9 用例，全过）

```bash
python -m pytest mcpserver/rf_brain/rlnc/test_apc_mesh_routing.py -q   # 9 passed
```

## 五、后续施工（真机）

1. **固件侧**：ESP32（C3/S3）维护每邻居 EWMA 可靠度表 + 冗余率切换 + RTC 存 generation/epoch；断电唤醒重同步。
2. **网关侧**：RLNC 增量解码缓冲（满秩即还原）+ 世代头重发应答。
3. **真机验证**：两节点一弱一强，弱链路节点自动加 RLNC 冗余，网关仍收到完整数据；断电重启后 epoch 变化网关可识别。

## 六、约束与风险

- 冗余占空比上升：low 档节点发送量 ×1.6，需遵守 433MHz 占空比法规（≤1%），弱链路上报周期相应拉长补偿。
- RLNC 算力高于 XOR FEC：GF(2^8) 查表 + 高斯消元，C3 240MHz 可跑但 k 不宜过大（原型 k≤32）。
- RLNC 抗随机丢包；突发全丢仍需窗口内等冗余块（与 XOR 同）。
