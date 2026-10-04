# SPEC-20 v1.6 · LoRaCanary 弱链路增强 · EWMA 可靠度分组 + 断电不丢相位

> 2026-08-29 · 实验田维护者线完成（原 AC-03 设计部分）· 论文依据：APC-RLNC 2608.26040 + MagPie 2608.25292
> 读者：Trae（算法原型施工）/ 实验田维护者（评审）/ 用户（真机验证）
> 现状基线：SPEC-20 v1（收口）+ v1.5（GPS/深度睡眠/C3，AB 工单施工中）
> 状态：设计稿 + EWMA 原型已验（tools/link_reliability.py）

## 〇、一句话定位

**v1.6 让 LoRaCanary 在 433MHz 弱链路（楼宇遮挡/移动节点/距离拉远）下不丢数据**：节点按 ACK 失败率动态分组，弱链路组自动加 XOR 冗余编码；休眠节点断电不丢时序状态，唤醒即重同步——不动 v1/v1.5 帧格式兼容层。

## 一、现状问题（差距清单）

| # | 现状 | 问题 |
|---|------|------|
| 1 | 星型单跳，节点→网关直发 | 无 ACK/重传机制，弱链路帧直接丢（ENV/GEO 无确认） |
| 2 | 固定 60s 定时上报 | 链路质量参差时无差异化（好链路也等 60s，坏链路也 60s 一锤子） |
| 3 | 明文 + CRC，无冗余 | 433MHz 市区遮挡场景 PER 高，单帧损坏即丢 |
| 4 | 深度睡眠 RTC 保持 seq/node_id | 无"唤醒即同步"协议，重启/换电池后网关侧节点状态未知 |
| 5 | 无链路质量观测 | 无法量化"哪条链路弱"，增强无从下手 |

## 二、APC-RLNC 增强设计（EWMA 分组 + XOR FEC）

### 2.1 EWMA 链路可靠度（每节点每帧维护）

```
R_n = α · ack_n + (1-α) · R_{n-1}        # ack_n ∈ {1=ACK收到/帧被网关确认, 0=丢}
初始 R_0 = 1.0，α = 0.3（实测可调，聚合历史 3-5 帧窗口）
分组阈值：
  R ≥ 0.8  → 强链路组（Group A）：单发，不加冗余
  0.5 ≤ R < 0.8 → 中链路组（Group B）：+1 XOR 冗余（发 2 取 1 恢复）
  R < 0.5  → 弱链路组（Group C）：+2 XOR 冗余（发 3 取 1 恢复）+ 上报周期翻倍兜底
```

- 观测源：网关侧收帧即回 ACK（ACK 帧已有 0xFE，v1.5 未用）；节点用 ACK 收没收到更新 R。
- 无需网关广播分组表——**节点本地维护自己的 R**，按 R 决定自己的冗余级别（无中心，符合 MagPie"无主控锚点"思想）。

### 2.2 编码选型评估（RLNC vs XOR FEC）

| 方案 | 算力 | RAM | 恢复能力 | 结论 |
|------|------|-----|---------|------|
| 完整 RLNC（GF(2^8) 随机编码，APC-RLNC 论文原版） | 中高（矩阵运算） | ~2-4KB 系数表 | 任意 k 包收 m≥k 即恢复，自适应最强 | v2 候选（C3 240MHz 可跑但复杂度高，先不做） |
| 简化 XOR FEC（k 数据包 + m 校验包 = k XOR 组合） | 极低（逐字节 XOR） | ~0（流式） | k+m 中收 k 个即可（含特定组合约束） | **v1.6 采用**：433 弱链路包小（≤23B），XOR 足够 |

选型结论：v1.6 用 XOR FEC（k=1,m=1 或 k=1,m=2，单帧冗余即最简单情形），RLNC 留 v2 评估——符合"老/重依赖只抄设计思想"授粉原则，算力评估已写死。

### 2.3 帧格式扩展（不破坏 v1/v1.5）

```
新增 type=0x04 REL（可靠帧）：
[0xD0 0xCC] [0x04] [seq:1] [node_id:1] [k:1 数据帧数] [m:1 校验帧数] [payload:N≤108] [crc16:2]
冗余帧 = 同 seq 的 XOR 校验：payload 为前 k 帧 payload 的逐字节 XOR（同长度，短帧补 0）
```

