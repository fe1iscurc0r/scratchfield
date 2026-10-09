# comprehensive_app_scanner.py — 综合应用扫描器（注册表 + 快捷方式 + macOS）
import asyncio
import glob
import json
import logging
import os
import platform
import subprocess
from typing import Dict, List, Optional
import threading

logger = logging.getLogger("AppScanner")

# 平台特定导入
if platform.system() == "Windows":
    try:
        import winreg
    except ImportError:
        winreg = None
else:
    winreg = None


def _resolve_path(raw: str) -> str | None:
    """清理并解析注册表中的路径：去引号、展开环境变量、验证存在性"""
    if not raw:
        return None
    # 去掉首尾引号
    p = raw.strip().strip('"').strip("'")
    # 展开环境变量（如 %ProgramFiles%）
    p = os.path.expandvars(p)
    p = os.path.expanduser(p)
    if p and os.path.exists(p):
        return p
    return None


class ComprehensiveAppScanner:
    """综合应用扫描器：Windows 注册表 + 快捷方式 + macOS Applications"""

    def __init__(self):
        self.apps_cache: list[dict] = []
        self._scan_completed = False
        self._scan_lock = asyncio.Lock()

    async def ensure_scan_completed(self):
        if not self._scan_completed:
            async with self._scan_lock:
                if not self._scan_completed:
                    await self._scan_all_sources_async()
                    self._scan_completed = True

    async def _scan_all_sources_async(self):
        apps: list[dict] = []
        system = platform.system()

        if system == "Windows":
            registry_apps = await asyncio.get_running_loop().run_in_executor(
                None, self._scan_registry_sync
            )
            apps.extend(registry_apps)

            shortcut_apps = await asyncio.get_running_loop().run_in_executor(
                None, self._scan_shortcuts_sync
            )
            apps.extend(shortcut_apps)

        elif system == "Darwin":
            mac_apps = await asyncio.get_running_loop().run_in_executor(
                None, self._scan_macos_sync
            )
            apps.extend(mac_apps)

        unique_apps = self._merge_and_deduplicate(apps)
        self.apps_cache = unique_apps
        logger.info(f"综合扫描完成，共找到 {len(self.apps_cache)} 个应用")

    # ─── Windows: 注册表扫描 ───────────────────────────────

    def _scan_registry_sync(self) -> list[dict]:
        apps: list[dict] = []
        if winreg is None:
            return apps

        # 1. App Paths（chrome.exe, msedge.exe 等）
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
            ) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        app_name = winreg.EnumKey(key, i)
                        if not app_name.lower().endswith(".exe"):
                            continue
                        subkey_path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{app_name}"
                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey_path) as app_key:
                            raw_path, _ = winreg.QueryValueEx(app_key, "")
                            exe_path = _resolve_path(raw_path)
                            if not exe_path:
                                continue
                            display_name = app_name[:-4]
                            try:
                                friendly, _ = winreg.QueryValueEx(app_key, "FriendlyAppName")
                                if friendly:
                                    display_name = friendly
                            except OSError:
                                pass
                            apps.append({
                                "name": display_name,
                                "path": exe_path,
                                "source": "registry",
                            })
                    except OSError:
                        continue
        except OSError as e:
            logger.debug(f"扫描 App Paths 失败: {e}")

        # 2. Uninstall 注册表（HKLM + HKCU）
        for hive, hive_name in [
            (winreg.HKEY_LOCAL_MACHINE, "HKLM"),
            (winreg.HKEY_CURRENT_USER, "HKCU"),
        ]:
            try:
                with winreg.OpenKey(
                    hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
                ) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, subkey_name) as subkey:
                                try:
                                    display_name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                                except OSError:
                                    continue
                                # 优先用 DisplayIcon（通常是 exe 路径）
                                exe_path = None
                                for val_name in ("DisplayIcon", "InstallLocation"):
                                    try:
                                        raw, _ = winreg.QueryValueEx(subkey, val_name)
                                        resolved = _resolve_path(raw.split(",")[0] if "," in raw else raw)
                                        if resolved and resolved.lower().endswith(".exe"):
                                            exe_path = resolved
                                            break
                                        elif resolved and os.path.isdir(resolved):
                                            # InstallLocation 是目录，找 exe
                                            for f in os.listdir(resolved):
                                                if f.lower().endswith(".exe"):
                                                    candidate = os.path.join(resolved, f)
                                                    if os.path.isfile(candidate):
                                                        exe_path = candidate
                                                        break
                                            if exe_path:
                                                break
                                    except OSError:
                                        continue
                                if display_name and exe_path:
                                    apps.append({
                                        "name": display_name,
                                        "path": exe_path,
                                        "source": "registry",
                                    })
                        except OSError:
                            continue
            except OSError as e:
                logger.debug(f"扫描 {hive_name} Uninstall 失败: {e}")

        return apps

    # ─── Windows: 快捷方式扫描 ─────────────────────────────

    def _scan_shortcuts_sync(self) -> list[dict]:
        apps: list[dict] = []
        start_menu_paths = [
            os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
            os.path.expanduser("~/Desktop"),
        ]

        # 尝试用 win32com 解析 .lnk
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            use_com = True
        except Exception:
            shell = None
            use_com = False
            logger.debug("win32com 不可用，快捷方式用 PowerShell 兜底")

        for base in start_menu_paths:
            if not os.path.isdir(base):
                continue
            for lnk_path in glob.glob(os.path.join(base, "**", "*.lnk"), recursive=True):
                info = None
                if use_com:
                    info = self._parse_lnk_com(shell, lnk_path)
                if info is None:
                    info = self._parse_lnk_powershell(lnk_path)
                if info:
                    apps.append(info)
        return apps

    @staticmethod
    def _parse_lnk_com(shell, lnk_path: str) -> dict | None:
        try:
            shortcut = shell.CreateShortCut(lnk_path)
            target = shortcut.TargetPath
            if target and os.path.isfile(target) and target.lower().endswith(".exe"):
                name = os.path.splitext(os.path.basename(lnk_path))[0]
                return {"name": name, "path": target, "source": "shortcut", "shortcut_path": lnk_path}
        except Exception:
            pass
        return None

    @staticmethod
    def _parse_lnk_powershell(lnk_path: str) -> dict | None:
        """win32com 不可用时用 PowerShell 解析 .lnk"""
        try:
            cmd = (
                f'(New-Object -ComObject WScript.Shell)'
                f'.CreateShortcut("{lnk_path}").TargetPath'
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True, text=True, timeout=5,
            )
            target = result.stdout.strip()
            if target and os.path.isfile(target) and target.lower().endswith(".exe"):
                name = os.path.splitext(os.path.basename(lnk_path))[0]
                return {"name": name, "path": target, "source": "shortcut", "shortcut_path": lnk_path}
        except Exception:
            pass
        return None

    # ─── macOS: /Applications 扫描 ─────────────────────────

    def _scan_macos_sync(self) -> list[dict]:
        apps: list[dict] = []
        app_dirs = ["/Applications", os.path.expanduser("~/Applications")]
        for app_dir in app_dirs:
            if not os.path.isdir(app_dir):
                continue
            for entry in os.listdir(app_dir):
                if not entry.endswith(".app"):
                    continue
                app_path = os.path.join(app_dir, entry)
                name = entry[:-4]  # 去 .app 后缀
                # macOS 用 open 命令启动
                apps.append({
                    "name": name,
                    "path": app_path,
                    "source": "macos_app",
                })
        return apps

    # ─── 公共方法 ──────────────────────────────────────────

    def _merge_and_deduplicate(self, apps: list[dict]) -> list[dict]:
        unique: dict[str, dict] = {}
        for app in apps:
            key = app["name"].lower()
            if key not in unique or app["source"] == "shortcut" and unique[key]["source"] != "shortcut":
                unique[key] = app
        result = list(unique.values())
        result.sort(key=lambda x: x["name"].lower())
        return result

    async def get_apps(self) -> list[dict]:
        await self.ensure_scan_completed()
        return self.apps_cache.copy()

    async def find_app_by_name(self, name: str) -> dict | None:
        await self.ensure_scan_completed()
        name_lower = name.lower()
        # 精确匹配
        for app in self.apps_cache:
            if app["name"].lower() == name_lower:
                return app
        # 模糊匹配
        for app in self.apps_cache:
            if name_lower in app["name"].lower() or app["name"].lower() in name_lower:
                return app
        return None

    async def refresh_apps(self):
        async with self._scan_lock:
            self._scan_completed = False
            await self._scan_all_sources_async()
            self._scan_completed = True

    async def get_app_info_for_llm(self) -> dict:
        await self.ensure_scan_completed()
        app_names = [app["name"] for app in self.apps_cache]
        return {"total_count": len(app_names), "apps": app_names}


_comprehensive_scanner: ComprehensiveAppScanner | None = None


_comprehensive_scanner_lock = threading.Lock()


def get_comprehensive_scanner() -> ComprehensiveAppScanner:
    global _comprehensive_scanner
    if _comprehensive_scanner is None:
        with _comprehensive_scanner_lock:
            if _comprehensive_scanner is None:
                _comprehensive_scanner = ComprehensiveAppScanner()
    return _comprehensive_scanner


async def refresh_comprehensive_apps():
    scanner = get_comprehensive_scanner()
    await scanner.refresh_apps()
