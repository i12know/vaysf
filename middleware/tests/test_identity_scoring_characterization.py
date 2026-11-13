"""Characterization tests for the identity scoring used by two callers (#311).

These pin what `check-consent` (`sync.consent_checker`) and
`investigate-consent-404s` (`sync.consent_404_investigator`) compute today.
They were written against the code *before* the scoring moved into
`sync.identity_scoring`, and reach it only through each caller's own names, so
the same file passing unchanged after the move is the proof that neither
caller's behaviour changed.

Do not "fix" an expectation here to make a refactor pass. A different score,
field order or strength label changes who gets a consent box ticked in
ChMeetings, or how a stale ID is classified.
"""

import itertools
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sync import consent_404_investigator as investigator_module
from sync import consent_checker as checker_module
from sync.consent_checker import ConsentChecker

FIELDS = ("birthdate", "email", "phone", "name")
WEIGHTS = {"birthdate": 33, "email": 27, "phone": 24, "name": 16}
FIELD_SUBSETS = [
    subset
    for size in range(len(FIELDS) + 1)
    for subset in itertools.combinations(FIELDS, size)
]

# What the 404 investigator calls each combination of matching fields.
# "strong" needs a score of 49+ AND a birthdate or exact-name anchor; that
# second half is what keeps relatives sharing a phone and email apart.
EXPECTED_STRENGTH = {
    (): "",
    ("birthdate",): "weak",
    ("email",): "weak",
    ("phone",): "weak",
    ("name",): "weak",
    ("birthdate", "email"): "strong",
    ("birthdate", "phone"): "strong",
    ("birthdate", "name"): "strong",
    ("email", "phone"): "possible",
    ("email", "name"): "possible",
    ("phone", "name"): "possible",
    ("birthdate", "email", "phone"): "strong",
    ("birthdate", "email", "name"): "strong",
    ("birthdate", "phone", "name"): "strong",
    ("email", "phone", "name"): "strong",
    ("birthdate", "email", "phone", "name"): "strong",
}


def _wp_participant(**overrides):
    participant = {
        "participant_id": 10,
        "chmeetings_id": 3630880,
        "first_name": "Jerry",
        "last_name": "Phan",
        "email": "jerry@example.com",
        "phone": "562-555-0101",
        "birthdate": "2008-04-15",
        "church_code": "RPC",
        "created_at": "2026-05-17 10:00:00",
        "updated_at": "2026-05-19 17:00:00",
    }
    participant.update(overrides)
    return participant


def _other_participant(matching):
    """A second WordPress row that agrees with `_wp_participant()` only on `matching`."""
    return _wp_participant(
        participant_id=11,
        chmeetings_id=4000001,
        birthdate="2008-04-15" if "birthdate" in matching else "2010-01-02",
        email="jerry@example.com" if "email" in matching else "other@example.com",
        phone="562-555-0101" if "phone" in matching else "714-555-0199",
        first_name="Jerry" if "name" in matching else "Khoa",
    )


# ── Weights and thresholds ───────────────────────────────────────────────────


def test_weights_and_thresholds_are_pinned():
    assert checker_module.CONSENT_SCORE_WEIGHTS == WEIGHTS
    assert investigator_module.CONSENT_SCORE_WEIGHTS == WEIGHTS
    assert sum(WEIGHTS.values()) == 100
    assert checker_module.CONSENT_THRESHOLD == 51
    assert checker_module.CONSENT_THRESHOLD_GUARDIAN == 49


# ── Normalizers shared by both callers ───────────────────────────────────────


