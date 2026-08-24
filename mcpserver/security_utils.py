"""security_utils.py - 统一安全工具模块

集中管理 SSRF 防护、路径遍历检测、参数净化等安全工具，
供所有 MCP Agent 复用，避免重复实现和不一致。
"""

import ipaddress
import re
import socket
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::ffff:0:0/96"),
]


def is_private_ip(hostname: str) -> bool:
    """检查主机名是否为私有/内部IP地址（含IPv4和IPv6）。"""
    if hostname.lower() == "localhost":
        return True
    try:
        addr = ipaddress.ip_address(hostname)
        for network in _BLOCKED_NETWORKS:
            if addr in network:
                return True
    except ValueError:
        pass
    return False


def is_private_url(url: str) -> bool:
    """检查URL是否指向私有/内部IP地址（支持域名通过DNS解析检测）。"""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return True
        hostname = parsed.hostname
        if not hostname:
            return True
        if is_private_ip(hostname):
            return True
        # DNS解析后二次校验（防DNS rebinding）
        try:
            resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for _, _, _, _, sockaddr in resolved:
                ip = sockaddr[0]
                addr = ipaddress.ip_address(ip)
                for network in _BLOCKED_NETWORKS:
                    if addr in network:
                        return True
        except (socket.gaierror, socket.herror):
            # DNS 解析失败时 fail-closed：视为不安全，拒绝该 URL
            return True
    except Exception:
        pass
    return False


def validate_callback_url(url: str) -> tuple[bool, str]:
    """验证回调URL安全性。返回 (是否安全, 消息)。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, f"不允许的URL协议: {parsed.scheme}"
    hostname = parsed.hostname
    if not hostname:
        return False, "callback_url 缺少主机名"
    if hostname.lower() == "localhost":
        return False, "不允许回调到 localhost"
    if is_private_url(url):
        return False, f"不允许回调到私有/内部IP地址: {hostname}"
    return True, "OK"


def validate_path_traversal(path_str: str, allowed_dirs: list[Path] | None = None) -> tuple[bool, str]:
    """验证文件路径安全性。返回 (是否安全, 消息)。"""
    p = Path(path_str)
    # 检查路径组件中是否包含 '..'（覆盖字面字符串、Unicode 变体）
    if ".." in p.parts:
        return False, "路径中包含 '..' 遍历序列"
    if path_str.startswith("/") or path_str.startswith("\\"):
        return False, "不允许Unix/Windows绝对路径"
    # Windows 盘符绝对路径（如 C:\、D:\）
    if len(path_str) >= 2 and path_str[1] == ":":
        return False, "不允许Windows绝对路径"
    if p.is_absolute():
        resolved = p.resolve()
        check_dirs = allowed_dirs or []
        for allowed_dir in check_dirs:
            try:
                resolved.relative_to(allowed_dir.resolve())
                return True, "OK"
            except ValueError:
                continue
        return False, "绝对路径不在允许的目录范围内"
    # 相对路径：resolve 后再次检查是否越界
    if allowed_dirs:
        resolved = p.resolve()
        for allowed_dir in (allowed_dirs or []):
            try:
                resolved.relative_to(allowed_dir.resolve())
                return True, "OK"
            except ValueError:
                continue
        return False, "相对路径 resolve 后越出允许目录范围"
    return True, "OK"


def sanitize_username(username: str, max_length: int = 50) -> tuple[bool, str]:
    """验证并净化用户名输入。返回 (是否安全, 消息)。"""
    VALID_PATTERN = re.compile(r'^[a-zA-Z0-9._-]{1,%d}$' % max_length)
    if not VALID_PATTERN.match(username):
        return False, "用户名只能包含字母、数字、点号、下划线和连字符"
    return True, "OK"


def sanitize_sites(sites: str) -> tuple[bool, str]:
    """验证并净化sherlock sites参数。返回 (是否安全, 消息)。"""
    if not sites:
        return True, "OK"
    VALID_SITE_PATTERN = re.compile(r'^[a-zA-Z0-9._-]{1,100}$')
    site_list = [s.strip() for s in sites.split(",")]
    for site in site_list:
        if not VALID_SITE_PATTERN.match(site):
            return False, f"非法站点名称: {site}"
    return True, "OK"


def sanitize_key_path(key: str, allowed_dirs: list[Path] | None = None) -> tuple[bool, str]:
    """验证密钥路径安全性。返回 (是否安全, 消息)。"""
    if not key:
        return True, "OK"
    return validate_path_traversal(key, allowed_dirs)


def validate_file_extension(file_path: str, allowed_extensions: set) -> tuple[bool, str]:
    """验证文件扩展名是否在允许列表中。返回 (是否安全, 消息)。"""
    ext = Path(file_path).suffix.lower()
    if ext not in allowed_extensions:
        return False, f"文件扩展名 '{ext}' 不在允许列表: {sorted(allowed_extensions)}"
    return True, "OK"


_NESTED_QUANTIFIER_RE = re.compile(
    r'\([^)]*[+*]\)[+*]'
)
_DANGEROUS_LITERAL_PATTERNS = ["(.*)+", "(..)+", "(*)*", "(+)+"]


def validate_regex_pattern(pattern: str, max_length: int = 100) -> tuple[bool, str]:
    """验证正则表达式安全性（防ReDoS）。返回 (是否安全, 消息)。"""
    if len(pattern) > max_length:
        return False, f"正则表达式过长（{len(pattern)} > {max_length}）"
    for dp in _DANGEROUS_LITERAL_PATTERNS:
        if dp in pattern:
            return False, f"正则表达式包含危险模式: {dp}"
    if _NESTED_QUANTIFIER_RE.search(pattern):
        return False, "正则表达式包含嵌套量词模式（如 (x+)+, (.*)+ 等），存在ReDoS风险"
    return True, "OK"


def sanitize_external_args(arguments: dict) -> dict:
    """过滤外部MCP工具参数中的敏感字段和危险模式。"""
    DANGEROUS_KEYS = {"password", "token", "secret", "api_key", "private_key", "passwd"}
    DANGEROUS_PATTERNS = [";", "&&", "||", "$(", "`", "\n", "|"]
    sanitized = {}
    for key, value in arguments.items():
        if any(danger in key.lower() for danger in DANGEROUS_KEYS):
            continue
        if isinstance(value, str):
            if any(danger in value for danger in DANGEROUS_PATTERNS):
                raise ValueError(f"参数 '{key}' 包含危险模式")
        sanitized[key] = value
    return sanitized
