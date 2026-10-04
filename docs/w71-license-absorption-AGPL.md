# W71 许可重裁 · AGPL 吸收裁定（本仓协议 AGPL-3.0）

> 用户裁定：本仓协议为 **AGPL**。「能吞就吞」——GPL-3.0 / AGPL-3.0 / MIT / Apache / BSD 的代码
> 可在 **AGPL 下并入**（合并后整体 AGPL，需保留原版权声明与许可头）；GPL-2.0-only 与 AGPL-3.0
> 版本不兼容、**只参考设计不吞代码**；NOASSERTION 仍「许可待核」。

## 逐项重裁

| 工单 | 项目 | 原裁定 | 重裁（AGPL） | 吞法 |
|---|---|---|---|---|
| W71-01 | painlessMesh | GPL 参考 | GPL（**需核 2.0-only 还是 3.0**）→ 3.0 可吞 / 2.0-only 参考 | 路由算法吞入（本批已实现）|
| W71-02 | meshtastic_sdr | GPL 参考 | GPL-3.0 → 可吞 | 软 LoRa PHY 思路吞入（并入 W71-08）|
| W71-03 | GitLab knowledge-graph | MIT 可借鉴 | MIT → **可吞** | 工单↔代码图吞入（本批已实现）|
| W71-04 | bluepad32 | Apache 可借鉴 | Apache-2.0 → **可吞** | HID 报告解析吞入（协议公开）|
| W71-05 | SatNOGS/gr-leo | AGPL/GPL 参考 | AGPL-3.0 / GPL-3.0 → **可吞** | 链路预算/多普勒吞入（本批已实现）|
| W71-06 | theseus-cores | 许可待核 | NOASSERTION → **仍待核** | Verilog 暂不吞（许可未明）|
| W71-07 | gnss-sdr | GPL 参考 | GPL-3.0 → **可吞** | GNSS 捕获状态机吞入（设计级）|
| W71-08 | gr-lora_sdr+lorhammer | GPL/待核 | GPL-3.0 → **可吞** | 软 LoRa chirp PHY 吞入（本批已实现）|
| W71-09 | x-qsl ADIF | 许可待核 | ADIF 开放格式 → **可自由实现** | ADIF 解析/生成吞入（本批已实现）|
| W71-10 | OpenRTX | GPL 参考 | GPL-3.0 → **可吞** | DMR 协议栈设计吞入（帧结构）|
| W71-11 | lorawan-server | MIT 待核 | MIT → **可吞** | 会话管理吞入（本批已实现）|

## 吞入原则

1. **AGPL 合并**：GPL-3.0/AGPL-3.0 代码并入后整体 AGPL-3.0，保留原作者版权 + 许可头（NOTICE）。
2. **GPL-2.0-only 红线**：版本不兼容 AGPL-3.0，只重写设计、不复制代码。
3. **待核项**：theseus-cores（NOASSERTION）在许可明确前不吞。
4. **吞 = 重写/移植思路**：多数为「借鉴设计 + 自研实现」（不整段 fork），即「能吞则吞、以自研为主」。

## 本批已吞入的原型（tools/）

- `adif.py`（W71-09 ADIF 格式，开放标准）
- `painlessmesh_router.py`（W71-01 无主 mesh 路由）
- `sat_link_budget.py`（W71-05 多普勒/链路预算）
- `soft_lora_phy.py`（W71-08/02 软 LoRa chirp PHY）
- `workorder_graph.py`（W71-03 工单↔代码图）
- `lorawan_session.py`（W71-11 会话管理）
