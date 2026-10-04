"""
Task1 Step1: 启动 Persistent Edge，检测 dom_probe_ready.flag 后自动抓 DOM
=========================================================================

【这个脚本在测什么 / 做什么】
    这是一个 DOM 侦察工具，不是断言型测试。它的作用：
      1) 启动 persistent Edge 并打开 MatChat；
      2) 等用户手动登录（通过 flag 文件触发）；
      3) 登录后自动扫描页面 DOM，把"候选输入框 / 候选发送按钮 / 候选 AI 消息容器"
         全部打印出来，并把整页 HTML dump 到 matchat_dom_dump.html。
    用途：当 matchat_bridge.py 的选择器失效（MatChat 改版）时，跑这个脚本重新找
          正确的 selector，再回去更新 matchat_bridge.py 顶部的常量。

【DOM 抓取流程（4 步）】
      ① 候选输入框：遍历 textarea / input(文本类) / contenteditable，打印 id/class/placeholder/尺寸
      ② 候选发送按钮：遍历 button/[role=button]，筛含"发送/Send"文案、含 svg、或尺寸像按钮的
      ③ 候选 AI 消息容器：遍历带 class 的元素，class 含 message/assistant/bubble/answer 等关键字
      ④ 完整 HTML dump：保存 body.outerHTML 到 matchat_dom_dump.html 供离线分析

【怎么判断"跑通了"】
    三个候选列表都打印出条目（尤其能看到 textarea#ai-input、发送按钮、#chat-scroll-container），
    且 matchat_dom_dump.html 生成成功。

【失败怎么办】
    - 浏览器启动失败：playwright/Edge 未装，或 user_data_dir 被占用（关残留 Edge）
    - 一直等不到 flag：见 FLAG_FILE 注释——必须用脚本打印的绝对路径建 flag
    - 抓取列表全空：页面未登录或还在 loading，确认聊天界面完整渲染后再建 flag
    - HTML dump 失败：页面跨域或 body 未就绪，重跑一次

【运行方式】
    cd d:\\my git\\scratchpad
    .\\.venv\\Scripts\\activate
    python dom_probe.py
    # 在弹出的 Edge 里登录 MatChat、看到聊天界面后，执行（注意用绝对路径）：
    #   PowerShell: New-Item 'd:\\my git\\scratchpad\\dom_probe_ready.flag'
"""
import os
import sys
import time

sys.path.insert(0, ".")

from mcpserver.material_science.matchat_bridge import MatchatBridge

# FLAG_FILE 用"脚本所在目录 + dom_probe_ready.flag"的绝对路径
# 这样无论从哪个 CWD 启动脚本，检测的都是同一个位置。
# 修复说明：原提示让用户用相对路径 `New-Item dom_probe_ready.flag` 建 flag，
#           若用户 CWD ≠ 脚本目录，flag 会建到别处，脚本永远检测不到。
#           现在统一用下面的绝对路径（见打印的提示命令）。
FLAG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dom_probe_ready.flag")
# 启动前先清掉上次的残留 flag，避免脚本一启动就误触发
if os.path.exists(FLAG_FILE):
    os.remove(FLAG_FILE)

# 构造 Bridge：默认 persistent + headless=False（要用户手动登录，必须可见）
b = MatchatBridge(headless=False)

# ── 连接浏览器 ────────────────────────────────────────────────────────
# 【在测什么】能否拉起持久化 Edge 并初始化 page
# 【怎么算通过】connect 返回 True，is_connected 返回 True
# 【失败怎么办】playwright/Edge 未装，或残留 Edge 占用 user_data_dir
ok = b.connect()
print(f"[连接状态] connect={ok}, is_connected={b.is_connected()}")
if not ok:
    print("❌ 浏览器启动失败，退出")
    sys.exit(1)

print(f"[当前页面] {b._page.url if b._page else 'None'}")
print()
print("=" * 70)
print("👉 Edge 浏览器已打开，MatChat 页面已加载")
print("   请在浏览器中完成登录，直到能看到聊天界面")
# 注意：这里必须打印 FLAG_FILE 的绝对路径，否则用户建错位置就触发不了
print("   登录完成后，创建 flag 文件触发 DOM 抓取：")
print(f"     PowerShell: New-Item '{FLAG_FILE}'")
print(f"     CMD:        type nul > \"{FLAG_FILE}\"")
print("   脚本检测到 flag 文件后将自动抓取 DOM 结构")
print("=" * 70)

