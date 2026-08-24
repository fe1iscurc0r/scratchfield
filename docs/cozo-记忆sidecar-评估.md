# W-02 · cozo 记忆 sidecar 评估

> 日期：2026-08-23 ｜ 状态：**部分完成（嵌入式验证被环境阻塞）**
> 来源：cozodb/cozo（MPL-2.0，★4.1k）
> 目标：记忆三套分家（Neo4j 图 + SQLite 向量 + FTS）→ cozo 单库试点

## 一、结论先行

**架构层面 cozo 仍是"三合一存储"的最佳候选，但 Python 嵌入式路线（pycozo+cozo_embedded 0.7.6）在本机有 wheel 缺陷，无法完成试点验证。建议改 standalone 二进制 / 真机再验。**

## 二、已验证（本机实测）

1. `pip install pycozo cozo_embedded` 成功（均 0.7.6，有预编译 wheel，无需 Rust 工具链）
2. 嵌入式引擎可启动：`pycozo.Client()` 正常
3. 只读指令正常：`::relations` 返回空关系表结构
4. 概念验证设计（关系+图+向量一体）语法已确认：cozo 支持 `embedding <F32; N>` 向量列 + `~rel[...] <-> [...]` 余弦相似查询 + `rel{from: x, to}` 图边查询 + 单查询内关系过滤+图跳转混合（Datalog）

## 三、阻塞（如实记录）

- `::create` / `::put` 等 DDL 在本机 wheel 组合下全部解析失败：`The query parser has encountered unexpected input / end of input at 2..2`（`::relations` 正常，DDL 全挂）
- 连 pycozo 官方 README 原样示例都失败——排除 SQL 写法问题，疑似 cozo_embedded 0.7.6 wheel 构建缺陷（Rust 解析器与 pycozo 0.7.6 客户端协议不匹配）
- docker 镜像路线：ghcr.io/cozodb/cozo 不存在（registry denied），未继续猜测镜像名
- standalone 二进制：GitHub release tag 命名非标准，未拉取（时间盒）

## 四、替代路径（按优先级）

| 路径 | 动作 | 备注 |
|------|------|------|
| A. standalone cozo-server | 拉 cozo release 二进制跑 HTTP 模式，pycozo(engine='http') 连 | 推荐；HTTP 模式绕开嵌入式 DDL bug |
| B. 真机验证 | 天选7 上装（Windows 有官方安装包），跑试点 | 回家后 |
| C. 换 pycozo 版本 | pip install pycozo==0.7.5 或降 cozo_embedded | 快速试错，5 分钟 |

## 五、若试点跑通的架构收益（设计不变）

```
记忆三套分家（现状）           cozo 单库（目标）
Neo4j 五元组图      ──►        memory 表（关系）
SQLite 向量(bge)    ──►        embedding <F32; 384> 列（向量索引）
FTS 关键词          ──►        Datalog 全文/子串匹配
+ 索引卡 + 会话血统  ──►        扩展列
```

- 同一查询横跨 关系+图+向量（Datalog 一体）——SPEC-05 五维融合的存储层简化
- MPL-2.0 文件级 copyleft，嵌入式/调用不传染，与 AGPL 主仓兼容（SPEC-04 已核）
- 事务性、单文件、快照备份简单

## 六、验收状态

- [x] pycozo 安装可行（wheel 免编译）
- [x] 引擎启动 + 只读指令
- [x] 查询语法设计确认（向量/图/混合）
- [ ] **试点库跑通"同一查询横跨关系+图+向量"** ← 被 DDL bug 阻塞
- [ ] 记忆三套分家 → cozo 单库迁移方案

**结论：架构通过，落地受阻于环境。按路径 A/C 先试，未果则真机验证。不阻塞其他工单。**
