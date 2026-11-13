"""Mock-mode tests for `find-duplicates` (#311, Canonical Identity RFC §4.4).

Every person here is synthetic. The names echo the cases the RFC describes
("Ngoc Le / Khoa Le", two "Justin Nguyen"s) and carry no real data.
"""

import ast
import itertools
import json
import os
import random
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main
from sync import duplicate_finder as finder_module
from sync.alias_reconciler import apply_aliases
from sync.duplicate_finder import (
    DUPLICATE_AUDIT_FILE,
    NOT_PROPOSED_COLUMNS,
    NOT_PROPOSED_SHEET,
    PROPOSAL_COLUMNS,
    PROPOSALS_SHEET,
    DuplicateFinder,
    duplicate_name_key,
)
from sync.identity_scoring import candidate_strength, identity_from_wp_participant, score_identity_match
from sync.person_aliases import PersonAliasError, load_person_aliases, resolve_chm_id
from wordpress.frontend_connector import WordPressConnector

READ_METHODS = {"get_participants", "get_rosters"}


def _participant(participant_id, chm_id, **overrides):
    participant = {
        "participant_id": participant_id,
        "chmeetings_id": chm_id,
        "first_name": "Ngoc",
        "last_name": "Le",
        "email": "ngoc@example.com",
        "phone": "562-555-0101",
        "birthdate": "2008-04-15",
        "gender": "Female",
        "church_code": "RPC",
        "approval_status": "pending",
        "consent_status": None,
        "created_at": "2026-05-01 10:00:00",
        "updated_at": "2026-05-01 10:00:00",
    }
    participant.update(overrides)
    return participant


def _ngoc_and_khoa():
    """The acceptance pair: same birthdate, email and phone; different names."""
    return [
        _participant(10, "3633885", first_name="Ngoc", approval_status="approved"),
        _participant(11, "3634002", first_name="Khoa", phone="(562) 555-0101"),
    ]


def _wp(participants, rosters_by_participant=None):
    """A WordPress connector that can only be read, serving `participants` in pages."""
    wp = MagicMock(spec=WordPressConnector)
    rosters_by_participant = rosters_by_participant or {}

    def get_participants(params=None):
        page, per_page = params["page"], params["per_page"]
        return participants[(page - 1) * per_page : page * per_page]

    wp.get_participants.side_effect = get_participants
    wp.get_rosters.side_effect = lambda params=None: rosters_by_participant.get(
        params["participant_id"], []
    )
    return wp


def _run(mocker, tmp_path, participants, *, aliases=None, rosters=None):
    """Run the finder against a mock connector and read the workbook it wrote."""
    mocker.patch("sync.duplicate_finder.load_person_aliases", return_value=aliases or {})
    wp = _wp(participants, rosters)
    summary = DuplicateFinder(wp, output_dir=tmp_path).run()
    assert summary["error"] == 0
    sheets = pd.read_excel(summary["output_file"], sheet_name=None, dtype=str)
    proposals = sheets[PROPOSALS_SHEET].fillna("").to_dict("records")
    not_proposed = sheets[NOT_PROPOSED_SHEET].fillna("").to_dict("records")
    return summary, proposals, not_proposed, wp


def _snippet_as_alias_map(tmp_path, *snippets):
    """Paste snippets into an alias file the way the operator would, and load it."""
    path = tmp_path / "person_aliases.local.json"
    path.write_text("{\n  " + ",\n  ".join(snippets) + "\n}\n", encoding="utf-8")
    return path, load_person_aliases(path)


# ── Acceptance (#311) ────────────────────────────────────────────────────────


def test_same_birthdate_email_phone_different_names_is_a_strong_proposal(mocker, tmp_path):
    summary, proposals, not_proposed, _ = _run(mocker, tmp_path, _ngoc_and_khoa())

    assert (summary["strong"], summary["possible"], summary["not_proposed"]) == (1, 0, 0)
    assert not_proposed == []
    [row] = proposals
    assert row["Strength"] == "strong"
    assert row["Score"] == "84"  # 33 + 27 + 24, nothing from the name
    assert row["Match Basis"] == "birthdate, email, phone"
    assert row["Canonical ChM ID"] == "3633885"
    assert row["Stale ChM ID"] == "3634002"
    assert row["Canonical Pick Basis"] == "approved"
    assert "Names differ" in row["Review Notes"]
    assert row["Alias Map Snippet"] == (
        '"3634002": {"canonical_chm_id": "3633885", '
        '"reason": "find-duplicates: strong match, score 84 (birthdate, email, phone)", '
        '"confirmed_by": "", "confirmed_on": "", "note": "Khoa Le / Ngoc Le"}'
    )


