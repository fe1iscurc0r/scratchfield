# 嘉立创EDA 寄生控制链 SPEC · v1

> 用途：翻手册 → 画原理图 → 复刻 → 屏幕控制 → 寄生操作系统 的施工契约
> 读者：Trae / WorkBuddy / 实验田维护者（自包含）
> 日期：2026-08-21

## 〇、一句话定位

**在嘉立创EDA（EasyEDA Pro）上建立「双通道寄生控制」：通道A=屏幕控制（看屏幕+操作屏幕，适用于任何无API的软件），通道B=软件接入（官方 eda.* 扩展API，类型化精确操作）。两条通道共用一个指挥层，先把 EDA 做成第一个宿主，再把同一套架构泛化到任意软件 → 寄生操作系统。**

## 一、背景与边界

### 现状盘点
| 资产 | 状态 |
|------|------|
| datasheets skill | 已有（提取PDF→结构化JSON→查表） |
| kicad skill | 已有（原理图/PCB分析，但只读KiCad格式） |
| lcsc / digikey / mouser / element14 skill | 已有（下载datasheet PDF） |
| easyeda-agent（第三方） | 已发现：Go daemon + 连接器插件 + 官方eda.* API |
| EasyEDA 官方扩展SDK | github.com/easyeda，扩展开发+demo |
| EasyEDA AI助手插件（Sunkai233） | 已发现：画布+对话面板 |
| screen_vision（scratchpad） | 空壳，待填实（屏幕感知） |
| voice / computer_use 工具链 | 部分可用 |

### 做 / 不做
| 做 | 不做 |
|----|------|
| 翻元器件手册（datasheet→结构化提取→校验） | 不从立创商城购料（死贵，走淘宝/闲鱼/渠道商） |
| 用 API 通道画原理图（放件/连线/DRC/BOM） | 手绘高质量原理图（目标=能出板，不是艺术） |
| 复刻拆解项目（AntiHunter节点/PicoRX/ZeroPhone） | 重新发明 EasyEDA API（用现成封装） |
| 屏幕控制通道（浏览器控制 EasyEDA Web 版） | 依赖官方不提供的功能（未公开API） |
| 指挥层抽象（通道A/B统一调度+状态同步） | 一次做完所有软件宿主（先 EDA 打样） |
| 寄生操作系统概念验证（以 EDA 为第一个宿主） | 泛化到任意软件（二期） |

### 核心决策（用户拍板）
1. **购料不走立创商城**：BOM 导出后走淘宝/闲鱼/渠道商比价（用户已有采购经验）
2. **画图不追求完美**：能出板、能打样、能复刻 = 合格
3. **复刻优先**：拆解报告里 13 个项目的硬件部分优先复刻
4. **双通道控制是灵魂**：屏幕控制=通用寄生能力，API=精确控制，两者互补
## 二、架构设计

```
┌─────────────────────────────────────────────────┐
│ 指挥层 Parasite-OS C2（本 Hermes / scratchpad）  │
│  · 任务解析（复刻什么/画什么板）                  │
│  · 双通道调度（A 屏幕 / B API / 混合）           │
│  · 状态同步（屏幕看到的 == API 查到的）          │
│  · 手册知识库（datasheets/extracted/）           │
└───────┬──────────────────────────┬──────────────┘
        │ 通道B（精确）              │ 通道A（通用）
┌───────▼──────────┐      ┌─────────▼─────────────┐
│ API 接入层        │      │ 屏幕控制层             │
│ easyeda-agent    │      │ · playwright/browser  │
│ (Go daemon)      │      │ · screen_vision 填实  │
│  ↔ WebSocket     │      │ · 截图→UI理解→点击    │
│  ↔ 连接器插件     │      │ · OCR/坐标定位         │
│  ↔ eda.* 官方API │      │ · 键盘/鼠标注入        │
└───────┬──────────┘      └─────────┬─────────────┘
        │                          │
┌───────▼──────────────────────────▼─────────────┐
│ 宿主 嘉立创EDA EasyEDA Pro                       │
│  · Web 版 pro.easyeda.com/editor                │
│  · 官方扩展插件运行时（eda 对象根作用域）         │
│  · 原理图/PCB/器件库/DRC/BOM                    │
└────────────────────────────────────────────────┘
```

