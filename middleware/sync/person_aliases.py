# Begin of sync/person_aliases.py
"""Canonical ChMeetings identity — the person alias map (Issue #308).

Phase 1 of ``docs/CANONICAL_IDENTITY_RFC.md`` §4.1–§4.2: a small,
operator-maintained map of "stale ChMeetings ID -> canonical ChMeetings ID",
applied once at the front door of the participant sync so the rest of the
system never sees a duplicate identity again.

The map is *never* written by code (guardrail G3). Real entries live in the
git-ignored ``middleware/data/person_aliases.local.json``; only an empty
example is committed (guardrail G5).

Two behaviours are binding (guardrail G2):

* Chains resolve transitively — ``A -> B`` and ``B -> C`` resolves ``A`` to ``C``.
* Cycles are a **hard failure**. ``A -> B -> A`` is operator error, and the
  sync refuses to run rather than guess which end of the loop is the person.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loguru import logger

from config import Config

# Maximum alias hops before we treat the map as pathological. A chain this long
# in a hand-maintained file is a mistake, not a legitimate merge history.
MAX_ALIAS_CHAIN_DEPTH = 50


class PersonAliasError(Exception):
    """Raised when the alias map is structurally unusable (e.g. contains a cycle)."""


def _normalize_chm_id(value: Any) -> str:
    """Return a ChMeetings ID as a trimmed string ('' when absent)."""
    if value is None or isinstance(value, bool):
        return ""
    return str(value).strip()


def _normalize_entry(chm_id: str, entry_raw: Any) -> Optional[Dict[str, Any]]:
    """Normalize one alias entry into a dict, or None when it should be ignored."""
    if isinstance(entry_raw, dict):
        canonical_chm_id = _normalize_chm_id(entry_raw.get("canonical_chm_id"))
        if not canonical_chm_id:
            logger.warning(
                f"[VAY SM] Ignoring person alias for chm_id={chm_id}: "
                "object entry is missing a non-empty 'canonical_chm_id'."
            )
            return None
        entry = {
            "canonical_chm_id": canonical_chm_id,
            "reason": str(entry_raw.get("reason", "") or "").strip(),
            "confirmed_by": str(entry_raw.get("confirmed_by", "") or "").strip(),
            "confirmed_on": str(entry_raw.get("confirmed_on", "") or "").strip(),
            "note": str(entry_raw.get("note", "") or "").strip(),
        }
    elif isinstance(entry_raw, (str, int)) and not isinstance(entry_raw, bool):
        # Shorthand form: {"3634001": "3633885"}
        canonical_chm_id = _normalize_chm_id(entry_raw)
        if not canonical_chm_id:
            logger.warning(
                f"[VAY SM] Ignoring person alias for chm_id={chm_id}: "
                "shorthand entry resolves to an empty canonical ID."
            )
            return None
        entry = {
            "canonical_chm_id": canonical_chm_id,
            "reason": "",
            "confirmed_by": "",
            "confirmed_on": "",
            "note": "",
        }
    else:
        logger.warning(
            f"[VAY SM] Ignoring person alias for chm_id={chm_id}: "
            f"expected a string or object, got {type(entry_raw).__name__}."
        )
        return None

    if entry["canonical_chm_id"] == chm_id:
        logger.warning(
            f"[VAY SM] Ignoring person alias for chm_id={chm_id}: "
            "an ID cannot be an alias of itself."
        )
        return None

    return entry


def _assert_no_cycles(aliases: Dict[str, Dict[str, Any]]) -> None:
    """Raise PersonAliasError if any alias chain loops back on itself."""
    for start_id in aliases:
        seen: List[str] = [start_id]
        seen_set = {start_id}
        current = start_id
        while current in aliases:
            current = aliases[current]["canonical_chm_id"]
            if current in seen_set:
                chain = " -> ".join(seen + [current])
                raise PersonAliasError(
                    f"[VAY SM] Person alias map contains a cycle: {chain}. "
                    "A cyclic alias map is operator error — the sync refuses to run "
                    "until it is corrected."
                )
            seen.append(current)
            seen_set.add(current)
            if len(seen) > MAX_ALIAS_CHAIN_DEPTH:
                raise PersonAliasError(
                    f"[VAY SM] Person alias chain starting at chm_id={start_id} exceeds "
                    f"{MAX_ALIAS_CHAIN_DEPTH} hops. Refusing to run on a map this deep; "
                    "collapse the chain to its terminal canonical ID."
                )


def load_person_aliases(
    path: Optional[Union[str, Path]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Load the stale-to-canonical ChMeetings ID map, keyed by stale ChMeetings ID.

    Follows the ``_load_late_racquet_overrides`` pattern: a missing file is the
    normal case and yields ``{}``; unparseable or wrongly-shaped JSON warns and
    yields ``{}`` so a typo never takes the sync down.

    A *cycle*, however, is not survivable — it raises :class:`PersonAliasError`
    (guardrail G2), because silently dropping half a loop would merge two people
    in whichever direction the file happened to be written.

    Args:
        path: Optional explicit path. Defaults to ``Config.PERSON_ALIASES_FILE``.

    Returns:
        Dict[str, Dict[str, Any]]: stale chm_id -> normalized alias entry, each
        with at least a non-empty ``canonical_chm_id``.

    Raises:
        PersonAliasError: if the map contains an alias cycle or a pathological chain.
    """
    alias_path = path if path is not None else getattr(Config, "PERSON_ALIASES_FILE", None)
    if not alias_path:
        return {}

    try:
        with open(alias_path, "r", encoding="utf-8") as handle:
            raw_aliases = json.load(handle)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        logger.warning(
            f"[VAY SM] Could not parse person aliases file '{alias_path}': {exc}. "
            "Ignoring person aliases for this run."
        )
        return {}

    if not isinstance(raw_aliases, dict):
        logger.warning(
            f"[VAY SM] Person aliases file '{alias_path}' must contain a JSON object. "
            "Ignoring person aliases for this run."
        )
        return {}

    aliases: Dict[str, Dict[str, Any]] = {}
    for chm_id_raw, entry_raw in raw_aliases.items():
        chm_id = _normalize_chm_id(chm_id_raw)
        if not chm_id:
            continue

        entry = _normalize_entry(chm_id, entry_raw)
        if entry is None:
            continue

        aliases[chm_id] = entry

    _assert_no_cycles(aliases)

    if aliases:
        logger.info(
            f"[VAY SM] Loaded {len(aliases)} person alias(es) from '{alias_path}'."
        )

    return aliases


