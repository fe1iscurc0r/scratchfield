# LLM4Decompile → MCP 本地化封装 SPEC v1

> 来源：Old-Target-New-Model-Plan 靶子 C  
> 施工者：Trae IDE（执行侧）  
> 审核者：实验田维护者（Hermes）  
> 目标平台：Windows x64（天选7 Pro，RTX 5060 8GB，Python 3.11+）  
> 周期：1-2 天

---

## 一、背景

### 1.1 为什么要做

LLM4Decompile 是目前最强的开源反编译 LLM——反编译后可再执行率超过 GPT-4o 和 Ghidra 100%+。MIT 许可，1.3B 参数，仅需 2.7GB 显存。

当前 Hermes 安全工具栈（VulnClaw / OSINT / 蜜罐反制）缺少一个「二进制→可读 C」的本地化工具。RS-BA1 CI-V 协议逆向虽然以抓包为主，但一旦涉及固件/二进制分析，LLM4Decompile 就是手术刀。

**核心价值**：把「Ghidra 吐出的难读伪 C」→「LLM4Decompile 润色成人类可读 C」，封装为 MCP server，Hermes 一键调用。

### 1.2 关键约束

| 约束 | 说明 |
|------|------|
| ⚠️ **仅支持 Linux x86_64 二进制** | LLM4Decompile 当前版本不支持 Windows PE。RS-BA1 是 Windows 程序，不能直接反编译。**但**：Ghidra 先将 PE 反编译为 C，再送 LLM4Decompile 润色——这个迂回管线可行 |
| ✅ 模型小，本地可跑 | 1.3B 参数，2.7GB VRAM，RTX 5060 (8GB) 毫无压力 |
| ✅ MIT 许可 | 无协议风险，直接集成 |
| ✅ Python 生态 | vLLM / llama.cpp / transformers 三种推理后端可选 |

---

## 二、架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                     Hermes Agent (云服)                       │
│   "反编译 /home/ubuntu/targets/binary.o → 可读 C"            │
└────────────────────────┬────────────────────────────────────┘
                         │ MCP 协议 (JSON-RPC)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              LLM4Decompile MCP Server (Windows 天选7)         │
│                                                              │
│  ┌──────────────────┐    ┌──────────────────────────────┐   │
│  │  MCP Handler      │    │  LLM4Decompile Inference     │   │
│  │  - decompile()    │───▶│  - llama.cpp (推荐，最轻)    │   │
│  │  - polish_ghidra()│    │  - GGUF 格式模型             │   │
│  │  - health()       │    │  - GPU offload (CUDA)        │   │
│  └──────────────────┘    └──────────────────────────────┘   │
│                                                              │
│  输入：二进制文件路径 / Ghidra 伪 C 文本                       │
│  输出：人类可读 C 代码                                        │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 MCP 接口定义

```json
{
  "name": "llm4decompile",
  "version": "1.0.0",
  "tools": [
    {
      "name": "decompile_binary",
      "description": "反编译 Linux x86_64 ELF 二进制文件 → 人类可读 C",
      "parameters": {
        "binary_path": "string (必填) — 二进制文件绝对路径",
        "optimization": "string (可选) — O0/O1/O2/O3，默认 auto 自动检测",
        "max_tokens": "int (可选) — 最大输出 token，默认 4096"
      }
    },
    {
      "name": "polish_ghidra_output",
      "description": "将 Ghidra/IDA 反编译输出润色为人类可读 C（适用于 PE/非 ELF 二进制）",
      "parameters": {
        "pseudo_c": "string (必填) — Ghidra 反编译输出的伪 C 代码",
        "function_name": "string (可选) — 函数名，帮助模型理解上下文",
        "context_hint": "string (可选) — 额外上下文（如 '这是 Icom CI-V 协议处理函数'）"
      }
    },
    {
      "name": "health",
      "description": "检查模型加载状态、显存使用、可用 token 数",
      "parameters": {}
    }
  ]
}
```

### 2.2 两条调用路径

| 路径 | 输入 | 适用场景 |
|------|------|---------|
| **A: 直接反编译** | ELF 二进制文件 | Linux 二进制分析（蜜罐捕获的样本、CTF 题目） |
| **B: Ghidra 迂回** | Ghidra 伪 C 文本 | **RS-BA1 (PE 格式)**、任何非 ELF 二进制 |

**路径 B 是你当前的主用路径**：Ghidra 先反编译 RS-BA1 的 DLL/EXE，吐出伪 C，然后 LLM4Decompile MCP 接手润色——变量重命名、控制流简化、注释补全。

---

