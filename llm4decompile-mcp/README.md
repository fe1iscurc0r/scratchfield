# LLM4Decompile MCP 封装

将开源反编译模型 [LLM4Decompile](https://github.com/LLM4Binary/llm4decompile)（MIT 许可，1.3B）封装为
MCP server，让 Hermes/陆墨 一键把「二进制/Ghidra 伪 C」转成可读 C 代码。

## 两条路径

| 路径 | 输入 | 适用场景 |
|------|------|---------|
| **A: decompile_binary** | ELF 二进制文件 | Linux 二进制分析（蜜罐样本、CTF） |
| **B: polish_ghidra_output** | Ghidra/IDA 伪 C 文本 | **RS-BA1 (PE)**、任何非 ELF 二进制 |

> RS-BA1 是 Windows PE，不能直接反编译（路径 A 仅支持 ELF）。正确用法：
> Ghidra 先把 DLL/EXE 反编译成伪 C，再用 `polish_ghidra_output()` 润色成可读 C。

## 安装

```bash
pip install llama-cpp-python mcp capstone PyYAML
```

模型（约 1.5GB，Q4_K_M 量化）：

```bash
# HuggingFace: LLM4Binary/llm4decompile-1.3b-v2-GGUF
# 下载 llm4decompile-1.3b-v2-q4_k_m.gguf 到本地 models 目录
```

## 配置

```bash
cp config.yaml.example config.yaml
# 编辑 config.yaml 填写 model.path 指向 GGUF 文件
```

## 启动（stdio transport）

```bash
python mcp_server.py --config config.yaml
```

## Hermes 侧对接

Hermes 的 MCP 配置中注册（stdio 或经隧道暴露的 SSE）：

```yaml
mcp_servers:
  llm4decompile:
    transport: "stdio"
    command: "python"
    args: ["D:/my git/scratchpad/llm4decompile-mcp/mcp_server.py", "--config", "config.yaml"]
```

若天选7 与云服不同局域网，用 Tailscale/frp 打通后改用 `sse` transport。

## 测试

```bash
cd llm4decompile-mcp
python -m unittest discover -s test -v
```

- `test_polish.py` — 路径 B（Ghidra 润色，核心路径）
- `test_decompile.py` — 路径 A（ELF 反编译）

测试无需真实模型（mock 推理层，验证 prompt 模板与后处理）。

## 已知限制

- 仅支持 Linux x86_64 ELF（路径 A）；PE 走路径 B Ghidra 迂回
- 1.3B 模型适合 C 函数级反编译，复杂 C++ 类层次可能不准
- 每次调用独立，不做跨函数增量分析

## 收尾状态（台账⑥）

- `mcp_server.py` 修复：`import mcp_types` → `from mcp import types`（官方 SDK 类型模块），
  stdio 协议测试 3/3 过（initialize / tools/list / health）
- 测试全量 12/12：`python -m pytest llm4decompile-mcp/test -v --noconftest -o addopts=`
- 平行的 transformers 路线在 `mcpserver/adapters/llm4decompile.py`（flat adapter）：
  模型 LLM4Binary/llm4decompile-1.3b-v1.5 已缓存，CPU bf16 实测 ~3 分钟/256 token，
  Windows 无 objdump 时走 capstone+pefile 兜底反汇编；单测 tests/test_llm4decompile_adapter.py 11/11
- Hermes 接入：mcpserver/external_services.example.json 已提供 llm4decompile stdio 条目（_disabled 待启用）