def resolve_chm_id(chm_id: Any, aliases: Optional[Dict[str, Dict[str, Any]]]) -> str:
    """Resolve a ChMeetings ID to its terminal canonical ID.

    Follows alias chains transitively (``A -> B``, ``B -> C`` resolves ``A`` to
    ``C``) with a visited set. An empty or missing map returns the input
    unchanged, which is what makes landing this a no-op (RFC §3, property 3).

    Args:
        chm_id: The ChMeetings ID to resolve.
        aliases: The map returned by :func:`load_person_aliases`.

    Returns:
        str: The canonical ChMeetings ID (the input, stringified, when unaliased).

    Raises:
        PersonAliasError: if resolution loops. ``load_person_aliases`` already
            rejects cyclic maps, so this is a defensive backstop for callers that
            assemble a map some other way.
    """
    current = _normalize_chm_id(chm_id)
    if not aliases or not current:
        return current

    seen = [current]
    seen_set = {current}
    while current in aliases:
        current = aliases[current]["canonical_chm_id"]
        if current in seen_set:
            chain = " -> ".join(seen + [current])
            raise PersonAliasError(
                f"[VAY SM] Person alias cycle while resolving chm_id={seen[0]}: {chain}."
            )
        seen.append(current)
        seen_set.add(current)
        if len(seen) > MAX_ALIAS_CHAIN_DEPTH:
            raise PersonAliasError(
                f"[VAY SM] Person alias chain starting at chm_id={seen[0]} exceeds "
                f"{MAX_ALIAS_CHAIN_DEPTH} hops."
            )

    return current

# End of sync/person_aliases.py