# ── 轮询 flag 文件 ────────────────────────────────────────────────────
# 最多等 30 分钟，每 3s 检查一次；每 30s 打印一次进度
waited = 0
while waited < 1800:  # 最多等 30 分钟
    if os.path.exists(FLAG_FILE):
        print("\n✅ 检测到 dom_probe_ready.flag，开始抓取 DOM...")
        break
    time.sleep(3)
    waited += 3
    if waited % 30 == 0:
        print(f"   等待用户登录... ({waited//60} 分钟 {waited%60} 秒)")
else:
    # 超时：flag 一直没建，退出码 2 便于脚本化区分
    print("⏱️  等待超时，未检测到 dom_probe_ready.flag")
    sys.exit(2)

# ──────────────────────────────────────────────────────────────────────
# 下面是 DOM 抓取主体，全部用 page.evaluate 在浏览器内执行 JS 收集信息
# 设计原则：不依赖 matchat_bridge.py 的常量选择器（那正是要被验证/更新的），
#           而是广撒网扫描所有可能的候选元素。
# ──────────────────────────────────────────────────────────────────────
print()
print("[抓取 DOM 结构中...]")

# ════════════════════════════════════════════════════════════════════
# ① 候选输入框 (textarea / input / contenteditable)
# 【作用】定位"用户输入消息"的元素，对应 matchat_bridge.py 的 CHAT_INPUT_SELECTOR
# 【筛选逻辑】
#   - textarea：最常见，MatChat 实际用的就是 textarea#ai-input
#   - input：只看 text/search/url/email 类型（button/hidden 等不算）
#   - contenteditable：富文本编辑器兜底
# 【每条记录字段】type / idx / id / className / placeholder / tag / rect / visible
# ════════════════════════════════════════════════════════════════════
print("\n" + "=" * 50)
print("🔍 候选输入框 (textarea / input / contenteditable)")
print("=" * 50)
input_info = b._page.evaluate("""() => {
    const result = [];
    document.querySelectorAll('textarea').forEach((el, i) => {
        result.push({type:'textarea', idx:i, id:el.id, className:el.className,
            placeholder:el.placeholder, tag:el.tagName,
            rect:el.getBoundingClientRect().width+'x'+el.getBoundingClientRect().height,
            visible: el.offsetParent !== null});
    });
    document.querySelectorAll('input').forEach((el, i) => {
        if(['text','search','url','email'].includes(el.type)||!el.type){
        result.push({type:'input-'+el.type, idx:i, id:el.id, className:el.className,
            placeholder:el.placeholder, tag:el.tagName,
            rect:el.getBoundingClientRect().width+'x'+el.getBoundingClientRect().height,
            visible: el.offsetParent !== null});
        }
    });
    document.querySelectorAll('[contenteditable="true"],[contenteditable="plaintext-only"]').forEach((el, i) => {
        result.push({type:'contenteditable', idx:i, id:el.id, className:el.className,
            placeholder:el.getAttribute('placeholder')||'', tag:el.tagName,
            role:el.getAttribute('role')||'',
            rect:el.getBoundingClientRect().width+'x'+el.getBoundingClientRect().height,
            visible: el.offsetParent !== null,
            innerText: (el.innerText||'').slice(0,60)});
    });
    return result;
}""")
# 只打印可见的候选，避免被 display:none 的干扰
for item in input_info:
    if item.get('visible'):
        print(f"  [{item['type']}] idx={item['idx']} id={item['id']!r} class={str(item['className'])[:60]!r} ph={item['placeholder'][:40]!r} rect={item['rect']}")

