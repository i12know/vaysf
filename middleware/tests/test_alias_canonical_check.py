"""`apply-aliases` confirms the canonical ChMeetings ID before acting (#396).

An alias whose canonical ID is gone from ChMeetings points every later sync
and approval write at a dead ID. These tests pin the three answers the lookup
can give — exists, 404, could not verify — in report-only and `--execute`
modes, and that the lookup itself is a single GET with no ChMeetings write.
"""

import pytest
import requests
from loguru import logger

from sync.alias_reconciler import apply_aliases

from test_canonical_identity import (  # noqa: F401  (the connectors are fixtures)
    _participant,
    _wire_participants,
    chm_connector,
    wp_connector,
)

CHM_READS = {"authenticate", "get_person"}
WP_WRITES = ("update_participant", "update_approval", "update_validation_issue", "delete_roster")


def _alias(canonical):
    return {
        "canonical_chm_id": canonical,
        "reason": "duplicate registration",
        "confirmed_by": "Bumble",
        "confirmed_on": "2026-07-20",
        "note": "",
    }


def _chm_answers(chm, answers):
    """Make `get_person` answer per ID: 'ok', 'not_found', 'failed' or an exception."""

    def get_person(person_id):
        answer = answers.get(person_id, "ok")
        if isinstance(answer, Exception):
            raise answer
        chm.last_get_person_status = answer
        return {"id": person_id} if answer == "ok" else None

    chm.get_person.side_effect = get_person


def _audit_rows(mocker):
    write_audit = mocker.patch("sync.alias_reconciler._write_audit")
    return lambda: write_audit.call_args.args[0]


def _assert_no_wordpress_call(wp):
    wp.get_participants.assert_not_called()
    wp.get_rosters.assert_not_called()
    for method in WP_WRITES:
        getattr(wp, method).assert_not_called()


@pytest.fixture
def log_lines():
    lines = []
    sink = logger.add(lambda message: lines.append(str(message)), format="{level} {message}")
    yield lines
    logger.remove(sink)


# ── Exists ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "execute, expected_outcome", [(False, "would_reconcile"), (True, "reconciled")]
)
def test_canonical_exists_proceeds_as_before(
    wp_connector, chm_connector, mocker, execute, expected_outcome
):
    _wire_participants(wp_connector)
    rows = _audit_rows(mocker)

    assert apply_aliases(execute=execute) is True

    [row] = rows()
    assert row["Outcome"] == expected_outcome
    assert row["Canonical In ChMeetings"] == "yes"
    assert "Skipped Because" not in row
    chm_connector.get_person.assert_called_once_with("200")  # the canonical, not the stale ID
    assert wp_connector.update_participant.called is execute


def test_only_reads_reach_chmeetings(wp_connector, chm_connector, mocker):
    _wire_participants(wp_connector)
    wp_connector.get_rosters.return_value = [{"roster_id": 1}]
    wp_connector.get_approvals.return_value = [{"approval_id": 2, "approval_status": "pending"}]
    wp_connector.get_validation_issues.return_value = [{"issue_id": 3}]
    _audit_rows(mocker)

    assert apply_aliases(execute=True) is True

    called = {call[0] for call in chm_connector.method_calls}
    assert called == CHM_READS


# ── 404 ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("execute", [False, True])
def test_canonical_404_is_skipped_and_reported(wp_connector, chm_connector, mocker, execute):
    _wire_participants(wp_connector)
    _chm_answers(chm_connector, {"200": "not_found"})
    rows = _audit_rows(mocker)

    assert apply_aliases(execute=execute) is False  # cannot scroll past unnoticed

    [row] = rows()
    assert row["Outcome"] == "canonical_not_in_chmeetings"
    assert row["Canonical In ChMeetings"] == "not found"
    assert row["Skipped Because"] == (
        "canonical ID not found in ChMeetings; check direction (the stale ID may be the "
        "live one) and fix the alias file"
    )
    assert (row["Stale ChM ID"], row["Canonical ChM ID"]) == ("100", "200")
    assert (row["Reason"], row["Confirmed By"]) == ("duplicate registration", "Bumble")
    _assert_no_wordpress_call(wp_connector)


