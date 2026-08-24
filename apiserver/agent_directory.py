"""干员目录与解析辅助。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Optional

from system.config import get_data_dir

BUILTIN_NAGA_AGENT_ID = "naga-default"
_NAGA_BUILTIN_NAMES = {"娜迦", "naga", "nagacore", "naga-core", "lumo-core"}
NAGA_CORE_ENGINES = {"lumo-core", "naga-core", "nagacore", "naga_core"}


@dataclass
class AgentDescriptor:
    id: str
    name: str
    engine: str
    character_template: str | None = None
    builtin: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_agent_engine(engine: str | None) -> str:
    value = (engine or "openclaw").strip().lower()
    if value in {"nagacore", "naga_core", "naga-core"}:
        value = "lumo-core"
    return value


def _manifest_path():
    return get_data_dir() / "agents" / "agents.json"


def _active_character_name() -> str | None:
    try:
        from system.config import get_config

        return get_config().system.active_character or None
    except Exception:
        return None


def builtin_naga_descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        id=BUILTIN_NAGA_AGENT_ID,
        name="陆墨",
        engine="lumo-core",
        character_template=_active_character_name(),
        builtin=True,
    )


def list_agent_descriptors(include_builtin: bool = True) -> list[AgentDescriptor]:
    items: list[AgentDescriptor] = []
    if include_builtin:
        items.append(builtin_naga_descriptor())

    manifest_path = _manifest_path()
    if not manifest_path.exists():
        return items

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return items

    for entry in manifest.get("agents", []):
        agent_id = str(entry.get("id") or "").strip()
        if not agent_id:
            continue
        items.append(
            AgentDescriptor(
                id=agent_id,
                name=str(entry.get("name") or agent_id),
                engine=normalize_agent_engine(entry.get("engine")),
                character_template=entry.get("character_template"),
                builtin=False,
            )
        )
    return items


def resolve_agent_descriptor(
    agent_id: str | None = None,
    agent_name: str | None = None,
    *,
    include_builtin: bool = True,
) -> AgentDescriptor | None:
    wanted_id = (agent_id or "").strip()
    wanted_name = (agent_name or "").strip()
    if not wanted_id and not wanted_name:
        return None

    if include_builtin:
        builtin = builtin_naga_descriptor()
        if wanted_id == builtin.id:
            return builtin
        if wanted_name and wanted_name.strip().lower() in _NAGA_BUILTIN_NAMES:
            return builtin

    all_agents = list_agent_descriptors(include_builtin=include_builtin)
    if wanted_id:
        for item in all_agents:
            if item.id == wanted_id:
                return item

    if wanted_name:
        wanted_name_lower = wanted_name.lower()
        exact = [item for item in all_agents if item.name.lower() == wanted_name_lower]
        if exact:
            return exact[0]
        fuzzy = [item for item in all_agents if wanted_name_lower in item.name.lower()]
        if len(fuzzy) == 1:
            return fuzzy[0]

    return None


def format_agent_directory_text() -> str:
    lines = []
    for item in list_agent_descriptors(include_builtin=True):
        extra = []
        if item.builtin:
            extra.append("builtin")
        extra.append(item.engine)
        if item.character_template:
            extra.append(f"template={item.character_template}")
        lines.append(f"- {item.name} | id={item.id} | {' | '.join(extra)}")
    return "\n".join(lines) if lines else "(无干员)"
