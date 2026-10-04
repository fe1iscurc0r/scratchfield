# W95-02 · luciobaiocchi/heard 勘察（ESP32 LoRa 组网 + SITL）

**上游**：luciobaiocchi/heard（88★ · Apache-2.0 · 2026-08-08 活跃）
**勘察方式**：GitHub 浅克隆（D:\wo34-recon\heard，depth-1）+ README/目录结构阅读
**工单**：第三十四期扩轮卷95 · W95-02【评估】

---

## 1. 项目定位

HEARD = Hiking Emergency Assistance and Rescue Device：徒步群组在**无蜂窝覆盖**环境下的
离线安全组网设备（学士论文产物，博洛尼亚大学 2024-2025）。每人携带 ESP32 + GPS + LoRa
设备；领队设备（Core）周期轮询群组，离队成员经**多跳中继**回传；全程无手机/无互联网/无 SIM。
硬件对口度极高：ESP32 + u-blox GPS（NEO-6M 同级）+ LoRa + 2.9" e-ink，与本仓
ESP32-S3 SuperMini + SX1278 + NEO6M 储备几乎同构。

## 2. 架构拆解（顶层实测）

```
code/
├── core/        # 领队设备：群组轮询、SOS、e-ink 群组状态、路径记录
├── node/        # 成员设备：GPS 定位、IN_PATH/OUT_PATH 自判、应答/中继
├── path_loader/ # GPX 解析 + 路径偏离分类（置信区间）
└── simulator/   # firmware-in-the-loop：固件逻辑跑主机 + 虚拟射频信道 + 3D replay
PCB V1/          # 硬件设计（KiCad）
images/          # 原型照片/示意图
```

要点：
- **FITL 模拟器**是本项目最大工程亮点：固件业务逻辑与硬件 HAL 解耦，主机侧注入
  虚拟 GPS/射频事件即可跑全链路，配 3D replay 复盘——**无真机也能先验证组网逻辑**。
- **路径守门**：onboard 算法把徒步者分类为 IN_PATH / OUT_PATH（带置信区间），
  只有离队/异常才占用 LoRa 空气时间——空气时间预算意识值得学。
- **轮询+中继**：Core 周期 poll，超距成员由中间节点 relay，协议极简（无 mesh 路由表）。

## 3. 与本仓对照

| 维度 | 本仓 | heard |
|---|---|---|
| 固件形态 | 哨兵（OOK 采集）+ LoRaCanary 帧原型 | 群组安全 mesh（core/node 双角色） |
| 仿真 | firmware/tests 主机 g++ 单测（无信道模型） | FITL 模拟器 + 虚拟信道 + 3D replay |
| 位置 | 无（哨兵固定点） | GPS + GPX 路径偏离分类 |
| 协议 | LoRaCanary 帧（自检/回滚） | 轮询/应答/中继极简协议 |

## 4. 可落地借鉴点（≥3）

1. **FITL 模拟器方法论**（核心借鉴）：给 loracanary/哨兵加 host-sim target——
   把射频收发与 GPS 抽象为事件注入接口，主机跑「多节点虚拟信道」仿真，
   复用现有 firmware/tests g++ 三件套结构扩展即可；先做 2 节点轮询仿真。
2. **空气时间预算**：借鉴「只报异常/离队」的上报策略——哨兵 OOK 解码结果当前全量
   NDJSON 上报，可加「变化触发 + 周期心跳」双模，LoRa 回传侧同理。
3. **GPX 路径偏离分类**：天线云台/无人机场景的位置守门参照（IN_PATH/OUT_PATH
   置信区间 → 云台越界告警），path_loader 的 GPX 解析可直接参考实现思路。
4. **core/node 双角色单固件**：编译期角色切换（同一代码树两入口），比本仓
   node/gateway 两工程更省维护——可评估 loracanary 合并为单工程双 target。

## 5. 许可裁定

- **Apache-2.0**：可融合代码（保留版权声明 + NOTICE 登记）。
- 建议路径：先借方法论（借鉴点 1/2 自研实现），sim 模块试点代码级融合
  （path_loader 的 GPX 解析若直接采用需保留 Apache 头）。

## 6. 执行清单

- [x] 克隆 + 结构/许可核验
- [x] 借鉴点 4 条（含模拟器方法论抽取）+ Apache 融合判定
- [ ] （后续工单）loracanary host-sim 2 节点原型
