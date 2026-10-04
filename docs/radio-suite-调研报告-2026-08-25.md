# radio_suite 软件调研报告 · 优缺点与社区反馈 · 2026-08-25

> 调研人：沈遥（Hermes）· 依据：Reddit / eHam / RadioReference / 哈罗CQ / HamCQ / SourceForge 评论 / rtl-sdr.com
> 用途：SPEC-17 radio_suite 选型与避坑依据。不只看优点，重点挖社区吐槽。

---

## 一、数字模式（FT8/弱信号）

### WSJT-X（国际主流，GPL-3.0）
- **优点**：模式全家桶（FT8/FT4/JT65/JT9/Q65/MSK144/WSPR）；弱信号解码标杆；跨平台（Win/Linux/RPi）
- **缺点/吐槽**：
  - **串口/CAT 是最大痛点**——"FT8 Rant"：Xiegu G90 + CE-19 卡 COM bus error，可用率只有 40%；发射无响应、答 CQ 无人回是常见求助帖
  - **时间同步依赖外部工具**（D4.EXE/Dimension 4），时钟不准解码全废
  - FT8 本身有"无脑通联、机器化、没技术含量"争议（Reddit 有专门骂帖："Hate all you want on FT8..."）
  - 解码对弱信号好但**解调参数固定**（2500Hz 带宽常数），自定义空间小

### JTDX（WSJT-X 二次开发，GPL，中文社区主力）
- **优点**：**解码/操控比 WSJT-X 更强**（社区公认）；简体中文版；支持 FT4/FT8/T10/JT65/JT9；哈罗CQ/HamCQ 大量教程
- **缺点**：更新节奏与 WSJT-X 不同步；部分模式缺失；中文用户多但英文文档少
- **启示**：中文社区实际主力是 JTDX 不是 WSJT-X——我们 FT8 解码器 UI 要中文友好，解码策略可参考 JTDX 的增强思路

### FT8CN（安卓 APP，中文 DIY）
- 哈罗CQ 有"FT8CN + 自制 CIV 线"玩 FT8 教程——手机侧弱信号玩法，移动场景参考

## 二、SSTV

### MMSSTV（Windows，freeware 停更）
- **优点**：引擎强大（JE3HHT）、robust（"always worked"）、模式全
- **缺点/吐槽**：停更多年；**解码失败 90% 是音频链问题**（virtual audio cable / stereo mix 引入噪声），不是软件问题；高频噪声投诉多
- **启示**：SSTV 最大坑是音频路由——**radio_suite 直接用文件输入（.wav 解码）绕开音频链**，这是差异化点

### QSSTV（Linux，GPL）
- **优点**：Linux 原生、兼容 MMSSTV/EasyPal
- **缺点**：**配置难**（"Am losing my mind trying to get QSSTV..."——RPi5+RTL-SDR+GQRX+QSSTV 自动收图折腾案例）；Qt 依赖重；音频配置坑多

### Black Cat SSTV（Windows，免费）
- 社区反馈：**弱信号解码比 MMSSTV 好**——值得参考其 DSP 思路

### RX-SSTV
- MMSSTV Engine 后端 + 维护活跃 + 自动模式检测；SWL 无需 TX

## 三、SDR 软件

### SDR#（Windows）
- **优点**：插件生态最丰富（卫星/AIS/ADS-B）
- **缺点/吐槽**：Windows only；含闭源组件；**噪声底表现一般**（同天线同频 SDRConsole -135dBm vs SDR++ -130 vs SDR# -115，SDR# 底噪偏高被实测吐槽）

### SDR++（跨平台，GPL-3.0）
- **优点**：开源跨平台、轻量、界面现代、低配机性能好；模块内置核心
- **缺点**：**插件生态弱**（早期无插件系统）；有 quirks（用户反馈）

### SDR Console（Windows）
- **优点**：**噪声底表现最好**（-135dBm 实测）；功能全
- **缺点**：Windows only；界面复杂对新手不友好