# ── Could not verify ─────────────────────────────────────────────────────────


def _http_error(status_code):
    response = requests.Response()
    response.status_code = status_code
    return requests.HTTPError(f"{status_code} error", response=response)


@pytest.mark.parametrize(
    "answer",
    [
        "failed",  # the connector caught a 5xx, a timeout or a 401
        requests.ConnectionError("network down"),
        _http_error(503),
        _http_error(429),  # still rate limited after the connector's retries
        ValueError("response body was not JSON"),
        "unknown",  # no person and no clear status: not proof of anything
    ],
    ids=["status_failed", "connection_error", "http_503", "http_429", "bad_json", "no_status"],
)
@pytest.mark.parametrize("execute", [False, True])
def test_unverifiable_canonical_fails_closed(wp_connector, chm_connector, mocker, answer, execute):
    _wire_participants(wp_connector)
    _chm_answers(chm_connector, {"200": answer})
    rows = _audit_rows(mocker)

    assert apply_aliases(execute=execute) is False

    [row] = rows()
    assert row["Outcome"] == "canonical_unverified"
    assert row["Canonical In ChMeetings"] == "could not verify"
    assert row["Skipped Because"].startswith("could not verify the canonical ID in ChMeetings")
    _assert_no_wordpress_call(wp_connector)


def test_a_person_without_an_ok_status_is_not_proof(wp_connector, chm_connector, mocker):
    """Fail closed both ways: a body with a failed status is still unverified."""
    _wire_participants(wp_connector)

    def get_person(person_id):
        chm_connector.last_get_person_status = "failed"
        return {"id": person_id}

    chm_connector.get_person.side_effect = get_person
    rows = _audit_rows(mocker)

    assert apply_aliases(execute=True) is False
    assert rows()[0]["Outcome"] == "canonical_unverified"
    _assert_no_wordpress_call(wp_connector)


def test_failed_authentication_verifies_nothing_and_applies_nothing(
    wp_connector, chm_connector, mocker
):
    mocker.patch(
        "sync.alias_reconciler.load_person_aliases",
        return_value={"100": _alias("200"), "101": _alias("201")},
    )
    chm_connector.authenticate.return_value = False
    rows = _audit_rows(mocker)

    assert apply_aliases(execute=True) is False

    assert [row["Outcome"] for row in rows()] == ["canonical_unverified"] * 2
    chm_connector.get_person.assert_not_called()
    _assert_no_wordpress_call(wp_connector)


# ── Several entries ──────────────────────────────────────────────────────────


def test_one_bad_entry_does_not_block_the_good_ones(wp_connector, chm_connector, mocker):
    mocker.patch(
        "sync.alias_reconciler.load_person_aliases",
        return_value={"100": _alias("200"), "101": _alias("201"), "102": _alias("202")},
    )
    by_chm_id = {
        "100": _participant("100", 10), "200": _participant("200", 20),
        "101": _participant("101", 11), "201": _participant("201", 21),
        "102": _participant("102", 12), "202": _participant("202", 22),
    }
    wp_connector.get_participants.side_effect = lambda params=None: [
        by_chm_id[params["chmeetings_id"]]
    ]
    _chm_answers(chm_connector, {"201": "not_found", "202": "failed"})
    rows = _audit_rows(mocker)

    assert apply_aliases(execute=True) is False

    assert {row["Stale ChM ID"]: row["Outcome"] for row in rows()} == {
        "100": "reconciled",
        "101": "canonical_not_in_chmeetings",
        "102": "canonical_unverified",
    }
    wp_connector.update_participant.assert_called_once_with(10, {"approval_status": "merged"})
    asked_wordpress_about = {
        call.kwargs["params"]["chmeetings_id"] for call in wp_connector.get_participants.call_args_list
    }
    assert asked_wordpress_about == {"100", "200"}