def test_snippet_loads_through_the_real_alias_loader(mocker, tmp_path):
    _, [row], _, _ = _run(mocker, tmp_path, _ngoc_and_khoa())

    _, aliases = _snippet_as_alias_map(tmp_path, row["Alias Map Snippet"])

    assert resolve_chm_id("3634002", aliases) == "3633885"
    assert aliases["3634002"]["note"] == "Khoa Le / Ngoc Le"
    # A proposal is not a confirmation: those two fields are the operator's.
    assert aliases["3634002"]["confirmed_by"] == ""
    assert aliases["3634002"]["confirmed_on"] == ""


def test_pasted_snippet_drives_apply_aliases(mocker, tmp_path):
    """The proposal feeds the existing workflow: paste, then `apply-aliases`."""
    participants = _ngoc_and_khoa()
    _, [row], _, _ = _run(mocker, tmp_path, participants)
    alias_path, _ = _snippet_as_alias_map(tmp_path, row["Alias Map Snippet"])
    mocker.patch("sync.person_aliases.Config.PERSON_ALIASES_FILE", alias_path)

    by_chm_id = {p["chmeetings_id"]: p for p in participants}
    connector = MagicMock()
    connector.__enter__.return_value = connector
    connector.get_participants.side_effect = lambda params=None: [
        by_chm_id[params["chmeetings_id"]]
    ]
    connector.get_rosters.return_value = [{"roster_id": 1}]
    connector.get_approvals.return_value = []
    connector.get_validation_issues.return_value = []
    mocker.patch("sync.alias_reconciler.WordPressConnector", return_value=connector)
    mocker.patch("sync.alias_reconciler._badge_filename", return_value="stale.png")
    audit = mocker.patch("sync.alias_reconciler._write_audit")

    assert apply_aliases(execute=False) is True

    [reconciled] = audit.call_args.args[0]
    assert reconciled["Outcome"] == "would_reconcile"
    assert reconciled["Stale ChM ID"] == "3634002"
    assert reconciled["Canonical ChM ID"] == "3633885"
    assert reconciled["Stale WP Participant ID"] == 11
    assert reconciled["Approval Mismatch"] == "no"  # the approved row was kept


def test_merged_rows_are_excluded(mocker, tmp_path):
    participants = _ngoc_and_khoa()
    participants[1]["approval_status"] = "merged"

    summary, proposals, not_proposed, _ = _run(mocker, tmp_path, participants)

    assert proposals == [] and not_proposed == []
    assert (summary["live"], summary["skipped_merged"]) == (1, 1)


# ── Siblings and shared household contacts (Registrant Trust RFC Q6, D12) ────


@pytest.mark.parametrize(
    "older_born, younger_born",
    [
        ("2008-04-15", "2010-09-01"),  # two teenagers
        ("2012-03-02", "2015-11-20"),  # one 14, one 10-12 (Scripture Memorization)
        ("2015-01-10", "2016-06-30"),  # both 10-12: neither has a phone of their own
    ],
)
def test_siblings_sharing_a_parents_phone_and_email_are_never_strong(
    mocker, tmp_path, older_born, younger_born
):
    siblings = [
        _participant(20, "4000001", first_name="An", last_name="Tran", birthdate=older_born,
                     email="parent@example.com", phone="714-555-0100", gender="Male"),
        _participant(21, "4000002", first_name="Binh", last_name="Tran", birthdate=younger_born,
                     email="parent@example.com", phone="714-555-0100", gender="Male"),
    ]

    summary, proposals, not_proposed, wp = _run(mocker, tmp_path, siblings)

    assert summary["strong"] == 0
    assert proposals == []  # so there is no snippet to paste
    [row] = not_proposed
    assert row["Score"] == "51"  # email + phone, the family-share signature
    assert row["Match Basis"] == "email, phone"
    assert row["Why Not Proposed"].startswith("Shared contact only")
    wp.get_rosters.assert_not_called()  # no pick is made for a pair that is not proposed


def test_family_share_rule_is_the_shared_anchor_rule():
    """The finder does not carry its own copy of the rule."""
    older, younger = (
        identity_from_wp_participant(p, name_key=duplicate_name_key)
        for p in (
            _participant(20, "4000001", first_name="An", birthdate="2008-04-15"),
            _participant(21, "4000002", first_name="Binh", birthdate="2010-09-01"),
        )
    )

    score, _, basis = score_identity_match(older, younger)

    assert (score, basis) == (51, ["email", "phone"])
    assert candidate_strength(score, basis) == "possible"


