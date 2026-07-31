"""Load and resolve operator-confirmed ChMeetings person aliases."""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

from loguru import logger

from config import Config

AliasEntry = Dict[str, str]
AliasMap = Dict[str, AliasEntry]
_METADATA_FIELDS = ("reason", "confirmed_by", "confirmed_on", "note")


class PersonAliasError(ValueError):
    """The configured alias map is unsafe to use."""


def _chm_id(value: Any, label: str) -> str:
    if value is None or isinstance(value, bool):
        raise PersonAliasError(f"{label} must be a non-empty ChMeetings ID")
    normalized = str(value).strip()
    if not normalized:
        raise PersonAliasError(f"{label} must be a non-empty ChMeetings ID")
    return normalized


def _entry(stale_id: str, raw: Any) -> AliasEntry:
    if isinstance(raw, dict):
        canonical_id = _chm_id(raw.get("canonical_chm_id"), f"alias {stale_id}")
        entry = {field: str(raw.get(field, "") or "").strip() for field in _METADATA_FIELDS}
    elif isinstance(raw, (str, int)) and not isinstance(raw, bool):
        canonical_id = _chm_id(raw, f"alias {stale_id}")
        entry = {field: "" for field in _METADATA_FIELDS}
    else:
        raise PersonAliasError(
            f"alias {stale_id} must be a canonical ID or an object with canonical_chm_id"
        )

    if canonical_id == stale_id:
        raise PersonAliasError(f"alias {stale_id} cannot point to itself")
    return {"canonical_chm_id": canonical_id, **entry}


def resolve_chm_id(chm_id: Any, aliases: Optional[AliasMap]) -> str:
    """Resolve an ID through an alias chain and reject cycles."""
    current = _chm_id(chm_id, "chm_id")
    if not aliases:
        return current

    seen = []
    while current in aliases:
        if current in seen:
            cycle = " -> ".join([*seen, current])
            raise PersonAliasError(f"person alias cycle: {cycle}")
        seen.append(current)
        current = _chm_id(
            aliases[current].get("canonical_chm_id"),
            f"alias {current}",
        )
    return current


def load_person_aliases(path: Optional[Union[str, Path]] = None) -> AliasMap:
    """Load a strict stale-ID to canonical-ID map.

    A missing file means no aliases. An existing malformed file fails closed so
    sync cannot silently recreate identities that were previously retired.
    """
    alias_path = Path(path or Config.PERSON_ALIASES_FILE)
    if not alias_path.exists():
        return {}

    try:
        raw_aliases = json.loads(alias_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PersonAliasError(f"cannot load person aliases from {alias_path}: {exc}") from exc

    if not isinstance(raw_aliases, dict):
        raise PersonAliasError(f"person aliases in {alias_path} must be a JSON object")

    aliases: AliasMap = {}
    for raw_stale_id, raw_entry in raw_aliases.items():
        stale_id = _chm_id(raw_stale_id, "alias key")
        if stale_id in aliases:
            raise PersonAliasError(f"duplicate normalized alias key: {stale_id}")
        aliases[stale_id] = _entry(stale_id, raw_entry)

    for stale_id in aliases:
        resolve_chm_id(stale_id, aliases)

    if aliases:
        logger.info(f"[VAY SM] Loaded {len(aliases)} person alias(es) from {alias_path}")
    return aliases