@pytest.mark.parametrize(
    "value, expected",
    [
        ("  Jerry   PHAN ", "jerry phan"),
        ("Nguyễn", "nguyễn"),  # lowercased, diacritics kept
        (None, ""),
        ("", ""),
        (0, ""),
        (123, "123"),
    ],
)
def test_normalize_text(value, expected):
    assert checker_module._normalize_text(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("(562) 555-0101", "5625550101"),
        ("562.555.0101", "5625550101"),
        ("+1 562 555 0101", "15625550101"),  # the country code is not stripped
        (None, ""),
        ("n/a", ""),
    ],
)
def test_normalize_phone(value, expected):
    assert checker_module._normalize_phone(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2008-04-15", "2008-04-15"),
        ("04/15/2008", "2008-04-15"),
        ("2008-04-15 00:00:00", "2008-04-15"),
        ("", ""),
        (None, ""),
        (float("nan"), ""),
        ("not a date", ""),
    ],
)
def test_normalize_birthdate(value, expected):
    assert checker_module._normalize_birthdate(value) == expected


def test_full_name_joins_and_normalizes():
    assert checker_module._full_name(" Jerry ", "PHAN") == "jerry phan"
    assert checker_module._full_name(None, "Phan") == "phan"
    assert checker_module._full_name(None, None) == ""
    # Diacritics are significant to both existing callers.
    assert checker_module._full_name("Ngọc", "Lê") != checker_module._full_name("Ngoc", "Le")


# ── check-consent: consent row vs participant ────────────────────────────────


def _consent_row(matching):
    return {
        "athlete_birthdate": "2008-04-15" if "birthdate" in matching else "2010-01-02",
        "athlete_email": "jerry@example.com" if "email" in matching else "other@example.com",
        "athlete_phone": "5625550101" if "phone" in matching else "7145550199",
        "normalized_signer_name": "jerry phan" if "name" in matching else "khoa phan",
    }


@pytest.mark.parametrize("matching", FIELD_SUBSETS)
def test_consent_checker_score_for_every_field_combination(matching):
    checker = ConsentChecker(MagicMock(), MagicMock())

    score, breakdown = checker._score(_consent_row(matching), _wp_participant())

    assert score == sum(WEIGHTS[field] for field in matching)
    assert breakdown == {
        field: WEIGHTS[field] if field in matching else 0 for field in FIELDS
    }
    # The audit column is built from this order.
    assert list(breakdown) == ["birthdate", "phone", "email", "name"]


def test_consent_checker_empty_values_never_match():
    checker = ConsentChecker(MagicMock(), MagicMock())
    blank_row = {
        "athlete_birthdate": "",
        "athlete_email": "",
        "athlete_phone": "",
        "normalized_signer_name": "",
    }
    blank_participant = _wp_participant(
        first_name="", last_name="", email="", phone="", birthdate=""
    )

    score, breakdown = checker._score(blank_row, blank_participant)

    assert score == 0
    assert set(breakdown.values()) == {0}


def test_consent_checker_breakdown_display_format():
    assert (
        checker_module._format_breakdown({"birthdate": 33, "phone": 0, "email": 27, "name": 0})
        == "birthdate=33, phone=0, email=27, name=0"
    )


# ── investigate-consent-404s: identity records ───────────────────────────────


def test_identity_from_wp_participant_exact_shape():
    identity = investigator_module._identity_from_wp_participant(
        _wp_participant(first_name=" Ngọc ", last_name="Lê", phone="(562) 555-0101")
    )

    assert identity == {
        "source": "wordpress",
        "participant_id": "10",
        "chmeetings_id": "3630880",
        "first_name": "Ngọc",
        "last_name": "Lê",
        "name": "Ngọc  Lê",
        "name_norm": "ngọc lê",
        "email": "jerry@example.com",
        "email_norm": "jerry@example.com",
        "phone": "(562) 555-0101",
        "phone_norm": "5625550101",
        "birthdate": "2008-04-15",
        "church_code": "RPC",
        "created_at": "2026-05-17 10:00:00",
        "updated_at": "2026-05-19 17:00:00",
    }


def test_identity_from_empty_wp_participant_is_all_blank():
    identity = investigator_module._identity_from_wp_participant({})

    assert identity.pop("source") == "wordpress"
    assert set(identity.values()) == {""}