def test_three_siblings_and_a_real_duplicate_in_one_household(mocker, tmp_path):
    """A duplicate of one child is found; the siblings around it are not merged."""
    household = dict(last_name="Tran", email="parent@example.com", phone="714-555-0100")
    participants = [
        _participant(20, "4000001", first_name="An", birthdate="2008-04-15", **household),
        _participant(21, "4000002", first_name="Binh", birthdate="2010-09-01", **household),
        _participant(22, "4000003", first_name="Chi", birthdate="2014-02-11", **household),
        # Binh registered again.
        _participant(23, "4000009", first_name="Binh", birthdate="2010-09-01", **household),
    ]

    _, proposals, not_proposed, _ = _run(mocker, tmp_path, participants)

    [row] = proposals
    assert {row["Canonical ChM ID"], row["Stale ChM ID"]} == {"4000002", "4000009"}
    assert (row["Strength"], row["Score"]) == ("strong", "100")
    assert "Phone shared by 4 live participants." in row["Review Notes"]
    assert "Email shared by 4 live participants." in row["Review Notes"]
    assert len(not_proposed) == 5  # every other pair in the household
    assert all(r["Why Not Proposed"].startswith("Shared contact only") for r in not_proposed)


def test_brother_and_sister_twins_are_not_proposed(mocker, tmp_path):
    twins = [
        _participant(30, "4100001", first_name="Minh", gender="Male"),
        _participant(31, "4100002", first_name="Mai", gender="Female"),
    ]

    _, proposals, not_proposed, _ = _run(mocker, tmp_path, twins)

    assert proposals == []
    [row] = not_proposed
    assert row["Why Not Proposed"] == "Genders differ (Male / Female)."
    assert row["Score"] == "84"


@pytest.mark.parametrize(
    "second, expected_score, expected_basis",
    [
        # Same name and birthdate, new contacts.
        ({"email": "other@example.com", "phone": "999-999-9999"}, "49", "birthdate, name"),
        # The pair from the first live run: all four fields agree.
        ({}, "100", "birthdate, email, phone, name"),
        # The name agrees only once diacritics are removed.
        ({"first_name": "Ngọc", "last_name": "Lê", "email": "other@example.com",
          "phone": "999-999-9999"}, "49", "birthdate, name"),
    ],
)
def test_same_name_and_birthdate_with_different_genders_is_proposed(
    mocker, tmp_path, second, expected_score, expected_basis
):
    """#395: a matching name makes a gender disagreement a typo, not a twin."""
    participants = [
        _participant(32, "4110001", gender="Female", approval_status="approved"),
        _participant(33, "4110002", gender="Male", **second),
    ]

    _, proposals, not_proposed, _ = _run(mocker, tmp_path, participants)

    assert not_proposed == []
    [row] = proposals
    assert (row["Strength"], row["Score"], row["Match Basis"]) == (
        "strong", expected_score, expected_basis,
    )
    assert (
        "Genders differ (Female / Male): likely a data-entry error. "
        "Fix the gender in ChMeetings before applying the alias."
    ) in row["Review Notes"]
    _, aliases = _snippet_as_alias_map(tmp_path, row["Alias Map Snippet"])
    assert resolve_chm_id("4110002", aliases) == "4110001"


def test_same_name_and_gender_carries_no_gender_note(mocker, tmp_path):
    participants = [
        _participant(32, "4110001", gender="Female"),
        _participant(33, "4110002", gender="female"),  # case is not a disagreement
        _participant(34, "4110003", gender=""),  # nor is a blank
    ]

    _, proposals, not_proposed, _ = _run(mocker, tmp_path, participants)

    assert len(proposals) == 3 and not_proposed == []
    assert all("Genders differ" not in row["Review Notes"] for row in proposals)


def test_shared_contact_only_pair_is_unchanged_by_a_gender_difference(mocker, tmp_path):
    """Brother and sister of different ages on a parent's phone and email."""
    siblings = [
        _participant(20, "4000001", first_name="An", birthdate="2008-04-15", gender="Male"),
        _participant(21, "4000002", first_name="Chi", birthdate="2012-03-02", gender="Female"),
    ]

    _, proposals, not_proposed, _ = _run(mocker, tmp_path, siblings)

    assert proposals == []
    [row] = not_proposed
    assert row["Why Not Proposed"].startswith("Shared contact only")
    assert "Genders differ" not in row["Why Not Proposed"]
    assert "Genders differ" not in row["Review Notes"]


