import json

from schedule_publisher import (
    CANCELLABLE_GAME_STATUSES,
    PROTECTED_GAME_STATUSES,
    build_publish_diff,
    compute_source_hash,
    merge_schedule,
    run_publish_schedule,
)


def _schedule_input_2team_3team():
    return {
        "games": [
            {
                "game_id": "BBM-01",
                "event": "Basketball - Men Team",
                "stage": "Pool",
                "pool_id": "P1",
                "round": 1,
                "team_a_id": "BBM-P1-T1",
                "team_a_label": "RPC Men",
                "team_b_id": "BBM-P1-T2",
                "team_b_label": "VNBC Men",
                "duration_minutes": 60,
                "resource_type": "Basketball Court",
            },
            {
                "game_id": "BC-01",
                "event": "Bible Challenge",
                "stage": "Pool",
                "pool_id": "P1",
                "round": 1,
                "team_a_id": "BC-T1",
                "team_a_label": "Church A",
                "team_b_id": "BC-T2",
                "team_b_label": "Church B",
                "team_c_id": "BC-T3",
                "team_c_label": "Church C",
                "duration_minutes": 30,
                "resource_type": "Classroom",
            },
        ],
        "resources": [
            {
                "resource_id": "GYM-Sat-1-1",
                "resource_type": "Basketball Court",
                "label": "Court-1",
                "day": "Sat-1",
                "open_time": "08:00",
                "close_time": "10:00",
                "slot_minutes": 60,
                "venue_name": "EHS Main Gym",
            },
            {
                "resource_id": "ROOM-Sat-1-1",
                "resource_type": "BC Station",
                "label": "Court-1",
                "day": "Sat-1",
                "open_time": "08:00",
                "close_time": "10:00",
                "slot_minutes": 30,
                "venue_name": "EHS Library",
            },
        ],
    }


def _schedule_output_2team_3team():
    return {
        "status": "OPTIMAL",
        "assignments": [
            {"game_id": "BBM-01", "resource_id": "GYM-Sat-1-1", "slot": "Sat-1-08:00"},
            {"game_id": "BC-01", "resource_id": "ROOM-Sat-1-1", "slot": "Sat-1-08:00"},
        ],
        "unscheduled": [],
    }


def _merged_game(**overrides):
    base = {
        "game_key": "BBM-01",
        "event": "Basketball - Men Team",
        "stage": "Pool",
        "pool_id": "P1",
        "round_number": 1,
        "team_a_key": "BBM-P1-T1",
        "team_a_label": "RPC Men",
        "team_b_key": "BBM-P1-T2",
        "team_b_label": "VNBC Men",
        "team_c_key": None,
        "team_c_label": None,
        "team_ids_json": json.dumps(["BBM-P1-T1", "BBM-P1-T2"]),
        "resource_id": "GYM-Sat-1-1",
        "scheduled_slot": "Sat-1-08:00",
        "scheduled_location": "EHS Main Gym - Court 1",
    }
    base.update(overrides)
    base["source_hash"] = compute_source_hash(base)
    base.setdefault("game_status", "scheduled")
    return base


# ---------------------------------------------------------------------------
# compute_source_hash
# ---------------------------------------------------------------------------

def test_compute_source_hash_deterministic():
    game = _merged_game()
    assert compute_source_hash(game) == compute_source_hash(dict(game))


def test_compute_source_hash_sensitive_to_content_change():
    game_a = _merged_game()
    game_b = _merged_game(team_b_key="BBM-P1-T5")
    assert compute_source_hash(game_a) != compute_source_hash(game_b)


def test_compute_source_hash_order_independent():
    game = _merged_game()
    reordered = dict(reversed(list(game.items())))
    assert compute_source_hash(game) == compute_source_hash(reordered)


def test_compute_source_hash_ignores_identity_and_bookkeeping_fields():
    """game_key/game_status/source_hash/published_at must not affect the hash
    — they are identity or bookkeeping, not game content."""
    game_a = _merged_game(game_key="BBM-01", game_status="scheduled")
    game_b = _merged_game(game_key="BBM-99", game_status="reported")
    assert compute_source_hash(game_a) == compute_source_hash(game_b)


# ---------------------------------------------------------------------------
# merge_schedule
# ---------------------------------------------------------------------------

