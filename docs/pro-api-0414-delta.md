# pro-api-types 版本差异与底层适配面（工单218 任务二）

> 日期：2026-10-08 ｜ 方法：npm registry 拉 0.4.14 tarball 与本地 SDK 的 0.4.14 做**字节级 diff**（类型定义级盘点，零运行时依赖引入）。

---

## 1. ⭐ 首要结论：**不存在 0.3.12 → 0.4.14 版本差**（工单前提更正）

实测证据链：

1. 本地 `github_haul/easyeda/pro-api-sdk/node_modules/@jlceda/pro-api-types/package.json` →
   **version = "0.4.14"**（HW-06B 勘察时装的已是最新）；
2. npm registry 官方 tarball（`@jlceda/pro-api-types-0.4.14.tgz`，238 KB）解包后与本地文件
   **字节级 diff = 完全相同**（130 类 / 43342 行 index.d.ts）；
3. 工单说的"本机索引只到 0.3.12（93 命名空间/742 方法）"——那是 **easyeda-agent CLI 的内置索引**
   （daemon 60832 的 API 目录），不是类型包版本。**真正的差异 = CLI 索引滞后于类型包**，
   影响仅限"agent 工具目录里缺新 API 描述"，不影响类型面本身。

**含义**：没有"藏着的新 API"等着挖——**130 类就是全量**；要做的是让 CLI 索引追上（可从 0.4.14 的
index.d.ts 自动生成，属 easyeda-agent 线的维护项）。

## 2. SYS_MessageBus 盘点（工单点名）—— 结论：**不是编辑器事件总线**

`SYS_MessageBus`（index.d.ts:41113，0.4.14 原文）：

```ts
class SYS_MessageBus {
    createPrivateMessageBus(): void;      // 创建私有消息总线（重复调用无副作用）
    subscribe(topic, callback): ...;      // 订阅主题（扩展间通信）
    publish(topic, message): ...;         // 发布消息，回调立即触发
    // ...
}
```

- **定位：扩展 ↔ 扩展的私有 pub/sub**（按扩展 UUID 隔离）——用于**自家多个扩展互相通信**，
  **不广播编辑器事件**（文档切换/保存/选区变化不在它的主题里）；
- 对"EDA 状态实时镜像"：**用错工具**——它能在"我们的扩展 A ↔ 我们的扩展 B"之间传消息
  （比如 parasite-export ↔ 仿真桥互相同步），但**感知不到编辑器本身的状态变化**。

## 3. ⭐ 真正的事件订阅面：DMT/SCH/PCB_Event（可实时镜像）

类型定义里存在**专门的编辑器事件类**（这才是工单想要的）：

| 类 | 关键监听方法 | 用途 |
|---|---|---|
| `DMT_Event` | `addEditorTabEventListener(id, eventType, callFn, onlyOnce)`（@beta） | **标签页打开/关闭/切换**（EDMT_EditorTabEventType）——文档切换镜像 |
| `SCH_Event` | `addPrimitiveEventListener` / `addMouseEventListener` / `addSimulationEnginePullEventListener` / `removeEventListener` | 原理图元件增删改、鼠标、**仿真引擎拉取事件** |
| `PCB_Event` | `addNetEventListener`（EPCB_NetEventType）/ `addPrimitiveEventListener` / `addRealTimeDrcResultEventListener` / `addCrossProbeSelectEventListener` / 3D 视图相机与材质点击 | **网络变更**、元件变更、**实时 DRC 结果**、选区变化 |
| （配套）`SYS_FileManager` | `getDocumentSource()` | 事件触发后拉最新文档源码 |

**"EDA 状态实时镜像到云服"的可行性：✅ 成立**——
事件监听（如 PCB_Event.addNetEventListener）→ 回调里 `getDocumentSource()` 拿增量源 →
POST `/api/eda/ingest`（工单217 已落地的接收端！）。比手动 ingest 高一层，且**复用现有链路**，
不需要新端点。注意事项：
- `DMT_Event` 标注 **@beta**（接口可能变，桥代码要容错）；
- "仅扩展有效，独立脚本环境调用 throw"（事件监听不能在独立脚本里用）——必须在扩展内；
- 高频事件（鼠标/元件拖动）要做**节流**再推送（否则 ingest 被打爆）。

## 4. 底层改造禁区（哪些不可依赖）

| 面 | 禁区原因 |
|---|---|
| `SYS_MessageBus` 的私有总线**跨扩展侦听** | 按扩展 UUID 隔离的设计意图就是隔离；侦听别人的总线属未定义行为 |
| `@internal` 标注的构造器/方法 | 类型明示内部 API，版本间无兼容承诺 |
| `DMT_Event` 的 @beta 接口 | 可用但要容错（升级可能改名/改签名） |
| 编辑器 DOM/渲染层（canvas 内部结构） | 未在类型定义里暴露 = 私有实现，一升级就碎 |
| `eda.editor.getDocument()` 这类不存在的方法 | HW-06 已证不存在；等价链 = `getCurrentDocumentInfo()` + `getDocumentSource()` |

## 5. M2 桥三选一（工单任务三结论）：✅ **B —— easyeda-agent connector 60832 daemon**

| 维度 | A：扩展内嵌 HTTP server | **B：daemon typed action** | C：POST-push 拉取 |
|---|---|---|---|
| 实时性 | 高 | **高**（WebSocket 长连） | 低（轮询） |
| 配置复杂度 | 每个扩展各自配端口+开关 | **一次装 connector 全体受益** | 低但每插件各自实现 |
| 与现有 skills 兼容 | 新通道 | **直接复用**（autodraw/clearance-fix 已走此路） | 不兼容 |
| 上游更新冲突 | fork 才能加面 → 漂移风险 | **零 fork**（桥在自家 connector，上游插件不动） | 每个上游插件都要 fork 加 POST |
| 事件订阅（§3） | ✅ 可行 | ✅ 可行（扩展侧薄 listener 转发 daemon） | ❌ 无推送能力 |

**统一桥标准（所有 M2 改造共用）**：
1. 上游插件**不 fork**（上游更新冲突 = 0）；触发面走自家 connector daemon 60832 的 typed action；
2. 需要事件/状态镜像时，写**自家薄扩展**（pro-api-sdk 构建）挂 listener → 转发 daemon → 云服；
3. 结果回云服统一 POST `/api/eda/*` 端点族（ingest 模式：token 鉴权 + 落盘 + EventBus 事件）。

（A 的"每插件内嵌 server"模式仅当上游插件自带时利用——如 knowledge-base 的 OpenAI 兼容源。）
