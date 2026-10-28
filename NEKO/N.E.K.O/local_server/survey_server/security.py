# -*- coding: utf-8 -*-
# Copyright 2025-2026 Project N.E.K.O. Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Survey Server — security module

Identical scheme to the telemetry server, but a **separate** HMAC secret so a
leaked telemetry key can't forge survey submissions (and vice versa):

1. HMAC-SHA256 signature verification (anti-tampering) — secret from env only
2. Timestamp window verification (anti-replay)
3. Per-device rate limiting (anti-abuse)
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from collections import defaultdict
from threading import Lock

# ---------------------------------------------------------------------------
# ★ 密钥只从环境读取，源码里不保留任何可用值。
#   首选 SURVEY_HMAC_SECRET，兼容旧名 NEKO_SURVEY_HMAC_SECRET。
# 与 telemetry 通道**故意不同**：两条上报通道互不背书。
# 与 telemetry 同样的理由：软签名对抗不了逆向，但「源码自带一份可用密钥」会把
# 一次仓库泄露放大成全量伪造能力，所以未配置时的正确行为是不启动。
# ---------------------------------------------------------------------------

HMAC_SECRET_ENV_KEYS = ("SURVEY_HMAC_SECRET", "NEKO_SURVEY_HMAC_SECRET")


class HMACSecretNotConfigured(RuntimeError):
    """No usable HMAC secret in the environment."""


def load_hmac_secret() -> str:
    """Read the HMAC secret from the environment.

    Raises when unset. The message names only the variables — never a value.
    """
    for key in HMAC_SECRET_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    raise HMACSecretNotConfigured(
        "HMAC secret is not configured: set " + " or ".join(HMAC_SECRET_ENV_KEYS)
    )


def _secret_or_env(secret: str | None) -> str:
    return secret if secret else load_hmac_secret()


def compute_signature(payload_json: str, timestamp: float, secret: str | None = None) -> str:
    """Compute HMAC-SHA256(secret, f"{timestamp}|{sha256(payload_json)}")."""
    secret = _secret_or_env(secret)
    body_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    message = f"{timestamp}|{body_hash}"
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(
    payload_json: str,
    timestamp: float,
    signature: str,
    secret: str | None = None,
) -> bool:
    """Verify the signature (constant-time comparison, guards against timing attacks)."""
    # Fail closed when no secret is configured: a misconfigured deployment rejects
    # unsigned traffic rather than accepting it.
    try:
        secret = _secret_or_env(secret)
    except HMACSecretNotConfigured:
        return False
    # hmac.compare_digest raises TypeError on str containing non-ASCII; a forged
    # request with a non-ASCII signature would crash verify into a 500 instead of
    # a clean 403. The signature is always a hex digest (pure ASCII), so any
    # non-ASCII value is necessarily invalid — reject it early.
    if not isinstance(signature, str) or not signature.isascii():
        return False
    expected = compute_signature(payload_json, timestamp, secret)
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# 时间戳窗口
# ---------------------------------------------------------------------------

TIMESTAMP_TOLERANCE = 300  # ±5 分钟


def verify_timestamp(timestamp: float, tolerance: float = TIMESTAMP_TOLERANCE) -> bool:
    """Reject requests older/newer than ±tolerance seconds (anti-replay)."""
    return abs(time.time() - timestamp) <= tolerance


# ---------------------------------------------------------------------------
# 速率限制（滑动窗口，per-device，内存存储）
# ---------------------------------------------------------------------------

class RateLimiter:
    """At most max_requests per device_id within a window of `window` seconds.

    Survey traffic is far sparser than telemetry — one submission per user per
    app version — so the default ceiling is intentionally low; it only exists to
    blunt a forged-request flood, not to throttle legitimate users.
    """

    def __init__(self, max_requests: int = 20, window: float = 3600.0):
        self.max_requests = max_requests
        self.window = window
        self._records: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def is_allowed(self, device_id: str) -> bool:
        now = time.time()
        cutoff = now - self.window
        with self._lock:
            ts_list = self._records[device_id]
            self._records[device_id] = [t for t in ts_list if t > cutoff]
            if len(self._records[device_id]) >= self.max_requests:
                return False
            self._records[device_id].append(now)
            return True

    def cleanup_stale(self, max_age: float = 86400.0):
        """Clean up long-inactive device records (prevents memory bloat)."""
        cutoff = time.time() - max_age
        with self._lock:
            stale = [k for k, v in self._records.items() if not v or v[-1] < cutoff]
            for k in stale:
                del self._records[k]
