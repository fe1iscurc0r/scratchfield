"""
agent_browser.py - MCP Agent wrapper for browser automation.
Powers browser interaction: navigate, click, type, extract content, screenshot.
Merges concepts from browser-use (107k⭐) and nanobrowser (13k⭐).

Independently importable. Requires Playwright + Chromium.
"""

import asyncio
import atexit
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def _check_playwright() -> str | None:
    """Check if Playwright is installed, return error message or None."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        return (
            "Playwright is not installed. Install with:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )
    return None


class AgentBrowser:
    """MCP Agent for browser automation via Playwright/CDP."""

    def __init__(self):
        self._browser = None
        self._context = None
        self._page = None
        err = _check_playwright()
        if err:
            raise RuntimeError(err)

    async def _ensure_browser(self, headless: bool = True):
        """Lazy-init browser, context, and page."""
        if self._browser is None:
            from playwright.async_api import async_playwright

            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(
                headless=headless,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            self._context = await self._browser.new_context()
            self._page = await self._context.new_page()
        return self._page

    async def _close(self):
        """Cleanup browser resources."""
        try:
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if hasattr(self, "_pw") and self._pw:
                await self._pw.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None

    # ── Command implementations ──────────────────────────────────────

    async def navigate(
        self,
        url: str,
        new_tab: bool = False,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """Navigate to a URL."""
        try:
            page = await self._ensure_browser()
            if new_tab:
                page = await self._context.new_page()
                self._page = page
            response = await page.goto(url, timeout=timeout * 1000)
            return {
                "status": "ok",
                "message": f"Navigated to {url}",
                "data": {
                    "url": page.url,
                    "title": await page.title(),
                    "status_code": response.status if response else None,
                },
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc), "data": None}

    async def get_page_state(self) -> dict[str, Any]:
        """Get interactive elements from current page."""
        try:
            page = await self._ensure_browser()
            # Extract clickable/input elements
            elements = await page.evaluate("""
                () => {
                    const els = [];
                    const interactives = document.querySelectorAll(
                        'a, button, input, select, textarea, [role="button"], [onclick], [tabindex]'
                    );
                    interactives.forEach((el, idx) => {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            els.push({
                                index: idx,
                                tag: el.tagName.toLowerCase(),
                                type: el.type || null,
                                text: (el.innerText || el.value || el.placeholder || '').substring(0, 100),
                                id: el.id || null,
                                name: el.name || null,
                                href: el.href || null,
                                visible: true
                            });
                        }
                    });
                    return els;
                }
            """)
            return {
                "status": "ok",
                "message": f"Found {len(elements)} interactive elements",
                "data": {
                    "url": page.url,
                    "title": await page.title(),
                    "elements": elements,
                },
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc), "data": None}

    async def click_element(
        self,
        index: int,
    ) -> dict[str, Any]:
        """Click an element by its index from get_page_state."""
        try:
            page = await self._ensure_browser()
            result = await page.evaluate(
                """
                (idx) => {
                    const interactives = document.querySelectorAll(
                        'a, button, input, select, textarea, [role="button"], [onclick], [tabindex]'
                    );
                    const el = interactives[idx];
                    if (!el) return {clicked: false, error: 'Element not found at index ' + idx};
                    el.scrollIntoView({behavior: 'smooth', block: 'center'});
                    el.click();
                    return {clicked: true, tag: el.tagName, text: (el.innerText || el.value || '').substring(0, 100)};
                }
            """,
                index,
            )
            await asyncio.sleep(0.5)  # Wait for navigation/action
            return {
                "status": "ok" if result.get("clicked") else "error",
                "message": f"Clicked element [{index}]: {result.get('tag', 'unknown')}",
                "data": {
                    **result,
                    "current_url": page.url,
                },
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc), "data": None}

    async def type_text(
        self,
        index: int,
        text: str,
    ) -> dict[str, Any]:
        """Type text into an input element identified by index."""
        try:
            page = await self._ensure_browser()
            elements = page.locator(
                'a, button, input, select, textarea, [role="button"], [onclick], [tabindex]'
            )
            await elements.nth(index).fill(text)
            return {
                "status": "ok",
                "message": f"Typed '{text}' into element [{index}]",
                "data": {"text": text, "index": index},
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc), "data": None}

    async def extract_content(
        self,
        query: str,
    ) -> dict[str, Any]:
        """Extract page content based on a natural-language query."""
        try:
            page = await self._ensure_browser()
            # Get page text and metadata
            text_content = await page.evaluate("""
                () => {
                    const main = document.querySelector('main, article, .content, #content, body');
                    if (!main) return document.body ? document.body.innerText.substring(0, 5000) : '';
                    return main.innerText.substring(0, 5000);
                }
            """)
            title = await page.title()
            return {
                "status": "ok",
                "message": f"Extracted content for query: {query}",
                "data": {
                    "query": query,
                    "url": page.url,
                    "title": title,
                    "text": text_content,
                },
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc), "data": None}

    async def execute_task(
        self,
        task: str,
        max_steps: int = 10,
    ) -> dict[str, Any]:
        """Execute a high-level task by navigating and interacting.
        This is a simplified execution loop: navigate → observe → decide → act.
        """
        try:
            page = await self._ensure_browser()
            steps_taken = 0
            logs = []

            # Basic task execution loop
            for _ in range(max_steps):
                steps_taken += 1
                state = await self.get_page_state()
                logs.append({
                    "step": steps_taken,
                    "url": state.get("data", {}).get("url", ""),
                    "element_count": len(state.get("data", {}).get("elements", [])),
                })
                # Without LLM integration, perform basic fallback:
                # try to extract content as best-effort


            return {
                "status": "ok",
                "message": f"Task execution attempted ({steps_taken} steps)",
                "data": {
                    "task": task,
                    "steps_taken": steps_taken,
                    "logs": logs,
                    "note": "Full task execution requires LLM integration for decision-making",
                },
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc), "data": None}

    async def screenshot(
        self,
        full_page: bool = False,
    ) -> dict[str, Any]:
        """Take a screenshot of the current page."""
        try:
            page = await self._ensure_browser()
            import base64
            import tempfile

            screenshot_bytes = await page.screenshot(full_page=full_page)
            b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            # Also save to temp file for persistence
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(screenshot_bytes)
                path = f.name
                atexit.register(lambda p=path: os.unlink(p) if os.path.exists(p) else None)

            return {
                "status": "ok",
                "message": f"Screenshot captured ({len(screenshot_bytes)} bytes)",
                "data": {
                    "path": path,
                    "base64": b64[:100] + "...",  # Truncated in JSON
                    "size_bytes": len(screenshot_bytes),
                },
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc), "data": None}


    async def handle_handoff(self, task: dict[str, Any]) -> str:
        """Entry point: receive task dict, dispatch to tool, return JSON string.

        Task format:
            {"tool_name": "navigate|get_page_state|click_element|type_text|extract_content|execute_task|screenshot",
             ...params}
        """
        tool_name = str(task.get("tool_name") or "").strip()

        dispatcher = {
            "navigate": lambda: self.navigate(
                url=task.get("url", ""),
                new_tab=task.get("new_tab", False),
                timeout=task.get("timeout", 30),
            ),
            "get_page_state": lambda: self.get_page_state(),
            "click_element": lambda: self.click_element(
                index=task.get("index", 0),
            ),
            "type_text": lambda: self.type_text(
                index=task.get("index", 0),
                text=task.get("text", ""),
            ),
            "extract_content": lambda: self.extract_content(
                query=task.get("query", "extract all"),
            ),
            "execute_task": lambda: self.execute_task(
                task=task.get("task", ""),
                max_steps=task.get("max_steps", 10),
            ),
            "screenshot": lambda: self.screenshot(
                full_page=task.get("full_page", False),
            ),
        }

        handler = dispatcher.get(tool_name)
        if handler is None:
            result = {
                "status": "error",
                "message": f"Unknown tool: {tool_name}. Available: {list(dispatcher.keys())}",
                "data": None,
            }
        else:
            result = await handler()

        return json.dumps(result, ensure_ascii=False)


# Module-level wrapper for backward compatibility
async def handle_handoff(task: dict[str, Any]) -> str:
    """Module-level wrapper for AgentBrowser.handle_handoff.
    Ensures browser resources are closed after the call to prevent leaks.
    """
    agent = AgentBrowser()
    try:
        return await agent.handle_handoff(task)
    finally:
        await agent._close()