## 三、施工步骤

### Step 1：模型准备（0.5h）

```bash
# 在 WSL2 或 Windows native 下载 GGUF 模型
# 下载地址（选一个）：
# HuggingFace: LLM4Binary/llm4decompile-1.3b-v2-GGUF
# 模型大小 ~1.5GB (Q4_K_M 量化)

# Windows 路径建议：
mkdir C:\Users\<user>\models\llm4decompile
# 下载 Q4_K_M.gguf 到此目录
```

### Step 2：llama.cpp 推理后端（1h）

```bash
# 方案 A: llama-cpp-python (推荐，纯 Python)
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121

# 方案 B: 直接用 llama.cpp 的 server 模式（备选）
# 下载 llama.cpp Windows release，启动 server
```

**选型建议**：`llama-cpp-python` 是推荐的——纯 Python 绑定，CUDA 加速，API 简单，和 MCP server 同进程。不需要额外启动推理服务。

### Step 3：MCP Server 骨架（2h）

目录结构：
```
llm4decompile-mcp/
├── mcp_server.py          # MCP 协议处理 + 工具注册
├── inference.py           # LLM4Decompile 推理封装
├── mcp_manifest.json      # MCP 工具定义
├── requirements.txt       # 依赖
├── config.yaml            # 模型路径/GPU 层数/上下文长度
└── test/
    ├── test_decompile.py
    └── test_polish.py
```

**mcp_server.py 核心逻辑**：

```python
# 伪代码——Trae 按此结构填充
class LLM4DecompileMCPServer:
    def __init__(self, config):
        self.model = Llama(
            model_path=config["model_path"],
            n_gpu_layers=config.get("n_gpu_layers", -1),  # -1 = 全部上 GPU
            n_ctx=config.get("n_ctx", 16384),
            verbose=False
        )
    
    def decompile_binary(self, binary_path, optimization="auto"):
        # 1. 读取二进制文件
        # 2. objdump -d 提取汇编（如果没有 objdump，用 Python capstone）
        # 3. 构造 prompt（参考 LLM4Decompile 官方 prompt 模板）
        # 4. 调用 self.model.create_completion()
        # 5. 后处理：提取 C 代码块，去除 markdown 包裹
        pass
    
    def polish_ghidra_output(self, pseudo_c, function_name, context_hint):
        # 1. 构造润色 prompt："以下是一个函数的 Ghidra 反编译结果，请重写为人类可读的 C 代码"
        # 2. 调用 self.model.create_completion()
        # 3. 后处理
        pass
```

**关键 Prompt 模板**（参考 LLM4Decompile 官方）：

```
# 反编译 prompt（路径 A）
Below is the assembly code of a Linux x86_64 function compiled with {opt} optimization.
Please decompile it into human-readable C source code.

[assembly code here]

Decompiled C code:
```

```
# Ghidra 润色 prompt（路径 B）
The following is Ghidra's decompilation output of a function from a Windows binary.
The function is related to: {context_hint}
Please rewrite it into clean, readable C code with meaningful variable names and comments.

[Ghidra pseudo-C here]

Rewritten C code:
```

### Step 4：MCP 协议适配（1h）

Trae 侧只需要实现 MCP stdio transport：

```python
# 使用 mcp 官方 SDK
from mcp import Server, Tool
from mcp.types import TextContent

server = Server("llm4decompile")

@server.tool()
async def decompile_binary(binary_path: str, optimization: str = "auto") -> list[TextContent]:
    result = llm.decompile_binary(binary_path, optimization)
    return [TextContent(type="text", text=result)]

@server.tool()
async def polish_ghidra_output(pseudo_c: str, function_name: str = "", context_hint: str = "") -> list[TextContent]:
    result = llm.polish_ghidra_output(pseudo_c, function_name, context_hint)
    return [TextContent(type="text", text=result)]

@server.tool()
async def health() -> list[TextContent]:
    status = llm.get_status()
    return [TextContent(type="text", text=json.dumps(status))]
```

### Step 5：Hermes 侧注册（0.5h）

在云服 Hermes 的 MCP 配置中添加：

```yaml
# ~/.hermes/config.yaml 或 profiles/default/config.yaml
mcp_servers:
  llm4decompile:
    transport: "sse"           # 如果 Trae/Windows 侧开 HTTP SSE
    url: "http://<天选7内网IP>:9876/sse"
    # 或通过 frp/隧道暴露到云服可达
```

> ⚠️ 网络：天选7 和云服不在同一局域网。需要 frp 隧道或 Tailscale 打通。优先 Tailscale——天选7 装 Tailscale，加入 tailc262bc.ts.net，云服通过 `100.x.x.x:9876` 直连。

