# Begin of tests/test_person_aliases.py
"""Tests for the canonical ChMeetings identity alias map (Issue #308).

Covers the loader edge cases, transitive chain resolution, cycle hard-failure
(guardrail G2), and resolution at the sync choke point ahead of get_person()
(guardrail G1).
"""
import json

import pytest
from unittest.mock import MagicMock

from sync.participants import ParticipantSyncer
from sync.person_aliases import (
    MAX_ALIAS_CHAIN_DEPTH,
    PersonAliasError,
    load_person_aliases,
    resolve_chm_id,
)
from config import APPROVAL_STATUS, SPORT_UNSELECTED


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_aliases(tmp_path, payload):
    """Write an alias map (JSON object or raw text) and return its path."""
    alias_path = tmp_path / "person_aliases.local.json"
    if isinstance(payload, str):
        alias_path.write_text(payload, encoding="utf-8")
    else:
        alias_path.write_text(json.dumps(payload), encoding="utf-8")
    return alias_path


# ── load_person_aliases ───────────────────────────────────────────────────────

class TestLoadPersonAliases:
    def test_missing_file_returns_empty(self, tmp_path):
        assert load_person_aliases(tmp_path / "does_not_exist.json") == {}

    def test_no_configured_path_returns_empty(self, mocker):
        mocker.patch("sync.person_aliases.Config.PERSON_ALIASES_FILE", None)
        assert load_person_aliases() == {}

    def test_uses_config_path_by_default(self, tmp_path, mocker):
        alias_path = _write_aliases(tmp_path, {"3634001": "3633885"})
        mocker.patch("sync.person_aliases.Config.PERSON_ALIASES_FILE", alias_path)
        assert load_person_aliases()["3634001"]["canonical_chm_id"] == "3633885"

    def test_bad_json_warns_and_returns_empty(self, tmp_path):
        alias_path = _write_aliases(tmp_path, "{not json")
        assert load_person_aliases(alias_path) == {}

    def test_non_object_json_returns_empty(self, tmp_path):
        alias_path = _write_aliases(tmp_path, ["3634001", "3633885"])
        assert load_person_aliases(alias_path) == {}

    def test_empty_object_returns_empty(self, tmp_path):
        alias_path = _write_aliases(tmp_path, {})
        assert load_person_aliases(alias_path) == {}

    def test_shorthand_entry(self, tmp_path):
        alias_path = _write_aliases(tmp_path, {"3634001": "3633885"})
        aliases = load_person_aliases(alias_path)
        assert aliases == {
            "3634001": {
                "canonical_chm_id": "3633885",
                "reason": "",
                "confirmed_by": "",
                "confirmed_on": "",
                "note": "",
            }
        }

    def test_object_entry_keeps_metadata(self, tmp_path):
        alias_path = _write_aliases(tmp_path, {
            "3634002": {
                "canonical_chm_id": "3633885",
                "reason": "re-registered to change sports",
                "confirmed_by": "Bumble",
                "confirmed_on": "2026-07-20",
                "note": "Ngoc Le / Khoa Le",
            }
        })
        entry = load_person_aliases(alias_path)["3634002"]
        assert entry["canonical_chm_id"] == "3633885"
        assert entry["reason"] == "re-registered to change sports"
        assert entry["confirmed_by"] == "Bumble"
        assert entry["confirmed_on"] == "2026-07-20"
        assert entry["note"] == "Ngoc Le / Khoa Le"

    def test_numeric_ids_are_stringified(self, tmp_path):
        alias_path = _write_aliases(tmp_path, {"3634001": 3633885})
        assert load_person_aliases(alias_path)["3634001"]["canonical_chm_id"] == "3633885"

    def test_whitespace_is_trimmed(self, tmp_path):
        alias_path = _write_aliases(tmp_path, {"  3634001  ": "  3633885  "})
        assert load_person_aliases(alias_path) == {
            "3634001": {
                "canonical_chm_id": "3633885",
                "reason": "",
                "confirmed_by": "",
                "confirmed_on": "",
                "note": "",
            }
        }

    def test_self_map_is_rejected(self, tmp_path):
        alias_path = _write_aliases(tmp_path, {"3634001": "3634001", "3634002": "3633885"})
        aliases = load_person_aliases(alias_path)
        assert "3634001" not in aliases
        assert "3634002" in aliases

    def test_object_self_map_is_rejected(self, tmp_path):
        alias_path = _write_aliases(
            tmp_path, {"3634001": {"canonical_chm_id": "3634001", "reason": "oops"}}
        )
        assert load_person_aliases(alias_path) == {}

    def test_blank_key_is_skipped(self, tmp_path):
        alias_path = _write_aliases(tmp_path, {"   ": "3633885", "3634002": "3633885"})
        assert list(load_person_aliases(alias_path)) == ["3634002"]

    def test_blank_canonical_is_skipped(self, tmp_path):
        alias_path = _write_aliases(tmp_path, {"3634001": "   ", "3634002": "3633885"})
        assert list(load_person_aliases(alias_path)) == ["3634002"]

    def test_object_without_canonical_is_skipped(self, tmp_path):
        alias_path = _write_aliases(tmp_path, {"3634001": {"reason": "forgot the ID"}})
        assert load_person_aliases(alias_path) == {}

    def test_unsupported_entry_types_are_skipped(self, tmp_path):
        alias_path = _write_aliases(tmp_path, {
            "3634001": True,
            "3634002": None,
            "3634003": ["3633885"],
            "3634004": "3633885",
        })
        assert list(load_person_aliases(alias_path)) == ["3634004"]

    def test_chain_loads_without_collapsing(self, tmp_path):
        """The loader stores the map as written; resolution walks the chain."""
        alias_path = _write_aliases(tmp_path, {"A": "B", "B": "C"})
        aliases = load_person_aliases(alias_path)
        assert aliases["A"]["canonical_chm_id"] == "B"
        assert aliases["B"]["canonical_chm_id"] == "C"

    def test_two_hop_cycle_hard_fails(self, tmp_path):
        alias_path = _write_aliases(tmp_path, {"A": "B", "B": "A"})
        with pytest.raises(PersonAliasError) as exc:
            load_person_aliases(alias_path)
        assert "cycle" in str(exc.value).lower()

    def test_three_hop_cycle_hard_fails(self, tmp_path):
        alias_path = _write_aliases(tmp_path, {"A": "B", "B": "C", "C": "A"})
        with pytest.raises(PersonAliasError):
            load_person_aliases(alias_path)

    def test_cycle_reachable_from_a_clean_entry_hard_fails(self, tmp_path):
        """A -> B -> C -> B: A itself isn't in the loop, but the map is still cyclic."""
        alias_path = _write_aliases(tmp_path, {"A": "B", "B": "C", "C": "B"})
        with pytest.raises(PersonAliasError):
            load_person_aliases(alias_path)

    def test_overlong_chain_hard_fails(self, tmp_path):
        payload = {str(i): str(i + 1) for i in range(MAX_ALIAS_CHAIN_DEPTH + 5)}
        alias_path = _write_aliases(tmp_path, payload)
        with pytest.raises(PersonAliasError) as exc:
            load_person_aliases(alias_path)
        assert "hops" in str(exc.value)

    def test_committed_example_file_is_empty(self):
        """Guardrail G5: only an empty example ships in git."""
        from config import PERSON_ALIASES_FILE

        with open(PERSON_ALIASES_FILE, "r", encoding="utf-8") as handle:
            assert json.load(handle) == {}