### 数据流
1. **翻手册**：lcsc/digikey 下载 PDF → datasheets 提取 → `datasheets/extracted/*.json` → 查表校验
2. **画原理图（API）**：指挥层 → easyeda-agent CLI（放件/连线/DRC）→ WebSocket → 连接器插件 → eda.* API → 画布
3. **画原理图（屏幕）**：指挥层 → browser 打开编辑器 → screen_vision 截图 → 坐标定位 → 点击/输入 → 截图校验
4. **状态同步**：屏幕截图 OCR 结果 ↔ API `eda.sys_FileManager.getDocumentSource()` 结果做交叉验证（2026-08-22 Trae 实测勘误：真实 API 入口为 `eda.sys_FileManager.getDocumentSource()`，原稿 `eda.editor.getDocument()` 不存在）
5. **BOM/复刻**：API 导出 BOM → 淘宝/闲鱼比价 → 采购单；原项目原理图 → 复刻到 EasyEDA 工程
## 三、施工步骤（分层）

### Phase 0：地基确认（1-2 天）
- [ ] 0.1 安装 easyeda-agent（Go daemon）到云服，跑通 demo
- [ ] 0.2 EasyEDA Pro 安装「EasyEDA Agent Connector」扩展（ext.lceda.cn 搜索）
- [ ] 0.3 验证 WebSocket 通道：`eda.sys_FileManager.getDocumentSource()` 返回当前工程（API 名已按 Trae 实测勘误）
- [ ] 0.4 验证屏幕通道：playwright 打开 pro.easyeda.com/editor 能登录并截图
- [ ] 0.5 验收：两条通道都能「看到」同一个空工程

### Phase 1：手册管线（1-2 天）
- [ ] 1.1 选 5 个复刻项目核心元件（ESP32-S3/SX1278/NEO6M/舵机/nRF24L01）
- [ ] 1.2 lcsc/digikey 批量下载 PDF → datasheets 提取 → 结构化 JSON
- [ ] 1.3 校验：`lookup("ESP32-S3")` 返回引脚图/电气特性
- [ ] 1.4 元件符号检查：EasyEDA 库是否有对应符号，缺的走 API 建符号

### Phase 2：API 通道画图（2-3 天）
- [ ] 2.1 用 easyeda-agent 放 5 个器件到画布
- [ ] 2.2 连线（电源网络 + 关键信号）
- [ ] 2.3 跑 DRC，读回错误列表
- [ ] 2.4 导出 BOM
- [ ] 2.5 验收：DRC 0 error 或可解释的 error 清单 + BOM 完整

### Phase 3：屏幕通道控制（2-3 天）
- [ ] 3.1 screen_vision 填实：截图 → 视觉模型 → 结构化 UI 描述（按钮/画布/坐标）
- [ ] 3.2 鼠标键盘注入：点击坐标/输入文本/快捷键
- [ ] 3.3 屏幕-API 交叉验证：截图看到的内容 == API 查到的内容
- [ ] 3.4 验收：屏幕通道能独立完成「放一个电阻 + 连线」（不依赖 API）

### Phase 4：复刻打样（3-5 天）
- [ ] 4.1 选第一个复刻目标（建议 AntiHunter DIGI 节点，物料最贴近）
- [ ] 4.2 按拆解报告重建原理图（API 通道主画，屏幕通道校）
- [ ] 4.3 DRC + 导出 Gerber/BOM
- [ ] 4.4 采购：BOM → 淘宝/闲鱼比价 → 下单（不走立创商城）
- [ ] 4.5 打样：嘉立创打样（PCB 只打样，不贴片，自己焊）
- [ ] 4.6 验收：真机点亮（用户测试）

### Phase 5：寄生操作系统抽象（二期，先立概念）
- [ ] 5.1 把「通道A/B + 指挥层」从 EDA 解耦成通用框架
- [ ] 5.2 定义宿主适配器接口：`HostAdapter { sense(), act(), api() }`
- [ ] 5.3 概念验证：用同一框架控制第二个宿主（如 KiCad / 手机模拟器 / 任意 GUI）
- [ ] 5.4 验收：换宿主不改指挥层代码（只换适配器）
## 四、关键假设与 fallback

