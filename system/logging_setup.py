#!/usr/bin/env python3
"""
统一日志管理

所有环境下均将详细日志写入 logs/details/ 文件夹，支持轮转。
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 是否为 PyInstaller 打包环境
IS_PACKAGED: bool = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


class SafeRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler 的安全版本，防御 stream 文件描述符失效。

    Windows + 多线程 + 长时间运行环境下，stream 的文件描述符可能失效，
    导致 shouldRollover / write / flush 抛 OSError([Errno 9] Bad file descriptor)。
    标准 FileHandler.emit 会把异常交给 handleError 输出 '--- Logging error ---' 到
    stderr，频繁刷屏。本类在 shouldRollover / flush / emit 三个环节全部主动捕获
    OSError 并重建 stream，实现自愈。
    """

    def shouldRollover(self, record):
        if self.stream is None:
            self.stream = self._open()
        if self.maxBytes > 0:
            try:
                pos = self.stream.tell()
            except OSError:
                # 文件描述符失效，重建 stream 后跳过本次轮转判断，
                # 让后续 emit 在新 stream 上正常写入
                self._reopen_stream()
                return False
            if not pos:
                return False
            msg = "%s\n" % self.format(record)
            if pos + len(msg) >= self.maxBytes:
                # 非普通文件不轮转（如管道、设备文件）
                if os.path.exists(self.baseFilename) and not os.path.isfile(self.baseFilename):
                    return False
                return True
        return False

    def flush(self):
        """刷新 stream，捕获 fd 失效异常并自愈。

        标准实现直接 self.stream.flush()，fd 失效时会抛 OSError。
        此处保留标准锁机制，捕获后重建 stream，避免异常上抛。
        """
        self.acquire()
        try:
            if self.stream is None or not hasattr(self.stream, "flush"):
                return
            try:
                self.stream.flush()
            except OSError:
                # fd 已失效，重建 stream；下次 flush 再失败也不会抛
                self._reopen_stream()
            except Exception:
                # 其他异常吞掉，flush 失败不该影响调用方
                pass
        finally:
            self.release()

    def emit(self, record):
        """写入日志，stream 失效时自愈并重试一次。

        标准 FileHandler.emit → StreamHandler.emit 会捕获 OSError 并调用
        handleError，输出 '--- Logging error ---' 到 stderr 刷屏。
        此处完全接管写入流程，主动捕获 OSError 并重建 stream 后重写一次。
        """
        # stream 尚未打开或上次重建失败：尝试重开
        if self.stream is None:
            try:
                self.stream = self._open()
            except OSError:
                return
        # 轮转判断（shouldRollover 已防御 fd 失效）
        try:
            need_rollover = self.shouldRollover(record)
        except Exception:
            need_rollover = False
        if need_rollover:
            try:
                self.doRollover()
            except OSError:
                # 轮转失败（如旧 stream 已废），重建后继续写入
                self._reopen_stream()
        # 实际写入
        try:
            msg = "%s\n" % self.format(record)
            self.stream.write(msg)
            self.flush()
        except OSError:
            # stream 写入或刷新失败，重建并重试一次
            self._reopen_stream()
            try:
                if self.stream is not None:
                    msg = "%s\n" % self.format(record)
                    self.stream.write(msg)
                    self.flush()
            except OSError:
                # 重建后仍失败，放弃此条记录避免异常上抛刷屏
                pass
        except RecursionError:
            raise
        except Exception:
            # 其他类型异常走标准 handleError
            self.handleError(record)

    def _reopen_stream(self):
        """安全重建 stream：关闭旧 stream（可能已失效）并重新打开"""
        try:
            if self.stream:
                self.stream.close()
        except OSError:
            pass
        finally:
            self.stream = None
        try:
            self.stream = self._open()
        except OSError:
            # 重新打开也失败，保持 stream=None，
            # 下次 emit / shouldRollover 会再次尝试 _open()
            self.stream = None


def _resolve_log_dir() -> Path:
    """推导日志根目录（logs/）"""
    from system.config import get_data_dir
    return get_data_dir() / "logs"


def setup_logging() -> None:
    """统一初始化日志系统，所有环境均写入文件日志"""
    log_dir = _resolve_log_dir()
    details_dir = log_dir / "details"
    details_dir.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # 详细日志 → logs/details/naga-backend.log
    backend_handler = SafeRotatingFileHandler(
        details_dir / "naga-backend.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    backend_handler.setLevel(logging.DEBUG)
    backend_handler.setFormatter(fmt)

    # OpenClaw 专用 → logs/details/openclaw.log
    openclaw_handler = SafeRotatingFileHandler(
        details_dir / "openclaw.log",
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding="utf-8",
    )
    openclaw_handler.setLevel(logging.DEBUG)
    openclaw_handler.setFormatter(fmt)

    # 控制台 Handler — 简洁输出
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )

    # 配置 root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(backend_handler)
    root.addHandler(console_handler)

    # OpenClaw 命名空间额外写入专用日志
    logging.getLogger("agentserver.openclaw").addHandler(openclaw_handler)

    # 抑制第三方库噪音
    for name in ["httpcore", "httpx", "urllib3", "asyncio", "LiteLLM",
                  "uvicorn.access", "openai._base_client"]:
        logging.getLogger(name).setLevel(logging.WARNING)