def test_merge_schedule_joins_assignments_to_game_metadata():
    merged = merge_schedule(_schedule_input_2team_3team(), _schedule_output_2team_3team())
    by_key = {game["game_key"]: game for game in merged}

    assert set(by_key) == {"BBM-01", "BC-01"}

    two_team = by_key["BBM-01"]
    assert two_team["event"] == "Basketball - Men Team"
    assert two_team["team_a_key"] == "BBM-P1-T1"
    assert two_team["team_b_key"] == "BBM-P1-T2"
    assert json.loads(two_team["team_ids_json"]) == ["BBM-P1-T1", "BBM-P1-T2"]
    assert two_team["resource_id"] == "GYM-Sat-1-1"
    assert two_team["scheduled_slot"] == "Sat-1-08:00"
    assert two_team["scheduled_location"] == "EHS Main Gym - Court 1"
    assert two_team["game_status"] == "scheduled"


def test_merge_schedule_handles_three_team_games():
    merged = merge_schedule(_schedule_input_2team_3team(), _schedule_output_2team_3team())
    by_key = {game["game_key"]: game for game in merged}

    three_team = by_key["BC-01"]
    assert three_team["team_a_key"] == "BC-T1"
    assert three_team["team_b_key"] == "BC-T2"
    assert three_team["team_c_key"] == "BC-T3"
    assert json.loads(three_team["team_ids_json"]) == ["BC-T1", "BC-T2", "BC-T3"]
    assert three_team["scheduled_location"] == "EHS Library - Station 1"


def test_merge_schedule_skips_assignments_without_game_id():
    schedule_output = {"assignments": [{"resource_id": "GYM-Sat-1-1", "slot": "Sat-1-08:00"}]}
    merged = merge_schedule(_schedule_input_2team_3team(), schedule_output)
    assert merged == []


# ---------------------------------------------------------------------------
# build_publish_diff
# ---------------------------------------------------------------------------

def test_build_publish_diff_new_game():
    merged = [_merged_game(game_key="BBM-01")]
    diff = build_publish_diff(merged, published_rows=[])
    assert [g["game_key"] for g in diff["new"]] == ["BBM-01"]
    assert diff["changed"] == diff["unchanged"] == diff["cancelled_candidates"] == []
    assert diff["completed_conflicts"] == diff["missing_completed"] == []


def test_build_publish_diff_unchanged_game():
    game = _merged_game(game_key="BBM-01")
    published = {"game_key": "BBM-01", "game_status": "scheduled", "source_hash": game["source_hash"]}
    diff = build_publish_diff([game], [published])
    assert [g["game_key"] for g in diff["unchanged"]] == ["BBM-01"]
    assert diff["new"] == diff["changed"] == []


def test_build_publish_diff_changed_future_game():
    game = _merged_game(game_key="BBM-01", team_b_key="BBM-P1-T9")
    published = {"game_key": "BBM-01", "game_status": "scheduled", "source_hash": "stale-hash"}
    diff = build_publish_diff([game], [published])
    assert [g["game_key"] for g in diff["changed"]] == ["BBM-01"]
    assert diff["unchanged"] == diff["new"] == []


def test_build_publish_diff_cancelled_candidate():
    """A non-protected published game absent from the new schedule is a
    cancellation candidate, not a completed conflict."""
    published = {"game_key": "BBM-01", "game_status": "scheduled", "source_hash": "x"}
    diff = build_publish_diff(merged_games=[], published_rows=[published])
    assert [g["game_key"] for g in diff["cancelled_candidates"]] == ["BBM-01"]
    assert diff["missing_completed"] == diff["completed_conflicts"] == []


def test_build_publish_diff_completed_conflict_refused():
    """A protected game whose content changed is refused loudly, never
    silently absorbed into 'changed'."""
    game = _merged_game(game_key="BBM-01", team_b_key="BBM-P1-T9")
    published = {"game_key": "BBM-01", "game_status": "official", "source_hash": "stale-hash"}
    diff = build_publish_diff([game], [published])
    assert [g["game_key"] for g in diff["completed_conflicts"]] == ["BBM-01"]
    assert diff["changed"] == diff["new"] == []


def test_build_publish_diff_protected_unchanged_is_silent():
    """A protected game whose content is unchanged appears in none of the
    buckets — nothing to report, nothing to do."""
    game = _merged_game(game_key="BBM-01")
    published = {"game_key": "BBM-01", "game_status": "reported", "source_hash": game["source_hash"]}
    diff = build_publish_diff([game], [published])
    for bucket in diff.values():
        assert bucket == []


