"""
MatChat Bridge — Playwright 双模式桥接层

架构：
  模式 A (persistent, 默认): launch_persistent_context 自管理浏览器，
  用户首次登录后 session 持久化，MCP 工具通过此浏览器自动调用。
  模式 B (cdp, 可选): connect_over_cdp 接入外部 Chrome/Edge，
  保留向后兼容，适合极少数场景。

与 BrowserView 内嵌流程完全解耦：
  - Bridge.py 专注 AI Agent 自动化调用 (MCP 工具链)
  - BrowserView 流程 (手动问答 → 入库) 由 Electron 侧 matchat.ts 处理

架构：实验田维护者 | 决策：杜赞 | 实现：fe1iscurc0r (Trae)
"""
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Playwright 延迟导入——仅在首次使用时加载，避免无浏览器环境崩
# 使用 .start() 获取 Playwright 实例 (非上下文管理器模式，便于跨方法持久化)
_playwright_instance = None
# 全局锁：保护 _playwright_instance 的创建/销毁，防止多线程并发初始化出多个实例
_playwright_lock = threading.Lock()


def _get_playwright():
    """获取（必要时创建）全局 Playwright 实例。

    为什么要加锁：Playwright sync_api 实例绑定创建它的线程，
    且 sync_playwright().start() 重复调用会报错。用锁保证只初始化一次。
    真正的"同线程使用"保证由 materialscience_agent.py 的单线程池完成。
    """
    global _playwright_instance
    # 双检锁：先读后锁，命中则免去加锁开销
    if _playwright_instance is None:
        with _playwright_lock:
            if _playwright_instance is None:
                from playwright.sync_api import sync_playwright
                _playwright_instance = sync_playwright().start()
    return _playwright_instance


def _stop_playwright():
    """停止全局 Playwright 实例（供模块卸载/测试清理用）。"""
    global _playwright_instance
    with _playwright_lock:
        if _playwright_instance:
            try:
                _playwright_instance.stop()
            except Exception:
                # 已停止或异常时静默忽略，避免清理流程中断
                pass
            _playwright_instance = None