# ── resolve_chm_id ────────────────────────────────────────────────────────────

class TestResolveChmId:
    def test_empty_map_returns_input(self):
        assert resolve_chm_id("3633885", {}) == "3633885"
        assert resolve_chm_id("3633885", None) == "3633885"

    def test_unaliased_id_returns_input(self):
        aliases = {"3634001": {"canonical_chm_id": "3633885"}}
        assert resolve_chm_id("9999999", aliases) == "9999999"

    def test_single_hop(self):
        aliases = {"3634001": {"canonical_chm_id": "3633885"}}
        assert resolve_chm_id("3634001", aliases) == "3633885"

    def test_chain_resolves_to_terminal_id(self):
        aliases = {
            "A": {"canonical_chm_id": "B"},
            "B": {"canonical_chm_id": "C"},
        }
        assert resolve_chm_id("A", aliases) == "C"
        assert resolve_chm_id("B", aliases) == "C"

    def test_input_is_stringified_and_trimmed(self):
        aliases = {"3634001": {"canonical_chm_id": "3633885"}}
        assert resolve_chm_id(3634001, aliases) == "3633885"
        assert resolve_chm_id("  3634001 ", aliases) == "3633885"

    def test_blank_input_returns_blank(self):
        aliases = {"3634001": {"canonical_chm_id": "3633885"}}
        assert resolve_chm_id("", aliases) == ""
        assert resolve_chm_id(None, aliases) == ""

    def test_cycle_raises(self):
        """Defensive backstop for maps assembled outside load_person_aliases()."""
        aliases = {
            "A": {"canonical_chm_id": "B"},
            "B": {"canonical_chm_id": "A"},
        }
        with pytest.raises(PersonAliasError):
            resolve_chm_id("A", aliases)