| # | 假设 | 若不成立 |
|---|------|----------|
| H1 | easyeda-agent 连接器插件可用（WebSocket 通） | 退回：直接用官方扩展 SDK 自写插件（github.com/easyeda） |
| H2 | EasyEDA Web 版可被 playwright 控制（登录无验证码墙） | 退回：本机装 EasyEDA 桌面客户端 + 屏幕控制（pyautogui） |
| H3 | 官方 eda.* API 覆盖放件/连线/DRC/BOM | 部分覆盖：API 画不了的用屏幕通道补（混合模式） |
| H4 | datasheets 提取对国产元件（ESP32-S3等）质量够 | 低质量：人工补录关键字段 + 标注 trust_level: low |
| H5 | 淘宝/闲鱼能找到散件 | 找不到：走 LCSC 单买（贵但兜底），或并单摊运费 |

## 五、已知限制

1. **EasyEDA Pro 是 Web 应用**：屏幕通道依赖浏览器自动化稳定性（登录态/弹窗/版本更新都可能破）
2. **easyeda-agent 是第三方**：非官方，更新频率/稳定性未知，需 pin 版本
3. **画图质量天花板**：AI 画的原理图能出板但不够规范（可读性/复用性差），接受
4. **官方 API 文档量大**（120类/62枚举/70接口/19别名），封装成本在 Phase 0 集中
5. **嘉立创打样政策**：贴片需商城购料（用户不走），所以只打样+自己焊 → 元器件焊接工作量在用户
6. **寄生操作系统是概念验证**：一期只证明 EDA 能寄生，泛化到任意软件是二期，不要一期膨胀

## 六、测试用例（云服可跑，python -c 优先）

1. `curl localhost:<port>/health` → 200（easyeda-agent daemon 活着）
2. `easyeda-agent doc` → 返回当前工程 JSON（API 通道通了）
3. `python3 -c "import datasheet_types; print(lookup('ESP32-S3') is not None)"` → True
4. 屏幕通道：playwright 截图 → screen_vision 输出含「原理图编辑器」字样
5. DRC：跑完返回 findings JSON，error 数 < 5 或全部可解释
6. BOM 导出 CSV 行数 ≥ 元件数
7. 交叉验证：截图元件数 == API 元件数（±10%）

## 七、交付物清单