def test_build_publish_diff_missing_completed_is_separate_from_cancelled():
    """A protected game absent from the new schedule is a drift alarm
    (missing_completed), never folded into ordinary cancellation candidates."""
    published = {"game_key": "BBM-01", "game_status": "reported", "source_hash": "x"}
    diff = build_publish_diff(merged_games=[], published_rows=[published])
    assert [g["game_key"] for g in diff["missing_completed"]] == ["BBM-01"]
    assert diff["cancelled_candidates"] == []


def test_build_publish_diff_already_cancelled_game_is_ignored():
    published = {"game_key": "BBM-01", "game_status": "cancelled", "source_hash": "x"}
    diff = build_publish_diff(merged_games=[], published_rows=[published])
    for bucket in diff.values():
        assert bucket == []


def test_protected_and_cancellable_status_sets_are_disjoint():
    assert PROTECTED_GAME_STATUSES.isdisjoint(CANCELLABLE_GAME_STATUSES)


# ---------------------------------------------------------------------------
# run_publish_schedule
# ---------------------------------------------------------------------------

_UNSET = object()


class _FakeConnector:
    def __init__(self, published_rows=_UNSET, upsert_response=None):
        self.published_rows = [] if published_rows is _UNSET else published_rows
        self.upsert_response = upsert_response
        self.get_schedules_calls = 0
        self.upsert_calls = []

    def get_schedules(self, params=None):
        self.get_schedules_calls += 1
        return self.published_rows

    def upsert_schedules(self, games, schedule_version, force_cancel=False):
        self.upsert_calls.append(
            {"games": games, "schedule_version": schedule_version, "force_cancel": force_cancel}
        )
        if self.upsert_response is not None:
            return self.upsert_response
        return {
            "success": True,
            "schedule_version": schedule_version,
            "created_count": len(games),
            "updated_count": 0,
            "skipped_count": 0,
            "results": [],
        }


def _write_fixtures(tmp_path):
    input_path = tmp_path / "schedule_input.json"
    input_path.write_text(json.dumps(_schedule_input_2team_3team()), encoding="utf-8")
    output_path = tmp_path / "schedule_output.json"
    output_path.write_text(json.dumps(_schedule_output_2team_3team()), encoding="utf-8")
    return input_path, output_path


def test_run_publish_schedule_dry_run_never_upserts(tmp_path):
    input_path, output_path = _write_fixtures(tmp_path)
    connector = _FakeConnector()

    exit_code = run_publish_schedule(
        schedule_input_path=input_path,
        schedule_output_path=output_path,
        wp_connector=connector,
        dry_run=True,
    )

    assert exit_code == 0
    assert connector.get_schedules_calls == 1
    assert connector.upsert_calls == []


def test_run_publish_schedule_execute_sends_only_new_and_changed(tmp_path):
    input_path, output_path = _write_fixtures(tmp_path)
    published = [{"game_key": "BBM-01", "game_status": "official", "source_hash": "stale"}]
    connector = _FakeConnector(published_rows=published)

    exit_code = run_publish_schedule(
        schedule_input_path=input_path,
        schedule_output_path=output_path,
        wp_connector=connector,
        dry_run=False,
    )

    assert exit_code == 0
    assert len(connector.upsert_calls) == 1
    upserted_keys = {g["game_key"] for g in connector.upsert_calls[0]["games"]}
    # BBM-01 is a completed_conflict (protected + changed) and must never be
    # sent; BC-01 is new and must be sent.
    assert upserted_keys == {"BC-01"}


def test_run_publish_schedule_force_cancel_includes_cancellations(tmp_path):
    input_path, output_path = _write_fixtures(tmp_path)
    # A published game not present in the newly generated schedule at all.
    published = [{"game_key": "OLD-99", "game_status": "scheduled", "source_hash": "x"}]
    connector = _FakeConnector(published_rows=published)

    exit_code = run_publish_schedule(
        schedule_input_path=input_path,
        schedule_output_path=output_path,
        wp_connector=connector,
        dry_run=False,
        force_cancel=True,
    )

    assert exit_code == 0
    assert len(connector.upsert_calls) == 1
    payload_games = connector.upsert_calls[0]["games"]
    cancelled = [g for g in payload_games if g["game_key"] == "OLD-99"]
    assert len(cancelled) == 1
    assert cancelled[0]["game_status"] == "cancelled"
    assert connector.upsert_calls[0]["force_cancel"] is True


