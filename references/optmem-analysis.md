# OptMem 架构分析

> 来源：[VictorTaelin/OptMem](https://github.com/VictorTaelin/OptMem) | ⭐880+ | 2026-07-28 创建
> 状态：📋 待消化 — 对 Hermes memory 系统有直接参考价值

---

## 一句话

**两个文本文件 + 一个 859 行 Python 零依赖脚本 = Agent 无限记忆。** 426 token 的 prompt 即插即用。

## 文件结构

```
~/.optmem/
  memo          ← 单文件 Python 3，零依赖
  memory/
    LOG.txt     ← 定长 320B/条，append-only，永不编辑
    TREE/       ← 压缩摘要树，可从 LOG 重建
    config      ← 可调参数，只需动 WAKE_LINES
```

## 核心数据结构

### 定长记录 = 位置即身份

- `LOG_REC = 320` 字节/条，`TREE_REC = 288` 字节/块
- 查找第 i 条记忆 = `fseek(i * 320)`，O(1)，不需要索引
- 100 万条记忆（608MB），`wake` 只需 0.03 秒

### 二进制树压缩

```
新记忆 #0 #1 #2 #3 #4 #5 #6 #7  ← 逐条保留
       \  /     \  /     \  /
      #0-1     #2-3     #4-5   ← 老化→压缩为摘要块
          \       /       |
          #0-3          #4-7   ← 继续老化→更大块
```

### cover(T, budget) 算法

核心创新：用 alpha tiling 决定哪些块保留为摘要、哪些展开为原始记忆。

- **alpha**：块大小 ≤ alpha × 年龄 → 越老越粗，越新越细
- **budget**：WAKE_LINES=96（≈8k token），wake 输出严格卡在这个预算内
- 二进制搜索 alpha 使输出精确匹配 budget

### "Nap, don't sleep"

不在后台压缩，而是 agent 自己做：

```
memo note "新记忆" → 输出：
  Compress memories #16-31 into one line of at most 280 characters.
  Keep what has lasting effect, drop what does not. Invent nothing.
  
    #16-17 <子摘要A>
    #18-19 <子摘要B>
  
  1 compression remains after this one.
  Run: memo nap 16-31 "<your line>"
```

Agent 收到 prompt → 写摘要 → `memo nap 16-31 "摘要内容"` → 写入 TREE/

### 并发安全

`fcntl.flock`（Unix）/ `msvcrt.locking`（Windows），同机多 agent session 可并发写。append-only LOG + 文件锁保证 id 分配原子性。

## 四个命令

| 命令 | 作用 |
|------|------|
| `memo wake` | 读记忆，每 session 第一条命令 |
| `memo note "..."` | 追加一条记忆（≤280 字节） |
| `memo nap` | 执行待处理压缩 |
| `memo recall <regex>` | 全文搜索，一次遍历 |

## 关键设计决策

1. **append-only LOG** — 永不编辑/删除，LOG 是真理源。TREE 可重建。
2. **agent 做压缩** — LLM 自己总结自己的记忆，不需要第二个模型。
3. **固定宽度记录** — 位置即身份，零索引开销。
4. **subagent 隔离** — subagent 不运行 memo，避免重复/错误记忆。
5. **"You are awake"** — wake 分页输出，最后一页才打印此句，保证完整读取。

## 对 Hermes 的参考价值

| OptMem | Hermes 现状 | 差距 |
|--------|------------|------|
| 定长 O(1) seek | SQLite FTS5 | 无差距，Hermes 数据量小 |
| append-only | 支持 edit/remove | ⚠️ 破坏不可变性 |
| 二进制树老化压缩 | 固定 2200 字符截断 | 🔴 核心差距 |
| agent 做 nap | 无压缩机制 | 🟡 Hermes tool call 天然适配 |
| 并发 flock | 单进程 | 无需求 |

## 可复用代码

- `cover(T, budget)` 算法 → 直接移植到 Hermes memory 输出端
- "Nap" 模式 → Hermes memory 加 `compress` 操作
- `pending()` 块管理 → 确定哪些记忆到了压缩时机

## 结论

不是"又一个 memory 方案"，是用极简主义（两个文件 + 一个算法）解决了 Agent memory 最核心的问题：**无限记忆 + 常数上下文**。完全符合最小依赖哲学。
