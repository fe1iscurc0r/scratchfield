# MODEL_INTERFACE: hyalite

- 上游仓库: https://github.com/Psy-Fer/hyalite
- 许可证: MIT（引用须保留，见 ../LICENSES.md）
- 安装: Rust crate（`cargo add hyalite`，Rust ≥ 1.85）；无官方 Python 绑定
- 模块名: `hyalite`（Rust）

## 算法定位

精确、SIMD 加速的成对/数据库序列比对（纯 Rust）：Smith-Waterman（局部）、
Needleman-Wunsch（全局）、两种半全局（HW/SHW）、重叠（OV），仿射空位罚分，
运行时 CPU 分派（SSE4.1/AVX2/NEON/标量），跨后端结果按位一致（确定性保证）。
是 Opal（Rognes 的 inter-sequence SIMD Smith-Waterman）的 Rust 重实现。

## 核心 API（Rust）

```rust
use hyalite::{Database, Mode, Scoring, Scratch, SearchType};

let scoring = Scoring::new(4, matrix_row_major, /*gap_open*/ 2, /*gap_ext*/ 1)?;
let db = Database::builder()
    .sequences(&seqs).scoring(scoring)
    .mode(Mode::Sw).search_type(SearchType::ScoreEnd)
    .max_query_len(64).build()?;

let mut scratch = Scratch::new(&db);       // 每线程独立
let hit = db.scan(&mut scratch, &query);   // 最高分命中
// traceback: db.scan_aligned / align() 返回 score + spans + CIGAR
```

## 数据格式

- 输入: 字母表索引序列（u8 vec，如 ACGT=0,1,2,3）+ 行主序替换矩阵
- 输出: 得分、数据库索引、查询/目标端点、CIGAR（traceback 时）
- 确定性: 同一输入所有后端结果按位相同（DETERMINISM.md 承诺）

## Lumo 工作台用途

- 序列类数据（引物/接头/标记序列）的精确去冗余比对
- 属 Rust 生态资产：Lumo 主链为 Python，仅在需要自建比对服务时接入
  （可经 PyO3 封装）；当前优先级低

## 引用

hyalite 为 Opal 的独立重实现；算法基础: Rognes, T. (2011). Faster
Smith-Waterman database searches with inter-sequence SIMD parallelisation.
BMC Bioinformatics 12, 221. doi:10.1186/1471-2105-12-221
