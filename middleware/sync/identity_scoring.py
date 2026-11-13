"""Shared identity scoring: is this record the same human as that one?

One instrument, three readers (#311, docs/CANONICAL_IDENTITY_RFC.md §4.4):

- ``check-consent`` (``sync.consent_checker``) uses the weights to match a
  consent-form row to a participant.
- ``investigate-consent-404s`` (``sync.consent_404_investigator``) uses the
  identity record, the pair score and the strength rule to find the live
  replacement for a stale ChMeetings ID.
- ``find-duplicates`` (``sync.duplicate_finder``) runs the same pair score and
  strength rule across every live WordPress participant.

This module only compares records. It reads nothing and writes nothing, and
it imports no connector. Its behaviour for the first two readers is pinned by
``tests/test_identity_scoring_characterization.py``.
"""

from typing import Any, Callable, Dict, Iterable, List, Tuple

import pandas as pd

# Points for an exact match on each field. They sum to 100.
IDENTITY_SCORE_WEIGHTS = {
    "birthdate": 33,
    "email": 27,
    "phone": 24,
    "name": 16,
}

# Fields that identify the person rather than the household. A phone number
# and an email address are routinely shared by siblings and by a parent who
# registers the children, so neither can make a match "strong" by itself.
ANCHOR_FIELDS = frozenset({"birthdate", "name"})

# Name + birthdate (16 + 33) is the lowest-scoring pair that carries an anchor.
STRONG_MIN_SCORE = 49
# Email alone (27) is the floor, and it also takes two matching fields.
POSSIBLE_MIN_SCORE = 27

STRENGTH_STRONG = "strong"
STRENGTH_POSSIBLE = "possible"
STRENGTH_WEAK = "weak"


def safe_str(value: Any) -> str:
    return str(value or "").strip()


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def normalize_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def normalize_birthdate(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
        return ""

    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.date().isoformat()


def full_name(first_name: Any, last_name: Any) -> str:
    """Matching key for a name: lowercased, whitespace collapsed, diacritics kept."""
    return normalize_text(f"{first_name or ''} {last_name or ''}")


def identity_from_wp_participant(
    participant: Dict[str, Any],
    name_key: Callable[[Any, Any], str] = full_name,
) -> Dict[str, str]:
    """The comparable identity record for one WordPress participant row.

    ``name_key`` builds the matching key for the name. The default keeps
    diacritics significant, which is what the consent tools have always done;
    ``find-duplicates`` passes a diacritic-insensitive key. Display fields
    (``first_name``, ``last_name``, ``name``) are never normalized.
    """
    return {
        "source": "wordpress",
        "participant_id": safe_str(participant.get("participant_id")),
        "chmeetings_id": safe_str(participant.get("chmeetings_id")),
        "first_name": safe_str(participant.get("first_name")),
        "last_name": safe_str(participant.get("last_name")),
        "name": safe_str(
            f"{participant.get('first_name', '') or ''} {participant.get('last_name', '') or ''}"
        ),
        "name_norm": name_key(
            participant.get("first_name", ""), participant.get("last_name", "")
        ),
        "email": safe_str(participant.get("email")),
        "email_norm": normalize_text(participant.get("email", "")),
        "phone": safe_str(participant.get("phone")),
        "phone_norm": normalize_phone(participant.get("phone", "")),
        "birthdate": normalize_birthdate(participant.get("birthdate")),
        "church_code": safe_str(participant.get("church_code")),
        "created_at": safe_str(participant.get("created_at")),
        "updated_at": safe_str(participant.get("updated_at")),
    }


def score_identity_match(
    left: Dict[str, str], right: Dict[str, str]
) -> Tuple[int, Dict[str, int], List[str]]:
    """Score two identity records: ``(score, per-field points, matching fields)``.

    A field scores only when it is present on both sides and equal. A blank
    never matches a blank.
    """
    breakdown = {
        "birthdate": IDENTITY_SCORE_WEIGHTS["birthdate"]
        if left["birthdate"] and left["birthdate"] == right["birthdate"]
        else 0,
        "email": IDENTITY_SCORE_WEIGHTS["email"]
        if left["email_norm"] and left["email_norm"] == right["email_norm"]
        else 0,
        "phone": IDENTITY_SCORE_WEIGHTS["phone"]
        if left["phone_norm"] and left["phone_norm"] == right["phone_norm"]
        else 0,
        "name": IDENTITY_SCORE_WEIGHTS["name"]
        if left["name_norm"] and left["name_norm"] == right["name_norm"]
        else 0,
    }
    basis = [field for field, weight in breakdown.items() if weight]
    return sum(breakdown.values()), breakdown, basis


def has_identity_anchor(basis: Iterable[str]) -> bool:
    """True when the match rests on a birthdate or an exact name, not only contacts."""
    return bool(ANCHOR_FIELDS & set(basis))


def candidate_strength(score: int, basis: List[str]) -> str:
    basis_set = set(basis)
    # Family members often share phone/email, so require at least one
    # identity anchor (birthdate or exact full name) before calling a
    # replacement candidate "strong".
    if score >= STRONG_MIN_SCORE and has_identity_anchor(basis_set):
        return STRENGTH_STRONG
    if score >= POSSIBLE_MIN_SCORE and len(basis_set) >= 2:
        return STRENGTH_POSSIBLE
    if score > 0:
        return STRENGTH_WEAK
    return ""


def format_basis(basis: List[str]) -> str:
    return ", ".join(basis)


def strength_rank(strength: str) -> int:
    return {
        STRENGTH_STRONG: 0,
        STRENGTH_POSSIBLE: 1,
        STRENGTH_WEAK: 2,
        "": 3,
    }.get(strength, 3)