# ── Resolution at the sync choke point ────────────────────────────────────────

@pytest.fixture
def syncer(mocker):
    """ParticipantSyncer with fully mocked connectors and no alias map on disk."""
    mocker.patch("sync.participants.load_person_aliases", return_value={})
    mocker.patch("sync.participants.Config.SPORTS_FEST_DATE", "2026-07-18")
    stats = {
        "participants": {"created": 0, "updated": 0, "errors": 0},
        "rosters": {"created": 0, "deleted": 0, "errors": 0, "updated": 0},
        "validation_issues": {
            "created": 0, "updated": 0, "resolved": 0,
            "unchanged": 0, "skipped": 0, "errors": 0,
        },
        "approvals": {"created": 0, "updated": 0, "errors": 0},
    }
    return ParticipantSyncer(MagicMock(), MagicMock(), stats, {})


def _chm_person(chm_id):
    """Minimal ChMeetings person payload using exact CHM_FIELDS names."""
    return {
        "id": chm_id,
        "first_name": "Ngoc",
        "last_name": "Le",
        "email": "ngocle@example.com",
        "mobile": "(714) 391-1875",
        "gender": "Female",
        "birth_date": "2008-04-23",
        "photo": "",
        "updated_on": "2026-06-15T16:30:12.280-07:00",
        "additional_fields": [
            {"field_name": "Church Team", "value": "WAG"},
            {"field_name": "My role is", "value": "Athlete/Participant"},
            {"field_name": "Primary Sport", "value": "Basketball - Men Team"},
            {"field_name": "Secondary Sport", "value": ""},
            {"field_name": "Other Events", "value": ""},
            {"field_name": "Primary Racquet Sport Format", "value": ""},
            {"field_name": "Primary Racquet Sport Partner (if applied)", "value": ""},
            {"field_name": "Secondary Racquet Sport Format", "value": ""},
            {"field_name": "Secondary Racquet Sport Partner (if applied)", "value": ""},
            {"field_name": "Completion Check List", "value": ""},
            {"field_name": "Name of my parents or legal guardian", "value": ""},
            {"field_name": "Email of my parents or legal guardian", "value": ""},
            {"field_name": "Cell phone of my parents or legal guardian", "value": ""},
            {
                "field_name": "Would the team's Senior Pastor say that you belong to his church?",
                "value": "No",
            },
        ],
    }


def _wp_participant(chm_id):
    return {
        "participant_id": 413,
        "chmeetings_id": chm_id,
        "first_name": "Ngoc",
        "last_name": "Le",
        "email": "ngocle@example.com",
        "phone": "(714) 391-1875",
        "gender": "Female",
        "birthdate": "2008-04-23",
        "church_code": "WAG",
        "primary_sport": "Basketball - Men Team",
        "secondary_sport": SPORT_UNSELECTED,
        "other_events": "",
        "approval_status": APPROVAL_STATUS["PENDING"],
        "is_church_member": False,
        "membership_claim_at_approval": None,
        "photo_url": "",
        "created_at": "2026-05-01 10:00:00",
    }


