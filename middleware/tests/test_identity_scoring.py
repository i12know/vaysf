"""Tests for the shared identity scoring module (#311).

What the scoring *computes* is pinned by
`test_identity_scoring_characterization.py`, through its original callers.
These tests cover the module's own contract: both callers run the shared
code, not a copy, and the module stays free of I/O.
"""

import ast
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sync import consent_404_investigator as investigator_module
from sync import consent_checker as checker_module
from sync import identity_scoring


def test_both_callers_use_the_shared_objects_not_copies():
    assert checker_module.CONSENT_SCORE_WEIGHTS is identity_scoring.IDENTITY_SCORE_WEIGHTS
    assert checker_module._normalize_text is identity_scoring.normalize_text
    assert checker_module._normalize_phone is identity_scoring.normalize_phone
    assert checker_module._normalize_birthdate is identity_scoring.normalize_birthdate
    assert checker_module._full_name is identity_scoring.full_name

    assert investigator_module.CONSENT_SCORE_WEIGHTS is identity_scoring.IDENTITY_SCORE_WEIGHTS
    assert (
        investigator_module._identity_from_wp_participant
        is identity_scoring.identity_from_wp_participant
    )
    assert investigator_module._score_identity_match is identity_scoring.score_identity_match
    assert investigator_module._candidate_strength is identity_scoring.candidate_strength
    assert investigator_module._strength_rank is identity_scoring.strength_rank
    assert investigator_module._format_basis is identity_scoring.format_basis


def test_weights_and_strength_floors():
    assert identity_scoring.IDENTITY_SCORE_WEIGHTS == {
        "birthdate": 33,
        "email": 27,
        "phone": 24,
        "name": 16,
    }
    assert identity_scoring.STRONG_MIN_SCORE == 49
    assert identity_scoring.POSSIBLE_MIN_SCORE == 27
    assert identity_scoring.ANCHOR_FIELDS == {"birthdate", "name"}


@pytest.mark.parametrize(
    "basis, anchored",
    [
        (["birthdate"], True),
        (["name"], True),
        (["email", "phone", "name"], True),
        (["email", "phone"], False),  # a shared household contact is not an anchor
        (["email"], False),
        ([], False),
    ],
)
def test_has_identity_anchor(basis, anchored):
    assert identity_scoring.has_identity_anchor(basis) is anchored


def test_identity_name_key_is_pluggable_and_display_fields_are_untouched():
    participant = {"first_name": "Ngọc", "last_name": "Lê"}

    default = identity_scoring.identity_from_wp_participant(participant)
    custom = identity_scoring.identity_from_wp_participant(
        participant, name_key=lambda first, last: f"{last}|{first}".upper()
    )

    assert default["name_norm"] == "ngọc lê"
    assert custom["name_norm"] == "LÊ|NGỌC"
    assert custom["name"] == default["name"] == "Ngọc Lê"
    assert custom["first_name"] == "Ngọc"
    assert custom["last_name"] == "Lê"


def test_module_imports_no_connector_and_no_project_code():
    """A pure comparison module: it must not be able to reach an API."""
    tree = ast.parse(Path(identity_scoring.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])

    assert imported == {"typing", "pandas"}
