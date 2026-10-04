# zhuomianling（桌面灵）授粉报告 · Live2D 桌宠框架 → NEKO 身体层

> 来源：qiyueblues-design/zhuomianling（17★，MIT，TypeScript/Electron）
> 审查：实验田维护者（Hermes）｜日期：2026-08-16
> 定位：融合参考层——开源可自定义 Live2D 桌宠框架，授粉到 NEKO 桌宠身体层。

---

## 一、这是什么

「桌面灵」是一款**本地优先、可自定义的 Live2D 桌宠软件框架**（Windows，Electron + React + TypeScript）。核心路径：创建桌宠 → 导入 Live2D 模型 → 配置人设/事件/语音 → 启用。**框架本身不内置任何模型/角色/密钥**，全由用户导入。

跟我们 NEKO 的关系：它是「桌宠框架」，我们是「NEKO 桌宠身体」。它不是成品，是**框架可扩展性的参考样本**。

---

## 二、源领域 → 目标域 映射

| 源（桌面灵） | 目标（scratchpad/NEKO） | 授粉方式 | 收益 |
|---|---|---|---|
| 桌宠数据按 `pets/<pet-id>/` 隔离 | NEKO 多桌宠数据隔离 | 抄目录结构 | 中 |
| Electron `safeStorage` 加密 API Key | NEKO 桌宠的凭证落盘 | 抄加密策略 | 高 |
| 本地 BGE INT8 记忆检索（按桌宠隔离） | 陆墨本地记忆（memory 已有） | 参考架构 | 中 |
| 构建时资源边界审计（Live2D 不打包） | NEKO 发布包资源治理 | 抄审计思路 | 中 |
| 「开源版不包含」清单（模型/密钥/参考音频） | NEKO 开源的版权边界 | 抄边界声明 | 中 |
| 事件配置（加载/点击/拖拽 → 动作/表情/台词） | NEKO 交互事件映射 | 参考映射结构 | 中 |

---

## 三、核心共鸣（两处最值钱）

### 3.1 凭证加密：`safeStorage` 而非明文

```
API Key 和腾讯云凭据由 Electron safeStorage 加密保存，
普通配置只保留必要的状态或非敏感元数据。
```

**共鸣点**：NEKO 桌宠（Electron 壳）如果要存 LLM/TTS 凭证，必须走 `safeStorage`（OS 级加密，DPAPI/Keychain），不能明文写 config。这是 Electron 桌宠的**安全基线**。我们当前 NEKO 壳的凭证管理应参照此——零成本授粉。

### 3.2 「开源版不包含」的版权边界

README 显式列出开源版**不包含**：受版权 Live2D 模型、商业角色配置、API Key、GPT-SoVITS 声音模型、参考音频、`.pth/.ckpt`。构建时用审计脚本强制（`verify-packed-assets.mjs`），**Live2D 模型混进 release 直接构建失败**。

**共鸣点**：NEKO 开源时同样面临「角色模型版权 + 声音模型 + 密钥」三重边界。桌面灵给了两个可抄的东西：① 显式清单（README 声明不包含什么）；② 构建期审计（脚本挡资源泄漏）。这比「写个免责声明」硬核得多。

---

## 四、难度 × 收益

| 授粉项 | 难度 | 收益 | 建议 |
|---|---|---|---|
| `safeStorage` 凭证加密 | **低**（Electron 原生 API） | **高**（NEKO 安全基线） | **立即授粉** |
| 「开源版不包含」清单 + 构建审计 | **低**（声明 + 脚本） | 中（版权合规） | 授粉到 NEKO 发布流程 |
| 桌宠数据 `pet-id` 隔离 | **低**（目录约定） | 中 | 参考 |
| 事件映射（动作/表情/台词） | 中（需对接 Live2D SDK） | 中 | 参考 |

**总评**：桌面灵不是拿来「融合」的（它是独立 Electron 应用，跟 NEKO 身体重叠），而是**框架设计的参照物**——看一个「开源、可自定义、本地优先」的桌宠框架怎么处理模型导入、凭证加密、版权边界。这三样我们 NEKO 都要面对。

---

## 五、可执行验收

```bash
grep -c "safeStorage" docs/zhuomianling-授粉报告.md   # ≥2
grep -c "开源版不包含" docs/zhuomianling-授粉报告.md   # ≥2
grep -c "MIT" docs/zhuomianling-授粉报告.md            # ≥1
grep -c "难度 × 收益" docs/zhuomianling-授粉报告.md     # ≥1
git diff --stat -- NEKO apiserver | wc -l              # 0
```

*授权：MIT → 主仓 AGPL v3 允许直接吞。注意：其 Live2D Cubism SDK 文件遵循 Live2D 官方许可，授粉时只抄「框架设计思想」，不抄 SDK 文件。源码归档在 github_haul/fusion/zhuomianling/。*
