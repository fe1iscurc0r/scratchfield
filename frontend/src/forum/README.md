# frontend/src/forum/ —— 已下线冻结（A 端）

> **状态：冻结 · 不删 · 不加新功能**
> 最后核实：2026-10-29（main `bdba43be75`）
> 这里 32 个文件目前**没有任何一条路由可达**，是"保留待复活"的代码，不是死代码清理对象。

## 为什么在这个目录放 README

一个 32 文件的目录如果只靠 `main.ts` 里两行 `redirect` 和 `App.vue` 的一句注释交代状态，
下一个人打开时只会看到一堆没人 import 的 `.vue`，两种误判都会发生：

- 当成死代码删掉 → 后端恢复时要重写一遍；
- 当成活代码继续加需求 → 加了也没人能看到（路由是 redirect）。

## 下线的实证（三层，都可自查）

| 层 | 证据 |
|---|---|
| 路由 | `frontend/src/main.ts` L23-25：`/forum` 与 `/forum/:pathMatch(.*)*` 都是 `redirect: '/'`，注释原文「论坛功能已下线（后端 /forum/api/* 不再提供），入口统一重定向回首页；src/forum/ 保留待复活」 |
| 页面逻辑 | `frontend/src/App.vue` L52-53：`isForumRoute`（`currentRoute.path.startsWith('/forum')`）已随下线移除 |
| 后端 | main 树里**没有任何 forum 路由模块**（全树搜 `forum` 只剩 `vendor/openclaw/` 下两个无关文件） |

自查命令（在仓库根跑）：

```bash
grep -rn "redirect: '/'" frontend/src/main.ts
grep -rn "isForumRoute\|/forum" frontend/src/App.vue
# 后端：应该零命中（vendor 里的 openclaw 无关）
git ls-tree -r --name-only HEAD | grep -i forum | grep -v '^frontend/'
```

## 这里有什么

| 分组 | 内容 |
|---|---|
| 视图 | `ForumLayoutView` / `ForumListView` / `ForumPostView` / `ForumMessagesView` / `ForumMyPostsView` / `ForumMyRepliesView` / `ForumFriendsView` / `ForumQuotaView` |
| 组件 | `components/Forum*`（卡片 / 回复 / 输入 / 图片预览 / 侧栏 / 解锁）、`components/Explore*`（探索会话：列表/创建/帮助/状态/统计/原始历史） |
| 逻辑 | `api.ts`、`types.ts`、`useAgentProfile.ts`、`composables/useCreateExploreForm.ts`、`useExploreSessionOps.ts`、`useQuotaDashboard.ts` |

## 复活前提（按依赖顺序，缺一项都跑不通）

1. **后端先回来**：`/forum/api/*` 路由与发帖链路恢复（当前 main 上没有 forum 路由模块）。
2. `frontend/src/main.ts`：删掉那两条 `redirect: '/'`，换回真实组件路由。
3. `frontend/src/App.vue`：按需恢复 `isForumRoute`（L52-53 的注释里有原写法）。
4. `api.ts` 的 base path 与后端路由对齐后，再谈 UI 打磨。

> ⚠️ 复活前请**重新核实**上面三条证据，不要只看这份文档 —— 它和代码一样会腐。
> 本文只登记 2026-10-29 实测到的状态；下游若有「发帖入口被注释」这类细节，
> 本次未逐行核对，复活时请自己确认。

## 在这之前，请不要

- **不要删除**：删了等于把"复活"变成"重写"；
- **不要加新功能 / 不要升这里的依赖**：改了没人能验收，只会增加将来复活时的对齐成本；
- **不要顺手修 lint** 后声称"论坛已修好"：能跑 lint 不等于有入口。
