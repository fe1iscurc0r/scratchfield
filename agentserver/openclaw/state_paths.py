#!/usr/bin/env python3

from __future__ import annotations

import os
from pathlib import Path

from system.config import get_data_dir


def get_openclaw_state_dir() -> Path:
    state_override = os.environ.get("OPENCLAW_STATE_DIR", "").strip()
    if state_override:
        return Path(state_override).expanduser()

    return get_data_dir() / "openclaw"


def get_openclaw_config_path() -> Path:
    config_override = os.environ.get("OPENCLAW_CONFIG_PATH", "").strip()
    if config_override:
        return Path(config_override).expanduser()
    return get_openclaw_state_dir() / "openclaw.json"