def test_identity_from_chm_person_exact_shape():
    identity = investigator_module._identity_from_chm_person(
        {
            "id": 9999999,
            "first_name": "Jerry",
            "last_name": "Phan",
            "email": "Jerry@Example.com",
            "mobile": "562-555-0101",
            "birth_date": "2008-04-15T00:00:00",
            "created_on": "2026-05-17T10:00:00+00:00",
            "updated_on": "2026-05-19T17:00:00+00:00",
        }
    )

    assert identity == {
        "source": "chmeetings",
        "participant_id": "",
        "chmeetings_id": "9999999",
        "first_name": "Jerry",
        "last_name": "Phan",
        "name": "Jerry Phan",
        "name_norm": "jerry phan",
        "email": "Jerry@Example.com",
        "email_norm": "jerry@example.com",
        "phone": "562-555-0101",
        "phone_norm": "5625550101",
        "birthdate": "2008-04-15",
        "church_code": "",
        "created_at": "2026-05-17T10:00:00+00:00",
        "updated_at": "2026-05-19T17:00:00+00:00",
    }


def test_identity_from_chm_person_falls_back_to_birthdate_key():
    identity = investigator_module._identity_from_chm_person(
        {"id": "1", "birthdate": "2008-04-15"}
    )

    assert identity["birthdate"] == "2008-04-15"


# ── investigate-consent-404s: pair score and strength ────────────────────────


@pytest.mark.parametrize("matching", FIELD_SUBSETS)
def test_investigator_score_and_strength_for_every_field_combination(matching):
    stale = investigator_module._identity_from_wp_participant(_wp_participant())
    candidate = investigator_module._identity_from_wp_participant(
        _other_participant(matching)
    )

    score, breakdown, basis = investigator_module._score_identity_match(stale, candidate)

    assert score == sum(WEIGHTS[field] for field in matching)
    assert breakdown == {
        field: WEIGHTS[field] if field in matching else 0 for field in FIELDS
    }
    # "Match Basis" in the workbook is this list, in this order.
    assert list(breakdown) == ["birthdate", "email", "phone", "name"]
    assert basis == list(matching)
    assert investigator_module._candidate_strength(score, basis) == EXPECTED_STRENGTH[matching]


def test_investigator_empty_values_never_match():
    blank = investigator_module._identity_from_wp_participant({})

    score, breakdown, basis = investigator_module._score_identity_match(blank, dict(blank))

    assert (score, basis) == (0, [])
    assert set(breakdown.values()) == {0}


def test_investigator_names_differing_only_by_diacritics_do_not_match():
    plain = investigator_module._identity_from_wp_participant(
        _wp_participant(first_name="Ngoc", last_name="Le")
    )
    accented = investigator_module._identity_from_wp_participant(
        _wp_participant(first_name="Ngọc", last_name="Lê")
    )

    _, breakdown, basis = investigator_module._score_identity_match(plain, accented)

    assert breakdown["name"] == 0
    assert "name" not in basis


@pytest.mark.parametrize(
    "score, basis, expected",
    [
        (49, ["birthdate", "name"], "strong"),  # exactly at the strong floor
        (48, ["birthdate", "name"], "possible"),  # one point under it
        (49, ["birthdate"], "strong"),  # an anchor is enough once the score is there
        (51, ["email", "phone"], "possible"),  # family share: high score, no anchor
        (100, ["email", "phone"], "possible"),  # no score rescues a missing anchor
        (27, ["email", "phone"], "possible"),  # exactly at the possible floor
        (26, ["email", "phone"], "weak"),
        (33, ["birthdate"], "weak"),  # one field is never more than weak below 49
        (33, ["birthdate", "birthdate"], "weak"),  # repeated field counts once
        (1, [], "weak"),
        (0, [], ""),
        (0, ["birthdate"], ""),
    ],
)
def test_candidate_strength_boundaries(score, basis, expected):
    assert investigator_module._candidate_strength(score, basis) == expected


def test_strength_rank_and_basis_display():
    ranks = [
        investigator_module._strength_rank(strength)
        for strength in ("strong", "possible", "weak", "", "anything else")
    ]

    assert ranks == [0, 1, 2, 3, 3]
    assert investigator_module._format_basis(["birthdate", "email"]) == "birthdate, email"
    assert investigator_module._format_basis([]) == ""