def _wire_canonical_only(syncer, stale_id, canonical_id):
    """ChMeetings 404s the stale ID and serves the canonical one; WP knows only canonical."""
    def get_person(requested_id):
        if str(requested_id) == canonical_id:
            syncer.chm_connector.last_get_person_status = "ok"
            return _chm_person(canonical_id)
        syncer.chm_connector.last_get_person_status = "not_found"
        return None

    syncer.chm_connector.get_person.side_effect = get_person
    syncer.wordpress_connector.get_participants.return_value = [_wp_participant(canonical_id)]
    syncer.wordpress_connector.update_participant.return_value = _wp_participant(canonical_id)
    syncer.wordpress_connector.get_approvals.return_value = []
    syncer.wordpress_connector.get_rosters.return_value = []
    syncer.wordpress_connector.get_validation_issues.return_value = []
    syncer.churches_cache = {"WAG": {"church_id": 16, "church_code": "WAG"}}


class TestResolutionAtChokePoint:
    def test_stale_id_404s_but_canonical_resolves(self, syncer):
        """Guardrail G1: resolution happens before get_person(), so the 404 never occurs."""
        syncer.person_aliases = {"3634001": {"canonical_chm_id": "3633885"}}
        _wire_canonical_only(syncer, "3634001", "3633885")

        assert syncer._sync_single_participant("3634001") is True

        requested = [str(c.args[0]) for c in syncer.chm_connector.get_person.call_args_list]
        assert requested == ["3633885"], "the stale ID must never reach ChMeetings"

    def test_no_create_participant_for_aliased_stale_id(self, syncer):
        """The canonical WordPress row is updated; no duplicate row is manufactured."""
        syncer.person_aliases = {"3634001": {"canonical_chm_id": "3633885"}}
        _wire_canonical_only(syncer, "3634001", "3633885")

        syncer._sync_single_participant("3634001")

        syncer.wordpress_connector.create_participant.assert_not_called()
        syncer.wordpress_connector.update_participant.assert_called()
        assert syncer.wordpress_connector.update_participant.call_args[0][0] == 413

    def test_chain_resolves_to_terminal_id_at_choke_point(self, syncer):
        syncer.person_aliases = {
            "3634001": {"canonical_chm_id": "3634002"},
            "3634002": {"canonical_chm_id": "3633885"},
        }
        _wire_canonical_only(syncer, "3634001", "3633885")

        syncer._sync_single_participant("3634001")

        requested = [str(c.args[0]) for c in syncer.chm_connector.get_person.call_args_list]
        assert requested == ["3633885"]

    def test_empty_map_leaves_the_id_untouched(self, syncer):
        """Regression guard: an empty map is today's behavior, byte for byte."""
        assert syncer.person_aliases == {}
        _wire_canonical_only(syncer, "3634001", "3633885")

        syncer._sync_single_participant("3633885")

        requested = [str(c.args[0]) for c in syncer.chm_connector.get_person.call_args_list]
        assert requested == ["3633885"]

    def test_unaliased_stale_id_still_takes_the_orphan_skip_path(self, syncer):
        """Without an alias entry, a 404 behaves exactly as it does today."""
        _wire_canonical_only(syncer, "3634001", "3633885")

        assert syncer._sync_single_participant("3634001", allow_missing_person_skip=True) is True
        assert syncer.stats["participants"]["skipped_missing_people"] == 1
        syncer.wordpress_connector.create_participant.assert_not_called()

    def test_cyclic_map_refuses_to_construct_the_syncer(self, tmp_path, mocker):
        """Guardrail G2: the sync refuses to run on a cyclic map."""
        alias_path = _write_aliases(tmp_path, {"A": "B", "B": "A"})
        mocker.patch("sync.person_aliases.Config.PERSON_ALIASES_FILE", alias_path)
        mocker.patch("sync.participants.Config.SPORTS_FEST_DATE", "2026-07-18")

        with pytest.raises(PersonAliasError):
            ParticipantSyncer(MagicMock(), MagicMock(), {}, {})

# End of tests/test_person_aliases.py