### 结论
- 频谱面板 UI 参考 SDR++（跨平台轻量）；噪声底/AGC 处理参考 SDRConsole

## 四、日志软件

### Log4OM
- **优点**：DXCC 追踪、集群、**FTX Monitor（FT8 直接日志管理，替代 JTAlert）**——亮点
- **争议**：eHam 有"Log4OM is rubbish"帖（社区两极：功能强 vs 复杂/有 bug）；支持者回怼"great piece of software"
- **启示**：**FTX Monitor 思路正是我们 Y-01 想要的**——FT8 通联自动入日志，不做独立 JTAlert

### Cloudlog / hamlog.online
- Cloudlog：自托管 Web 日志（GPL-2.0），展示层思路参考
- **注意**：hamlog.online 是云端日志平台，与我们已授粉的桌面 HamLog（Log.db SQLite）**是两码事**，别混

### N1MM+
- 比赛向，日常重——打比赛再上

## 五、卫星解码

### SatDump（GPL-3.0）
- **优点**：几乎全好评——"all this pain and suffering can be put to an end"（对比 WXtoIMG 时代是革命）；多卫星并行捕获、自动停 SDR 省电、离线解码、Win/Linux/安卓
- **缺点**：吐槽少；主要门槛是**天线/硬件**（GOES 要碟形天线）；配置有学习曲线
- **启示**：APT 解码模块直接参考其解码链架构（GPL 可吞）

## 六、APRS

### Direwolf（GPL-2.0）
- **优点**：软件 TNC 成熟，igate/digipeater 全功能
- **缺点/吐槽**：**配置复杂**（新手"发了但 digipeater 没收到的"求助常见）；音频/声卡配置坑；中文教程少
- **启示**：igate 逻辑参考，但**配置要我们自己做简单化**（radio_suite 的配置文件模板化）

## 七、FT8 辅助

### GridTracker（GPL）
- 几乎**零吐槽**："Making FT8 Fun Again"；实时地图/网格追踪/统计；WSJT-X 伴侣
- 启示：地图可视化思路可进 radio_suite UI（通联地图面板）

---

## 关键洞察（对 radio_suite 的避坑清单）

1. **时间同步是 FT8 第一痛点**——radio_suite 内置 NTP 对时（不依赖外部 D4.EXE）
2. **串口/CAT 是第二痛点**——我们已有 rsba1_adapter（RS-BA1 逆向），天然规避 COM 口地狱；配置要模板化
3. **SSTV 最大坑是音频链**——radio_suite 走文件输入（.wav）绕开；弱信号解码参考 Black Cat DSP
4. **中文社区主力是 JTDX**——我们 UI 中文友好，解码增强参考 JTDX 思路（不 copy）
5. **日志 FTX Monitor 思路**——FT8 通联自动入日志是刚需，不做独立 JTAlert
6. **频谱面板 UI 学 SDR++，底噪处理学 SDRConsole**
7. **FT8"无脑通联"争议**——radio_suite 定位不是替代 FT8 社交，是仪器层；通联质量统计（信噪比/距离）可以做成卖点
8. **Direwolf 配置复杂**——igate 功能进 radio_suite 时配置模板化

---

## 八、数字语音（FreeDV / M17）

| 软件 | 许可 | 说明 | 评价 |
|---|---|---|---|
| FreeDV | GPL | 开源 HF 数字语音（Codec2 编码），弱信号下比 SSB 清晰 | 前沿，新人后置 |
| M17 | MIT | 新一代开放数字语音协议，DMR 的开源替代，无需商业热点 | 前瞻参考 |
| **RadioTransciptor** | 开源 | **Whisper 实时转写无线电语音**（VAD 触发，只转写说话时） | ⚠️ 与 X-02 语音记录撞车——其 VAD+转写管线思路直接参考 |

## 九、卫星轨道（GPredict / Orbitron）

