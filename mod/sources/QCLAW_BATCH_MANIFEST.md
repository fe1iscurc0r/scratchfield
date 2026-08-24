     1|# QClaw 批量改造清单 — 30 包 → scratchpad
     2|
     3|> **给 QClaw 的指令：** 逐一按以下分组处理。每组内有具体的改造要求、输出格式、文件放置位置。每完成一个包，在最后打 ✅。
     4|> **原则：** 不猜，遇到歧义就停。先读 manifest 规范，再开工。
     5|
     6|---
     7|
     8|## 0. 环境与路径
     9|
    10|> **⚠️ 开工前先设 `PKG_DIR`，指向你本地解压后的包目录。QClaw 自己根据实际路径改下面一行。**
    11|
    12|```
    13|PKG_DIR=C:\Users\ASUS\Desktop\github_haul     ← 改成你本机实际路径
    14|```
    15|
    16|```
    17|源码包位置:    $PKG_DIR/mcp/*.tar.gz 等
    18|scratchpad:    $PKG_DIR/../scratchpad  (或你本机 scratchpad 根目录)
    19|MCP Agent:     scratchpad/mcpserver/agent_<name>/
    20|Skill:         scratchpad/skills/<name>/SKILL.md
    21|融合参考:       scratchpad/references/<name>/
    22|```
    23|
    24|---
    25|
    26|## 1. MCP Agent 规范（必读，先读这段再开工）
    27|
    28|### 1.1 目录结构
    29|
    30|```
    31|mcpserver/agent_<英文名>/
    32|├── __init__.py              # 空文件即可
    33|├── agent-manifest.json      # 见 1.2
    34|└── agent_<英文名>.py        # Agent 类，见 1.3
    35|```
    36|
    37|### 1.2 agent-manifest.json 格式
    38|
    39|```json
    40|{
    41|  "name": "<英文标识，registry key>",
    42|  "displayName": "<中文显示名>",
    43|  "version": "1.0.0",
    44|  "description": "<一句话描述>",
    45|  "author": "GitHub <原作者> + QClaw 改造",
    46|  "agentType": "mcp",
    47|  "entryPoint": {
    48|    "module": "mcpserver.agent_<英文名>.agent_<英文名>",
    49|    "class": "<AgentClassName>"
    50|  },
    51|  "capabilities": {
    52|    "invocationCommands": [
    53|      {
    54|        "command": "<工具名>",
    55|        "description": "<详细描述，含参数说明>",
    56|        "example": "{\"tool_name\": \"<工具名>\", \"<参数>\": \"<值>\"}"
    57|      }
    58|    ]
    59|  }
    60|}
    61|```
    62|
    63|### 1.3 Agent 类规范
    64|
    65|```python
    66|class XxxAgent:
    67|    """<描述>"""
    68|    name = "<显示名>"
    69|
    70|    async def handle_handoff(self, task: dict) -> str:
    71|        """接收 task = {"tool_name": "...", ...参数}，返回 JSON 字符串。
    72|        返回格式: {"status": "ok"|"error", "message": "...", "data": {...}}
    73|        """
    74|        tool_name = str(task.get("tool_name") or "").strip()
    75|        # 路由到具体方法
    76|        ...
    77|
    78|    def _call_cli(self, args: list[str], timeout: int = 120) -> dict:
    79|        """封装 subprocess.run，处理超时、异常"""
    80|        ...
    81|```
    82|
    83|**关键要求：**
    84|- Agent 必须能独立 import，不依赖 scratchpad 其他模块（除了标准库）
    85|- CLI 工具路径硬编码或用绝对路径，不要假设 PATH
    86|- 所有返回值必须是 JSON 字符串，包含 `status`, `message`, `data` 三个字段
    87|- `handle_handoff` 是 async 方法
    88|
    89|### 1.4 注册机制
    90|
    91|只要 `agent-manifest.json` 放在正确位置，scratchpad 的 `mcp_registry.py` 会自动扫描注册。不需要手动改注册表。
    92|
    93|---
    94|
    95|## 2. Skill 规范
    96|
    97|### 2.1 目录结构
    98|
    99|```
   100|skills/<英文名>/
   101|└── SKILL.md    # YAML frontmatter + Markdown 正文
   102|```
   103|
   104|### 2.2 SKILL.md 格式
   105|
   106|```markdown
   107|---
   108|name: <英文名>
   109|description: <中文描述>
   110|version: 1.0.0
   111|author: QClaw 改造自 <原项目>
   112|tags:
   113|  - <标签1>
   114|  - <标签2>
   115|enabled: true
   116|---
   117|
   118|# <标题>
   119|
   120|## 触发条件
   121|...
   122|
   123|## 执行步骤
   124|...
   125|
   126|## 输出格式
   127|...
   128|```
   129|
   130|---
   131|
   132|## 3. QClaw 实际要改造的包（按优先级分组）
   133|
   134|---
   135|
   136|### 🟢 组A：轻量 CLI 包装 — 6 个包（手写不划算，但 QClaw 批量快）
   137|
   138|每个包的任务：读源码 → 理解 CLI 参数 → 写 agent 类 → 写 manifest → 打包放好。
   139|
   140|#### A1. nuclei (23k⭐ MIT)
   141|
   142|- **源码包:** `$PKG_DIR/mcp/nuclei.tar.gz`
   143|- **输出:** `mcpserver/agent_nuclei/`
   144|- **改造要点:**
   145|  - 核心工具：`nuclei -u <URL> -json` 扫描单个目标，`nuclei -l <file>` 批量扫描
   146|  - invocationCommands:
   147|    1. `scan_url` — 单个 URL 漏洞扫描，参数 `url`, `templates`(可选，指定模板目录)
   148|    2. `scan_list` — 批量扫描，参数 `file_path`(目标列表文件)
   149|    3. `list_templates` — 列出可用模板，参数 `severity`(可选过滤: critical/high/medium/low)
   150|  - Agent 内部用 subprocess 调 nuclei 二进制（假设在 PATH 或 `/usr/local/bin/nuclei`）
   151|  - 返回结构化 JSON，从 nuclei 的 `-json` 输出解析
   152|
   153|#### A2. trivy (37k⭐ Apache 2.0)
   154|
   155|- **源码包:** `$PKG_DIR/mcp/trivy.tar.gz`
   156|- **输出:** `mcpserver/agent_trivy/`
   157|- **改造要点:**
   158|  - 核心工具：`trivy image <image>` 扫镜像，`trivy fs <path>` 扫文件系统，`trivy repo <url>` 扫仓库
   159|  - invocationCommands:
   160|    1. `scan_image` — 容器镜像漏洞扫描，参数 `image`
   161|    2. `scan_filesystem` — 文件系统扫描，参数 `path`
   162|    3. `scan_repo` — 代码仓库扫描，参数 `repo_url`
   163|  - 输出解析 trivy 的 JSON 输出（`-f json`）
   164|
   165|#### A3. syft (9.3k⭐ Apache 2.0)
   166|
   167|- **源码包:** `$PKG_DIR/mcp/syft.tar.gz`
   168|- **输出:** `mcpserver/agent_sbom/`
   169|- **改造要点:**
   170|  - 核心工具：`syft <target>` 生成 SBOM
   171|  - invocationCommands:
   172|    1. `generate_sbom` — 生成 SBOM，参数 `target`(镜像/路径), `format`(可选: cyclonedx-json/spdx-json)
   173|    2. `list_packages` — 列出包清单，参数 `target`
   174|  - 输出解析 syft 的 JSON 输出
   175|
   176|#### A4. cosign (6.1k⭐ Apache 2.0)
   177|
   178|- **源码包:** `$PKG_DIR/mcp/cosign.tar.gz`
   179|- **输出:** `mcpserver/agent_signing/`
   180|- **改造要点:**
   181|  - 核心工具：`cosign verify`, `cosign sign`
   182|  - invocationCommands:
   183|    1. `verify_image` — 验证镜像签名，参数 `image`, `key`(可选公钥路径)
   184|    2. `verify_attestation` — 验证 attestation，参数 `image`, `type`(可选)
   185|  - 注意：cosign 需要密钥文件，Agent 应允许配置 key 路径
   186|
   187|#### A5. sherlock (63k⭐ MIT)
   188|
   189|- **源码包:** `$PKG_DIR/mcp/sherlock.tar.gz`
   190|- **输出:** `mcpserver/agent_osint/`
   191|- **改造要点:**
   192|  - 核心工具：`sherlock <username>` 跨 300+ 平台搜索用户名
   193|  - invocationCommands:
   194|    1. `search_username` — 搜索用户名，参数 `username`, `sites`(可选，指定站点列表)
   195|    2. `search_batch` — 批量搜索，参数 `usernames`(逗号分隔)
   196|  - 输出解析 sherlock 的文本输出，转为结构化 JSON（命中/未命中/错误）
   197|  - 注意限速，sherlock 本身会处理，但 Agent 端做超时保护
   198|
   199|#### A6. jadx (43k⭐ Apache 2.0)
   200|
   201|- **源码包:** `$PKG_DIR/mcp/jadx.tar.gz`
   202|- **输出:** `mcpserver/agent_decompile/`
   203|- **改造要点:**
   204|  - 核心工具：`jadx -d <output_dir> <apk_file>` 反编译 APK
   205|  - invocationCommands:
   206|    1. `decompile_apk` — 反编译 APK/DEX，参数 `apk_path`, `output_dir`(可选)
   207|    2. `decompile_dex` — 反编译单个 DEX，参数 `dex_path`
   208|    3. `search_code` — 在反编译结果中搜索，参数 `keyword`, `search_dir`(可选)
   209|  - 注意：jadx 反编译较慢，需要较长超时（5-10分钟）
   210|
   211|---
   212|
   213|### 🟡 组B：中等复杂度 — 5 个包
   214|
   215|#### B1. falco (9.2k⭐ Apache 2.0)
   216|
   217|- **源码包:** `$PKG_DIR/mcp/falco.tar.gz`
   218|- **输出:** `mcpserver/agent_runtime/`
   219|- **改造要点:**
   220|  - Falco 是一个内核级运行时威胁检测守护进程
   221|  - MCP Agent 不启动 Falco（它自己作为 systemd 服务跑），而是读取 Falco 事件
   222|  - invocationCommands:
   223|    1. `get_recent_events` — 获取最近事件，参数 `limit`(默认 50), `priority`(过滤: Emergency/Alert/Critical/Error/Warning)
   224|    2. `get_event_stats` — 事件统计，参数 `duration`(如 1h/24h)
   225|    3. `check_rule` — 测试规则，参数 `rule_content`
   226|  - Agent 通过 `falcoctl` 或读取 Falco 的 JSON 输出/gRPC API 获取事件
   227|  - 如果 Falco 没安装，Agent 应优雅降级返回 "falco daemon not running"
   228|
   229|#### B2. coraza (3.7k⭐ Apache 2.0)
   230|
   231|- **源码包:** `$PKG_DIR/mcp/coraza.tar.gz`
   232|- **输出:** `mcpserver/agent_waf/`
   233|- **改造要点:**
   234|  - Coraza 是 WAF 规则引擎（OWASP Coraza 的 Go 实现）
   235|  - invocationCommands:
   236|    1. `test_rule` — 测试 WAF 规则，参数 `rule`, `payload`
   237|    2. `validate_ruleset` — 验证规则集，参数 `rules_path`
   238|    3. `explain_rule` — 解释规则含义，参数 `rule_id`
   239|  - Agent 内嵌 Coraza 的规则解析逻辑，或调 `coraza-wasmer` CLI
   240|
   241|#### B3. LLM4Decompile (6.8k⭐ MIT)
   242|
   243|- **源码包:** `$PKG_DIR/mcp/LLM4Decompile.tar.gz`
   244|- **输出:** `mcpserver/agent_llm_decompile/`
   245|- **改造要点:**
   246|  - 这是一个 LLM 辅助反编译工具，需要 GPU + 模型加载
   247|  - invocationCommands:
   248|    1. `decompile_binary` — 反编译二进制，参数 `binary_path`, `arch`(x86/arm), `format`(elf/pe)
   249|    2. `decompile_function` — 反编译单个函数，参数 `binary_path`, `function_addr`
   250|  - Agent 假设模型已加载（作为常驻进程），通过 API/gRPC 调推理接口
   251|  - 如果模型进程未启动，返回错误并提示启动方式
   252|
   253|#### B4. pentagi (21k⭐ MIT)
   254|
   255|- **源码包:** `$PKG_DIR/mcp/pentagi.tar.gz`
   256|- **输出:** `mcpserver/agent_pentest/` + `skills/pentest-chain/SKILL.md`
   257|- **改造要点:**
   258|  - PentAGI 是一个 LLM 驱动的多步渗透测试 Agent
   259|  - 不要照搬——拆成两部分：
   260|    1. **MCP Agent:** 提供渗透原子工具（端口扫描、目录爆破、漏洞检测等），每次调用一个原子操作
   261|    2. **Skill:** 编排多步渗透链，调用 MCP Agent 的原子工具
   262|  - MCP invocationCommands 需要从 PentAGI 源码中提取其实际调用的工具列表
   263|  - Skill 写一个工作流：侦察 → 枚举 → 漏洞检测 → 利用 → 报告
   264|
   265|#### B5. browser-use (107k⭐ MIT)
   266|
   267|- **源码包:** `$PKG_DIR/mcp/browser-use.tar.gz`
   268|- **输出:** `mcpserver/agent_browser/`
   269|- **改造要点:**
   270|  - 这是价值最大的包——107k⭐ 的浏览器自动化 Agent
   271|  - Browser-Use 本身已经是一个 Agent，直接拆它的能力为 MCP 工具：
   272|  - invocationCommands:
   273|    1. `navigate` — 导航到 URL，参数 `url`, `new_tab`(bool)
   274|    2. `get_page_state` — 获取当前页面可交互元素列表
   275|    3. `click_element` — 点击元素，参数 `index`(来自 get_page_state)
   276|    4. `type_text` — 输入文本，参数 `index`, `text`
   277|    5. `extract_content` — AI 提取页面内容，参数 `query`(要提取什么)
   278|    6. `execute_task` — 执行高层任务（让 Browser-Use 自己决策），参数 `task`
   279|    7. `screenshot` — 截图，参数 `full_page`(bool)
   280|  - 需要 Playwright + 浏览器环境（Chromium）
   281|  - Agent 启动时检查 Playwright 是否安装，没有则提示 `playwright install chromium`
   282|
   283|---
   284|
   285|### 🔴 组C：高复杂度 — 5 个包
   286|
   287|#### C1. frida (18k⭐ wxWindows)
   288|
   289|- **源码包:** `$PKG_DIR/mcp/frida.tar.gz`
   290|- **输出:** `mcpserver/agent_frida/`
   291|- **改造要点:**
   292|  - Frida 是动态插桩框架——注入进程、Hook 函数、读写内存
   293|  - 需要 frida-server 运行在目标设备上（Android/iOS）
   294|  - invocationCommands:
   295|    1. `list_processes` — 列出目标设备进程，参数 `device`(默认 usb)
   296|    2. `attach_process` — 附加到进程，参数 `pid` 或 `name`, `device`
   297|    3. `inject_script` — 注入 JS 脚本，参数 `pid`, `script`
   298|    4. `hook_function` — Hook 函数，参数 `pid`, `module`, `function_name`
   299|    5. `read_memory` — 读内存，参数 `pid`, `address`, `size`
   300|    6. `detach` — 脱离进程，参数 `pid`
   301|  - Agent 通过 `frida-python` 库调 Frida API，不是子进程
   302|  - 需要管理 Frida 会话生命周期（attach→操作→detach）
   303|
   304|#### C2. strix (46k⭐ Apache 2.0)
   305|
   306|- **源码包:** `$PKG_DIR/mcp/strix.tar.gz`
   307|- **输出:** `mcpserver/agent_strix/`
   308|- **改造要点:**
   309|  - Strix 是一个渗透测试自动化编排器，本身有 Agent 调度逻辑
   310|  - MCP 化时要拆成原子工具，不让它做调度（调度由 scratchpad 的 Lumo Bus 做）
   311|  - invocationCommands（从 Strix 源码中提取其功能模块）:
   312|    1. `port_scan` — 端口扫描，参数 `target`, `ports`(可选)
   313|    2. `service_detect` — 服务识别，参数 `target`, `port`
   314|    3. `vuln_scan` — 漏洞扫描，参数 `target`, `service`
   315|    4. `exploit_check` — 漏洞验证，参数 `target`, `cve_id`
   316|    5. `brute_force` — 爆破，参数 `target`, `service`, `userlist`, `passlist`
   317|    6. `report` — 生成报告，参数 `scan_id`
   318|  - 注意：Strix 内部可能强依赖其自身的编排逻辑，拆解时仔细读源码
   319|
   320|#### C3. nanobrowser (13k⭐ Apache 2.0)
   321|
   322|- **源码包:** `$PKG_DIR/mcp/nanobrowser.tar.gz`
   323|- **输出:** `mcpserver/agent_browser/`（与 browser-use 合并到同一个 Agent 目录）
   324|- **改造要点:**
   325|  - nanobrowser 是 browser-use 的轻量 Chrome 扩展版
   326|  - 不单独建 Agent——把 nanobrowser 的独特能力（如扩展特有的 DOM 访问）补充到 `agent_browser` 中
   327|  - 如果 browser-use 已经覆盖了所有 nanobrowser 功能，则仅在 manifest 的 description 中注明 "参考 nanobrowser"
   328|
   329|#### C4. pentest-agents (785⭐)
   330|
   331|- **源码包:** `$PKG_DIR/fusion/pentest-agents.tar.gz`
   332|- **输出:** `references/pentest-agents/`（参考架构）+ 提取其中可用的工具逻辑补充到 `agent_pentest/`
   333|- **改造要点:**
   334|  - 这是一个多 Agent 渗透协同系统，架构参考价值 > 直接 MCP 化
   335|  - 任务：
   336|    1. 通读源码，写一份 `references/pentest-agents/ARCHITECTURE_NOTES.md`（≤3KB），总结其 Agent 协同模式
   337|    2. 提取其中可独立使用的工具模块，补充到 `agent_pentest/`
   338|
   339|#### C5. AI_Animation (无⭐)
   340|
   341|- **源码包:** `$PKG_DIR/mcp/AI_Animation.tar.gz`
   342|- **输出:** `mcpserver/agent_animation/` + `skills/animation/SKILL.md`
   343|- **改造要点:**
   344|  - AI_Animation 是一个完整项目，包含多个 Skill（dynamic-archify 等）和动画生成管线
   345|  - 拆两部分：
   346|    1. **MCP Agent:** 提供图表/动画生成 API
   347|    2. **Skill:** 工作流编排——接收描述 → 选模板 → 生成 → 导出
   348|  - invocationCommands:
   349|    1. `generate_diagram` — 生成架构/流程/时序图，参数 `type`(architecture/workflow/sequence/dataflow/lifecycle), `spec`(JSON 规格)
   350|    2. `export_diagram` — 导出图表，参数 `diagram_id`, `format`(png/jpeg/svg/gif/webm)
   351|    3. `list_templates` — 列出可用模板
   352|
   353|---
   354|
   355|### 🔵 组D：Skill 封装 — 5 个包
   356|
   357|这些不写代码，只需要通读源码后写 SKILL.md。
   358|
   359|#### D1. baoyu-skills (20MB)
   360|
   361|- **源码包:** `$PKG_DIR/skills/baoyu-skills.tar.gz`
   362|- **输出:** `skills/baoyu-comic/SKILL.md` `skills/baoyu-infographic/SKILL.md` `skills/baoyu-illustrator/SKILL.md` (按实际内容拆分)
   363|- **任务:** 解压 → 通读每个 Skill 的 README → 按 scratchpad SKILL.md 格式重写
   364|
   365|#### D2. AI-Animation-Skill (308KB)
   366|
   367|- **源码包:** `$PKG_DIR/skills/AI-Animation-Skill.tar.gz`
   368|- **输出:** `skills/animation/SKILL.md`（如果 C5 已创建则合并）
   369|- **任务:** 同上
   370|
   371|#### D3. crewAI (149MB 56k⭐)
   372|
   373|- **源码包:** `$PKG_DIR/fusion/crewAI.tar.gz`
   374|- **输出:** `references/crewai/`（不放 skills/）
   375|- **任务:** 读源码中 Agent 编排/任务分发/角色定义的核心逻辑 → 写 `references/crewai/ARCHITECTURE_NOTES.md`（≤3KB）
   376|- 不用写代码，这是架构参考
   377|
   378|#### D4. agent-memory (14MB 392⭐)
   379|
   380|- **源码包:** `$PKG_DIR/fusion/agent-memory.tar.gz`
   381|- **输出:** `references/agent-memory/`
   382|- **任务:** 读其图记忆引擎的实现 → 写 `references/agent-memory/MEMORY_PATTERNS.md`（≤3KB），对比 scratchpad 的 `summer_memory/`
   383|
   #### D5. dify (31MB 151k⭐) + Flowise (23MB 55k⭐) + mastra (54MB 26k⭐) + anything-llm (35MB 64k⭐)

   - **源码包:** `$PKG_DIR/fusion/dify.tar.gz`, `$PKG_DIR/fusion/Flowise.tar.gz`, `$PKG_DIR/fusion/mastra.tar.gz`, `$PKG_DIR/fusion/anything-llm.tar.gz`
   - **输出:** `references/dify/`, `references/flowise/`, `references/mastra/`, `references/anything-llm/`
   388|- **任务:** 各写一份 ≤3KB 的架构笔记，聚焦：
   389|  - dify: 可视化工作流编排器的 DSL 设计
   390|  - Flowise: 节点式 Agent 构建的交互范式
   391|  - mastra: TS Agent 框架的工具注册/工作流模式
   392|  - anything-llm: 本地优先的全栈架构
   393|- 不写代码，纯参考
   394|
   395|---
   396|
   ### ⚫ 组E：不改造 — 6 个包

   这些包直接放在对应位置，不改代码。

   | 包 | 源码路径 | 放置位置 | 说明 |
   |---|---|---|---|
   | `neko_src_v0.8.3` | `$PKG_DIR/coupled/neko_src_v0.8.3.tar.gz` | 已在 `scratchpad/NEKO/` | 桌面端主体，已集成 |
   | `Live2DPet` | `$PKG_DIR/coupled/Live2DPet.tar.gz` | `references/live2dpet/` | 备胎参考，解压即用 |
   | `emqx` | `$PKG_DIR/infra/emqx.tar.gz` | 不放入 scratchpad | MQTT Broker，独立部署 |
   | `EmbeddedMqttBroker` | `$PKG_DIR/infra/EmbeddedMqttBroker.tar.gz` | `references/esp32-mqtt/` | ESP32 固件，硬件参考 |
   | `LightRAG` | `$PKG_DIR/fusion/LightRAG.tar.gz` | `references/lightrag/` | 架构笔记 ≤3KB |
   | `graphiti` | `$PKG_DIR/fusion/graphiti.tar.gz` | `references/graphiti/` | 架构笔记 ≤3KB |
   408|
   409|---
   410|
   411|## 4. 完成检查清单
   412|
   413|每完成一个包，在下面打 ✅：
   414|
   415|### 组A（CLI 包装）
   416|- [x] A1 nuclei → `mcpserver/agent_nuclei/` ✅
   417|- [x] A2 trivy → `mcpserver/agent_trivy/` ✅
   418|- [x] A3 syft → `mcpserver/agent_sbom/` ✅
   419|- [x] A4 cosign → `mcpserver/agent_signing/` ✅
   420|- [x] A5 sherlock → `mcpserver/agent_osint/` ✅
   421|- [x] A6 jadx → `mcpserver/agent_decompile/` ✅
   422|
   423|### 组B（中等复杂度）
   424|- [x] B1 falco → `mcpserver/agent_runtime/` ✅
   425|- [x] B2 coraza → `mcpserver/agent_waf/` ✅
   426|- [x] B3 LLM4Decompile → `mcpserver/agent_llm_decompile/` ✅
   427|- [x] B4 pentagi → `mcpserver/agent_pentest/` + `skills/pentest-chain/SKILL.md` ✅
   428|- [x] B5 browser-use → `mcpserver/agent_browser/` ✅
   429|
   430|### 组C（高复杂度）
   431|- [x] C1 frida → `mcpserver/agent_frida/` ✅
   432|- [x] C2 strix → `mcpserver/agent_strix/` ✅
   433|- [x] C3 nanobrowser → 合并到 `mcpserver/agent_browser/` ✅
   434|- [x] C4 pentest-agents → `references/pentest-agents/` + 补充 `agent_pentest/` ✅
   435|- [x] C5 AI_Animation → `mcpserver/agent_animation/` + `skills/animation/SKILL.md` ✅
   436|
   437|### 组D（Skill 封装）
   438|- [x] D1 baoyu-skills → `skills/baoyu-*/` ✅
   439|- [x] D2 AI-Animation-Skill → `skills/animation/` ✅
   440|- [x] D3 crewAI → `references/crewai/` ✅
   441|- [x] D4 agent-memory → `references/agent-memory/` ✅
   442|- [x] D5 dify/flowise/mastra/anything-llm → `references/<name>/` ✅
   443|
   ### 组E（不改造）
   - [x] E1 确认 neko_src 已就位 → `$PKG_DIR/coupled/` ✅
   - [x] E2 Live2DPet 解压到 `references/live2dpet/` ✅
   - [x] E3 LightRAG 架构笔记 ✅
   - [x] E4 graphiti 架构笔记 ✅
   - [x] E5 emqx 跳过（不放入 scratchpad） ✅
   - [x] E6 EmbeddedMqttBroker → `references/esp32-mqtt/` ✅
   448|
   449|---
   450|
   451|## 5. 最后一步：验证
   452|
   453|全部完成后，运行：
   454|
   ```bash
   cd scratchpad
   python -c "from mcpserver.mcp_registry import auto_register_mcp; ms = auto_register_mcp(); print(f'Registered {len(ms)} MCP services: {ms}')"
   ```
   459|
   460|预期输出应包含所有组A/B/C的 MCP Agent 名称。
   461|