# ════════════════════════════════════════════════════════════════════
# ② 候选发送按钮 (button/[role=button]，带 SVG 或 '发送' 文案)
# 【作用】定位"点一下发送消息"的按钮，对应 SEND_BUTTON_SELECTOR / SEND_BUTTON_FALLBACK
# 【筛选逻辑】保留满足任一条件的按钮：
#   - 文案含"发送"或"Send"
#   - 内含 <svg>（图标按钮）
#   - 宽度在 20~200px 之间（像按钮的尺寸）
# 【每条记录字段】idx / id / className / tag / text / hasSvg / rect / visible
# ════════════════════════════════════════════════════════════════════
print("\n" + "=" * 50)
print("🔍 候选发送按钮 (button/[role=button]，带 SVG 或 '发送' 文案)")
print("=" * 50)
btn_info = b._page.evaluate("""() => {
    const result = [];
    document.querySelectorAll('button, [role=button]').forEach((el, i) => {
        const txt = (el.innerText || '').trim();
        const hasSvg = el.querySelector('svg') !== null;
        const w = el.getBoundingClientRect().width;
        if (txt.includes('发送')||txt.includes('Send')||hasSvg||(w>20&&w<200)) {
            result.push({idx:i, id:el.id, className:el.className, tag:el.tagName,
                text:txt.slice(0,40), hasSvg:hasSvg,
                rect:w+'x'+el.getBoundingClientRect().height,
                visible: el.offsetParent !== null});
        }
    });
    return result;
}""")
for item in btn_info:
    if item.get('visible'):
        print(f"  idx={item['idx']} id={item['id']!r} class={str(item['className'])[:60]!r} text={item['text']!r} svg={item['hasSvg']} rect={item['rect']}")

# ════════════════════════════════════════════════════════════════════
# ③ 候选 AI 消息容器 (带 message/assistant/chat/bubble/answer 关键字)
# 【作用】定位"AI 回复渲染在哪"，对应 MESSAGES_CONTAINER / RESPONSE_SELECTOR
# 【筛选逻辑】遍历所有带 class 的元素，class（小写）含以下任一关键字：
#   message / assistant / chat-message / ai-message / bubble / answer / response / reply
#   且：有子元素 或 innerText 长度 > 30（排除空壳）
# 【去重】按 "class+前20字样本" 去重；高度 < 20px 的跳过（不可见/占位）
# 【限制】最多返回 25 条，避免输出爆炸
# ════════════════════════════════════════════════════════════════════
print("\n" + "=" * 50)
print("🔍 候选 AI 消息容器 (带 message/assistant/chat/bubble/answer 关键字)")
print("=" * 50)
msg_info = b._page.evaluate("""() => {
    const result = [];
    const seen = new Set();
    document.querySelectorAll('[class]').forEach((el) => {
        const cls = (el.className && typeof el.className === 'string') ? el.className : '';
        if (!cls) return;
        const cl = cls.toLowerCase();
        if ((cl.includes('message')||cl.includes('assistant')||cl.includes('chat-message')
            ||cl.includes('ai-message')||cl.includes('bubble')||cl.includes('answer')
            ||cl.includes('response')||cl.includes('reply')) && (el.children.length>0 || (el.innerText||'').length>30)) {
            const sample = (el.innerText || '').slice(0, 80);
            const h = el.getBoundingClientRect().height;
            const w = el.getBoundingClientRect().width;
            const key = cls + '|' + sample.slice(0,20);
            if (seen.has(key) || h < 20) return;
            seen.add(key);
            result.push({tag:el.tagName, className:cls, height:h, width:w,
                innerTextSample:sample, childCount:el.children.length});
        }
    });
    return result.slice(0, 25);
}""")
for i, item in enumerate(msg_info):
    print(f"  [{i}] {item['tag']}.{str(item['className'])[:80]} {item['width']}x{item['height']}px children={item['childCount']} sample={item['innerTextSample'][:50]!r}")

# ════════════════════════════════════════════════════════════════════
# ④ 完整 HTML dump
# 【作用】把 body.outerHTML 存到 matchat_dom_dump.html，供离线 Ctrl+F 搜选择器
# 【怎么算通过】文件生成且字符数 > 0
# 【失败怎么办】页面跨域/body 未就绪，重跑；或直接在浏览器 F12 复制
# ════════════════════════════════════════════════════════════════════
print("\n" + "=" * 50)
print("📋 HTML dump 已保存到 matchat_dom_dump.html")
print("=" * 50)
try:
    html = b._page.evaluate("document.body.outerHTML")
    if isinstance(html, str):
        # 写到当前工作目录（CWD）下的 matchat_dom_dump.html
        with open("matchat_dom_dump.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  已保存 {len(html)} 字符")
except Exception as e:
    print(f"  HTML dump 失败: {e}")

# 清除 flag：抓取完成后再删，避免下次启动误触发
try:
    os.remove(FLAG_FILE)
except Exception:
    pass

print("\n✅ DOM 抓取完成！")
print("   浏览器保持打开 30 秒供你参考，然后自动关闭。")
time.sleep(30)
# disconnect 会关闭持久化 context；用 disconnect()（类无 close() 方法）
b.disconnect()
print("   浏览器已关闭。")
