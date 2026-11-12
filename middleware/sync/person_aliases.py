"""Load and resolve operator-confirmed ChMeetings person aliases."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from loguru import logger

from config import BASE_DIR, Config

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


def _map_chm_id(value: Any, label: str) -> str:
    """A ChMeetings ID as written in the alias file: ASCII digits only.

    ChMeetings person IDs are integers. A typo such as ``36260O0`` would
    otherwise load cleanly and make that person silently stop syncing.
    """
    normalized = _chm_id(value, label)
    if not (normalized.isascii() and normalized.isdigit()):
        raise PersonAliasError(
            f"{label} must be a numeric ChMeetings ID, got {normalized!r}"
        )
    return normalized


def _reject_repeated_keys(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    """json object hook: a key listed twice is an error, not last-one-wins."""
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PersonAliasError(f"repeated key {key!r} in person alias file")
        result[key] = value
    return result


def _entry(stale_id: str, raw: Any) -> AliasEntry:
    if isinstance(raw, dict):
        canonical_id = _map_chm_id(raw.get("canonical_chm_id"), f"alias {stale_id}")
        entry = {field: str(raw.get(field, "") or "").strip() for field in _METADATA_FIELDS}
    elif isinstance(raw, (str, int)) and not isinstance(raw, bool):
        canonical_id = _map_chm_id(raw, f"alias {stale_id}")
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
    if not alias_path.is_absolute():
        alias_path = BASE_DIR / alias_path
    if not alias_path.exists():
        # Still an empty map by decision (#308), but never a silent one: this
        # line is how an operator notices the file is not where sync looks.
        logger.info(f"[VAY SM] Loaded 0 person aliases (file not found at {alias_path})")
        return {}

    try:
        # utf-8-sig: a byte-order mark (Windows PowerShell 5.1, some editors) is
        # not an error. Any other encoding, e.g. UTF-16 from a `>` redirect, is.
        raw_aliases = json.loads(
            alias_path.read_text(encoding="utf-8-sig"),
            object_pairs_hook=_reject_repeated_keys,
        )
    except UnicodeDecodeError as exc:
        raise PersonAliasError(
            f"cannot load person aliases from {alias_path}: the file is not UTF-8 "
            f"({exc.reason}); re-save it as UTF-8"
        ) from exc
    except PersonAliasError as exc:
        raise PersonAliasError(f"cannot load person aliases from {alias_path}: {exc}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise PersonAliasError(f"cannot load person aliases from {alias_path}: {exc}") from exc

    if not isinstance(raw_aliases, dict):
        raise PersonAliasError(f"person aliases in {alias_path} must be a JSON object")

    aliases: AliasMap = {}
    for raw_stale_id, raw_entry in raw_aliases.items():
        stale_id = _map_chm_id(raw_stale_id, "alias key")
        if stale_id in aliases:
            raise PersonAliasError(f"duplicate normalized alias key: {stale_id}")
        aliases[stale_id] = _entry(stale_id, raw_entry)

    for stale_id in aliases:
        resolve_chm_id(stale_id, aliases)

    logger.info(f"[VAY SM] Loaded {len(aliases)} person alias(es) from {alias_path}")
    return aliases


def load_person_aliases_for_reader(consumer: str) -> AliasMap:
    """Load the alias map for a read-side consumer that must stay available.

    Participant sync and ``apply-aliases`` fail closed on a malformed map (#308
    decision). Validation, consent checking and the church-team export were
    deliberately left runnable in that situation, so they use this wrapper: the
    problem is reported loudly and the consumer continues on raw ChMeetings IDs.
    ``merged`` WordPress rows are still excluded by those consumers either way.
    """
    try:
        return load_person_aliases()
    except PersonAliasError as exc:
        logger.error(
            f"[VAY SM] Person alias map is unusable ({exc}); {consumer} continues "
            "WITHOUT alias resolution. Fix the file and rerun."
        )
        return {}
