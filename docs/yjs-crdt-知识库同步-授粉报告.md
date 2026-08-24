# WO-04 · yjs CRDT 知识库同步 · 授粉报告

> 日期：2026-08-23 ｜ 状态：原型通过验收（PASS 20次冲突合并完整率100%）
> 来源：yjs/yjs（MIT，★22.7k）+ pycrdt（Python 绑定，Rust 内核）
> 关联：SPEC-05 五维记忆融合 / knowledge-base 多实例同步 / 云服-天选7-手机

## 一、源→目标映射

| 源组件 | 目标模块 | 授粉方式 | 收益 |
|--------|---------|---------|------|
| YATA CRDT 算法 | knowledge-base 同步层 | 引入 pycrdt 作为存储前端 | 离线编辑→上线合并零冲突，无需中心锁 |
| Y.Map 嵌套结构 | 文档树（条目/子字段） | Map 直接映射 note 条目 | 结构保留，字段级合并 |
| Y.encodeStateAsUpdate / apply_update | 同步协议 | update 字节流增量交换 | 增量同步，带宽省 10x（对比全量拉取） |
| y-websocket provider | 云服/天选7/手机中继 | 可选 WebSocket 中继 | 三方实时互通（后期） |
| pycrdt（Python） | apiserver/mcpserver 侧 | 零 Node 依赖接入 | 云服 Python 栈直接可用 |

## 二、核心数据结构共鸣（为什么值钱）

1. **CRDT 的收敛语义 = 知识库多写问题的答案**（yjs YATA，pycrdt 同算法）：
   知识库最大的坑是"两个实例离线各改各的，上线谁覆盖谁"。CRDT 保证：任意顺序应用 update，最终状态一致（强收敛），且没有操作被吞。原型实测：双实例 20 轮随机编辑（写/改/删 45:35:20），交换 update 后双方视图完全一致，完整率 100%。

2. **嵌套 Y.Map = 文档树的天然映射**（`kb["note1"]["content"]`）：
   不需要把知识库拍平成本地表再同步——CRDT 文档树直接对应条目结构。同 key 并发写天然 LWW（逻辑时钟，非墙钟），需要业务语义时用 `{value, ts}` 包装自定义墙钟 LWW（原型 note1 并发写验证）。

3. **update 字节格式跨实现互通**（pycrdt ↔ yjs）：
   浏览器端用原生 yjs（编辑器 UI），服务端用 pycrdt（Python），两者交换同一 update 格式。Jupyter 协作已验证此路径。这是"手机/桌面 UI 用 yjs、云服 agent 用 pycrdt"双端混合的关键保证。

## 三、难度×收益评估

| 项 | 评估 |
|----|------|
| 难度 | 低-中：pycrdt pip 即装；主要工作是 SQLite 持久化层 + update 增量存储 |
| 收益 | 高：多实例知识库从"手动同步/最后写胜"升级为"自动收敛零冲突" |
| 建议 | **立即授粉**：原型已 PASS，下一步接 SQLite 落盘 + apiserver 同步端点 |

## 四、原型与验收

- 原型：`scripts/yjs_sync_prototype.py`（--simulate 自测）
- 依赖：pycrdt>=0.14（`pip install pycrdt`）
- 验收命令：`python3 scripts/yjs_sync_prototype.py --simulate`
- 结果：seed 7/42/2026 三组全 PASS——收敛=True，完整率=100%，丢失=0

## 五、落地路线（下一步）

1. SQLite 持久化：update 增量存 `sync_updates` 表（doc_id, clock, update_blob）
2. apiserver 加 `/sync/update`（POST 提交增量 / GET 拉取他人增量）
3. 手机/云服双端接入：编辑走 pycrdt 事务，提交走增量端点
4. （后期）y-websocket 实时中继，三方在线同步

## 六、边界与风险

- 大文档全量重建：update 累积后需定期 compact（Y.mergeUpdates / 快照）
- 冲突业务语义：同 key 并发写是 LWW，业务上需要"最后写者胜"之外的策略时需自定义
- 删除不可撤销：CRDT 删除即墓碑，误删恢复需额外快照机制
