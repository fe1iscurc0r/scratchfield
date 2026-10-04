# WO-05: Reticulum 许可确认 + mesh 授粉勘察报告

> 日期：2026-08-22 晚 | 委托：实验田维护者自做 | 状态：✅ 完成
> 结论先行：**许可不兼容主仓 → 参考不融合**

## 一、许可全文判定（Reticulum License, 2016-2026 Mark Qvist）

条款结构 = MIT 式权利 + 两条额外禁令：

| 条款 | 内容 | 判定 |
|------|------|------|
| 权利 | 使用/复制/修改/合并/发布/分发/再许可/出售 | ✅ 标准宽松 |
| 禁令① | 不得用于任何包含"故意伤害人类"功能的系统 | ✅ 无冲突（我们也不干） |
| **禁令②** | **不得直接或间接用于创建 AI/ML/LLM 训练数据集，包括任何有助于训练或开发此类模型/算法的用途** | ⚠️ **与主仓性质冲突** |

## 二、兼容性结论：不兼容（AGPL 主仓不能并）

- 我们的主仓（rf_brain/NEKO/Lumo）本身就是 AI 决策系统：射频大脑 = LLM 决策闭环，NEKO 记忆 = 可训练记忆层
- 禁令② 的 "including but not limited to any use that contributes to the training or development of such a model or algorithm" 边界极宽——即使 Reticulum 只当通信层，其数据流仍可能落入"AI 系统运行"范畴
- **风险不对称**：并仓收益（mesh 路由）远小于法律风险（作者明确不欢迎 AI 用途）
- **裁决：禁止 clone 进主仓，只归档设计思路**

## 三、mesh 层设计思路归档（参考不融合）

源码结构（RNS/ 包）：
- `Transport.py` — 核心传输/路由（路径表 + 广播发现）
- `Packet.py` — 数据包封装（头/校验/分片）
- `Link.py` — 点对点链路（重传/确认/流控）
- `Identity.py` + `Cryptography/` — 身份/加密（X25519 + AES-256-CTR + HKDF）
- `Interfaces/` — 多种物理接口抽象（LoRa/串口/UDP/TCP）

### 可借鉴设计要点（不抄代码，抄思路）

1. **传输层路由模型**：Reticulum 用"路径表+周期性广播"而非 OLSR 的洪泛，节点数少时开销低——适合 rf_brain 的 3-10 节点 LoRa mesh
2. **加密分层**：身份(Identity)与传输(Packet)分离，链路层用 X25519 协商 + 会话密钥——LoRa 共享介质必须加密，这套设计可直接映射
3. **接口抽象**：`Interfaces/` 把 LoRa/UART/UDP 统一成同一接口——rf_brain mesh 层照此抽象，SX1278 与串口链路可互换

## 四、映射表（rf_brain mesh 层对照）

| Reticulum 模块 | 设计意图 | rf_brain 对应 |
|---------------|---------|--------------|
| Transport.py | 路径发现/维护 | mesh_router（新建） |
| Packet.py | 分片/校验/重传 | mesh_packet |
| Link.py | 点对点可靠链路 | mesh_link |
| Identity/Crypto | X25519+AES 加密 | mesh_crypto |
| Interfaces/ | 物理接口统一抽象 | 适配 SX1278 SPI / UART |

## 五、后续建议

- 若未来需 mesh 通信：**参考此设计自己写**（路由表+广播+AES 都是成熟算法，~500 行核心）
- 或评估替代协议：LoRaMeshProtocol（MIT）、Meshtastic（GPL-3，可并主仓但重）
- Reticulum 作者立场清晰（AI 禁令），不碰为敬

---
*附录：WO-05 原工单验收标准——许可兼容性判定 ✅（不兼容，已裁决）；mesh 层映射表 ✅（见四）*
