# church_teams_scheduling.py
# Version 1.0.0
"""Scheduling hand-off for the church-teams export (Issue #376).

This is the only church_teams_* module that imports ``schedule_workbook``.
The dependency stays one-way: ``schedule_workbook.py`` must never import from
here, from ``church_teams_export.py`` or from ``church_teams_report.py``.

Three jobs, all of them "pass it to ScheduleWorkbookBuilder":

* ``delegate_schedule_workbook_methods`` keeps ChurchTeamsExporter's
  long-standing scheduling method surface by binding the builder's own
  functions onto the exporter class (no copies live in the export modules).
* ``write_schedule_input_for_export`` writes ``schedule_input.json`` next to
  the consolidated ALL workbook.
* ``stamp_sport_export_tab_statuses`` adds the status banners to the finished
  Church_Team_Status workbook.
"""
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger

from schedule_workbook import ScheduleWorkbookBuilder

# Keep ChurchTeamsExporter's long-standing scheduling method surface stable while
# making ScheduleWorkbookBuilder the single authoritative implementation.
SCHEDULE_WORKBOOK_METHOD_NAMES = (
    "_decompose_event_name",
    "_get_rules_manager",
    "_get_min_team_size",
    "_count_estimating_teams",
    "_get_playoff_teams",
    "_get_playoff_teams_for_event",
    "_compute_court_slots",
    "_normalize_racquet_gender",
    "_get_racquet_entry_limits",
    "_racquet_rule_parameter_for_row",
    "_count_racquet_entries",
    "_pod_format_class",
    "_make_division_id",
    "_build_pod_error_lookup",
    "_build_pod_divisions_rows",
    "_build_pod_entries_review_rows",
    "_resolve_pod_doubles",
    "_resolve_pod_singles",
    "_expected_partner_issue_type",
    "_partner_validation_key",
    "_reconcile_pod_validation",
    "_build_venue_capacity_rows",
    "_pool_assignments_sidecar_path",
    "_normalize_pool_seed",
    "_positive_int_or_none",
    "_pool_assignment_event_prefix",
    "_event_sort_index",
    "_load_pool_assignment_state",
    "_write_pool_assignment_state",
    "_build_pool_assignment_base_rows",
    "_default_random_draw_orders",
    "_serpentine_pool_slots",
    "_pool_sizes_for_assignment",
    "_apply_pool_assignments_to_rows",
    "_build_pool_assignment_rows",
    "_normalize_resource_type_name",
    "_resource_id_prefix",
    "_normalize_primary_sport_name",
    "_solver_team_id",
    "_pool_assignment_placeholder_map",
    "_build_core_gym_team_lookup",
    "_pool_numeric_suffix",
    "_bc_no_repeat_triplets",
    "_build_assigned_bc_game_objects",
    "_build_assigned_soccer_game_objects",
    "_build_single_elim_playoff",
    "_build_manual_team_sport_game_objects",
    "_build_gym_game_objects",
    "_build_assigned_gym_game_objects",
    "_build_gym_team_conflicts",
    "_team_state_to_unit",
    "_make_shared_athlete_edge",
    "_build_cross_sport_conflicts",
    "_build_pod_game_objects",
    "_build_gym_resource_objects",
    "_build_gym_resources_from_allocator",
    "_clean_excel_text",
    "_float_from_excel",
    "_load_venue_input_rows",
    "_load_playoff_slots",
    "_load_venue_date_day_map",
    "_resolve_venue_playoff_slots",
    "_split_slot_label",
    "_load_gym_modes",
    "_build_schedule_input",
    "_write_schedule_input_tab",
    "_build_scenario_schedule",
    "_two_game_pool_sizes",
    "_summarize_pool_policy",
    "_make_legacy_pool_game_pairs",
    "_make_pool_game_pairs",
    "_make_playoff_ids",
    "_write_court_schedule_sketch",
    "_parse_hour",
    "_load_venue_input",
    "_build_pod_resource_rows",
    "_write_pod_resource_estimate",
    "_warn_if_schedules_mismatched",
    "_warn_if_resource_slot_minutes_differ_from_config",
    "_build_schedule_output_flat_rows",
    "_write_schedule_output_report",
    "write_schedule_input_json",
    "write_schedule_workbook",
    "write_schedule_output_workbook",
)

SCHEDULE_WORKBOOK_ATTR_NAMES = (
    "_GYM_CORE_SOLVER_POOL",
    "_POD_PARTNER_ISSUE_TYPES",
    "_POOL_ASSIGNMENT_COLUMNS",
    "_POOL_ASSIGNMENT_EVENT_DEFS",
    "_POOL_ASSIGNMENT_HEADER_NOTES",
)


def delegate_schedule_workbook_methods(cls):
    """Class decorator: bind ScheduleWorkbookBuilder's scheduling surface onto ``cls``.

    The builder's raw ``__dict__`` entries are reused (not wrapped), so
    ``cls.__dict__[name] is ScheduleWorkbookBuilder.__dict__[name]`` holds and
    staticmethod/classmethod descriptors behave exactly as on the builder.
    """
    for method_name in SCHEDULE_WORKBOOK_METHOD_NAMES:
        setattr(cls, method_name, ScheduleWorkbookBuilder.__dict__[method_name])
    for attr_name in SCHEDULE_WORKBOOK_ATTR_NAMES:
        setattr(cls, attr_name, getattr(ScheduleWorkbookBuilder, attr_name))
    return cls


def write_schedule_input_for_export(
    exporter,
    roster_rows: List[Dict[str, Any]],
    validation_rows: List[Dict[str, Any]],
    venue_input_path: Path,
    output_dir: Path,
) -> None:
    """Write schedule_input.json (and its sidecars) beside the consolidated export.

    Consumed by solve-schedule and build-schedule-workbook; the scheduling tabs
    themselves live in Schedule_Workbook_*.xlsx (build-schedule-workbook).
    Failures are logged and swallowed on purpose: a bad venue file or a bug in
    schedule-input generation must not stop the sport-specific tabs from being
    written into the Church_Team_Status workbook.
    """
    try:
        schedule_input = exporter.write_schedule_input_json(
            roster_rows,
            validation_rows,
            venue_input_path,
            output_dir / "schedule_input.json",
            pool_assignment_path=output_dir / "pool_assignments.json",
            manual_matchup_path=output_dir / "manual_team_matchups.json",
            manual_schedule_path=output_dir / "manual_schedule_overrides.json",
            match_schedule_overrides_path=output_dir / "match_schedule_overrides.json",
        )
        json_path = output_dir / "schedule_input.json"
        logger.info(
            f"schedule_input.json: {schedule_input['game_count']} games, "
            f"{schedule_input['resource_count']} resources -> {json_path}"
        )
    except Exception as _si_exc:
        logger.error(
            f"schedule_input.json generation failed (sport tabs will still be written): {_si_exc}",
            exc_info=True,
        )


def stamp_sport_export_tab_statuses(workbook) -> None:
    """Stamp the status banner on every tab of a Church_Team_Status workbook."""
    ScheduleWorkbookBuilder._stamp_known_tab_statuses(
        workbook,
        default_unknown=ScheduleWorkbookBuilder._SPORT_EXPORT_TAB_STATUS,
    )