def test_same_gender_twins_cannot_be_told_apart_and_are_flagged_for_review(mocker, tmp_path):
    """Known limit, pinned on purpose.

    Twins of the same gender registered by one parent carry exactly the data
    of the "Ngoc Le / Khoa Le" duplicate. The scoring cannot separate them; the
    row says so, and guardrail G3 leaves the decision with the operator.
    """
    twins = [
        _participant(30, "4100001", first_name="Minh", gender="Male"),
        _participant(31, "4100002", first_name="Manh", gender="Male"),
    ]

    _, [row], _, _ = _run(mocker, tmp_path, twins)

    assert row["Strength"] == "strong"
    assert "or twins/relatives sharing a household's contact details?" in row["Review Notes"]


def test_two_different_people_with_the_same_name_are_not_listed(mocker, tmp_path):
    participants = [
        _participant(40, "4200001", first_name="Justin", last_name="Nguyen",
                     birthdate="2005-01-01", email="j1@example.com", phone="111-111-1111"),
        _participant(41, "4200002", first_name="Justin", last_name="Nguyen",
                     birthdate="2007-07-07", email="j2@example.com", phone="222-222-2222"),
    ]

    summary, proposals, not_proposed, _ = _run(mocker, tmp_path, participants)

    assert summary["pairs_scored"] == 1  # compared, scored 16 (weak), dropped
    assert proposals == [] and not_proposed == []


# ── Names ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "accented, plain",
    [
        (("Ngọc", "Lê"), ("Ngoc", "Le")),
        (("Thảo", "Nguyễn"), ("thao", "NGUYEN")),
        (("Hồng", "Phạm"), ("Hong", "Pham")),
        (("Trâm", "Trần"), ("Tram", "Tran")),
        (("Hải", "Hồ"), ("Hai", "Ho")),
        (("Đức", "Đinh"), ("Duc", "Dinh")),
    ],
)
def test_diacritic_variants_of_a_name_match_and_display_keeps_the_original(
    mocker, tmp_path, accented, plain
):
    participants = [
        _participant(50, "4300001", first_name=accented[0], last_name=accented[1],
                     email="first@example.com", phone="111-111-1111"),
        _participant(51, "4300002", first_name=plain[0], last_name=plain[1],
                     email="second@example.com", phone="222-222-2222",
                     updated_at="2026-06-01 10:00:00"),
    ]

    _, [row], _, _ = _run(mocker, tmp_path, participants)

    assert (row["Strength"], row["Score"], row["Match Basis"]) == ("strong", "49", "birthdate, name")
    assert "Names match only after removing diacritics." in row["Review Notes"]
    assert row["Stale Name"] == f"{accented[0]} {accented[1]}"
    assert row["Canonical Name"] == f"{plain[0]} {plain[1]}"
    # The pasted note keeps the Vietnamese spelling, not \u escapes.
    assert f"{accented[0]} {accented[1]} / {plain[0]} {plain[1]}" in row["Alias Map Snippet"]
    _, aliases = _snippet_as_alias_map(tmp_path, row["Alias Map Snippet"])
    assert aliases["4300001"]["note"].startswith(f"{accented[0]} {accented[1]}")


def test_identical_names_carry_no_diacritic_note(mocker, tmp_path):
    participants = [
        _participant(50, "4300001", email="first@example.com", phone="111-111-1111"),
        _participant(51, "4300002", email="second@example.com", phone="222-222-2222"),
    ]

    _, [row], _, _ = _run(mocker, tmp_path, participants)

    assert "diacritics" not in row["Review Notes"]
    assert "Names differ" not in row["Review Notes"]


def test_name_anchored_possible_match_is_proposed_with_its_caveats(mocker, tmp_path):
    """Same name and email, new phone, different birthdate on file: worth a look."""
    participants = [
        _participant(60, "4400001", church_code="RPC"),
        _participant(61, "4400002", phone="999-999-9999", birthdate="2008-04-16",
                     church_code="WAG"),
    ]

    summary, [row], _, _ = _run(mocker, tmp_path, participants)

    assert (summary["strong"], summary["possible"]) == (0, 1)
    assert (row["Strength"], row["Score"], row["Match Basis"]) == ("possible", "43", "email, name")
    assert "Birthdates differ." in row["Review Notes"]
    assert "Different churches." in row["Review Notes"]
    assert row["Alias Map Snippet"].startswith('"')


