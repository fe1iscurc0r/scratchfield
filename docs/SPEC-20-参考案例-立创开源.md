# SPEC-20 · 参考案例 · 立创开源社区扫描（LoRaCanary 用）

> 2026-08-26 扫描：为 LoRaCanary（LoRa 环境感知节点底板）找相似案例与可抄参考。
> 使用方式：画原理图/布局前先看对应案例；能给嘉立创 AI 链接就让 AI 参考。

---

## 一、直接同赛道（必看）

### 1. 基于LoRa的无线通信装置 — oshwhub @robba
- 链接：https://oshwhub.com/robba/wireless-communication-device-based-on-lora
- 内容：433MHz LoRa 数公里通信装置，手机 APP 人机交互
- 模块清单（可抄）：USB 转串口 / UART 烧录切换 / Type-C / 供电切换 / 升 5V boost / 锂电池保护 / 充电 / 3.3V LDO / LoRa 模块 / ESP32 模块
- **可借鉴**：①供电切换电路（USB/电池双供电怎么切）②模块化布局分区（充电-主控-射频三段）
- 毒点：他用的也是模块+ESP32 核心板组合，与方案①同构，直接抄思路

### 2. 立创ESP32S3功能拓展底板 — oshwhub @小涵电子工作室（立创官方二次收录，CC BY-SA 3.0）
- 链接：https://www.google.com/search?q=oshwhub+%E5%B0%8F%E6%B6%B5+ESP32S3%E5%8A%9F%E8%83%BD%E6%8B%93%E5%B1%95%E5%BA%95%E6%9D%BF （oshwhub 站内搜「小涵电子 ESP32S3 拓展底板」）
- 文档：https://openkits-wiki.easyeda.com/zh-hans/esp32s3r8n8/projects/expansion-board.html
- 内容：像 51 学习板那样学 ESP32 的功能拓展底板——WiFi/蓝牙、CH340 串口、多模块接口，完整原理图开源
- **可借鉴**：①排母/排针互连的标准画法（拓展底板范式）②CH340 串口调试方案（本板可用可不用——SuperMini 自带 USB）③官方认可 = 嘉立创生态惯例
- 毒点：官方文档说"喜欢就通过嘉立创免费打样一起玩"，社区惯例即 5 元/免费打样

### 3. SX1278-STM8S透传模块（PCB+原理图，直焊公版）— WhyCan 论坛
- 链接：https://whycan.com/t_2102.html （帖子附件 SX1278.7z 含完整 PCB+原理图+BOM）
- 内容：433MHz LoRa 透传模块，单片机+ SX1278 芯片直焊，批量过测
- **可借鉴**：①SX1278 芯片直焊的 **RF 匹配网络参考**（方案②必需）②天线布局实例
- 毒点：单片机下底层挖空、地孔处理等细节——直焊版照这套做

## 二、环境感知/显示终端（传感器+屏幕，借鉴 UI 与结构）

### 4. ESP32_32E 桌面天气终端 — oshwhub @trustedzxz
- 链接：https://oshwhub.com/trustedzxz/esp32_32e-zhuo-mian-tian-qi-zhong-duan
- 内容：ESP32-WROOM + SHT30/BMP280 温湿压 + 感光，联网显示本地天气
- **可借鉴**：传感器+小屏的结构布局；光照传感器接入（GY-30 用户有，v2 可加）

### 5. ESP32C3 homekit 温湿度时钟 — oshwhub @jackjones1211
- 链接：https://oshwhub.com/jackjones1211/esp32c3homekit-temperature-and-humidity-clock
- 内容：ESP32C3 + 1.54 寸 TFT + SHT30，HomeKit 温湿度计
- **可借鉴**：ESP32-C3 小节点的电源设计（用户有 4 片 C3，v2 节点群可用）

### 6. 可体感控制的气象站 — oshwhub @xiaohanxdzdy
- 链接：https://oshwhub.com/xiaohanxdzdy/a-kind-of-temperature-and-humidity-based-on-esp32
- 内容：体感控制 + 时间/天气/温湿度/光照/CO2/甲醛综合气象站，手机 APP 查看
- **可借鉴**：多传感器汇聚架构；APP 数据流（v2 网关上行可参考其通信方式）

### 7. 物联网温湿度台灯远传监控控制器 — oshwhub @lennone
- 链接：https://oshwhub.com/lennone/temperature-and-humidity-detecto
- 内容：温湿度云端监控 + 台灯远程控制（智能调节）
- **可借鉴**：数据→云端→远程控制闭环（与本板"节点→网关→主机 rf_brain"同构）

## 三、其他值得顺手的

### 8. esp32-si4732 全波段收音机（GitHub 镜像 oshwhub 项目）
- 链接：https://github.com/esp32-si4732/esp32-si4732-oshwhub
- 内容：ESP32 + SI4732 全波段收音机（ESP32 OLED ALL-IN-ONE 移植）
- 顺手价值：ESP32-S3 + OLED 的成熟工程组织；将来做 SDR/收音机面板可参考

### 9. ESP32 迷你游戏掌机（esplay_micro 精修版）
- 链接：https://oshwhub.com/explore（搜「ESPlay Micro 游戏掌机」）
- 顺手价值：ESP32-S3 模组直焊 + 电池 + 屏的紧凑布局参考（直焊版电源/结构可抄）

---

## 四、落地建议

1. **方案①开工前**：看案例 1（robba）的供电切换 + 案例 2（小涵）的排母范式
2. **方案②开工前**：必看案例 3（whycan SX1278 公版）——先把 SX1278.7z 的原理图 RF 匹配网络抄出来给 AI
3. 本清单已把 URL 都给出，可直接把链接附进嘉立创 AI 的提示词里，AI 联网能读