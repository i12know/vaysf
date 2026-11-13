"""Keep ``repair-form-people`` from recreating a retired (merged) person (#388).

``apply-aliases`` retires a duplicate by tombstoning its WordPress participant
(``approval_status == merged``). The tombstone keeps the retired name, email,
phone and birthdate. If the original form row is still in the export and the
retired ChMeetings person is gone, ``repair-form-people`` would otherwise see
"no live match", create a third ChMeetings person and put it in a Team group,
under an ID the alias map knows nothing about.

This module answers one question per form row: does it look like a tombstoned
person? It compares with the shared ``sync.identity_scoring`` instrument and
does not have a matcher of its own.

- A ``strong`` match (``candidate_strength``) blocks the row. So does a
  ``possible`` match that rests on a birthdate or exact-name anchor plus a
  second field (name + email, name + phone): ``candidate_strength`` scores
  those 43 and 40, under its strong cutoff of 49, yet they are the retired
  person, not a household.
- A match on contact details alone (email + phone) never blocks. Siblings
  share a parent's email and phone, so a younger sibling's first registration
  must not be stopped by an older sibling's tombstone. It is reported as a note.

Names are compared without diacritics ("Đức Phạm" == "Duc Pham"); the names
shown to the operator are the ones as registered.

The WordPress read fails closed: :func:`load_merged_tombstones` raises
:class:`MergedIdentityReadError` rather than returning a short list, because a
short list would read as "nobody was merged" and let the create go ahead.
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import requests
from loguru import logger
from tenacity import RetryError

from config import APPROVAL_STATUS
from sync.duplicate_finder import duplicate_name_key
from sync.identity_scoring import (
    STRENGTH_POSSIBLE,
    STRENGTH_STRONG,
    candidate_strength,
    format_basis,
    has_identity_anchor,
    identity_from_wp_participant,
    normalize_birthdate,
    normalize_phone,
    normalize_text,
    score_identity_match,
)

TENANT = "VAY SM"
_ENDPOINT = "wordpress GET /participants"
_PAGE_SIZE = 100  # the plugin caps per_page at 100
_MAX_PAGES = 200

BLOCKED_OUTCOME = "blocked_merged_identity"
NEXT_STEP = (
    "Check whether this is the merged person before creating. "
    "If it is, add an alias instead."
)


class MergedIdentityReadError(RuntimeError):
    """The merged-participant list could not be read completely."""


@dataclass(frozen=True)
class MergedMatch:
    """One form row compared against one tombstone."""

    strength: str
    score: int
    basis: List[str]
    tombstone: Dict[str, str]  # identity record from identity_from_wp_participant

    def tombstone_label(self) -> str:
        chm_id = self.tombstone["chmeetings_id"] or "none on record"
        return (
            f"merged WordPress participant_id={self.tombstone['participant_id']} "
            f"(ChMeetings ID {chm_id}, registered as {self.tombstone['name']!r})"
        )

    def block_detail(self, extra_matches: int = 0) -> str:
        more = f" and {extra_matches} other merged participant(s)" if extra_matches else ""
        return (
            f"Matches {self.tombstone_label()}{more}. "
            f"Match basis: {format_basis(self.basis)} (score {self.score}). {NEXT_STEP}"
        )

    def contact_note(self) -> str:
        return (
            f"Note: shares {format_basis(self.basis)} with {self.tombstone_label()}, "
            "with no matching birthdate or name; treated as a different person "
            "(siblings share a parent's contact details)."
        )


def load_merged_tombstones(wp_connector: Any) -> List[Dict[str, Any]]:
    """Every WordPress participant whose status is ``merged``. Fails closed.

    The participants endpoint has no status filter, so this pages through all
    of them, as ``find-duplicates`` does. Any failed page, or a total that
    falls short of what WordPress reported, raises
    :class:`MergedIdentityReadError`.
    """
    started = time.monotonic()
    participants: List[Dict[str, Any]] = []
    for page in range(1, _MAX_PAGES + 1):
        wp_connector.last_get_participants_status = "unknown"
        try:
            batch = wp_connector.get_participants({"page": page, "per_page": _PAGE_SIZE})
        except (RetryError, requests.RequestException) as exc:
            _log_read(started, "failed", len(participants))
            raise MergedIdentityReadError(
                f"WordPress participants page {page} could not be read ({exc.__class__.__name__})"
            ) from exc
        if getattr(wp_connector, "last_get_participants_status", None) == "failed":
            _log_read(started, "failed", len(participants))
            raise MergedIdentityReadError(f"WordPress participants page {page} could not be read")
        batch = batch or []
        participants.extend(batch)
        if len(batch) < _PAGE_SIZE:
            break
    else:
        _log_read(started, "failed", len(participants))
        raise MergedIdentityReadError(
            f"WordPress has more than {_MAX_PAGES * _PAGE_SIZE} participants; "
            "the merged list cannot be loaded completely"
        )

    # The connector keeps WordPress's X-WP-Total here; 0 means "not reported".
    total = getattr(wp_connector, "total_participants", None)
    if isinstance(total, int) and total > len(participants):
        _log_read(started, "incomplete", len(participants))
        raise MergedIdentityReadError(
            f"loaded {len(participants)} WordPress participant(s) but WordPress reported {total}"
        )

    tombstones = [p for p in participants if _is_merged(p)]
    _log_read(started, "ok", len(participants), merged=len(tombstones))
    return tombstones


def _log_read(started: float, status: str, loaded: int, merged: Optional[int] = None) -> None:
    detail = f" merged={merged}" if merged is not None else ""
    log = logger.info if status == "ok" else logger.error
    log(
        f"[{TENANT}] scope=church endpoint={_ENDPOINT} status={status} "
        f"duration_ms={int((time.monotonic() - started) * 1000)} "
        f"participants={loaded}{detail} purpose=repair-form-people merged-identity guard"
    )


def _is_merged(participant: Dict[str, Any]) -> bool:
    return str(participant.get("approval_status") or "").strip().lower() == APPROVAL_STATUS["MERGED"]


class MergedIdentityGuard:
    """Compare form rows with the merged tombstones, one identity record each."""

    def __init__(self, tombstones: Sequence[Dict[str, Any]]) -> None:
        self._tombstones = [
            identity_from_wp_participant(p, name_key=duplicate_name_key)
            for p in tombstones
            if _is_merged(p)
        ]

    def __len__(self) -> int:
        return len(self._tombstones)

    @staticmethod
    def _row_identity(row: Dict[str, str]) -> Dict[str, str]:
        return {
            "name_norm": duplicate_name_key(row.get("first_name", ""), row.get("last_name", "")),
            "email_norm": normalize_text(row.get("email", "")),
            "phone_norm": normalize_phone(row.get("mobile_phone", "")),
            "birthdate": normalize_birthdate(row.get("birth_date", "")),
        }

    def check(self, row: Dict[str, str]) -> "MergeCheck":
        """Matches that block the row, and contact-only matches that only get a note."""
        identity = self._row_identity(row)
        blocking: List[MergedMatch] = []
        contact_only: List[MergedMatch] = []
        for tombstone in self._tombstones:
            score, _, basis = score_identity_match(identity, tombstone)
            strength = candidate_strength(score, basis)
            match = MergedMatch(strength, score, basis, tombstone)
            if strength == STRENGTH_STRONG:
                blocking.append(match)
            elif strength == STRENGTH_POSSIBLE:
                # candidate_strength reserves "strong" for score >= 49, so a
                # name + email (43) or name + phone (40) pair is only
                # "possible". Two fields including an anchor is still the
                # retired person's identity, not a household's contact details.
                if has_identity_anchor(basis):
                    blocking.append(match)
                else:
                    contact_only.append(match)
        return MergeCheck(blocking=_best_first(blocking), contact_only=_best_first(contact_only))


def _best_first(matches: List[MergedMatch]) -> List[MergedMatch]:
    def key(match: MergedMatch) -> Any:
        pid = match.tombstone["participant_id"]
        return (-match.score, int(pid) if pid.isdigit() else 0, pid)

    return sorted(matches, key=key)


@dataclass(frozen=True)
class MergeCheck:
    blocking: List[MergedMatch]
    contact_only: List[MergedMatch]

    @property
    def blocked(self) -> bool:
        return bool(self.blocking)

    def block_detail(self) -> str:
        return self.blocking[0].block_detail(extra_matches=len(self.blocking) - 1)

    def contact_note(self) -> str:
        """Note for a row that is created anyway; empty when there is nothing to say."""
        return self.contact_only[0].contact_note() if self.contact_only else ""