# ── Canonical pick: approved > has rosters > most recent update ──────────────


@pytest.mark.parametrize(
    "first, second, rosters, expected_canonical, expected_basis",
    [
        # Approved beats rosters and recency.
        ({"approval_status": "approved"},
         {"updated_at": "2026-07-01 10:00:00"}, {2: [{"roster_id": 9}]},
         "501", "approved"),
        # Neither approved: the row with rosters beats the more recent one.
        ({}, {"updated_at": "2026-07-01 10:00:00"}, {1: [{"roster_id": 9}]},
         "501", "has rosters"),
        # Both approved, both with rosters: most recent update.
        ({"approval_status": "approved"},
         {"approval_status": "approved", "updated_at": "2026-07-01 10:00:00"},
         {1: [{"roster_id": 8}], 2: [{"roster_id": 9}]},
         "502", "most recent update"),
        # Nothing separates them: deterministic tie-break, flagged.
        ({}, {}, {}, "502", "tie-break: newer ChMeetings ID"),
        # A missing timestamp loses to a real one.
        ({"updated_at": ""}, {"updated_at": "2026-01-01 00:00:00"}, {},
         "502", "most recent update"),
        # Pending-approval is not approved.
        ({"approval_status": "pending_approval", "updated_at": "2026-07-01 10:00:00"},
         {"approval_status": "approved"}, {},
         "502", "approved"),
    ],
)
def test_canonical_pick(mocker, tmp_path, first, second, rosters, expected_canonical, expected_basis):
    participants = [
        _participant(1, "501", **first),
        _participant(2, "502", first_name="Khoa", **second),
    ]

    _, [row], _, _ = _run(mocker, tmp_path, participants, rosters=rosters)

    assert row["Canonical ChM ID"] == expected_canonical
    assert row["Stale ChM ID"] == ({"501", "502"} - {expected_canonical}).pop()
    assert row["Canonical Pick Basis"] == expected_basis
    assert ("Confirm it." in row["Review Notes"]) is expected_basis.startswith("tie-break")
    assert row["Alias Map Snippet"].startswith(f'"{row["Stale ChM ID"]}": ')


def test_roster_columns_and_all_team_orders_lookup(mocker, tmp_path):
    _, [row], _, wp = _run(
        mocker, tmp_path, _ngoc_and_khoa(), rosters={11: [{"roster_id": 9}]}
    )

    assert (row["Canonical Has Rosters"], row["Stale Has Rosters"]) == ("no", "yes")
    assert sorted(call.args[0]["participant_id"] for call in wp.get_rosters.call_args_list) == [10, 11]
    assert all(call.args[0]["all_team_orders"] == 1 for call in wp.get_rosters.call_args_list)


def test_roster_read_failure_is_unknown_not_no(mocker, tmp_path):
    mocker.patch("sync.duplicate_finder.load_person_aliases", return_value={})
    participants = [
        _participant(1, "501"),
        _participant(2, "502", first_name="Khoa", updated_at="2026-07-01 10:00:00"),
    ]
    wp = _wp(participants)
    wp.get_rosters.side_effect = requests.ConnectionError("boom")

    summary = DuplicateFinder(wp, output_dir=tmp_path).run()

    assert summary["error"] == 0  # still a usable proposal
    row = pd.read_excel(summary["output_file"], sheet_name=PROPOSALS_SHEET, dtype=str).iloc[0]
    assert (row["Canonical Has Rosters"], row["Stale Has Rosters"]) == ("unknown", "unknown")
    assert row["Canonical Pick Basis"] == "most recent update"
    assert "Roster lookup failed" in row["Review Notes"]


def test_consent_on_the_stale_row_only_is_called_out(mocker, tmp_path):
    """Registrant Trust RFC D9: consent carries across a confirmed merge."""
    participants = [
        _participant(1, "501", approval_status="approved", consent_status=None),
        _participant(2, "502", first_name="Khoa", consent_status="1"),
    ]

    _, [row], _, _ = _run(mocker, tmp_path, participants)

    assert (row["Canonical Consent On File"], row["Stale Consent On File"]) == ("no", "yes")
    assert "Consent is on file for the stale row only." in row["Review Notes"]
    assert "no new signature" in row["Review Notes"]