def test_run_publish_schedule_without_force_cancel_excludes_cancellations(tmp_path):
    input_path, output_path = _write_fixtures(tmp_path)
    published = [{"game_key": "OLD-99", "game_status": "scheduled", "source_hash": "x"}]
    connector = _FakeConnector(published_rows=published)

    run_publish_schedule(
        schedule_input_path=input_path,
        schedule_output_path=output_path,
        wp_connector=connector,
        dry_run=False,
        force_cancel=False,
    )

    payload_games = connector.upsert_calls[0]["games"]
    assert all(g["game_key"] != "OLD-99" for g in payload_games)


def test_run_publish_schedule_writes_audit_json(tmp_path):
    input_path, output_path = _write_fixtures(tmp_path)
    connector = _FakeConnector()
    audit_path = tmp_path / "audit.json"

    run_publish_schedule(
        schedule_input_path=input_path,
        schedule_output_path=output_path,
        wp_connector=connector,
        dry_run=True,
        audit_output_path=audit_path,
    )

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["dry_run"] is True
    assert {g["game_key"] for g in audit["diff"]["new"]} == {"BBM-01", "BC-01"}


def test_run_publish_schedule_missing_file_returns_1(tmp_path):
    connector = _FakeConnector()
    exit_code = run_publish_schedule(
        schedule_input_path=tmp_path / "missing_input.json",
        schedule_output_path=tmp_path / "missing_output.json",
        wp_connector=connector,
        dry_run=True,
    )
    assert exit_code == 1
    assert connector.get_schedules_calls == 0


def test_run_publish_schedule_invalid_contract_returns_1(tmp_path):
    input_path = tmp_path / "schedule_input.json"
    input_path.write_text(json.dumps({"games": [], "resources": []}), encoding="utf-8")
    output_path = tmp_path / "schedule_output.json"
    # Missing required "status"/"assignments" makes this an invalid contract.
    output_path.write_text(json.dumps({}), encoding="utf-8")
    connector = _FakeConnector()

    exit_code = run_publish_schedule(
        schedule_input_path=input_path,
        schedule_output_path=output_path,
        wp_connector=connector,
        dry_run=True,
    )

    assert exit_code == 1
    assert connector.get_schedules_calls == 0


def test_run_publish_schedule_blocks_partial_by_default(tmp_path):
    input_path, output_path = _write_fixtures(tmp_path)
    output = _schedule_output_2team_3team()
    output["status"] = "PARTIAL"
    output["unscheduled"] = ["BC-01"]
    output_path.write_text(json.dumps(output), encoding="utf-8")
    connector = _FakeConnector()

    exit_code = run_publish_schedule(
        schedule_input_path=input_path,
        schedule_output_path=output_path,
        wp_connector=connector,
        dry_run=True,
    )

    assert exit_code == 1
    assert connector.get_schedules_calls == 0


def test_run_publish_schedule_allow_partial_still_diffs(tmp_path):
    input_path, output_path = _write_fixtures(tmp_path)
    output = _schedule_output_2team_3team()
    output["status"] = "PARTIAL"
    output["unscheduled"] = ["BC-01"]
    output_path.write_text(json.dumps(output), encoding="utf-8")
    connector = _FakeConnector()

    exit_code = run_publish_schedule(
        schedule_input_path=input_path,
        schedule_output_path=output_path,
        wp_connector=connector,
        dry_run=True,
        allow_partial=True,
    )

    assert exit_code == 0
    assert connector.get_schedules_calls == 1


def test_run_publish_schedule_refuses_unknown_wordpress_state(tmp_path):
    input_path, output_path = _write_fixtures(tmp_path)
    connector = _FakeConnector(published_rows=None)

    exit_code = run_publish_schedule(
        schedule_input_path=input_path,
        schedule_output_path=output_path,
        wp_connector=connector,
        dry_run=True,
    )

    assert exit_code == 1
    assert connector.upsert_calls == []


def test_run_publish_schedule_failed_upsert_returns_1(tmp_path):
    input_path, output_path = _write_fixtures(tmp_path)
    connector = _FakeConnector(upsert_response={"success": False, "skipped_count": 1})

    exit_code = run_publish_schedule(
        schedule_input_path=input_path,
        schedule_output_path=output_path,
        wp_connector=connector,
        dry_run=False,
    )

    assert exit_code == 1
    assert len(connector.upsert_calls) == 1