def test_chain_checks_the_terminal_canonical_and_shared_canonicals_once(
    wp_connector, chm_connector, mocker
):
    # 100 -> 150 -> 200, and 101 -> 200: the only ID that must be live is 200.
    mocker.patch(
        "sync.alias_reconciler.load_person_aliases",
        return_value={"100": _alias("150"), "150": _alias("200"), "101": _alias("200")},
    )
    wp_connector.get_participants.return_value = []
    sleep = mocker.patch("sync.alias_reconciler.time.sleep")
    rows = _audit_rows(mocker)

    assert apply_aliases(execute=False) is True

    chm_connector.get_person.assert_called_once_with("200")
    sleep.assert_not_called()  # one lookup, nothing to pace
    assert {row["Canonical ChM ID"] for row in rows()} == {"200"}
    assert len({row["ChM Check Request ID"] for row in rows()}) == 1


def test_lookups_are_paced(wp_connector, chm_connector, mocker):
    mocker.patch(
        "sync.alias_reconciler.load_person_aliases",
        return_value={"100": _alias("200"), "101": _alias("201"), "102": _alias("202")},
    )
    wp_connector.get_participants.return_value = []
    sleep = mocker.patch("sync.alias_reconciler.time.sleep")
    _audit_rows(mocker)

    apply_aliases(execute=False)

    assert chm_connector.get_person.call_count == 3
    assert sleep.call_count == 2  # between lookups, not before the first


def test_already_tombstoned_alias_with_a_dead_canonical_is_still_reported(
    wp_connector, chm_connector, mocker
):
    """The alias stays in the map for good, so a canonical lost later must surface."""
    _wire_participants(wp_connector, stale=_participant("100", 10, "merged"))
    _chm_answers(chm_connector, {"200": "not_found"})
    rows = _audit_rows(mocker)

    assert apply_aliases(execute=False) is False
    assert rows()[0]["Outcome"] == "canonical_not_in_chmeetings"


def test_empty_alias_map_never_opens_chmeetings(mocker):
    mocker.patch("sync.alias_reconciler.load_person_aliases", return_value={})
    chm = mocker.patch("sync.alias_reconciler.ChMeetingsConnector")
    wp = mocker.patch("sync.alias_reconciler.WordPressConnector")

    assert apply_aliases(execute=True) is True
    chm.assert_not_called()
    wp.assert_not_called()


# ── Logging ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "answer, status, result, level",
    [
        ("ok", "ok", "exists", "INFO"),
        ("not_found", "not_found", "not_found", "ERROR"),
        ("failed", "failed", "unverified", "ERROR"),
    ],
)
def test_check_is_logged_with_the_structured_fields(
    wp_connector, chm_connector, mocker, log_lines, answer, status, result, level
):
    _wire_participants(wp_connector)
    _chm_answers(chm_connector, {"200": answer})
    rows = _audit_rows(mocker)

    apply_aliases(execute=False)

    request_id = rows()[0]["ChM Check Request ID"]
    [line] = [text for text in log_lines if "canonical check" in text]
    assert line.startswith(f"{level} [VAY SM] apply-aliases canonical check")
    for field in (
        "scope=church",
        "endpoint=GET api/v1/people/200",
        f"status={status}",
        "duration_ms=",
        f"request_id={request_id}",
        f"result={result}",
    ):
        assert field in line
    assert len(request_id) == 12


def test_skip_is_logged_with_both_ids_and_no_names(wp_connector, chm_connector, mocker, log_lines):
    _wire_participants(wp_connector)
    _chm_answers(chm_connector, {"200": "not_found"})
    _audit_rows(mocker)

    apply_aliases(execute=True)

    [line] = [text for text in log_lines if "skipped" in text]
    assert "ERROR [VAY SM] Alias 100 -> 200 skipped: canonical ID not found in ChMeetings" in line
    assert "Nothing was written for this entry." in line
    assert all("Ngoc" not in text for text in log_lines)
