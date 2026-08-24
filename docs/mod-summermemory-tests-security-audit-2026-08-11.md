# mod/ · summer_memory/ · tests/ 代码审查报告

**审查范围**：`d:\my git\scratchpad\` 下 mod/、summer_memory/、tests/ 三个目录全部已提交代码

---

## 安全基线结论（先说好消息）

| 检查项 | 结论 |
|--------|------|
| 硬编码密钥/token | ✅ 全量 grep（sk-、token、password、api_key 等模式）无匹配；docker-compose.yml 使用 `${NEO4J_AUTH}` 环境变量占位 |
| 命令注入 | ✅ 所有子进程调用均为 `asyncio.create_subprocess_exec` 列表参数形式，无 shell=True/os.system 拼接用户输入（唯一 os.system 在 summer_memory/main.py L55-57，参数为固定字符串 "docker compose version"） |
| 不安全反序列化 | ✅ 未发现 pickle/marshal；未发现无 Loader 的 yaml.load |
| Cypher 防注入 | ✅ `quintuple_graph.py` 全部参数化查询（$kw 占位符） |

**无 Critical 级问题。**

---

## High（5 项）

### H1. agent_pentest 模块级入口对 JSON 二次编码，破坏 handoff 契约

**位置**：`agent_pentest.py` L901-L910

**问题**：类内 `PentestAgent.handle_handoff` 已返回 `json.dumps(result)` 字符串；模块级 `handle_handoff` 又对其执行一次 json.dumps，返回双重编码字符串（`'"{\\"status\\": ..."'`）。调用方按 registry 约定 `json.loads` 一次后得到的是字符串而非 dict，下游 `result["status"]` 全部失败。这是 MCP registry 的真实入口路径。

**修复**：模块级函数直接 `return await agent.handle_handoff(task)`，不再二次编码。

### H2. summer_memory/main.py 导入即注册 atexit，任何进程退出都会停 Neo4j 容器

**位置**：`main.py` L97

**问题**：模块顶层 `atexit.register(stop_neo4j_container)`——任何仅 import 该模块的进程（测试、脚本、被其他服务复用）退出时都会 `docker compose down`，可能误杀他人正在用的 Neo4j 容器，CI 中尤其难排查。

**修复**：移入 `if __name__ == "__main__":` 块，或改为显式 `setup()`/`teardown()`。

### H3. TaskManager 构造参数被默认值覆盖，配置调优静默失效

**位置**：`task_manager.py` L57-L58

```python
self.max_workers = max_workers or config.grag.max_workers      # 默认 3 恒 truthy → config 永不生效
self.max_queue_size = max_queue_size or config.grag.max_queue_size  # 恒为 100
```

**修复**：默认值改 None，用 `is not None` 判断。

### H4. test_rag_fixes.py 的"嵌入失败 fail-fast"测试是恒真假测试

**位置**：`test_rag_fixes.py` L82-L117

**问题**：测试内部手工复现了 rag_service 的判断逻辑再断言自己写的结果——RAGService.add_documents 的真实代码从未被调用。即使生产代码的 fail-fast 修复被删除或回归，此测试仍永远通过。

**修复**：mock `_embedding_engine.encode` 返回 None，真调 `add_documents` 断言返回值。

### H5. test_rag_vault_integration.py 恒真断言 + "测试标准库"假测试

**位置**：`test_rag_vault_integration.py` L156-L168

**问题**：
- L160：`assertTrue(hasattr(VecDBClient, '_read_lock') or True)`——`or True` 恒过
- L162-168：实际测的是标准库 `threading.Lock()` 有 acquire/release 属性，与被测代码毫无关系

这两个测试名义上验证"线程安全修复点"，实际零覆盖。

---

## Medium（7 项）

| # | 位置 | 问题 |
|---|------|------|
| M1 | `agent_frida.py` L427-L434 | `_detach_all` 语义倒置：`detached_count = len(errors)`——出错时上报错误数，全成功时恒为 0 |
| M2 | `agent_decompile` / `agent_nuclei` | proc 创建阶段超时时未绑定，except 里 `proc.kill()` 抛 NameError 掩盖真实超时 |
| M3 | `memory_client.py` L126 | ① `entity_name` 未 URL 编码直接拼路径（含 `../`、`?` 可操纵请求路径）；② token 变更/登出时 `_client = None` 不 `aclose()`，连接池泄漏 |
| M4 | `task_manager.py` L270 附近 | 被取消的 PENDING 任务 future 永不置位，`get_task_result` 无 timeout 时永久挂起 |
| M5 | `agent_strix.py` L403-L404 | `cmd.extend(extra.split())` 把用户参数原样拼入 hydra argv——无 shell 注入但可注入任意 hydra 选项（如 `-o` 覆盖输出路径） |
| M6 | `test_mcp_adapters.py` L305-L350 | graceful-error 测试手工定义 memclaw_list 副本自测，真实闭包从未被调用（同 H4 假测试模式） |
| M7 | `test_rag_vault_integration.py` 多处 | 大量 `inspect.getsource` + 子串断言（如 `assertIn("2000", source)`），只查源码文本不验证行为，重构即碎、失效不红 |

---

## Low（6 项）

| # | 位置 | 问题 |
|---|------|------|
| L1 | `agent_runtime` / `agent_llm_decompile` | 健康检查一旦置 False 永久缓存不重试，服务恢复也不自愈 |
| L2 | `agent_runtime` L171 / `agent_waf` L252 | 固定 `/tmp/_*.yaml` 临时文件路径，并发竞态/TOCTOU，应改 mkstemp |
| L3 | `agent_llm_decompile` L343 | ELF 头恒按小端解析，未处理 `header[5]==2` 大端情况 |
| L4 | `agent_animation` L50 | 模块级 dict 无上限缓存 PNG（内存泄漏）；用户 label 未转义直接拼 DOT（轻度 DOT 注入） |
| L5 | `quintuple_extractor` L182-220/L363-401 | 重试循环 off-by-one：最后一次尝试实际到不了回退分支 |
| L6 | `test_rag_fixes` L126-149 / `test_mcp_adapters` L58-88 | 弱断言测试（循环体 pass 只断言非空；`assertIsInstance(result, bool)` True/False 皆过） |

---

## 接口一致性核对

| 检查项 | 结论 |
|--------|------|
| `test_config_and_tools.py` | ✅ 经 `httpx.ASGITransport` 真调两个 FastAPI app，与 apiserver/agentserver 接口高度一致（**该目录质量最高的部分**） |
| `test_mcp_adapters.py` 跨源冲突/路径逃逸测试 | ✅ 为真实 API 调用（M6 一处例外） |
| mod/ 14 个 agent 返回契约 | ✅ 均遵循 `{"status/message/data"}` 契约（H1 为唯一破坏者） |
| apiserver 对 summer_memory 的依赖 | ✅ 无直接依赖，H2 的 atexit 副作用目前是潜在而非已发生 |

---

## 各目录结论

- **mod/**：安全基线扎实，1 处接口契约破坏（H1）+ 若干返回值语义瑕疵，修 H1/M1/M2 后可达良好
- **summer_memory/**：图存储实现规范，但导入副作用（H2）、配置失效（H3）是三个目录中工程隐患最多的
- **tests/**：两极分化——`test_config_and_tools.py` 等 6 个文件断言扎实；`test_rag_fixes.py`/`test_rag_vault_integration.py` 含恒真假测试，关键修复点存在虚假覆盖，建议优先清除 H4/H5/M6

---

*报告生成时间：2026-08-11 | 审查模式：只读*
