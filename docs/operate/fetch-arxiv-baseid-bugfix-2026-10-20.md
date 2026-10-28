# fetch_arxiv.py base-id 去重收口（工单 264 任务 D）

> 状态：**文档交付**。仓外脚本（`/home/ubuntu/research/papers/`）不在本仓，本单**不执行**改动。

## 1. 症状

- 判断层已在 10-20 按 base id 去重：`new=740` → 真新增 `712`，**28 个是版本变体**。
- 但 corpus 行数仍在膨胀：`49,197 → 49,937` 行，**唯一论文数未增长**。
- 表现：表面差异（如"新增 800 篇"）里绝大部分是同一论文的 `v1/v2/v3`。

## 2. 根因

1. **双通道写入**：API 与 RSS 两条路径分别取数，两边都可能写入同一条论文的不同版本；
2. **`seen` 集合用完整 id**：`seen.add(aid)` 用的是带版本号的 id（`2610.12345v2`），
   于是 `2610.12345v1` 与 `v2` 被当成两条不同记录；
3. 去重发生在**判断层**（统计时）而不是**入库层**（写入时），所以统计看着对、语料仍在长。

## 3. 修法 diff（行号级）

`fetch_arxiv.py` 需要两处改动：

```diff
@@ 引入工具函数（文件顶部，紧接 imports 之后）
+def base_id(aid: str) -> str:
+    # 去掉 arXiv id 的版本后缀：2610.12345v2 -> 2610.12345
+    return aid.split("v")[0] if "v" in aid else aid
```

```diff
@@ 写入前判重（原逻辑近似：if aid not in seen: seen.add(aid); write(aid)）
-    if aid not in seen:
-        seen.add(aid)
+    if base_id(aid) not in seen:
+        seen.add(base_id(aid))
         write_record(aid)
```

**要点**：`base_id` 必须同时用于**判重**与**入集合**，只改一处会导致"判重通过但仍反复写入"。

## 4. 副作用（必须在评审里说清）

- **同一论文的 v2 修正版会被永久跳过**：如果某篇论文在 `v1` 之后发布了**实质性修订**（不只是排版），
  默认行为会丢掉修订内容。
- 若不接受该副作用，需改成**「base id 去重 + 版本号单独存 `rev` 字段」**：

```diff
-        seen.add(base_id(aid))
+        seen.add(base_id(aid))
+        record["rev"] = aid[len(base_id(aid)):] or "v1"   # 保留版本，供人工追修订
```

即：去重键仍是 base id，但把版本号落库，修订版可通过 `rev` 排序比对，不静默丢失。

## 5. 验收口径

```bash
# 下一轮跑批应满足：naive_diff == 真新增（差值为 0 或仅剩个位数噪声）
python3 -c "print(naive_diff - true_new)"   # 期望 0
```

**判定**：连续两轮跑批 `naive_diff - true_new <= 0`，且 corpus 唯一论文数**单调不减**、行数增速与唯一数增速一致。

## 6. 仓外部分（不执行）

- `/home/ubuntu/research/papers/` **不是 git 仓库**（`git log` 报 not a git repo），本仓改不了也推不了。
- 施工记录里"打 git tag `v2026-10-19-baseid-dedup`"**作废**。
- 替代做法：若师傅授权，在脚本旁放一个 `VERSION` 文件（内容 `2026-10-20-baseid-dedup`），
  并在 `weekly_pollination.md` 顶部记一行变更。
