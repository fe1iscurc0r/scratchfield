# 授粉报告 Batch-3：LoRa mesh / 无线电（4 项）

> 日期：2026-08-22 晚 | 模式：API 直读 | 许可：见各项

## 一、zjs81/meshcore-open（592★, MIT）— MeshCore 客户端

- **定位**：MeshCore LoRa mesh 设备的跨平台 Flutter 客户端（BLE 通信）
- **架构**：Flutter app ↔ BLE ↔ MeshCore 设备（点对点/公共频道/mesh 组网）
- **价值**：补 HW-01 MeshRadio 的**手机端**——Trae 的 mesh_layer.py 是固件/后端，meshcore-open 提供 BLE 手机交互层参考
- **授粉建议**：若未来做"手机→LoRa mesh 网关"，抄它的 BLE 客户端结构（不引入 Flutter，思路参考）
- **落点**：HW-01 参考材料

## 二、ClusterDuck-Protocol/ClusterDuck-Protocol（447★, Apache-2.0）— LoRa mesh 固件

- **定位**：物联网 ad-hoc LoRa mesh（Call for Code 项目，IoT 设备组网）
- **架构**：Cluck（设备节点）固件 + Ducklink（路由器）+ 管理后台
- **价值**：与 HW-01 MeshRadio 同赛道，但 CDP 更偏 **IoT 传感器网络**（非对等 mesh）
- **对比**：MeshRadio 对等 mesh + AES；CDP 星型/树型 + 管理端
- **授粉建议**：补 HW-01 的"管理端"设计（CDP 有完整 web 后台参考）
- **落点**：HW-01 参考材料（Apache 可直接抄管理端）

## 三、markrogoyski/math-php（2410★, MIT）— 纯 PHP 数学库

- **定位**：自包含纯 PHP 数学库（无依赖）
- **价值**：低（PHP 不是我们的栈）
- **授粉建议**：**跳过**——纯 PHP 与我们 Python/JS 栈无关
- **状态**：排除（理由：语言栈不匹配）

## 四、camellia2077/FlipBits（45★, Apache-2.0）— 文本→无线电声音

- **定位**：把文本编码变成声音 + 音频/编码可视化（Morse / BFSK / FSK / 双音映射）
- **价值**：⭐ 与 rf_brain 的调制教学/频谱可视化相关——把文本"说"成 FSK 声波，可做无线电教学演示
- **授粉建议**：FSK 调制可视化模块可抄（Python 栈若兼容）；flash 模式（bit 时长/停顿/Hz 模拟语气）有创意，适合演示
- **落点**：rf_brain 可视化增强参考（低优先级）

## 五、Batch-3 行动项

1. **HW-01 参考增强**：meshcore-open（手机 BLE 端）+ ClusterDuck（管理端）→ 并入 HW-01 工单参考
2. **FlipBits** → rf_brain 教学演示可选（低优先级）
3. math-php → 排除（语言栈不匹配）

---
*注：Batch-3 价值中等——主要补 HW-01 的周边参考，无线电线方向核心（MeshRadio/pagermon/MUSIC）已交工单或已授粉*
