# 序列比对/可视化库授粉报告（E-03）

> **工单**：E-03 · Lumo 科研库扩展
> **目标用户**：生物质能源与材料专业学生，研究木质素/纤维素/生物质转化
> **调研范围**：FAMSA、wfmash、asciiMol
> **风格参考**：MODEL_INTERFACE.md（W-09）

---

## 0. 核查结果：仓库地址纠正

| 库 | 工单给定地址 | 实际 GitHub 仓库 | 备注 |
|---|---|---|---|
| FAMSA | vogtn/FAMSA | **refresh-bio/FAMSA** | `vogtn` 是维护者个人页，非项目仓库 |
| wfmash | ekwanger/WFMash | **waveygang/wfmash** | 存在较大偏差 |
| asciiMol | sunraytao/asciiMol | **dewberryants/asciiMol** | 仓库所有人不同 |

---

## 1. FAMSA（实际仓库：refresh-bio/FAMSA）

### 基本信息

| 项目 | 内容 |
|---|---|
| 许可证 | **GPL v3**（工单标注为 MIT，实际为 GPLv3） |
| 语言 | C++（含 SIMD 加速：AVX2/NEON） |
| 安装 | 预编译二进制 / Bioconda / 源码编译 |
| Python 绑定 | PyFAMSA（Martin Larralde 维护，pip install pyfamsa） |
| 在线版 | WebAssembly 版本，支持浏览器端本地运行（最多 10 万条序列） |

### 核心能力

- **超大规模多序列比对（MSA）**：宣称可在 5 分钟内完成 300 万条 ABC 转运蛋白序列的比对（PF00005），内存 18 GB；8 小时处理完整 Pfam-A v37.0（约 6200 万条序列）。
- **渐进式比对**：支持 single-linkage、UPGMA、Neighbour-Joiningguide tree；可导入已有 guide tree。
- **距离矩阵导出**：支持 CSV 格式输出 pairwise distance 或 PID（Percent Identity）矩阵。
- **输入格式**：FASTA（支持 gzipped）；单输入为 MSA，双输入为 profile-profile 比对（保留 gap）。
- **输出格式**：FASTA 比对结果、Newick guide tree、CSV 距离矩阵。

### 关键参数摘要

```
-t <n>        线程数（默认自动）
-gt <type>    guide tree 类型：upgma / nj / single（默认 single）
-gz           输出 gzip 压缩
-dist_export  导出距离矩阵（CSV）
-pid          与 -dist_export 联用，输出 PID 矩阵而非距离
-refine_mode off  关闭 profile refinement（提速）
-medoidtree   先构建 approximated medoid tree 再做 UPGMA
```

### 与生物质能源研究的关联

生物质转化研究中常需分析酶家族序列（如糖苷水解酶 GH1/GH3、AA 氧化酶家族等）。FAMSA 适合：
- 对**大规模酶家族进行 MSA**，构建系统发育树，辅助功能注释。
- 导出距离/PID 矩阵后用其他工具做进化分析。
- PyFAMSA 可直接集成进 Python 分析流程。

### 局限性

- **GPL 许可证**（非 MIT），商业集成需注意许可证合规。
- 无内置进化树可视化，需配合 ETE3 等工具。
- 专注蛋白质序列；核苷酸序列支持未优化。

---

## 2. wfmash（实际仓库：waveygang/wfmash）

### 基本信息

| 项目 | 内容 |
|---|---|
| 许可证 | 未在 README 明确标注许可证 badge（建议使用时核实） |
| 语言 | C++ |
| 安装 | Bioconda / 源码编译 |
| 定位 | 全基因组泛基因组比对器（Pangenome-scale aligner） |
| 关键依赖 | MashMap 3.5（近似映射）+ WFA（Wave Front Alignment，碱基级比对） |

### 核心能力

- **全基因组规模比对**：在普通计算节点上，可对 Gb 级基因组进行分钟到小时级的比对（取决于序列分歧度）。
- **支持极低相似度**：平均核苷酸一致性（ANI）可低至 **70%**，适合高度分歧的基因组。
- **自动阈值**：默认根据输入序列的 ANI 分布自动确定比对阈值（使用中位数 50th percentile）。
- **PAF/SAM 双输出格式**：可输出 SAM 格式带 MD tag，便于与 BWA 等工具结果对比。
- **与 pggb 集成**：wfmash 是 pggb（PanGenome Graph Builder）的核心算法，用于构建泛基因组图谱。
- **分阶段流水线**：Mapping（minmer sketch）→ Chaining → Filtering → Scaffolding（可选）→ WFA 碱基级比对。

### 关键参数摘要