def test_no_consent_note_when_the_canonical_row_has_consent(mocker, tmp_path):
    participants = [
        _participant(1, "501", approval_status="approved", consent_status=1),
        _participant(2, "502", first_name="Khoa", consent_status=1),
    ]

    _, [row], _, _ = _run(mocker, tmp_path, participants)

    assert "Consent is on file" not in row["Review Notes"]


# ── The alias map: read to skip, never written ───────────────────────────────


def _alias(canonical):
    return {"canonical_chm_id": canonical, "reason": "", "confirmed_by": "", "confirmed_on": "", "note": ""}


def test_already_aliased_ids_are_skipped(mocker, tmp_path):
    summary, proposals, not_proposed, _ = _run(
        mocker, tmp_path, _ngoc_and_khoa(), aliases={"3634002": _alias("3633885")}
    )

    assert proposals == [] and not_proposed == []
    assert (summary["live"], summary["skipped_aliased"]) == (1, 1)


def test_proposal_onto_an_existing_alias_target_says_it_chains(mocker, tmp_path):
    participants = [
        _participant(1, "501"),  # already the canonical target of 400 -> 501
        _participant(2, "502", first_name="Khoa", approval_status="approved"),
    ]

    _, [row], _, _ = _run(mocker, tmp_path, participants, aliases={"400": _alias("501")})

    assert (row["Canonical ChM ID"], row["Stale ChM ID"]) == ("502", "501")
    assert "already the canonical target of an existing alias" in row["Review Notes"]
    # Pasted next to the existing entry it is a valid chain, not a cycle.
    path = tmp_path / "chain.json"
    path.write_text('{"400": "501", ' + row["Alias Map Snippet"] + "}", encoding="utf-8")
    assert resolve_chm_id("400", load_person_aliases(path)) == "502"


def test_three_registrations_of_one_person_flag_the_repeated_stale_id(mocker, tmp_path):
    participants = [
        _participant(1, "501", approval_status="approved"),
        _participant(2, "502", updated_at="2026-06-01 10:00:00"),
        _participant(3, "503"),
    ]

    _, proposals, _, _ = _run(mocker, tmp_path, participants)

    assert sorted((r["Stale ChM ID"], r["Canonical ChM ID"]) for r in proposals) == [
        ("502", "501"), ("503", "501"), ("503", "502"),
    ]
    repeated = [r for r in proposals if r["Stale ChM ID"] == "503"]
    assert all("stale side of 2 proposals; use at most one" in r["Review Notes"] for r in repeated)
    [single] = [r for r in proposals if r["Stale ChM ID"] == "502"]
    assert "stale side of" not in single["Review Notes"]
    # One entry per stale ID is a loadable map that sends everything to 501.
    _, aliases = _snippet_as_alias_map(
        tmp_path,
        single["Alias Map Snippet"],
        next(r for r in repeated if r["Canonical ChM ID"] == "501")["Alias Map Snippet"],
    )
    assert {resolve_chm_id(i, aliases) for i in ("501", "502", "503")} == {"501"}
    # Pasting both entries for 503 is refused by the loader, not silently merged.
    with pytest.raises(PersonAliasError, match="repeated key"):
        _snippet_as_alias_map(tmp_path, *(r["Alias Map Snippet"] for r in repeated))


def test_malformed_alias_map_fails_closed_before_any_read(mocker, tmp_path):
    mocker.patch(
        "sync.duplicate_finder.load_person_aliases", side_effect=PersonAliasError("bad json")
    )
    wp = _wp(_ngoc_and_khoa())

    summary = DuplicateFinder(wp, output_dir=tmp_path).run()

    assert summary["error"] == 1
    assert summary["output_file"] == ""
    assert wp.method_calls == []
    assert not (tmp_path / DUPLICATE_AUDIT_FILE).exists()


def test_rows_without_a_numeric_chmeetings_id_are_skipped(mocker, tmp_path):
    participants = [
        _participant(1, "501"),
        _participant(2, "", first_name="Khoa"),
        _participant(3, None, first_name="Khoa"),
        _participant(4, "36260O0", first_name="Khoa"),  # letter O: not an ID the map accepts
    ]

    summary, proposals, not_proposed, _ = _run(mocker, tmp_path, participants)

    assert proposals == [] and not_proposed == []
    assert (summary["live"], summary["skipped_no_chm_id"]) == (1, 3)


# ── Guardrail G3: propose, never write ───────────────────────────────────────


