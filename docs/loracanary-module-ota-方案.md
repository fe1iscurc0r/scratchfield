# LoRaCanary 固件模块验证 → OTA 自动回滚 · 方案（S13）

> 工单：S13 SkillForge 固件模块验证 → OTA 自动回滚（P0）
> 授粉源：`digest-g2-3-2026-08-30.md` 授粉点 B（SkillForge 技能持续验证生态 → 固件模块版本共存/热插拔，论文 2608.24747v1）
> 现状基线：`firmware/loracanary/`（AB 线 v1.5：GPS + 深度睡眠 + C3 轻量节点，帧协议 `loracanary_frame.*`，RTC 计数 `rtc_state.*`）
> 交付：本方案 + 骨架代码 `firmware/loracanary/module_manager/`（纯逻辑状态机，已对 C3 RISC-V 工具链编译通过）

---

## 1. 目标与非目标

**目标**：把 LoRaCanary C3 固件从「整机重刷式 OTA」升级为「模块级验证 + 失效模块自动回滚」——
固件模块在运行时通过环境交互（硬件状态反馈）验证自身正确性，失效模块回滚到上一版本，而非整体重刷。

**非目标（诚实边界）**：
- 本方案交付的是**验证/回滚的判定与状态机骨架**，不含 ESP-IDF 分区擦写/跳转实现（`esp_ota_set_boot_partition`），该层留到真机 OTA 集成。
- 不改 `loracanary_frame` 帧协议、不改 `node_config.h`，与 AA/AB 线既有固件字节兼容。

## 2. 授粉点 → 固件映射

SkillForge 的「技能银行通过环境交互持续验证 + 证据引导多路径归纳」在固件层的同构迁移：

| SkillForge 概念 | 固件模块概念 | 落地 |
|---|---|---|
| 技能（skill） | 固件模块（rf / gps / bme / 采集 / 上报） | `ModuleDescriptor` |
| 环境交互验证 | 硬件状态反馈自检（SPI/I2C 应答、ADC 电压、RSSI、看门狗） | `SelfCheckFn` + `HardwareFeedback` |
| 技能失效 | 连续自检不合格 | `consecutive_fails >= fail_threshold` |
| 版本共存/热插拔 | A/B 双槽位分区共存 | `ModuleVersion{slot}` |
| 失效回滚 | 切回上一已知良好槽位，不整机重刷 | `ModuleManager::rollback()` |

## 3. 总体设计

三个运行时环节，全部落在既有 C3 采集周期的既有锚点上（不新增常驻任务）：

1. **模块启动自检**：上电/唤醒后、采集前，逐模块跑一次 `self_check(hw_feedback)`，
   得到 0..100 健康分。硬件反馈从既有代码直接取：`s_radio.begin()` 返回值（SPI 应答）、
   `s_radio.getRSSI()`、`s_bme_ok`（I2C 在线）、ADC 读供电轨（预留引脚）。
2. **运行期健康检查**：每周期 `run_health_check()` 推进连续失败计数；
   一次合格即清零（滞回，避免偶发抖动脉冲触发）。
3. **失效回滚**：连续失败达阈值 → 置 FAILED → 切回 `prev` 槽位（A/B 切换），
   不整机重刷；回滚后仍失败 → QUARANTINED 隔离。

## 4. 回滚触发条件表（验收项）

| # | 触发条件 | 判定依据（骨架字段） | 动作 | 备注 |
|---|---|---|---|---|
| T1 | 连续 N 次自检评分 < 50 | `consecutive_fails >= fail_threshold`（默认 3） | 回滚到 `prev` 槽位，状态 `ROLLED_BACK`，`epoch+1` | 核心触发 |
| T2 | 一次自检评分 ≥ 50 | 滞回 | `consecutive_fails` 清零，不动作 | 防误回滚 |
| T3 | 无 `prev` 可回滚（单版本） | `active == prev` | 置 `FAILED`，交上层告警/隔离，不空回滚 | 单分区兜底 |
| T4 | 回滚后仍连续失败 | 再次达阈值且已 `ROLLED_BACK` | 置 `QUARANTINED`，停止体检与再回滚 | 防止回滚抖动 |
| T5 | 未注册自检回调的模块 | `self_check == nullptr` | 置 `INACTIVE`，不参与体检 | 无证据不臆造健康 |

各模块的 `fail_threshold` 可按外设特性单独调（rf 建议 3，gps 建议 5——GPS 冷启动天然降级，见 §7）。

## 5. 骨架结构与集成点

```
firmware/loracanary/module_manager/
├── module_manager.h           描述符 + 状态机接口（纯 C++，无 Arduino 依赖）
├── module_manager.cpp         评分/计数推进/回滚决策
├── module_manager_test.cpp    4 场景自测（失效回滚/健康不回滚/单版本/重复注册）
└── README.md                  编译自测 + 集成点
```

C3 节点（`loracanary_c3_node.ino`）三处接入，均在现有采集周期锚点上：

1. 组装 `HardwareFeedback`（采集前）；
2. `ModuleManager::run_health_check(fb)`（每周期 `loop()` 顶部）；
3. `evaluate_and_rollback()` 返回待回滚 id → ESP-IDF 层执行 `esp_ota_set_boot_partition(prev.slot)`。

**骨架可编译**：`module_manager.cpp` / `module_manager_test.cpp` 已对
`riscv32-esp-elf-g++`（C3 RISC-V 工具链）`-c` 全量编译通过（无链接，无 Arduino 依赖）。

## 6. 双槽位（A/B）与 OTA 关系

- 每个模块持有 `active`（当前）与 `prev`（上一已知良好）两个版本，`slot ∈ {0,1}` 对应双 app 分区。
- 正常 OTA：新版本写入非活动槽位 → 校验 CRC/签名 → 切换 `active`，旧版本下沉为 `prev`。
- 失效回滚：`rollback()` 交换 `active`/`prev`，等价于「切回旧槽位」，**不触发整机重刷**，
  与 SkillForge「模块级版本共存」语义一致。
- 本骨架只输出「回滚哪个模块、切到哪个槽位」的决策；分区擦写/跳转由 ESP-IDF 层完成（见 §1 边界）。

## 7. 诚实降级与未验证项

- GPS 模块冷启动 TTFF ~27s，短周期必然首几轮 `sat=0` 降级——这是**预期语义**而非模块失效。
  因此 gps 模块的自检回调应以「GPS 串口是否有 NMEA 字节」为判据，而非「是否 fix」，
  且 `fail_threshold` 建议 ≥5，避免把冷启动误判为失效回滚。
- 硬件反馈字段（`vcc_mv`、`bus_error_count`、`watchdog_resets`）在 C3 真机上的具体引脚/
  外设映射尚未实测，骨架以默认「健康」语义兜底，接线后由自检回调赋予权重。
- 分区跳转（`esp_ota_set_boot_partition`）未在本骨架实现，真机 OTA 前需补全（§1 已标注）。

## 8. 验收对照

- ✅ 方案含**回滚触发条件表**（§4，T1–T5）。
- ✅ 骨架代码 `firmware/loracanary/module_manager/` 已交付，且对 C3 工具链**可编译**（§5）。
- ✅ 与 AB 线现状结合：不改帧协议/引脚，复用 `s_radio`/`s_bme`/RTC 既有状态（§3、§5）。
