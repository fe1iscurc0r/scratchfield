# voice/ 目录只读代码审查报告

**审查范围**：`d:\my git\scratchpad\voice\` 下全部 24 个已提交 Python 源文件（tts_wrapper.py、output/、input/、input/voice_realtime/）  
**正面确认**：未发现硬编码 API key/token，未发现 os.system/shell=True/eval 类命令注入面

---

## Critical（必须修复）

无。

---

## High（强烈建议修复）

### H1. TTS HTTP 服务绑定 0.0.0.0 且默认关闭鉴权，存在空密钥绕过

**位置**：`voice/output/server.py` L53-L55、`voice/output/start_voice_service.py` L26、`voice/output/utils.py` L21-L36

**问题**：
- 服务以 `host='0.0.0.0'` 监听，暴露到局域网；而 `system/config.py` 中 `require_api_key` 默认 False、`api_key` 默认 `""`，即默认状态下局域网任何主机都可无鉴权调用 TTS（可被用于资源滥用/流量消耗）
- `require_api_key` 装饰器存在绕过缺陷：若启用鉴权但 api_key 仍为空串，请求头 `Authorization: Bearer` 解析出 `token == "" == API_KEY`，同样通过鉴权
- `token != API_KEY` 为非常量时间比较，理论上可被时序侧信道逐字节推断

**修复建议**：
- 默认绑定 127.0.0.1（确需对外再显式配置）
- 鉴权时校验 `if not API_KEY: 拒绝服务`
- 比较改用 `hmac.compare_digest(token, API_KEY)`

### H2. TTS 生成的临时音频文件全程无人清理，持续泄漏

**位置**：`voice/output/tts_handler.py` L75-L158、`voice/output/server.py` L41-L42

**问题**：`_generate_audio` 用 `NamedTemporaryFile(delete=False)` 生成 mp3/转码文件后直接把路径交给 FileResponse 返回，响应发送完毕后没有任何机制删除该文件——每次 TTS 请求都会永久残留一个临时音频文件，长期运行会撑满系统临时目录。

同样问题：`voice/tts_wrapper.py` L79/L87/L118/L151 生成的 `delete=False` 文件由 `apiserver/routes/chat.py` L1087-1095 消费后（经 `receive_audio_url` 本地路径分支）也未删除；`tts_wrapper._generate_audio_async` 中若 `communicator.save` 抛异常，L87 创建的空临时文件也会泄漏。

**修复建议**：使用 FastAPI BackgroundTask 在响应完成后删除文件：

```python
from starlette.background import BackgroundTask
import os
return FileResponse(output_file_path, media_type=mime_type,
                    background=BackgroundTask(os.unlink, output_file_path))
```

tts_wrapper 侧由调用方播放完成后删除，或在 `voice_integration._play_audio_from_url` 中对本地路径也执行清理。

### H3. 使用已废弃且不安全的 tempfile.mktemp

**位置**：`voice/output/voice_integration.py` L297、`voice/output/voice_integration.py` L523

**问题**：`mktemp` 只生成文件名不创建文件，存在 TOCTOU 竞争（官方文档明确警告安全隐患）；且 L297 创建的播放临时文件仅在正常路径末尾删除（L438-443），一旦 `pygame.mixer.music.load`/播放过程抛异常（L445 except 分支），临时文件永远不会泄漏。

**修复建议**：

```python
with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as tf:
    tf.write(audio_data)
    temp_file = tf.name
try:
    ...  # 播放
finally:
    os.unlink(temp_file) if os.path.exists(temp_file) else None
```

---

## Medium（应当修复）

### M1. set_callbacks(None) 无法清除回调，stop_voice 的"清回调"意图失效

**位置**：`voice/input/voice_realtime/core/base_client.py` L65-L74、`voice/input/voice_thread_safe_simple.py` L99-L106

**问题**：基类用 `if on_user_text:` 真值判断，传 None 时不会把回调置空。`stop_voice` 注释写明"先清除所有回调，防止断开时触发状态回调"，但实际上回调一个都没被清除；断开过程中底层客户端仍可能触发 on_status/on_error 回调到已停止的 UI 层，造成状态错乱或异常。

**修复建议**：基类改为显式判空语义（传参即覆盖）：

```python
if on_user_text is not None:
    self.on_user_text_callback = on_user_text