| 软件 | 许可 | 说明 | 评价 |
|---|---|---|---|
| GPredict | GPL | 跨平台实时轨道预测，SDR# 插件自动调频+多普勒补偿 | 卫星玩法标配 |
| Orbitron | 免费 | Windows 老牌，DDE 追踪 | 参考 |
- **启示**：radio_suite 卫星模块内置 TLE 轨道计算（SGP4，Python 有 pyorbital/skyfield，MIT 可拿）

## 十、电台控制库（Hamlib / Flrig / Omnirig）

| 软件 | 许可 | 说明 | 评价 |
|---|---|---|---|
| Hamlib | GPL | 库 + rigctld（**网络控制服务**），支持 300+ 电台 | 标准方案，复杂电台协议兜底 |
| Flrig | GPL | GUI + **net mode**（可被 Hamlib 当 rig，反之亦然） | net 思路参考 |
| Omnirig | 免费 | Windows | 参考 |
- **启示**：rsba1_adapter（RS-BA1 逆向）是我们的路径，Hamlib 通用对照；**"rig 作为网络服务"的思路跟 radio_suite 总线设计一致**（705 控制天然可网络化）

## 十一、通联确认服务（LoTW / eQSL / QRZ）

- **LoTW**：ARRL 官方确认——**Y-01 日志升级必接**（DXCC 奖状刚需）
- eQSL：电子 QSL 卡；QRZ：在线日志+确认
- **启示**：日志模块留 LoTW 上传接口（ADIF 导出是基础）

## 十二、天线仿真（MMANA-GAL / 4nec2）

| 软件 | 许可 | 说明 |
|---|---|---|
| MMANA-GAL | 免费 | 经典 MININEC 仿真，新手友好 |
| 4nec2 | 免费 | NEC2 引擎，专业 |
- **启示**：用户要玩天线（NanoVNA 已买）——闭环：仿真 → 手搓 → NanoVNA 实测 → 705 验证。radio_suite 可加天线计算小工具（偶极子长度/馈线损耗）

## 十三、其他值得知道

- **PSK Reporter**：反向信标网络——全球谁听到了你的 FT8 信号，通联可视化（免费网页）
- **SDRangel**：全能 SDR 分析仪（频谱/解调/瀑布/协议解码），比 SDR# 专业
- **URH（Universal Radio Hacker）**：已授粉进 rf_brain（G-01 工单）——自家资产，不提软件清单
- **HamClock**：卫星/传播/时钟信息屏（树莓派挂墙用）

---

## 十四、使用心得汇总（hands-on 反馈）

### PSK Reporter
- **核心心得**："我经常用 PSK Reporter 知道谁真的听到我了，免得浪费时间呼叫没人听的地区"（FT8 群）；"可测量收发机和天线性能"（KA5WSS）
- eHam 教程定位：监测你的 FT8/JT65/PSK 信号全球传播
- **启示**：Y-02 FT8 解码器可加 spotting 上报（PSK Reporter 思路）——通联数据既是传播观测也是天线测量

### SDRangel
- **心得**：全能但**复杂**——论坛有 RTL-SDR V4 识别问题帖；独特价值在 TX 能力（HackRF/Pluto 发射）+ 海量内置解码器（ADS-B/AIS/APT/Digital Voice/POCSAG/APRS/RS41 探空仪）；Android 可用
- **定位**：发烧友全能台，不适合新手当主力

### HamClock
- **心得**：**安装不简单**（"not the simplest install, had a few hiccups"）；官方 7 寸触屏太小分辨率低，22 寸旧显示器才好用；免费对比商业替代"no brainer"
- 功能：时钟/灰线地图/空间天气/实时 VOACAP/POTA/SOTA/卫星跟踪

### JTAlert（FT8 辅助）
- **心得**："WSJT-X + JT-Alert work together great! Automatically logs my QSO's"（K0PIR）——FT8 自动日志标配；需 .NET；三件套（主程序/呼号库/语音包）
- **对比**：Log4OM FTX Monitor = 内置版替代（一个软件搞定，不用独立 JTAlert）——Y-01 已采纳 FTX 思路