def test_run_only_reads_wordpress_and_leaves_the_alias_file_untouched(mocker, tmp_path):
    alias_path = tmp_path / "person_aliases.local.json"
    alias_path.write_text('{"400": "501"}', encoding="utf-8")
    mocker.patch("sync.person_aliases.Config.PERSON_ALIASES_FILE", alias_path)
    before = alias_path.read_bytes()
    out_dir = tmp_path / "out"
    wp = _wp(
        _ngoc_and_khoa()
        + [_participant(20, "4000001", first_name="An", birthdate="2010-09-01")]
    )

    summary = DuplicateFinder(wp, output_dir=out_dir).run()

    assert summary["error"] == 0 and summary["strong"] == 1
    assert {call[0] for call in wp.method_calls} == READ_METHODS
    assert alias_path.read_bytes() == before
    assert [p.name for p in out_dir.iterdir()] == [DUPLICATE_AUDIT_FILE]


def test_module_cannot_reach_chmeetings_or_a_wordpress_write():
    source = Path(finder_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not any(name.startswith(("chmeetings", "wordpress")) for name in imported)

    # Connector methods are called by name through _read(); those names are
    # string literals, and they must all be reads.
    connector_methods = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith(("get_", "update_", "create_", "delete_", "add_", "remove_"))
        and node.value.isidentifier()
    }
    assert connector_methods == READ_METHODS
    attribute_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not any(
        name.startswith(("update_", "create_", "delete_", "add_", "remove_"))
        for name in attribute_calls
    )


# ── Reads, paging, blocking, output ──────────────────────────────────────────


def test_a_duplicate_split_across_pages_is_found(mocker, tmp_path):
    fillers = [
        _participant(1000 + i, str(900000 + i), first_name=f"Filler{i}", last_name="Person",
                     email=f"filler{i}@example.com", phone=f"800-000-{i:04d}",
                     birthdate=(pd.Timestamp("1995-01-01") + pd.Timedelta(days=i)).date().isoformat())
        for i in range(120)
    ]
    ngoc, khoa = _ngoc_and_khoa()

    summary, [row], _, wp = _run(mocker, tmp_path, [ngoc, *fillers, khoa])

    assert summary["participants"] == 122
    assert [call.args[0]["page"] for call in wp.get_participants.call_args_list] == [1, 2]
    assert {row["Canonical ChM ID"], row["Stale ChM ID"]} == {"3633885", "3634002"}


@pytest.mark.parametrize("failure", ["raises", "status_failed"])
def test_participant_read_failure_writes_no_workbook(mocker, tmp_path, failure):
    mocker.patch("sync.duplicate_finder.load_person_aliases", return_value={})
    wp = MagicMock(spec=WordPressConnector)
    if failure == "raises":
        wp.get_participants.side_effect = requests.ConnectionError("boom")
    else:
        def failed_read(params=None):
            wp.last_get_participants_status = "failed"
            return []

        wp.get_participants.side_effect = failed_read

    summary = DuplicateFinder(wp, output_dir=tmp_path).run()

    assert summary["error"] == 1
    assert not (tmp_path / DUPLICATE_AUDIT_FILE).exists()


def test_blocking_finds_exactly_the_pairs_a_full_comparison_would(mocker, tmp_path):
    rng = random.Random(311)
    first_names = ["An", "Binh", "Chi", "Dung"]
    participants = [
        _participant(
            i,
            str(700000 + i),
            first_name=rng.choice(first_names),
            last_name=rng.choice(["Tran", "Le"]),
            email=rng.choice(["a@example.com", "b@example.com", "c@example.com", ""]),
            phone=rng.choice(["111-111-1111", "222-222-2222", "333-333-3333", ""]),
            birthdate=rng.choice(["2008-04-15", "2010-09-01", "2012-03-02", ""]),
            gender="",
        )
        for i in range(1, 41)
    ]
    records = [identity_from_wp_participant(p, name_key=duplicate_name_key) for p in participants]
    expected = set()
    for left, right in itertools.combinations(records, 2):
        score, _, basis = score_identity_match(left, right)
        if candidate_strength(score, basis) in ("strong", "possible"):
            expected.add(frozenset((left["chmeetings_id"], right["chmeetings_id"])))

    _, proposals, not_proposed, _ = _run(mocker, tmp_path, participants)

    listed = {frozenset((r["Canonical ChM ID"], r["Stale ChM ID"])) for r in proposals}
    listed |= {frozenset((r["A ChM ID"], r["B ChM ID"])) for r in not_proposed}
    assert expected and listed == expected