- 节点 Group B/C 上报时：先发数据帧（原 type=0x01 ENV 或 0x03 GEO），再发同 seq 的 0x04 冗余帧。
- 网关收帧：单帧 CRC 过 → 直接用；失败 → 等冗余帧 XOR 恢复（窗口 ≤2 帧周期）。
- 旧网关/旧节点不识别 0x04 → 丢弃（贞洁），向后兼容。

## 三、MagPie 增强设计（断电不丢相位）

### 3.1 现状 vs 增强

| 维度 | v1.5（已有） | v1.6 增强 |
|------|-------------|-----------|
| RTC 保持 | node_id/seq/epoch ✓ | + 链路可靠度 R（RTC 存储，重启不丢分组状态） |
| 唤醒源 | Timer 定时唤醒（60s） | + LoRa CAD 唤醒（网关可随时 ping，节点被叫醒响应，省无用上报） |
| 同步协议 | 无（隐式 seq 递增） | + epoch 版本化：节点每次重启 epoch+1，首帧带 epoch，网关据此区分"旧 seq 重放"vs"新状态" |
| 幂等 | seq 单调 | + 时隙幂等：同一 epoch+seq 的帧去重（网关存最近 N 个 (epoch,node_id,seq) 指纹） |

### 3.2 功耗预算（CAD 监听模式）

```
纯 Timer 唤醒（v1.5）：60s 周期 ≈ 0.8mA 平均（已估）
+ CAD 监听：SX1278 CAD 模式 ~1.2mA × 40ms 每 2s 扫描 ≈ +0.024mA → 可忽略
            但 CAD 常开增加复杂度和误唤醒风险 → v1.6 默认保持 Timer 唤醒，
            CAD 作为"网关按需 ping"可选通道（配置开关，默认关）
结论：v1.6 不牺牲 v1.5 功耗主线，CAD 是可选增强。
```

## 四、EWMA 原型（已实现+已验证）

`tools/link_reliability.py`（纯标准库）：
- `update_reliability(r, ack, alpha=0.3) -> r'`：EWMA 更新
- `group_for(r) -> 'A'|'B'|'C'`：分组判定
- `xor_redundancy(payloads: list[bytes]) -> bytes`：XOR 校验包生成
- `recover(payloads, xor_pkt) -> bytes`：单包丢失恢复

pytest `test_link_reliability.py`：
- EWMA 收敛正确性（全 ACK → R→1.0；全丢 → R→0）
- 分组边界（0.8/0.5 阈值）
- XOR 往返：k=2 丢 1 恢复；k=3 丢 2 恢复
- 短帧补零 XOR（不等长 payload）

## 五、施工步骤（Trae 后续，可选收进 AC 工单）

1. **AC-03a 算法落地**：tools/link_reliability.py 已有，需扩展 lora_frame.py 支持 type=0x04 REL（encode/decode/XOR）+ pytest ≥6 新用例
2. **AC-03b 固件**：C3/S3 侧 R 维护 + 冗余级别切换 + RTC 存 R/epoch；CAD ping 可选（默认关）
3. **AC-03c 网关**：ACK 回发（用 0xFE）+ 冗余帧恢复窗口 + epoch 去重指纹
4. **真机验证**（用户）：两节点一弱一强，弱链路节点 R 下降后自动切冗余，网关仍收到完整数据；断电重启后 epoch 变化网关可识别

## 六、验收标准（v1.6 全量）

```bash
cd tools && pytest -q                    # ≥22 passed（v1.5 16 + v1.6 6）
python -c "from link_reliability import *; r=update_reliability(1.0,0); print(group_for(r))"  # C
grep -n "0x04\|REL\|xor" tools/lora_frame.py   # 非空
grep -rn "requests.post\|openai\|anthropic" tools/ firmware/   # 空
```

## 七、约束与风险

- 冗余帧占空比上升：Group C 节点发送量 ×2-3，433MHz 占空比法规（≤1% 或 ≤36s/h）需遵守 → 弱链路节点上报周期自动拉长（60s→120s）补偿
- XOR FEC 只抗随机丢包，不抗突发全丢（网关侧需窗口内等冗余帧）
- ACK 本身也可能丢 → R 更新用"窗口内 N 帧中收到 ≥1 ACK 即算成功"（帧级 ACK 语义放宽）
- 中文注释/分项 commit/推 trae/agent-ac 分支（若 Trae 承接）