### KiwiSDR（远程 HF 接收机）
- **心得**："absolute joy"——整个 0-30MHz HF 频谱一次看到，缩放随意；自己接收不够时去 sdr.hu 听全球别人的接收机（远程 DXpedition 玩法）
- **吐槽**：**Web UI 资源占用高，手机/低配平板打开卡**（SWLing Post 实测）
- **启示**：⚠️ radio_suite 若做 Web UI，频谱渲染必须轻量化（canvas 节流/降采样）——KiwiSDR 的 UI 卡是现成反面教材

### 中文社区
- 哈罗CQ 有专门「电台日志软件」版块（fid=52）——中文日志软件讨论主阵地，后续调研/反馈收集源
- 中文主力数字模式软件 = JTDX（前文）

---

## 对 SPEC-17 的增量启示（使用心得版）

9. **PSK Reporter 思路进 Y-02**：FT8 解码器加 spotting 上报，通联数据变传播观测
10. **Web UI 轻量化**：频谱渲染 canvas 节流/降采样（KiwiSDR 的 UI 卡是反面教材）
11. **FT8 自动日志双方案确认**：JTAlert 模式（独立）vs FTX Monitor 模式（内置）——Y-01 走内置（不做独立 JTAlert）

---

## 十五、写频与测试工具（硬件配套）

### CHIRP（写频软件）
- **开源跨平台**（Win/Mac/Linux），支持 UV-K6（K5(8) 同族）；B 站中文教程多
- **UV-K6 写频刚需**——200 信道手动填不现实，必须电脑写频
- **发现：UV-K5/K6 第三方固件生态**——Egzumer（GitHub 活跃更新）、IJV 固件 3.0（**中文短信功能**，知乎有操作说明）——用户的 UV-K6 可刷增强固件
- 心得：CCR 编程偶尔有异常（RadioReference 帖）；先读一次当模板再改

### NanoVNA-Saver
- **NanoVNA 必配软件**（Rune B. Broberg，跨平台）；分段扫描 >101 点、Touchstone 保存、标记分析（电感/电容自动算）
- 心得：**校准是关键**（有用户"calibrated both and still couldn't get it right"——校准不到位测不准）；固件可更新到 1.5GHz
- 启示：用户 NanoVNA 已计划买——到手直接配 NanoVNA-Saver

## 十六、应急 / 进阶 / 学习

### fldigi + flmsg + flamp（NBEMS 应急通信套件）
- 心得：**12 年好评"just works"**（N5RYH）；ARES 应急训练标准（VHF 数字 L2 / HF 数字 L3）；与 Winlink 配套
- **吐槽："The most outdated application ever"（Reddit——UI 过时）**
- 启示：功能设计参考，**UI 我们做现代**——radio_suite 差异化点

### JS8Call
- 弱信号自由文本消息（**-24dB SNR 解码**）、实时聊天、定向/中继消息（store-and-forward）、心跳/网格监测——应急/离网通信场景
- JS8Call-Improved 现代分支（js8call.com）
- 启示：比 FT8 自由的弱信号消息——应急通信后置选项

### SDRTrunk / DSD+（数字集群监听）
- SDRTrunk：Java 跨平台 trunking 扫描（P25/DMR/NXDN），双 RTL-SDR 并行，免费 winner
- DSD+：数字语音解码（P25 Phase I/II、DMR、NXDN）
- ⚠️ **中国法律边界**：监听公共安全/政府频率违法——只可用于业余 DMR 中继等合法场景（我们的底线：不碰违法监听）

### CW 方向
- **CW Skimmer**：多通道贝叶斯解码（最多 700 信号同时），比赛利器——**吐槽 $100 太贵**（"best decoders but way too expensive"）
- **学习软件**：G4FON Koch / Just Learn Morse Code（方法式）、LCWO / Morse Code Ninja（灵活免费在线）——B/C 类若需 CW 再上

### RepeaterBook
- 全球中继数据库（免费 APP，70+ 国家）——手机查中继标配；社区维护数据（中国中继信息也有收录）

---

*调研：沈遥（Hermes）· 2026-08-25 · 供 SPEC-17 选型与工单避坑*