def test_workbook_layout_and_ordering(mocker, tmp_path):
    participants = [
        *_ngoc_and_khoa(),  # strong, 84
        _participant(60, "4400001", first_name="Lan", birthdate="2001-01-01",
                     email="lan@example.com", phone="300-000-0001"),
        _participant(61, "4400002", first_name="Lan", birthdate="2001-01-02",
                     email="lan@example.com", phone="300-000-0002"),  # possible, 43
        _participant(62, "4500001", first_name="Vy", birthdate="2002-02-02",
                     email="vy1@example.com", phone="300-000-0003"),
        _participant(63, "4500002", first_name="Vy", birthdate="2002-02-02",
                     email="vy2@example.com", phone="300-000-0004"),  # strong, 49
    ]

    summary, proposals, _, _ = _run(mocker, tmp_path, participants)

    sheets = pd.read_excel(summary["output_file"], sheet_name=None, dtype=str)
    assert list(sheets) == [PROPOSALS_SHEET, NOT_PROPOSED_SHEET, "How To Use"]
    assert list(sheets[PROPOSALS_SHEET].columns) == PROPOSAL_COLUMNS
    assert list(sheets[NOT_PROPOSED_SHEET].columns) == NOT_PROPOSED_COLUMNS  # headers even when empty
    assert [(r["Strength"], r["Score"]) for r in proposals] == [
        ("strong", "84"), ("strong", "49"), ("possible", "43"),
    ]
    how_to = " ".join(sheets["How To Use"].iloc[:, 0])
    assert "changed nothing" in how_to and "apply-aliases" in how_to
    # One line per snippet: Excel re-quotes a copied cell that contains a line break.
    assert all("\n" not in r["Alias Map Snippet"] for r in proposals)


def test_unwritable_workbook_is_an_error(mocker, tmp_path):
    mocker.patch("sync.duplicate_finder.load_person_aliases", return_value={})
    mocker.patch("sync.duplicate_finder.pd.ExcelWriter", side_effect=PermissionError("open in Excel"))

    summary = DuplicateFinder(_wp(_ngoc_and_khoa()), output_dir=tmp_path).run()

    assert summary["error"] == 1
    assert summary["output_file"] == ""


def test_output_path_override(mocker, tmp_path):
    mocker.patch("sync.duplicate_finder.load_person_aliases", return_value={})
    target = tmp_path / "nested" / "review.xlsx"

    summary = DuplicateFinder(_wp(_ngoc_and_khoa()), output_dir=tmp_path).run(output_file=str(target))

    assert summary["output_file"] == str(target)
    assert target.exists()


def test_snippet_is_valid_json_for_awkward_names():
    stale = {"chmeetings_id": "2", "name": 'Anh "AJ" O\'Brien\\'}
    canonical = {"chmeetings_id": "1", "name": "Đức Đinh"}

    snippet = finder_module.alias_snippet(stale, canonical, "why")

    assert json.loads("{" + snippet + "}") == {
        "2": {
            "canonical_chm_id": "1",
            "reason": "why",
            "confirmed_by": "",
            "confirmed_on": "",
            "note": 'Anh "AJ" O\'Brien\\ / Đức Đinh',
        }
    }


# ── CLI ──────────────────────────────────────────────────────────────────────


def test_parse_args_find_duplicates(monkeypatch):
    monkeypatch.setattr(main.sys, "argv", ["main.py", "find-duplicates"])
    args = main.parse_args()
    assert (args.command, args.output) == ("find-duplicates", None)

    monkeypatch.setattr(main.sys, "argv", ["main.py", "find-duplicates", "--output", "x.xlsx"])
    assert main.parse_args().output == "x.xlsx"


@pytest.mark.parametrize("errors, exit_code", [(0, 0), (1, 1)])
def test_main_dispatches_find_duplicates_without_chmeetings(monkeypatch, mocker, errors, exit_code):
    monkeypatch.setattr(main.sys, "argv", ["main.py", "find-duplicates", "--output", "x.xlsx"])
    wp = MagicMock()
    wp.__enter__.return_value = wp
    mocker.patch("main.WordPressConnector", return_value=wp)
    chm = mocker.patch("main.ChMeetingsConnector")
    finder = mocker.patch("sync.duplicate_finder.DuplicateFinder")
    finder.return_value.run.return_value = {"error": errors}

    with pytest.raises(SystemExit) as exc:
        main.main()

    assert exc.value.code == exit_code
    finder.assert_called_once_with(wp)
    finder.return_value.run.assert_called_once_with(output_file="x.xlsx")
    chm.assert_not_called()