class MatchatBridge:
    """MatChat 操控层 — 双模式 (persistent / cdp)

    用法:
        # 默认 persistent 模式 (推荐)
        bridge = MatchatBridge()
        bridge.connect()
        result = bridge.search_literature("木质素碳化温度")

        # CDP 模式 (向后兼容)
        bridge = MatchatBridge(mode="cdp", cdp_url="http://localhost:9222")
        bridge.connect()

    线程安全说明:
        本类用 self._lock 串行化浏览器操作，防止并发调用导致 Playwright 状态错乱。
        但 Playwright sync_api 对象绑定创建线程，跨线程使用仍会报错，
        因此调用方（agent 层）应保证所有调用来自同一线程（见 materialscience_agent 单线程池）。
    """

    MATCHAT_URL = "https://ai.matchat.cn"
    # 登录态判定：URL 中出现这些片段即认为跳到了登录页
    LOGIN_URL_PATTERNS = ["login", "passport", "account", "auth"]
    # — 2026-07-30 dom_probe.py 实抓校验：输入框、发送按钮、滚动容器三要素 —
    # 输入框：页面唯一 textarea id="ai-input"
    CHAT_INPUT_SELECTOR = "textarea#ai-input"
    # 发送按钮：带唯一 data-tooltip-id="send-btn-tooltip"；内嵌 <img alt="发送">
    SEND_BUTTON_SELECTOR = "button[data-tooltip-id='send-btn-tooltip']"
    # 发送按钮兜底：当 data-tooltip-id 标识变化时匹配内含发送图标的深色按钮
    SEND_BUTTON_FALLBACK = "button:has(img[alt='发送'])"
    # 聊天流滚动容器：聊天记录在 #chat-scroll-container 中渲染
    MESSAGES_CONTAINER = "#chat-scroll-container"
    # AI 回复提取兜底：滚动容器内最后一个渲染出的文本子块（高度>50）
    RESPONSE_SELECTOR = MESSAGES_CONTAINER
    AI_MESSAGE_FALLBACK_SELECTOR = "#chat-scroll-container > div > div:last-child"

    DEFAULT_USER_DATA_DIR = str(
        Path.home() / ".naga" / "matchat_browser_data"
    )

    def __init__(
        self,
        mode: str = "persistent",
        cdp_url: str = "http://localhost:9222",
        user_data_dir: str | None = None,
        timeout: int = 60000,
        headless: bool = False,
    ):
        """初始化桥接层

        Args:
            mode: "persistent" (默认, 自管理持久化浏览器) 或 "cdp" (连接外部浏览器)
            cdp_url: CDP 模式下的调试端口 URL
            user_data_dir: persistent 模式下的浏览器用户数据目录 (默认 ~/.naga/matchat_browser_data)
            timeout: 页面操作超时 (ms)
            headless: persistent 模式下是否无头 (默认 False, 便于用户登录)
        """
        if mode not in ("persistent", "cdp"):
            raise ValueError(f"未知 mode: {mode}, 支持 'persistent' / 'cdp'")

        self.mode = mode
        self.cdp_url = cdp_url
        self.user_data_dir = user_data_dir or self.DEFAULT_USER_DATA_DIR
        self.timeout = timeout
        self.headless = headless

        # 浏览器资源
        self._browser = None   # persistent: BrowserContext; cdp: Browser
        self._page = None
        self._pw = None
        self._connected = False
        # 操作锁：串行化对浏览器/page 的访问，避免并发 send_message 互相干扰
        self._lock = threading.Lock()

    # ── 生命周期 ──────────────────────────────────

    def connect(self) -> bool:
        """连接浏览器。失败返回 False, 不抛异常（便于上层降级处理）。"""
        with self._lock:
            try:
                if self.mode == "persistent":
                    return self._connect_persistent()
                else:
                    return self._connect_cdp()
            except Exception as e:
                logger.error(f"[MatchatBridge] connect() 异常: {e}")
                return False

    def _connect_persistent(self) -> bool:
        """persistent 模式: 启动自管理的持久化浏览器。

        用 launch_persistent_context 复用 user_data_dir，登录态/cookie 跨进程保留，
        避免每次都让用户重新登录。
        """
        try:
            os.makedirs(self.user_data_dir, exist_ok=True)
            self._pw = _get_playwright()

            self._browser = self._pw.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                channel="msedge",
                viewport={"width": 1280, "height": 800},
                args=[
                    # 隐藏自动化特征，降低被站点风控识别概率
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )

            # 尝试定位已有 MatChat 页面, 没有则新开
            pages = self._browser.pages
            for p in pages:
                if "matchat.cn" in p.url:
                    self._page = p
                    logger.info(f"[MatchatBridge] persistent: 复用已有页面 {p.url[:80]}")
                    self._connected = True
                    return True

            self._page = self._browser.new_page()
            self._page.goto(self.MATCHAT_URL, wait_until="domcontentloaded", timeout=self.timeout)
            logger.info(f"[MatchatBridge] persistent: 新开页面 {self.MATCHAT_URL}")
            self._connected = True
            return True

        except Exception as e:
            logger.error(f"[MatchatBridge] persistent 启动失败: {e}")
            self._cleanup_pw()
            return False

    def _connect_cdp(self) -> bool:
        """cdp 模式: 连接外部 Chrome/Edge 浏览器。

        要求外部浏览器以 --remote-debugging-port=9222 启动。
        适合用户已有浏览器实例、希望人工+自动化共用的场景。
        """
        try:
            self._pw = _get_playwright()
            self._browser = self._pw.chromium.connect_over_cdp(self.cdp_url)

            # 找已有 MatChat 标签页
            for context in self._browser.contexts:
                for page in context.pages:
                    if "matchat.cn" in page.url:
                        self._page = page
                        logger.info(f"[MatchatBridge] cdp: 复用已有页面 {page.url[:80]}")
                        self._connected = True
                        return True

            # 新开
            if self._browser.contexts:
                self._page = self._browser.contexts[0].new_page()
                self._page.goto(self.MATCHAT_URL, wait_until="domcontentloaded", timeout=self.timeout)
                logger.info(f"[MatchatBridge] cdp: 新开页面 {self.MATCHAT_URL}")
                self._connected = True
                return True

            logger.error("[MatchatBridge] cdp: 浏览器无可用 context")
            return False

        except Exception as e:
            logger.error(f"[MatchatBridge] cdp 连接失败: {e}")
            self._cleanup_pw()
            return False

    def disconnect(self):
        """断开连接。幂等（可重复调用，不会抛异常）。"""
        with self._lock:
            try:
                if self._browser:
                    self._browser.close()
            except Exception:
                # 关闭异常不应阻断后续清理
                pass
            self._browser = None
            self._page = None
            self._connected = False
            self._cleanup_pw()

    def _cleanup_pw(self):
        """清理 Playwright 资源。

        修复点：原实现只 stop Playwright 但未重置 self._browser，
        导致连接失败后 _browser 仍指向已失效对象。这里一并置空。
        """
        global _playwright_instance
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass
        self._pw = None
        self._browser = None  # 修复：同步置空，避免悬挂引用
        _playwright_instance = None

    def _ensure_page(self) -> bool:
        """定位 MatChat 页面。没有则新开。返回是否成功。

        修复点：原实现直接访问 self._page.url，若页面已被用户关闭会抛异常。
        这里用 try/except 兜底并清空 _page，触发后续重新开页。
        """
        try:
            if self._page and "matchat.cn" in (self._page.url or ""):
                return True
        except Exception:
            # 页面可能已被关闭，访问 .url 抛异常；清空后走重新定位流程
            self._page = None

        if self._mode_is_persistent:
            return self._ensure_page_persistent()
        else:
            return self._ensure_page_cdp()

    @property
    def _mode_is_persistent(self) -> bool:
        return self.mode == "persistent"

    def _ensure_page_persistent(self) -> bool:
        """persistent 模式下定位/新建 MatChat 页面，并等待输入框渲染就绪"""
        if not self._browser:
            logger.error("[MatchatBridge] 未连接")
            return False

        for page in self._browser.pages:
            if "matchat.cn" in page.url:
                self._page = page
                logger.info(f"[MatchatBridge] persistent: 复用 {page.url[:80]}")
                return self._wait_for_chat_ready()

        try:
            self._page = self._browser.new_page()
            self._page.goto(self.MATCHAT_URL, wait_until="domcontentloaded", timeout=self.timeout)
            logger.info(f"[MatchatBridge] persistent: 新开 {self.MATCHAT_URL}")
            return self._wait_for_chat_ready()
        except Exception as e:
            logger.error(f"[MatchatBridge] persistent 开页失败: {e}")
            return False

    def _ensure_page_cdp(self) -> bool:
        """cdp 模式下定位/新建 MatChat 页面，并等待输入框渲染就绪"""
        if not self._browser or not self._browser.contexts:
            logger.error("[MatchatBridge] cdp: 未连接或无 context")
            return False

        for context in self._browser.contexts:
            for page in context.pages:
                if "matchat.cn" in page.url:
                    self._page = page
                    logger.info(f"[MatchatBridge] cdp: 复用 {page.url[:80]}")
                    return self._wait_for_chat_ready()

        try:
            self._page = self._browser.contexts[0].new_page()
            self._page.goto(self.MATCHAT_URL, wait_until="domcontentloaded", timeout=self.timeout)
            logger.info(f"[MatchatBridge] cdp: 新开 {self.MATCHAT_URL}")
            return self._wait_for_chat_ready()
        except Exception as e:
            logger.error(f"[MatchatBridge] cdp 开页失败: {e}")
            return False

    def _wait_for_chat_ready(self) -> bool:
        """Next.js 页面需要 hydration，等待 textarea#ai-input 或 #chat-scroll-container 出现。

        为什么不直接 wait_for_load：MatChat 是 SPA，DOMContentLoaded 后 React 还在 hydration，
        输入框可能尚未挂载。等待具体 selector 更可靠。
        """
        if not self._page:
            return False
        try:
            # 优先等待输入框（聊天界面渲染完成的信号）
            self._page.wait_for_selector(
                f"{self.CHAT_INPUT_SELECTOR}, {self.MESSAGES_CONTAINER}",
                timeout=20000,
            )
            # 额外 500ms 让 React hydration 稳定，避免 fill() 时输入框还没绑定事件
            self._page.wait_for_timeout(500)
            return True
        except Exception as e:
            logger.warning(f"[MatchatBridge] 聊天界面未就绪: {e}")
            # 容错：如果 URL 是 matchat，就返回 True，由后续 _send_message 再做 selector 检查
            return "matchat.cn" in (self._page.url or "")

    def ensure_login(self) -> dict[str, Any]:
        """检查登录状态。未登录时返回 needs_login=True。

        判定顺序：URL 含登录关键词 → 页面存在"登录"按钮 → 视为已登录。

        Returns:
            {"needs_login": bool, "logged_in": bool, "page_url": str}
        """
        if not self._ensure_page():
            return {"needs_login": True, "logged_in": False, "page_url": "", "error": "页面不可用"}

        url = self._page.url.lower()
        for pattern in self.LOGIN_URL_PATTERNS:
            if pattern in url:
                return {
                    "needs_login": True,
                    "logged_in": False,
                    "page_url": self._page.url,
                    "message": f"请在打开的浏览器中登录 MatChat (检测到 {pattern})",
                }

        # 检查是否有登录按钮 (未登录状态)
        try:
            login_btn = self._page.query_selector(
                "button:has-text('登录'), a:has-text('登录'), .login-btn"
            )
            if login_btn:
                return {
                    "needs_login": True,
                    "logged_in": False,
                    "page_url": self._page.url,
                    "message": "检测到登录按钮, 请在浏览器中完成登录",
                }
        except Exception:
            # selector 查询失败不阻断流程，按已登录处理由后续发送环节兜底
            pass

        return {"needs_login": False, "logged_in": True, "page_url": self._page.url}

    # ── 核心操作 ──────────────────────────────────

    def search_literature(self, query: str, max_results: int = 5) -> dict[str, Any]:
        """在 MatChat 搜索材料科学文献

        Returns:
            {"success": True, "response": "AI 返回文本", ...}
        """
        if not self._ensure_page():
            return {"success": False, "error": "无法打开 MatChat 页面"}

        login_check = self.ensure_login()
        if login_check.get("needs_login"):
            return {
                "success": False,
                "error": login_check.get("message", "请先登录 MatChat"),
                "needs_login": True,
            }

        try:
            # 把检索需求包装成自然语言提问，让 MatChat AI 返回结构化结果
            message = f"请帮我搜索关于 {query} 的文献, 列出 {max_results} 篇最相关的论文, 包括标题和摘要要点。"
            return self._send_message(message)
        except Exception as e:
            logger.error(f"[MatchatBridge] 文献搜索失败: {e}")
            return {"success": False, "error": str(e)}

    def chat(self, message: str) -> dict[str, Any]:
        """与 MatChat AI 对话

        Returns:
            {"success": True, "response": "AI 回复文本"}
        """
        if not self._ensure_page():
            return {"success": False, "error": "无法打开 MatChat 页面"}

        login_check = self.ensure_login()
        if login_check.get("needs_login"):
            return {
                "success": False,
                "error": login_check.get("message", "请先登录 MatChat"),
                "needs_login": True,
            }

        return self._send_message(message)

    def _is_send_button_disabled(self, button) -> bool:
        """检查发送按钮是否处于 disabled 状态（aria-disabled 或 computed disabled 属性）。

        为什么要多重检查：MatChat 前端有时用 aria-disabled 而非原生 disabled，
        单靠 button.is_disabled() 会漏判，因此补充 JS 计算属性兜底。
        """
        try:
            aria_disabled = button.get_attribute("aria-disabled")
            if aria_disabled and str(aria_disabled).lower() in ("true", "disabled"):
                return True
            if button.is_disabled():
                return True
            computed = self._page.evaluate("""(btn) => {
                if (!btn) return false;
                if (btn.disabled) return true;
                if (btn.hasAttribute('disabled')) return true;
                const aria = btn.getAttribute('aria-disabled');
                if (aria && aria.toLowerCase() === 'true') return true;
                return false;
            }""", button)
            return bool(computed)
        except Exception as e:
            logger.warning(f"[MatchatBridge] 检查按钮 disabled 状态失败: {e}")
            # 检查失败时返回 False（按可用处理），让点击逻辑自行兜底
            return False

    def _send_message(self, message: str) -> dict[str, Any]:
        """核心: 向 MatChat 发送消息并等待回复。支持 disabled 检查与退避重试。

        流程：填入文本 → 点击发送(disabled 时用 Ctrl+Enter 兜底) → 等待回复 → 失败则重试。
        用 self._lock 串行化，防止并发调用导致输入框/页面状态错乱。
        """
        with self._lock:
            max_retries = 2       # 最多重试 2 次（共 3 次尝试）
            retry_interval = 3    # 重试间隔 3s，给页面恢复时间
            last_response = None  # 记录最后一次拿到的文本，供超时返回部分结果

            for attempt in range(max_retries + 1):
                try:
                    input_el = self._page.query_selector(self.CHAT_INPUT_SELECTOR)
                    if not input_el:
                        return {"success": False, "error": "找不到聊天输入框 (DOM selector 未匹配)"}

                    # 先 click 再 fill：部分前端需 focus 后 fill 才能触发 input 事件
                    input_el.click()
                    input_el.fill(message)

                    # 主选择器 + 兜底选择器，应对前端改版
                    send_btn = (
                        self._page.query_selector(self.SEND_BUTTON_SELECTOR)
                        or self._page.query_selector(getattr(self, "SEND_BUTTON_FALLBACK", ""))
                    )

                    if send_btn:
                        is_disabled = self._is_send_button_disabled(send_btn)
                        if is_disabled:
                            # disabled 通常是"内容为空/正在生成"导致的，用键盘兜底触发发送
                            logger.warning("[MatchatBridge] 发送按钮处于 disabled 状态，使用 Ctrl+Enter 键盘兜底")
                            input_el.click()
                            self._page.keyboard.press("Control+Enter")
                        else:
                            try:
                                send_btn.click(timeout=3000)
                            except Exception as e0:
                                # 点击超时/被遮挡时回退键盘发送
                                logger.warning(f"[MatchatBridge] 发送按钮点击失败，回退键盘: {e0}")
                                input_el.click()
                                self._page.keyboard.press("Control+Enter")
                    else:
                        # 找不到发送按钮，直接键盘发送
                        input_el.click()
                        self._page.keyboard.press("Control+Enter")

                    response = self._wait_for_response()
                    if response:
                        return {"success": True, "response": response}
                    else:
                        last_response = response
                        logger.warning(f"[MatchatBridge] 第 {attempt + 1} 次尝试未获取到回复")
                        if attempt < max_retries:
                            logger.info(f"[MatchatBridge] {retry_interval}s 后重试...")
                            time.sleep(retry_interval)
                            # 重新确保页面可用（可能因网络波动掉页）
                            self._ensure_page()
                            continue
                        if last_response:
                            return {"success": False, "error": "AI 回复超时", "response": last_response}
                        return {"success": False, "error": "AI 回复超时"}

                except Exception as e:
                    logger.error(f"[MatchatBridge] 发送消息失败 (第 {attempt + 1} 次): {e}")
                    if attempt < max_retries:
                        logger.info(f"[MatchatBridge] {retry_interval}s 后重试...")
                        time.sleep(retry_interval)
                        self._ensure_page()
                        continue
                    return {"success": False, "error": str(e)}

            if last_response:
                return {"success": False, "error": "AI 回复超时", "response": last_response}
            return {"success": False, "error": "发送失败"}

    def _count_message_children(self) -> int:
        """统计 #chat-scroll-container 内部可见的消息块数量（用直接子div数量近似）。

        用于检测 AI 回复是否产生了新消息块。
        """
        try:
            return self._page.evaluate("""() => {
                const host = document.querySelector('#chat-scroll-container');
                if (!host) return 0;
                return host.querySelectorAll(':scope > div, :scope > div > div').length;
            }""") or 0
        except Exception as e:
            logger.warning(f"[MatchatBridge] 统计消息块失败: {e}")
            return 0

    def _capture_latest_ai_text(self) -> str:
        """从 #chat-scroll-container 中提取最后一个高文本密度块（AI 回复）。

        策略：用 TreeWalker 遍历，对"文本>80、可见、高度>40、含 markdown 标签"的块打分，
        取分数最高者；都失败时退回到滚动容器最后 4000 字符。
        """
        try:
            return self._page.evaluate("""() => {
                const host = document.querySelector('#chat-scroll-container');
                if (!host) return '';
                // 收集所有深度不超过 3、文本长度>80、可见的候选块
                const candidates = [];
                const walker = document.createTreeWalker(host, NodeFilter.SHOW_ELEMENT, {
                    acceptNode(node) {
                        if (!(node instanceof HTMLElement)) return NodeFilter.FILTER_REJECT;
                        const style = window.getComputedStyle(node);
                        if (style.display === 'none' || style.visibility === 'hidden') return NodeFilter.FILTER_REJECT;
                        const txt = (node.innerText || '').trim();
                        if (txt.length < 80) return NodeFilter.FILTER_SKIP;
                        // 优先文本块：有 p / li / pre / code / h* 后代或纯文本占比高
                        const hasMarkdownKids = node.querySelector('p, li, pre, code, h1, h2, h3, h4, h5, h6');
                        const rect = node.getBoundingClientRect();
                        if (rect.height < 40) return NodeFilter.FILTER_SKIP;
                        let score = txt.length + (hasMarkdownKids ? 500 : 0);
                        candidates.push({ node, txt, score });
                        return NodeFilter.FILTER_SKIP;
                    }
                });
                while (walker.nextNode()) {}
                if (!candidates.length) {
                    // 退一：整个滚动容器最后 4000 字符
                    return (host.innerText || '').slice(-4000).trim();
                }
                // 分数最高 & 最后出现 优先
                candidates.sort((a, b) => (b.score - a.score) || 0);
                return candidates[0].txt.slice(-8000);
            }""") or ""
        except Exception as e:
            logger.warning(f"[MatchatBridge] 提取AI回复失败: {e}")
            # evaluate 失败时退回到 inner_text，至少拿到一些文本
            try:
                return (self._page.inner_text(self.MESSAGES_CONTAINER) or "").strip()[-6000:]
            except Exception:
                return ""

    def _wait_for_response(self, timeout_override: int = None) -> str | None:
        """等待 AI 回复完成并返回回复文本。

        判定逻辑（已修复稳定度检测的边缘 case）：
          1. 先记录基线（消息块数 + 当前文本），发送消息后 AI 回复会出现新块或文本增长。
          2. 一旦检测到"新内容"（块数增加 或 文本较基线增长超过 50 字符），进入稳定度计数阶段。
          3. 稳定度阶段每轮（1.2s）采样；文本长度连续 2 轮不变且总长 >150，视为回复完成。
          4. 超时未达稳定态时返回已捕获的部分文本（不返回 None，避免完全丢数据）。

        修复点：原逻辑在"基线已包含 AI 回复块但文本仍在流式增长"时，
          new_blocks/new_text 同时为 False 会跳过稳定度计数，必须等满整个超时才返回。
          新增 has_new_content 标志解决该问题：只要出现过新内容就持续做稳定度判定。

        Args:
            timeout_override: 可选超时（毫秒），默认用 self.timeout

        Returns:
            AI 回复文本（str）；超时且无任何文本时返回 None
        """
        timeout = timeout_override or self.timeout
        deadline = time.time() + timeout / 1000.0
        try:
            baseline_count = self._count_message_children()   # 发送前的消息块数
            baseline_text = self._capture_latest_ai_text()    # 发送前的文本快照
            stable_rounds = 0                                 # 文本连续未变化的轮数
            last_len = len(baseline_text)                     # 上一轮文本长度
            has_new_content = False                           # 是否已捕获到相对基线的新内容

            while time.time() < deadline:
                time.sleep(1.2)  # 1.2s 采样间隔：平衡响应速度与 CPU 开销
                current_count = self._count_message_children()
                current_text = self._capture_latest_ai_text()

                # 判定本轮是否出现"新内容"：块数增加 或 文本较基线显著增长（+50 字符防抖）
                new_blocks = current_count > baseline_count
                new_text = len(current_text) > len(baseline_text) + 50
                if new_blocks or new_text:
                    has_new_content = True

                if not has_new_content:
                    # 还没出现新内容，继续等待（不更新 last_len，保持与基线对比）
                    continue

                # 已出现新内容，进入稳定度判定
                if len(current_text) == last_len:
                    stable_rounds += 1  # 文本未增长，累加稳定轮数
                else:
                    stable_rounds = 0   # 文本仍在增长，重置计数
                last_len = len(current_text)

                # 连续 2 轮稳定 + 文本足够长（>150 字符），认为回复完成
                if stable_rounds >= 2 and len(current_text) > 150:
                    return current_text.strip()

            # 超时兜底：返回已捕获的部分文本，避免完全丢数据
            final = self._capture_latest_ai_text()
            if final:
                logger.warning("[MatchatBridge] 未达稳定态，返回已捕获的部分文本")
                return final.strip()
            return None
        except Exception as e:
            logger.warning(f"[MatchatBridge] 等待回复异常: {e}")
        return None

    def extract_page_text(self) -> dict[str, Any]:
        """提取当前页面文本内容（截断到 10000 字符防止过大返回）"""
        if not self._ensure_page():
            return {"success": False, "error": "无法打开 MatChat 页面"}

        try:
            text = self._page.inner_text("body")
            return {"success": True, "text": text[:10000]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def is_connected(self) -> bool:
        """检查连接状态 (两种模式通用)。

        不加锁：此方法只读，且各分支自带 try/except，并发读到中间态最多误报一次，
        由调用方 _get_bridge 触发重连兜底。
        """
        if not self._browser:
            return False
        try:
            if self._mode_is_persistent:
                # persistent context: 检查是否还有活跃 page
                return bool(self._browser.pages)
            else:
                # cdp browser: 检查 is_connected
                return self._browser.is_connected()
        except Exception:
            # browser 已关闭等异常视为未连接
            return False