---

## 四、技术选型决策树

```
Windows 上跑推理？
├── 有 WSL2 → llama-cpp-python (CUDA)，WSL2 内装
├── 无 WSL2，纯 Windows
│   ├── llama-cpp-python Windows wheel 可用 → 直接用
│   └── wheel 不可用 → llama.cpp server.exe + Python HTTP client
└── 显存不够？→ Q4_K_M 量化（1.5GB），不可能不够
```

**推荐路径**：如果有 WSL2，在 WSL2 里跑 llama-cpp-python CUDA 版，性能最好。如果没有，Windows 原生 llama-cpp-python 也完全够用（1.3B 模型小，CPU 推理也不慢）。

---

## 五、已知限制 & 诚实标注

| 限制 | 影响 | 缓解方案 |
|------|------|---------|
| ⚠️ 仅 ELF | RS-BA1 (PE) 不能用路径 A | 路径 B（Ghidra 迂回）完全可用 |
| 1.3B 模型能力有限 | 复杂 C++ 模板/virtual dispatch 可能不准 | 用于 C 函数级反编译，不碰 C++ 类层次 |
| 无增量反编译 | 每次调用是独立的，不做跨函数分析 | 后续迭代加 cross-function context |
| Windows objdump 缺失 | 路径 A 需要提取汇编 | 用 Python `capstone` 库替代，pip install capstone |

---

## 六、测试用例

### 6.1 路径 A：直接反编译

```python
# test_decompile.py
# 1. 编译一个简单的 C 函数为 ELF（需 WSL2 或 Linux 环境）
#    int add(int a, int b) { return a + b; }
# 2. 调用 decompile_binary("/path/to/add.o", optimization="O0")
# 3. 断言输出包含 "return a + b" 或等价逻辑
```

### 6.2 路径 B：Ghidra 润色（核心测试）

```python
# test_polish.py
ghidra_output = """
undefined8 FUN_140012340(longlong param_1,uint param_2)
{
  longlong lVar1;
  undefined8 uVar2;
  
  lVar1 = *(longlong *)(param_1 + 0x10);
  if (lVar1 == 0) {
    uVar2 = 0xffffffff;
  }
  else {
    uVar2 = (**(code **)(lVar1 + 0x28))(param_2);
  }
  return uVar2;
}
"""

result = polish_ghidra_output(
    pseudo_c=ghidra_output,
    function_name="send_ci_v_command",
    context_hint="Icom CI-V protocol: sends a command byte to radio, expects response"
)
# 期望：变量改名（param_1→serial_port, lVar1→vtable_ptr），逻辑注释
```

### 6.3 Health check

```python
result = health()
# 期望：{"model_loaded": true, "vram_used_mb": 1500, "max_context": 16384, "status": "ready"}
```

---

## 七、交付物清单

- [ ] `llm4decompile-mcp/` — 完整项目目录
- [ ] `mcp_server.py` — 可运行的 MCP server
- [ ] `inference.py` — LLM4Decompile 推理封装
- [ ] `requirements.txt` — 精确依赖（含版本号）
- [ ] `config.yaml.example` — 配置模板
- [ ] `README.md` — 安装 + 启动 + Hermes 对接步骤
- [ ] `test/test_polish.py` — 路径 B 测试通过（用 mock Ghidra 输出）
- [ ] Hermes 侧 MCP 配置片段

---

## 八、验收标准

1. ✅ `python mcp_server.py` 启动无报错
2. ✅ `health()` 返回模型已加载，显存 <4GB
3. ✅ `polish_ghidra_output()` 对 Ghidra 伪 C 输出可读性明显提升（变量重命名、控制流简化）
4. ✅ Hermes 能通过 MCP 调用（网络打通）
5. ✅ 单次推理延迟 <30 秒（1.3B 模型，1-2 个函数的伪 C）

---

## 附：为什么先做靶子 C 而不是 A/B/D

| 靶子 | 阻塞项 |
|------|--------|
| A (PDF→数据库) | 需先确认 olmOCR/Qwen3-VL 在天选7能跑，8GB 显存卡边界 |
| B (ML预测) | 需要实验数据，现在没数据 |
| D (PDF→Markdown) | 太简单，练手都不够 |
| **C (LLM4Decompile)** | 零阻塞——模型小、许可干净、有明确用例（RS-BA1 迂回路径），1-2 天出活 |

靶子 C 跑通 → MCP 工作流验证 → Trae+Hermes 协作模式固化 → 再啃 A/B。