```

或为 stop 场景提供独立的 `clear_callbacks()` 方法。

### M2. QwenVoiceClientRefactored.update_config 调用不存在的方法，必抛 AttributeError

**位置**：`voice/input/voice_realtime/adapters/qwen/client.py` L760-L763

**问题**：`self.audio_manager.set_vad_threshold(...)` 与 `set_echo_suppression(...)` 在 AudioManager 中均不存在（已全目录检索确认），只要 `update_config` 携带 `vad_threshold`/`echo_suppression` 键即抛 AttributeError。

**修复建议**：在 AudioManager 中补上这两个 setter（直接赋值 `self.vad_threshold` / `self.echo_suppression`），或在此处改为直接属性赋值并加 hasattr 防护。

### M3. interrupt_playback 的完成标志被立即清掉，打断逻辑自相矛盾

**位置**：`voice/input/voice_realtime/core/audio_manager.py` L720-L730

**问题**：L728 设置 `self.ai_response_done = True`，紧接着 L730 `clear_output_buffer()` 在 L712 又把它重置为 False。播放线程 `_output_player_loop` 依赖 `ai_response_done` 判断"AI 已完成可结束播放"，此标志被清掉后打断后的收尾判断失效，可能导致 was_playing 状态残留、需等待 30 次空队列的强制超时才结束。

**修复建议**：调整顺序——先 `clear_output_buffer()` 再设置 `self.ai_response_done = True`，或给 `clear_output_buffer` 增加不重置标志的参数。

### M4. _play_audio_from_url 下载无超时且不校验响应状态

**位置**：`voice/output/voice_integration.py` L519-L526

**问题**：`requests.get(audio_url)` 无 timeout，远端无响应时播放工作线程永久阻塞（该线程是唯一消费 audio_queue 的线程，阻塞后整条 TTS 管线随之卡死）；且未检查 `resp.status_code`，404/500 时错误页面 HTML 会被当作音频写入文件再交给 pygame 解码失败。

**修复建议**：

```python
resp = requests.get(audio_url, timeout=15)
resp.raise_for_status()
```

### M5. ffmpeg 子进程无超时，可能在异步事件循环中永久挂起

**位置**：`voice/output/tts_handler.py` L140

**问题**：`subprocess.run(ffmpeg_command, ...)` 无 timeout 参数。该函数经 server.py 的 async 端点直接 await，若 ffmpeg 因损坏输入挂起，将永久占用事件循环线程，整个 TTS 服务不可用。

**修复建议**：加 `timeout=60`（或可配置），并在 except 分支处理 `subprocess.TimeoutExpired`（含 kill 子进程）。

### M6. 本地模式健康检查与适配器地址三处互不一致

**位置**：`voice/input/unified_voice_manager.py` L66-L69、`voice/input/voice_realtime/adapters/local.py` L120

**问题**：与后端接口一致性问题。三处各自为政：
- `detect_available_modes` 用 `config.voice_realtime.asr_host` + `config.asr.port`（混用两个配置节；voice_realtime 自己有 `asr_port=5000` 字段却没用上）
- `LocalVoiceClientAdapter._init_openai_client` 硬编码 `http://127.0.0.1:5001/v1`，完全不读配置

健康探测结果与实际连接地址不一致，会出现"探测可用但连接失败/探测不可用但服务其实在跑"的误判。

**修复建议**：统一读取 `config.voice_realtime.asr_host` / `config.voice_realtime.asr_port`，适配器 base_url 由构造参数传入。

---

## Low（可考虑修复）

| # | 位置 | 问题 |
|---|------|------|
| L1 | `voice/tts_wrapper.py` L148-L154 | 静音回退文件为 0 字节，下游解码必然失败。`_create_silent_file` 只创建空文件，pygame 加载 0 字节 mp3 会抛异常；`_speed_to_rate` 允许 speed=0，产出 -100% 的边界 rate。建议写入一段真实静音音频，并钳 speed 下限到 0.25。 |
| L2 | `voice/output/handle_text.py` L50 | 文本清洗正则误删普通下划线。`re.sub(r"(\*\*|__|\*|_)", '', text)` 未限定词边界，会把正文中所有 `_` 删掉（如 snake_case、文件路径）。建议仅处理成对的 Markdown 强调标记。 |
| L3 | `voice/input/voice_realtime/adapters/local.py` L231-L324 | 本地适配器音频缓冲跨线程读写无同步。`_audio_buffer` 由音频回调线程 append、转录线程 `b''.join` 后 `clear()`，无锁交换；转录期间新到达的语音块会被一并清空（丢字），且 `len(audio_data) < 1000` 提前返回时不清空缓冲，旧数据会混入下一句。建议在启动转录前原子性地把缓冲"取出并置空"。 |
| L4 | `voice/tts_wrapper.py` L168-L173、`voice/output/voice_integration.py` L620-L624 | 全局单例无锁竞争。`get_tts_wrapper()` / `get_voice_integration()` 的 check-then-set 无锁，多线程并发首调可能创建两个实例。建议加 `threading.Lock` 双检锁。 |
| L5 | `voice/output/server.py` L43-L51 | 服务器错误日志文件无轮转、无界增长。每次异常以 `'a'` 模式追加完整 traceback 到 `voice_server_error.log`，长期运行文件无限增长。建议接入 logging 的 RotatingFileHandler 或限制大小。 |

---

## 总体质量结论

该模块功能完整、分层清晰（工厂/适配器/状态机/音频管理器），异常包裹充分，未发现硬编码密钥与命令注入这类红线问题。

**主要短板集中在**：
- **资源生命周期管理**（TTS 临时文件全链路无人清理、mktemp 使用）
- **安全默认值**（0.0.0.0 绑定 + 默认免鉴权）
- **并发回调/状态标志细节缺陷**（set_callbacks(None) 失效、ai_response_done 被误清、ffmpeg 无超时）

建议优先处理 H 级三项与 M1/M3，即可显著提升长期运行稳定性与安全性。

---

*报告生成时间：2026-08-11 | 审查模式：只读*