| 交付物 | 位置 |
|--------|------|
| SPEC v1 | docs/JLC-EDA-寄生控制链-SPEC-v1.md |
| 手册提取 JSON | datasheets/extracted/*.json |
| 复刻工程文件（EasyEDA JSON/源） | 云服 ~/tools/eda/ 或用户端 |
| 采购单（BOM+比价） | 数据目录 |
| 打样 Gerber | ~/tools/eda/<project>/fabrication/ |
| 寄生框架适配器接口（二期） | scratchpad（5.2 后） |

## 八、验收标准（可执行不变量）

```bash
# 1. easyeda-agent daemon 存活
curl -sf localhost:<port>/health | grep -q '"ok"'
# 2. API 通道能读工程
easyeda-agent doc 2>/dev/null | grep -q '"document"'
# 3. 手册管线通（选 5 个核心元件）
python3 - <<'PY'
from datasheet_types import lookup
assert all(lookup(p) is not None for p in ["ESP32-S3","SX1278","NEO6M"])
PY
# 4. 屏幕通道通（截图非空 + 可解析）
test -s /tmp/screen.png && python3 -c "from PIL import Image; Image.open('/tmp/screen.png').verify()"
# 5. 复刻板 DRC 通过
grep -q '"error": 0' ~/tools/eda/<project>/analysis/latest/drc.json 2>/dev/null || echo "DRC有error，需人工确认"
# 6. BOM 完整（CSV 行数=元件数）
[ $(wc -l < bom.csv) -ge $(grep -c '^' schematic_components.json) ]
```

## 九、提交规范

- 每个 Phase 完成 → 单独 commit：`feat(eda-phase0):` / `feat(eda-phase1):`
- 手册提取 JSON 进 `datasheets/extracted/`（项目级，不进主仓 git）
- 复刻工程文件进 `~/tools/eda/`（数据目录，不进 scratchpad 主仓）
- SPEC 修订：小改追加修订记录，大改升 v2

## 修订记录
- v1 (2026-08-21)：初版，双通道寄生控制架构 + 五阶段施工

## 十、Phase 0 精确执行单（天选7 · 2026-08-22 晨）

### 环境决策（用户拍板）
- 宿主运行环境 = 天选7（Windows 笔记本，RTX 5060）
- 云服只做：手册管线（datasheets 提取）+ 拆解/复刻图纸准备 + 采购单
- easyeda-agent 与 EasyEDA Pro 都装天选7

### 已验证事实（2026-08-21 查实）
| 项 | 值 |
|----|-----|
| easyeda-agent 主仓 | github.com/zhoushoujianwork/easyeda-agent ⭐274 MIT |
| 最新版 | v1.1.1（2026-08-20 发布，昨天）|
| Windows 二进制 | easyeda_windows_amd64.exe（15.8MB）|
| 连接器插件 | easyeda-agent-connector.eext（1.68MB，同 release 附送）|
| daemon 端口 | 60832（0xEDA0），自愈重连，冲突自动接管旧 daemon |
| 插件市场 | 立创扩展广场（jlc-ext.com/item/zhoushoujian/easyeda-agent-connector）|
| 官方 API 底座 | 86 个命名空间（eda.* 对象根作用域）|
| 原理图能力 | S0–S6 全流程可交付（方案→分页→分区→摆放→布线→门禁→交付）|
| PCB 能力 | P0–P10 持续演进中 |
| 相关生态 | 官方 AI 助手插件（easyeda/eext-easyeda-api-agent, Apache-2.0）、MCP server（QuincySx）、DSH 插件版 |

### 下载清单（明早顺序执行）
1. **EasyEDA 专业版**：pro.easyeda.com 下载 Windows 桌面版（需注册/登录嘉立创账号）
2. **easyeda-agent v1.1.1**：GitHub release 页面下载两个文件
   - easyeda_windows_amd64.exe
   - easyeda-agent-connector.eext
   - 备选：立创扩展广场直接装连接器（jlc-ext.com 搜 easyeda-agent-connector）
3. **校验**：下载后对照 checksums.txt 核对 SHA-256

### 安装步骤
1. 安装 EasyEDA Pro 桌面版，登录账号
2. 打开 EasyEDA Pro → 扩展管理（或扩展广场）→ 安装 easyeda-agent-connector.eext
3. 把 easyeda_windows_amd64.exe 放到固定目录（如 D:\tools\easyeda-agent\）
4. 双击启动 daemon（或 `easyeda_windows_amd64.exe daemon` 命令行启动）
5. 确认 daemon 监听 60832：`netstat -ano | findstr 60832`

### 双通道验证（明早必跑）
```powershell
# 通道B（API）：daemon 活着
curl http://localhost:60832/health
# 期望返回 ok

# 通道B：EasyEDA 里开个新原理图工程，连接器应显示已连接（绿灯）
# 跑一条 typed action（daemon CLI 或 skill 命令），如列出当前文档
easyeda_windows_amd64.exe doc

# 通道A（屏幕）：天选7 用 playwright/pyautogui 打开 EasyEDA 截图验证
# 或者暂缓：通道B 通了就先跑 B，A 是二期重点
```

### 明早执行结果回报格式
- [ ] EasyEDA Pro 装好+登录
- [ ] 连接器插件装好+绿灯
- [ ] daemon 起在 60832
- [ ] `doc` 动作返回当前工程 JSON
- [ ] 截图验证成功/失败

### 首日 P1 目标（手册管线，云服我这边并行开跑）
- ESP32-S3 / SX1278 / NEO6M / SG90舵机 / nRF24L01 五件套 PDF → datasheets 提取
- 你明早回来时，5 份结构化 JSON 已躺在云服 datasheets/extracted/
