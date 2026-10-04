# W96-03 · AMC 自动调制分类双件勘察（AMC-Net + AWN）

**上游**：
- zjwfufu/AMC-Net（72★ · MIT · ICASSP'23 官方代码，西电）
- zjwfufu/AWN（84★ · MIT · TCCN'23 自适应小波网络，同组）
**勘察方式**：GitHub 浅克隆（D:\wo34-recon\{amc-net,awn}）+ README/目录阅读
**口径**：防御/识别（调制识别属态势感知基础能力）
**工单**：第三十四期扩轮卷96 · W96-03【评估】

---

## 1. 项目定位

同组两篇论文的官方实现，构成「AMC 深度网络 + 自适应小波特征」双件：
- **AMC-Net**（ICASSP'23）：面向 RML2016.10a/b 的有效 AMC 网络；
- **AWN**（TCCN'23）：自适应小波网络，扩展到 RML2018.01a（19 种调制含 APSK/GMSK/OQPSK…）。
两者共享同一训练/评估管线（AMC-Net README 明示 pipeline 来自 AWN）。
对本仓意义：rf_brain Phase 4 目前是**手工特征 + 规则**（slope/flatness/snr），
AMC 双件提供「深度学习调制分类」的对照与可借用特征/网络结构（MIT 可直接借鉴）。

## 2. 架构拆解（两仓同构，顶层实测）

```
models/       # 网络定义（AMC-Net / AWN 主体）
data_loader/  # RML pkl/dat/hdf5 加载与变换
training/ inference/ util/ config/ checkpoint/
data/         # 数据集占位（RML 需自 DeepSig 下载，仓内不含数据）
doc-CN/       # 中文文档（对中文读者友好）
```

要点：
- **数据与代码分离**：RML 数据集不随仓（DeepSig 许可另计），仓内只放加载器——
  本仓若引入 RML 做 AMC 对照，沿用此边界（数据只索引不入仓）。
- **config 驱动 + checkpoint 随仓**：预训练权重提供下载链接（Google Drive），
  复现门槛低；本仓借结构时可先跑其预训练权重验证管线，再换自采数据微调。
- **AWN 的小波特征**：自适应小波变换作为前端特征，对低 SNR 更稳——
  与 rf_brain 现有 FFT 域特征互补（时频局部化）。

## 3. AMC 模型选型建议（对比 Artemis / meta-transformer / MAMC）

| 方案 | 许可 | 输入 | 适用 | 判定 |
|---|---|---|---|---|
| AMC-Net / AWN | MIT | IQ（RML 系） | 低中 SNR 调制分类，可自训练 | **首选借用**（结构+特征） |
| Artemis | GPL-3.0 | 实时频谱 | 信号→制式识别闭环（知识库） | 只参考设计（W96-01） |
| meta-transformer / MAMC | 待核（本轮未克隆） | IQ/谱 | 大模型路线 | 下轮补勘察再判 |

结论：**短期借 AWN 小波前端 + AMC-Net 骨干做自训练分类器**（MIT 可融合），
Artemis 作识别闭环组织参照；transformer 系等算力/数据到位再评。

## 4. 可落地借鉴点（≥3）

1. **自适应小波前端特征**：给 rf_brain 特征向量加小波域统计量（AWN 思路），
   低 SNR 场景补 FFT 域特征盲区；MIT 可直接移植实现。
2. **RML 加载器与变换管线**：data_loader 的 pkl/dat/hdf5 三格式加载 + 归一化，
   本仓做 AMC 对照实验直接复用（保留 MIT 头）。
3. **config+checkpoint 复现范式**：实验配置与权重分离、中文文档随仓——
   rf_brain 实验脚本照此组织（当前实验脚本散在根目录，可收敛）。
4. **19 调制标签表**（RML2018.01a）：作为本仓 MODULATIONS 枚举的扩展参照
   （当前 ASK/FSK/PSK/GFSK/OQPSK 五类，可渐进补 QAM/APSK 族）。

## 5. 许可裁定

- **MIT（两件）**：可融合代码（保留版权声明 + NOTICE 登记）。
- RML 数据集：DeepSig 许可（研究用途条款），**只索引不整包入仓**；
  自采数据训练不受其约束。

## 6. 执行清单

- [x] 双件克隆 + 结构/许可核验 + 选型对照表
- [x] 借鉴点 4 条 + MIT 融合判定
- [ ] （后续工单）小波前端特征进 rf_brain + RML 对照实验骨架