```
-p aniXX[+/-N]     ANI 阈值：ani25/ani50/ani75 或加减调整（默认 ani50）
-k <int>           k-mer 大小（默认 15）
-s <int>           sketch size（每个窗口 minmer 数，默认自动）
-m                 仅近似映射，跳过 WFA 碱基级比对（可处理更大片段）
-l <int>           最小比对块长度（默认 0）
-S <int>           scaffold 最小长度（默认 10k）
-t <int>           线程数
-Y '#'             PanSN 格式：排除同基因组内部比对（用于泛基因组分析）
-o                 仅报告每对 query/target 的最优比对
```

### 与生物质能源研究的关联

wfmash 定位偏向真核基因组规模比对，与木质素/纤维素研究的具体关联：
- **木质素降解微生物基因组比对**：分析降解菌株间的基因组结构变异（插入、缺失、重排）。
- **纤维素酶生产菌株泛基因组**：构建工业菌株（*Trichoderma reesei*、*Aspergillus* 等）的泛基因组图谱，挖掘候选酶基因。
- **热解油/生物油微生物群落（metagenome）**：对宏基因组组装基因组（MAG）进行全基因组比对，评估菌株间亲缘关系。

### 局限性

- **非 Python 原生库**：无直接 Python API，需通过 subprocess 调用，输出需自行解析 PAF/SAM。
- WFA 复杂度在比对长度上呈二次方，默认限制 50 kb；超过则需用 `-m` 近似映射模式。
- 专注核苷酸序列；非蛋白质 MSA 工具。
- 文档较简，部分高级参数需要阅读源码理解。

---

## 3. asciiMol（实际仓库：dewberryants/asciiMol）

### 评估结果：不采用

**原因**：

1. **README 为空**：无法通过文档评估接口契约、功能边界和稳定性。
2. **C++ 源码单文件架构**：降级调研发现源码仅一个 `asciimol.cpp` 文件，功能为将分子结构渲染为 ASCII art，无 Python 绑定，无标准化 API 接口。
3. **封装成本高、价值低**：该工具以终端交互为核心，无结构化输出接口，不适合封装为 MCP 工具。

如后续需终端分子可视化替代方案，建议评估 **py3dmol**（Jupyter 集成 3D 分子查看）或 **obabel**（命令行分子格式转换）更为成熟。

---

## 4. 三库横向对比

| 维度 | FAMSA | wfmash | asciiMol |
|---|---|---|---|
| **核心功能** | 蛋白质 MSA | 全基因组比对 | 分子 ASCII 可视化 |
| **语言** | C++ | C++ | C++ |
| **许可证** | GPL v3 ⚠️ | 未明确标注 | BSD-2 |
| **Python 集成** | PyFAMSA（pip） | 无原生 API | 无 |
| **输入** | FASTA（蛋白） | FASTA（核酸） | `.xyz` |
| **适用规模** | 百万级序列 MSA | Gb 级基因组 | 小分子 |
| **GUI** | Web UI（在线版） | 无 | 终端交互 |
| **主要应用** | 酶家族 MSA | 泛基因组构建 | 分子结构查看 |
| **MCP 采纳** | ✅ 建议采纳 | ✅ 建议采纳 | ❌ 不采用 |

---

## 5. 工单建议

针对生物质能源与材料专业学生，三工具优先级：

1. **FAMSA（建议采纳，最高优先级）**：蛋白质 MSA 需求明确；PyFAMSA 可无缝集成 Python 流程；适合分析糖苷水解酶、氧化酶等酶家族的进化关系。**注意 GPLv3 许可证约束**。
2. **wfmash（建议采纳，中优先级）**：若涉及工业菌株基因组变异分析或泛基因组构建，则有较高价值；否则优先级下降。无 Python 原生 API，需封装 subprocess 调用。
3. **asciiMol（不采用）**：README 为空，C++ 单文件架构，无标准化 API，封装成本高、价值低，不适合 MCP 工具封装。

---

## 6. 调研结论

本次调研发现工单提供的三个仓库地址均存在偏差，建议更新工单记录：

- **FAMSA**：`vogtn/FAMSA` → 实际为 `refresh-bio/FAMSA`；且工单标注 MIT 许可证，实际为 **GPLv3**。
- **wfmash**：`ekwanger/WFMash` → 实际为 `waveygang/wfmash`，仓库主体差异较大。
- **asciiMol**：`sunraytao/asciiMol` → 实际为 `dewberryants/asciiMol`；且因 README 为空、C++ 单文件架构，不适合 MCP 封装。

三库均属开源工具链中的专项工具，无相互替代关系：FAMSA 做蛋白质序列比对，wfmash 做全基因组比对，在生物质转化研究中覆盖了从酶家族进化分析到基因组结构变异的不同层次，具有较高 MCP 采纳价值。
