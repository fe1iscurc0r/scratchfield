# WO-04 调研报告：yjs CRDT 知识库同步（预研阶段）

日期：2026-08-22 ｜ 状态：WO-03（数据结构定义）未完成，按工单只做环境勘察与能力调研，未写原型代码。

## 1. yjs 能力画像（clone 已落 github_haul/yjs，MIT）

- **算法**：YATA CRDT。共享类型 Y.Map / Y.Array / Y.Text / Y.XmlFragment，任意副本离线编辑后合并保证收敛、无中心、无冲突丢失。
- **离线双端场景匹配度**：高。官方支持 offline editing + version snapshots（`Y.encodeStateAsUpdate` 增量、`Y.mergeUpdates` 合并），双端离线编辑后交换 update 即可合并，不需要中心服务器在线。
- **冲突策略**：
  - Y.Map 同 key 并发写 = 天然 LWW（最后写入胜出，按逻辑时钟，非墙钟）；
  - Y.Text/Y.Array 并发插入 = 两者都保留（交错但不丢字）；
  - 需要显式策略时可用 `Y.Map` 包一层 `{value, ts}` 自定义墙钟 LWW，或用 origin 元数据做"文档级合并"回调。
- **配套 provider**：y-websocket（在线中继）、y-indexeddb（浏览器离线持久化）、y-protocols（sync/awareness）。
- **成熟度**：★22.7k，最近推送 2026-08-06，有商业支持合同，被 Notion/Figma 类产品与 ProseMirror/TipTap/CodeMirror 生态广泛采用。

## 2. 关键发现：scratchpad 侧不必绑死 Node

yjs 本体是 JS 库，但知识库同步的后端（云服/本地 agent）是 Python。两条路线：

| 路线 | 说明 | 建议 |
|---|---|---|
| Node + yjs + y-websocket | 生态最全，编辑器绑定现成 | 若同步端主要是浏览器/编辑器 UI，走这条 |
| **pycrdt**（Python 绑定，Rust 内核） | API 镜像 yjs（Y.Doc/Y.Map/Y.Text），与 y-websocket 通过 update 字节格式互通；Jupyter 协作就用的它 | **推荐**：云服 agent 侧零 Node 依赖，浏览器端仍可用 yjs 原生 |

update 字节格式跨实现兼容（pycrdt ↔ yjs 可互相同步），这是选型时最重要的保证。

## 3. 环境准备状态（天选7 本机实测）

- Node.js：**未安装**（`where node` 无结果，无 nvm 目录）。若走 Node 路线需先装 LTS；走 pycrdt 路线只需 `pip install pycrdt`。
- github_haul/yjs 参考副本就位（1.3MB，去 .git）。
- Python venv 可用（scratchpad/.venv），pycrdt 未装（等 WO-03 定案再装，避免提前锁版本）。

## 4. WO-04 启动前置清单（给后续工单）

1. WO-03 产出知识库条目 schema（决定映射到 Y.Map 还是 Y.Text+外部结构）
2. 定 provider 拓扑：云服 y-websocket 中继 vs 纯离线 update 文件交换（git/网盘携带）
3. 按路线装环境：Node LTS（`winget install OpenJS.NodeJS.LTS`）或 `pip install pycrdt`
4. 验收用例可先写死：双端各离线编辑同一文档（一段改标题、一段改正文、同字段并发改），合并后三处变更齐全、同字段按 LWW 收敛
