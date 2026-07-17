# schedule_workbook.py
# Version 1.0.0
# ScheduleWorkbookBuilder — extracted from church_teams_export.py (Issue #98 Step 1)
#
# Contains all scheduling-related methods that previously lived in
# ChurchTeamsExporter.  One-way dependency: church_teams_export.py may import
# from here; this module must NOT import from church_teams_export.
import json
import pandas as pd
from pathlib import Path
from loguru import logger
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from collections import defaultdict
import random
import re
from math import ceil

from config import (
    SPORT_TYPE,
    SPORT_FORMAT,
    FORMAT_MAPPINGS,
    SOCCER_ENABLED,
    RACQUET_SPORTS,
    is_racquet_sport,
    COURT_ESTIMATE_EVENTS,
    COURT_ESTIMATE_RACQUET_EVENTS,
    COURT_ESTIMATE_DEFAULT_POOL_GAMES_PER_TEAM,
    COURT_ESTIMATE_POOL_GAMES_PER_TEAM,
    COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME,
    COURT_ESTIMATE_INCLUDE_THIRD_PLACE_GAME,
    COURT_ESTIMATE_MIN_TEAM_SIZE,
    COURT_ESTIMATE_MINUTES_PER_GAME,
    COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE,
    COURT_ESTIMATE_BC_TEAMS_PER_GAME,
    COURT_ESTIMATE_BC_RR_GAMES_PER_TEAM,
    COURT_ESTIMATE_BC_PLAYOFF_GAMES,
    COURT_ESTIMATE_BC_MIN_TEAMS_FOR_PLAYOFF,
    COURT_ESTIMATE_PLAYOFF_RULES,
    POD_SPORT_ABBREV,
    SCHEDULE_SKETCH_SATURDAY_START,
    SCHEDULE_SKETCH_SATURDAY_LAST_GAME,
    SCHEDULE_SKETCH_SUNDAY_START,
    SCHEDULE_SKETCH_SUNDAY_LAST_GAME,
    GYM_RESOURCE_TYPE_BASKETBALL,
    GYM_RESOURCE_TYPE_VOLLEYBALL,
    TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE,
    TEAM_RESOURCE_TYPE_SOCCER,
    SCHEDULE_SOLVER_GYM_COURTS,
    VENUE_INPUT_FILENAME,
    POD_RESOURCE_EVENT_TYPE,
)
from validation.doubles_resolver import Selection as _DblSelection, resolve_doubles as _resolve_dbl
from validation.name_matcher import normalized_name as _norm_name
from validation.models import RulesManager
from schedule_styles import (
    category_style,
    category_prefix,
)
from scheduling import xlsx_utils, venue_loader, output_report
from scheduling import planning_tabs
from scheduling import manual_matchups
from scheduling import master_schedule
from scheduling import match_schedule_overrides
from scheduling import input_builder
from scheduling import conflict_edges
from scheduling import game_builder
from scheduling import pool_assignment


class ScheduleWorkbookBuilder:
    """Builds schedule-planning workbooks and schedule_input.json from roster data.

    This class contains no API connections and no WordPress connector.
    It is instantiated without arguments and used by export-church-teams
    (via ChurchTeamsExporter) and the standalone build-schedule-workbook command.

    The class-level _rules_manager_cache attribute is set lazily by
    _get_min_team_size; __init__ intentionally does not touch it.
    """

    _rules_manager_cache: Optional[RulesManager] = None
    _rules_manager_cache_failed: bool = False
    _racquet_entry_limit_cache: Dict[str, Tuple[Dict[str, int], Optional[int]]] = {}

    def __init__(self) -> None:
        pass

    _GYM_CORE_SOLVER_POOL = "Gym Core"
    _SPORT_EXPORT_TAB_STATUS: Tuple[str, str, str] = (
        "READ-ONLY OUTPUT",
        "Generated sport-specific roster view. Do not edit; rerun export-church-teams.",
        "D9EAF7",
    )

    _POOL_ASSIGNMENT_COLUMNS: List[str] = [
        "Event",
        "Church Team",
        "Team Order",
        "Team ID",
        "Team Label",
        "Team Source",
        "Roster Count",
        "Min Team Size",
        "Seed",
        "Random Draw Order",
        "Draw Position",
        "Pool ID",
        "Pool Slot",
        "Assignment Basis",
        "Notes",
    ]
    _POOL_ASSIGNMENT_NOTE = (
        "If you add in a seed number for the top teams for fair pool-play, remember to rerun "
        "assign-pools --workbook command (see HOW-TO for details)"
    )
    _POOL_ASSIGNMENT_EVENT_DEFS: List[Tuple[str, str]] = [
        (SPORT_TYPE["BASKETBALL"], "BBM"),
        (SPORT_TYPE["VOLLEYBALL_MEN"], "VBM"),
        (SPORT_TYPE["VOLLEYBALL_WOMEN"], "VBW"),
        (SPORT_TYPE["BIBLE_CHALLENGE"], "BC"),
    ] + (
        [(SPORT_TYPE["SOCCER"], "SOC")] if SOCCER_ENABLED else []
    )
    _POOL_ASSIGNMENT_HEADER_NOTES: Dict[str, str] = {
        "Event": (
            "Canonical team-sport event this row belongs to. Current Phase 1 "
            "pool-assignment rows cover BB / VBM / VBW / BC"
            + (" / SOC." if SOCCER_ENABLED else ".")
        ),
        "Church Team": (
            "Church code contributing this team row, such as RPC or TLC."
        ),
        "Team Order": (
            "Explicit team order when roster rows already carry one, such as A or B. "
            "Blank means the row currently represents the church-level team grouping."
        ),
        "Team ID": (
            "Stable team identifier used by the planning workbook. Usually the church code, "
            "or church code plus team order when team_order is available."
        ),
        "Team Label": (
            "Human-readable team label for operators. Usually matches Team ID in this first version."
        ),
        "Team Source": (
            "How this row was derived. ChurchLevel means one team row per church. "
            "ExplicitTeamOrder means the roster already carries a team_order value."
        ),
        "Roster Count": (
            "Number of participant roster rows currently contributing to this team row."
        ),
        "Min Team Size": (
            "Minimum roster size from the validation rules used to decide whether this team is eligible."
        ),
        "Seed": (
            "Operator-editable. Leave blank or enter 0 for an unseeded random draw. "
            "Enter 1, 2, 3... for ranked teams placed first in ascending order."
        ),
        "Random Draw Order": (
            "Stable random-draw order used for unseeded teams. Normally not edited by hand."
        ),
        "Draw Position": (
            "Computed overall placement order after seeded teams are sorted first and unseeded teams follow."
        ),
        "Pool ID": (
            "Computed assigned pool, such as P1 or P2."
        ),
        "Pool Slot": (
            "Computed slot within the assigned pool, such as T1 or T3. Under the 3-game "
            "policy, the highest slot in an odd pool (T5 in a 5-team pool, T7 in a 7-team "
            "pool) receives the extra 4th game."
        ),
        "Assignment Basis": (
            "Computed explanation for the row placement: Seeded, SeededDuplicate, "
            "RandomDraw, or WaitingForMoreTeams."
        ),
        "Notes": (
            "Operator notes. Safe to edit."
        ),
    }

    _POD_DIVISION_HEADER_NOTES: Dict[str, str] = {
        "division_id": (
            "Canonical division label used across the planning tabs. "
            "Built from sport + gender + format, for example BAD-Men-Doubles."
        ),
        "sport_type": (
            "Base sport name for this division, such as Badminton, Pickleball, "
            "Table Tennis, or Tennis."
        ),
        "sport_gender": (
            "Gender bucket for the division: Men, Women, or Mixed."
        ),
        "sport_format": (
            "Division format used for planning: Singles, Doubles, or an anomaly placeholder "
            "when the roster data does not fit a normal pod division."
        ),
        "resource_type": (
            "Exact court or table resource type this division needs in the venue plan and solver. "
            "This must line up with the resource names used in venue_input.xlsx and schedule_input.json."
        ),
        "minutes_per_game": (
            "Planning duration per game in minutes for this division."
        ),
        "planning_entries": (
            "Total entries the planner can currently schedule for this division. "
            "For doubles, this counts pairs, not individual people."
        ),
        "confirmed_entries": (
            "Entries currently considered ready for planning after open ERROR-level validation issues "
            "are excluded. For doubles, this also counts pairs, not people."
        ),
        "provisional_entries": (
            "Entries that appear to exist mathematically but still need cleanup before they are fully "
            "confirmed, such as unresolved validation issues."
        ),
        "anomaly_count": (
            "Roster rows that did not fit a normal Singles or Doubles planning entry and therefore "
            "need manual review."
        ),
        "division_status": (
            "Planner readiness flag. Ready = clean to plan, Partial = some entries still need review, "
            "AnomalyOnly = only anomaly rows exist, Empty = no entries found."
        ),
        "notes": (
            "Operator notes column for manual comments or follow-up reminders."
        ),
    }
    _VENUE_ESTIMATOR_HEADER_NOTES: Dict[str, str] = {
        "Event": (
            "Canonical event name used for the venue estimate."
        ),
        "Potential Teams/Entries": (
            "Rule-aware ceiling for this event based on current registrations. Team sports count "
            "all current team units with at least one roster entry; racquet sports cap each "
            "church using the 2026 entry-limit rules while still allowing incomplete doubles "
            "pairs to mature into valid entries."
        ),
        "Estimating Teams/Entries": (
            "Entries currently counted for court estimation. Team sports count only churches "
            "that meet minimum team size; racquet sports count singles plus complete doubles pairs."
        ),
        "Teams": (
            "Comma-separated qualifying team identifiers. Usually these are church codes, but "
            "explicit A/B team splits appear as church code plus team order, such as RPC-A."
        ),
        "Target Pool Games/Team": (
            "Configured planning target for pool games per team. This column is generated "
            "from middleware/config.py and is not edited in Excel. Supported core team-sport "
            "targets are 2 and 3."
        ),
        "Actual Pool Games/Team": (
            "Actual pool-game planning assumption for this event. For the standard team-sport "
            "model this is the average implied by the normalized pool layout; for 3-game "
            "team-sport mode, odd team counts may show a value slightly above 3.0 when one "
            "odd-size pool gives its highest slot an extra game. For Bible "
            "Challenge it reflects the organizer-facing 2-games-per-team target once enough "
            "teams exist to run the Jeopardy format."
        ),
        "Pool Composition": (
            "Pool sizes used by the current planning policy, such as 4 + 3 + 3. Under the "
            "3-game policy, a 5-team or 7-team pool note means the highest slot in that odd "
            "pool takes the extra 4th game."
        ),
        "BYE Slots": (
            "Implicit bye slots created by the current pool layout. Most relevant when 5-team pools "
            "are used under the 2-game planning policy."
        ),
        "Minutes Per Game": (
            "Planning duration in minutes for one game in this event."
        ),
        "Pool Slots": (
            "Total pool-stage game slots needed for this event."
        ),
        "Playoff Teams": (
            "Number of teams assumed to advance from pools into the playoff bracket."
        ),
        "Playoff Slots": (
            "Bracket game slots required, excluding any third-place game."
        ),
        "Third Place?": (
            "Whether the estimate assumes a third-place game for this event."
        ),
        "Third Place Slots": (
            "Additional slots reserved for a third-place game when enabled."
        ),
        "Total Court Slots": (
            "Total planned slots for this event: pool + playoff + third-place."
        ),
        "Estimated Court Hours": (
            "Approximate court-hours required for this event based on total slots and minutes per game."
        ),
    }
    _POD_ENTRY_HEADER_NOTES: Dict[str, str] = {
        "entry_id": (
            "Unique row ID for this review entry within the workbook."
        ),
        "division_id": (
            "Canonical pod division label that this entry belongs to, such as BAD-Men-Doubles."
        ),
        "entry_type": (
            "Planner classification for the entry: Singles, DoublesPair, UnresolvedDoubles, or Anomaly."
        ),
        "participant_1_name": (
            "Primary participant name for the entry."
        ),
        "participant_2_name": (
            "Second participant name for a confirmed doubles pair. Blank for singles, unresolved, or anomaly rows."
        ),
        "source_participant_ids": (
            "Underlying participant IDs that produced this planning entry. Usually WordPress participant IDs, "
            "with ChMeetings IDs as fallback if needed."
        ),
        "church_team": (
            "Church code or codes contributing to this entry."
        ),
        "partner_status": (
            "Partner-matching result. Examples: N/A, Confirmed, MissingPartner, PartnerNotFound, or NonReciprocal."
        ),
        "review_status": (
            "Operator readiness flag. OK means clean enough for planning; NeedsReview means the entry still needs manual attention."
        ),
        "notes": (
            "Reason the entry needs review, plus room for operator notes."
        ),
    }
    _POD_RESOURCE_HEADER_NOTES: Dict[str, str] = {
        "Event": (
            "Racquet event being evaluated for pod-resource fit."
        ),
        "Resource Type": (
            "Exact court or table type that this event requires."
        ),
        "Entries / Teams": (
            "Planning entries counted for this event. Doubles count as complete pairs, not individual people."
        ),
        "Required Slots": (
            "Approximate match slots required under the current single-elimination assumption: entries minus one."
        ),
        "Available Slots": (
            "Slots currently available for this resource type from venue_input.xlsx or the derived schedule-input resources."
        ),
        "Surplus / Shortage": (
            "Available slots minus required slots. Negative values mean the venue is short."
        ),
        "Fit Status": (
            "Traffic-light summary. Green = enough slots, Yellow = small shortage, Red = larger shortage, "
            "No venue data = availability could not be loaded."
        ),
    }
    _SCHEDULE_INPUT_GAME_HEADER_NOTES: Dict[str, str] = {
        "game_id": (
            "Unique placeholder game ID used by the solver and by playoff-slot pinning."
        ),
        "event": (
            "Canonical event name for the game."
        ),
        "stage": (
            "Tournament stage, such as Pool, QF, Semi, Final, or 3rd."
        ),
        "pool_id": (
            "Pool label for pool-stage games. Blank for non-pool games."
        ),
        "round": (
            "Round number within the stage when applicable."
        ),
        "team_a_id": (
            "Placeholder team slot or team ID for side A."
        ),
        "team_b_id": (
            "Placeholder team slot or team ID for side B."
        ),
        "team_c_id": (
            "Optional third team ID for multi-team games such as Bible Challenge."
        ),
        "duration_minutes": (
            "Game duration in minutes used by the solver."
        ),
        "resource_type": (
            "Exact resource type this game must be assigned to."
        ),
        "earliest_slot": (
            "Optional earliest allowed slot constraint for this game."
        ),
        "latest_slot": (
            "Optional latest allowed slot constraint for this game."
        ),
    }
    _SCHEDULE_INPUT_PRECEDENCE_HEADER_NOTES: Dict[str, str] = {
        "before_game_id": (
            "Game that must start before the paired after_game_id."
        ),
        "after_game_id": (
            "Game that must start after before_game_id."
        ),
        "min_gap_slots": (
            "Minimum number of solver slot starts that must separate the two games."
        ),
    }
    _SCHEDULE_INPUT_RESOURCE_HEADER_NOTES: Dict[str, str] = {
        "resource_id": (
            "Exact solver resource ID. This is the value to copy into Playoff-Slots when pinning games."
        ),
        "resource_type": (
            "Resource category offered by this row, such as Basketball Court or Badminton Court."
        ),
        "label": (
            "Human-readable label for the resource, usually what operators will recognize on-site."
        ),
        "day": (
            "Schedule day key, such as Fri-1, Sat-1, Sun-1, Fri-2, or Sun-2."
        ),
        "open_time": (
            "Start of the available scheduling window for this resource."
        ),
        "close_time": (
            "End of the available scheduling window for this resource."
        ),
        "slot_minutes": (
            "Length of each solver slot for this resource."
        ),
        "exclusive_group": (
            "Mutually-exclusive venue group, if any. Resources in the same group cannot all be used at once."
        ),
    }
    _SCHEDULE_INPUT_PLAYOFF_HEADER_NOTES: Dict[str, str] = {
        "game_id": (
            "Exact playoff game ID to pin to a specific slot."
        ),
        "event": (
            "Canonical event name for the pinned playoff game."
        ),
        "stage": (
            "Playoff stage being pinned, such as QF, Semi, Final, or 3rd."
        ),
        "resource_id": (
            "Exact resource ID the playoff game must use."
        ),
        "slot": (
            "Exact solver slot label, typically Day-HH:MM, that the playoff game must occupy."
        ),
        "x_master_schedule_cell": (
            "Source cell in the imported visual master schedule workbook, when this fixed slot came from manual_schedule_overrides.json."
        ),
        "x_master_schedule_raw": (
            "Raw source value from the imported visual master schedule workbook, useful for auditing unresolved or surprising pins."
        ),
    }
    _GYM_ALLOCATION_DECISION_HEADER_NOTES: Dict[str, str] = {
        "gym_name": (
            "Exclusive Venue Group / gym block name being allocated."
        ),
        "day": (
            "Schedule day for this gym block."
        ),
        "open_time": (
            "Start time of the allocated gym block."
        ),
        "close_time": (
            "End time of the allocated gym block."
        ),
        "mode": (
            "Chosen sport mode or resource mode for this block."
        ),
        "courts": (
            "Number of courts assigned to the chosen mode in this block."
        ),
        "slot_minutes": (
            "Slot length in minutes for this block."
        ),
    }
    _GYM_ALLOCATION_SUPPLY_HEADER_NOTES: Dict[str, str] = {
        "mode": (
            "Sport mode or resource mode being compared."
        ),
        "demand": (
            "Total slot demand from games needing this mode."
        ),
        "supply": (
            "Total slot supply produced by the allocator for this mode."
        ),
        "shortfall": (
            "Unmet slots after allocation. Zero means the current allocation covers demand."
        ),
    }

    # ── Shared helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _decompose_event_name(event_name: str) -> Tuple[str, str, str]:
        """Split a canonical event name like 'Basketball - Men Team' into
        (sport_type, sport_gender, sport_format) using the same casing the
        roster rows store after sync."""
        parts = event_name.split(" - ", 1)
        sport_type = parts[0].strip()
        if len(parts) < 2:
            return sport_type, "", "Team"
        suffix = parts[1].upper()
        if "WOMEN" in suffix:
            gender = "Women"
        elif "MEN" in suffix:
            gender = "Men"
        elif "MIXED" in suffix or "COED" in suffix:
            gender = "Mixed"
        else:
            gender = ""
        sport_format = "Singles" if "SINGLES" in suffix else "Team"
        return sport_type, gender, sport_format

    @classmethod
    def _get_rules_manager(cls) -> Optional[RulesManager]:
        """Return the cached SUMMER_2026 RulesManager when available."""
        rules_manager_cache = getattr(cls, "_rules_manager_cache", None)
        rules_manager_cache_failed = bool(getattr(cls, "_rules_manager_cache_failed", False))
        if rules_manager_cache is None and not rules_manager_cache_failed:
            try:
                setattr(cls, "_rules_manager_cache", RulesManager(collection="SUMMER_2026"))
            except Exception as e:
                logger.warning(f"Could not load validation rules for venue estimate: {e}")
                setattr(cls, "_rules_manager_cache_failed", True)
        return getattr(cls, "_rules_manager_cache", None)

    @classmethod
    def _get_min_team_size(cls, event_name: str) -> int:
        """Look up minimum team size from the validation ruleset; fall back
        to COURT_ESTIMATE_MIN_TEAM_SIZE if the JSON rule is absent."""
        rules_manager = cls._get_rules_manager()
        if rules_manager is not None:
            for rule in rules_manager.get_rules_for_sport(event_name):
                if rule.get("rule_type") == "team_size" and rule.get("category") == "min":
                    try:
                        return int(rule.get("value"))
                    except (TypeError, ValueError):
                        pass
        return int(COURT_ESTIMATE_MIN_TEAM_SIZE.get(event_name, 0))

    @classmethod
    def _count_estimating_teams(cls, roster_rows: List[Dict[str, Any]],
                                 event_name: str, min_team_size: int) -> Dict[str, Any]:
        """Return estimating/potential team counts and the qualifying team ids.

        Approval-agnostic — every roster entry counts.

        Returns a dict with:
          n_estimating  – teams with >= min_team_size entries (ready to compete)
          n_potential   – teams with >= 1 but < min_team_size entries (still forming)
          team_codes    – sorted, comma-separated list of estimating team ids
        """
        if min_team_size <= 0:
            return {"n_estimating": 0, "n_potential": 0, "team_codes": ""}
        target_type, target_gender, _ = cls._decompose_event_name(event_name)
        counts_by_team: Dict[Tuple[str, str], int] = {}
        for r in roster_rows:
            r_type = str(r.get("sport_type") or "").strip()
            r_gender = str(r.get("sport_gender") or "").strip()
            # Primary/secondary sports are stored as the base name (e.g. "Basketball");
            # Other-Events sports are stored as the full SPORT_TYPE value verbatim.
            # Accept either so both paths match.
            if (r_type.casefold() != target_type.casefold() and
                    r_type.casefold() != event_name.casefold()):
                continue
            if target_gender and r_gender.casefold() != target_gender.casefold():
                continue
            church = str(r.get("Church Team") or "").strip().upper()
            if not church:
                continue
            team_order = str(r.get("team_order") or "").strip().upper()
            team_key = (church, team_order)
            counts_by_team[team_key] = counts_by_team.get(team_key, 0) + 1
        estimating = sorted(
            church if not team_order else f"{church}-{team_order}"
            for (church, team_order), n in counts_by_team.items()
            if n >= min_team_size
        )
        partial = [
            (church, team_order)
            for (church, team_order), n in counts_by_team.items()
            if 0 < n < min_team_size
        ]
        return {
            "n_estimating": len(estimating),
            "n_potential": len(estimating) + len(partial),  # all team units with >= 1 entry
            "team_codes": ", ".join(estimating),
        }

    @staticmethod
    def _get_playoff_teams(n_teams: int) -> int:
        for rule in COURT_ESTIMATE_PLAYOFF_RULES:
            if rule["min_teams"] <= n_teams <= rule["max_teams"]:
                return int(rule["playoff_teams"])
        return 0

    @staticmethod
    def _get_playoff_teams_for_event(event_name: str, n_teams: int) -> int:
        """Return playoff-team count for one event under the live planning policy."""
        if event_name == SPORT_TYPE["SOCCER"]:
            return 4 if n_teams >= 4 else 0
        return ScheduleWorkbookBuilder._get_playoff_teams(n_teams)

    def _compute_court_slots(self, n_teams: int,
                              minutes_per_game: int = COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME,
                              pool_games_per_team: int = COURT_ESTIMATE_DEFAULT_POOL_GAMES_PER_TEAM,
                              actual_pool_games: Optional[int] = None,
                              event_name: str = "") -> Dict[str, Any]:
        include_third = COURT_ESTIMATE_INCLUDE_THIRD_PLACE_GAME

        # When the caller already knows the exact game count (e.g. from
        # _make_pool_game_pairs), use it directly so the Venue-Estimator and
        # schedule_input.json stay aligned with the current pool-generation
        # policy instead of falling back to a rough ceil(n*gpg/2) estimate.
        if actual_pool_games is not None:
            pool_slots = actual_pool_games
        else:
            pool_slots = ceil((n_teams * pool_games_per_team) / 2) if n_teams > 0 else 0
        playoff_teams = self._get_playoff_teams_for_event(event_name, n_teams)
        playoff_slots = max(playoff_teams - 1, 0)
        third_place_slots = 1 if include_third and playoff_teams >= 4 else 0
        total_slots = pool_slots + playoff_slots + third_place_slots
        return {
            "pool_games_per_team": pool_games_per_team,
            "minutes_per_game": minutes_per_game,
            "pool_slots": pool_slots,
            "playoff_teams": playoff_teams,
            "playoff_slots": playoff_slots,
            "include_third_place": include_third,
            "third_place_slots": third_place_slots,
            "total_slots": total_slots,
            "court_hours": round(total_slots * minutes_per_game / 60, 2),
        }

    @staticmethod
    def _normalize_racquet_gender(raw_gender: str, raw_format: str = "") -> str:
        """Normalize a racquet roster row's gender to Men/Women/Mixed when possible."""
        tokens = f"{raw_gender} {raw_format}".casefold()
        if "women" in tokens:
            return "Women"
        if "mixed" in tokens or "coed" in tokens:
            return "Mixed"
        if "men" in tokens:
            return "Men"
        return ""

    @classmethod
    def _get_racquet_entry_limits(cls, sport_name: str) -> Tuple[Dict[str, int], Optional[int]]:
        """Return ({format parameter -> max entries}, doubles_total_limit) for one racquet sport."""
        cache = getattr(cls, "_racquet_entry_limit_cache", None)
        if cache is None:
            cache = {}
            setattr(cls, "_racquet_entry_limit_cache", cache)
        cached = cache.get(sport_name)
        if cached is not None:
            return cached

        format_limits: Dict[str, int] = {}
        doubles_total_limit: Optional[int] = None
        rules_manager = cls._get_rules_manager()
        if rules_manager is not None:
            for rule in rules_manager.get_rules_for_sport(sport_name):
                if rule.get("rule_type") != "entry_limit":
                    continue
                parameter = str(rule.get("parameter") or "").strip()
                category = str(rule.get("category") or "").strip()
                try:
                    max_entries = int(rule.get("value"))
                except (TypeError, ValueError):
                    continue
                if category == "format" and parameter:
                    format_limits[parameter] = max_entries
                elif (
                    category == "format_total"
                    and parameter.casefold() == SPORT_FORMAT["DOUBLES"].casefold()
                ):
                    doubles_total_limit = max_entries

        cache[sport_name] = (format_limits, doubles_total_limit)
        return format_limits, doubles_total_limit

    @classmethod
    def _racquet_rule_parameter_for_row(cls, row: Dict[str, Any]) -> Optional[str]:
        """Map one racquet roster row to a church-level entry-limit parameter."""
        raw_format = str(row.get("sport_format") or "").strip()
        format_cf = raw_format.casefold()
        gender = cls._normalize_racquet_gender(
            str(row.get("sport_gender") or "").strip(),
            raw_format,
        )

        if "single" in format_cf:
            if gender in {"Men", "Women"}:
                return f"{gender} Single"
            return None
        if "double" in format_cf or format_cf == SPORT_FORMAT["TEAM"].casefold() or not format_cf:
            if gender in {"Men", "Women", "Mixed"}:
                return f"{gender} Double"
            return None
        return None

    def _count_racquet_entries(self, roster_rows: List[Dict[str, Any]],
                               sport_name: str) -> Dict[str, Any]:
        """Count racquet sport entries for the venue estimator.

        Estimating Entries = complete pairs floor(n_doubles / 2) + n_singles.
        Potential Entries  = rule-aware per-church ceiling using the SUMMER_2026
                             entry-limit rules, while still allowing incomplete
                             doubles registrations to mature into valid pairs.
        """
        n_singles = 0
        n_doubles = 0
        singles_by_church: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        doubles_regs_by_church: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        fallback_potential_by_church: Dict[str, int] = defaultdict(int)
        for r in roster_rows:
            if str(r.get("sport_type") or "").strip().casefold() != sport_name.casefold():
                continue
            fmt = str(r.get("sport_format") or "").strip().casefold()
            church = str(r.get("Church Team") or "").strip().upper()
            parameter = self._racquet_rule_parameter_for_row(r)
            if "single" in fmt:
                n_singles += 1
                if church and parameter:
                    singles_by_church[church][parameter] += 1
                elif church:
                    fallback_potential_by_church[church] += 1
            else:
                n_doubles += 1
                if church and parameter:
                    doubles_regs_by_church[church][parameter] += 1
                elif church:
                    fallback_potential_by_church[church] += 1
        n_estimating = n_singles + (n_doubles // 2)
        format_limits, doubles_total_limit = self._get_racquet_entry_limits(sport_name)
        if format_limits or doubles_total_limit is not None:
            churches = (
                set(singles_by_church.keys())
                | set(doubles_regs_by_church.keys())
                | set(fallback_potential_by_church.keys())
            )
            n_potential = 0
            for church in churches:
                church_total = fallback_potential_by_church.get(church, 0)
                for parameter, count in singles_by_church.get(church, {}).items():
                    limit = format_limits.get(parameter)
                    church_total += min(count, limit) if limit is not None else count
                doubles_total = 0
                for parameter, count in doubles_regs_by_church.get(church, {}).items():
                    team_count = ceil(count / 2)
                    limit = format_limits.get(parameter)
                    doubles_total += min(team_count, limit) if limit is not None else team_count
                if doubles_total_limit is not None:
                    doubles_total = min(doubles_total, doubles_total_limit)
                church_total += doubles_total
                n_potential += church_total
        else:
            n_potential = n_singles + n_doubles
        return {
            "n_estimating": n_estimating,
            "n_potential": n_potential,
            "team_codes": "",
        }

    # ── Pod helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _pod_format_class(sport_format: str) -> str:
        """Classify a sport_format string into 'singles', 'doubles', or 'anomaly'."""
        fmt = (sport_format or "").strip().casefold()
        if "single" in fmt:
            return "singles"
        if "double" in fmt:
            return "doubles"
        return "anomaly"

    @staticmethod
    def _make_division_id(sport_type: str, sport_gender: str, format_class: str) -> str:
        """Return a canonical division_id string, e.g. 'BAD-Men-Singles'."""
        abbrev = POD_SPORT_ABBREV.get(sport_type, sport_type[:3].upper())
        gender_part = sport_gender or "Unknown"
        format_part = format_class.title() if format_class != "anomaly" else "Anomaly"
        return f"{abbrev}-{gender_part}-{format_part}"

    @staticmethod
    def _build_pod_error_lookup(
        validation_rows: List[Dict[str, Any]],
    ) -> Dict[str, set]:
        """Return {str(participant_id) → set(sport_types)} for open ERRORs."""
        lookup: Dict[str, set] = {}
        for v in validation_rows:
            if str(v.get("Severity", "")).upper() != "ERROR":
                continue
            if str(v.get("Status", "")).lower() != "open":
                continue
            pid = str(v.get("Participant ID (WP)") or "").strip()
            if not pid or pid in ("0",):
                continue
            sport = str(v.get("sport_type") or "").strip()
            lookup.setdefault(pid, set()).add(sport)
        return lookup

    def _build_pod_divisions_rows(
        self,
        roster_rows: List[Dict[str, Any]],
        validation_rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Build one summary row per pod division for the Pod-Divisions tab."""
        error_lookup = self._build_pod_error_lookup(validation_rows)

        # Accumulate per-division counts.
        # key: (sport_type, sport_gender, format_class)
        divs: Dict[tuple, Dict[str, Any]] = {}
        seen_singles_ids: Dict[tuple, set[str]] = defaultdict(set)

        for r in roster_rows:
            sport_type = str(r.get("sport_type") or "").strip()
            if sport_type not in RACQUET_SPORTS:
                continue
            sport_gender = str(r.get("sport_gender") or "").strip()
            sport_format = str(r.get("sport_format") or "").strip()
            fmt_class = self._pod_format_class(sport_format)

            key = (sport_type, sport_gender, fmt_class)
            if key not in divs:
                divs[key] = {
                    "sport_type": sport_type,
                    "sport_gender": sport_gender,
                    "sport_format": sport_format,
                    "n_total": 0,
                    "n_confirmed": 0,
                    "n_anomaly": 0,
                }

            pid = str(r.get("Participant ID (WP)") or "").strip()
            if fmt_class == "singles" and pid:
                if pid in seen_singles_ids[key]:
                    continue
                seen_singles_ids[key].add(pid)
            has_error = bool(pid and pid not in ("0",) and sport_type in error_lookup.get(pid, set()))

            if fmt_class == "anomaly":
                divs[key]["n_anomaly"] += 1
            else:
                divs[key]["n_total"] += 1
                if not has_error:
                    divs[key]["n_confirmed"] += 1

        rows: List[Dict[str, Any]] = []
        for (sport_type, sport_gender, fmt_class), div in sorted(divs.items()):
            division_id = self._make_division_id(sport_type, sport_gender, fmt_class)
            mpg = COURT_ESTIMATE_MINUTES_PER_GAME.get(sport_type, COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME)

            if fmt_class == "doubles":
                planning = div["n_total"] // 2
                confirmed = div["n_confirmed"] // 2
            else:
                planning = div["n_total"]
                confirmed = div["n_confirmed"]

            provisional = planning - confirmed
            anomaly_count = div["n_anomaly"]

            if planning == 0 and anomaly_count == 0:
                status = "Empty"
            elif planning == 0:
                status = "AnomalyOnly"
            elif anomaly_count > 0 or provisional > 0:
                status = "Partial"
            else:
                status = "Ready"

            rows.append({
                "division_id": division_id,
                "sport_type": sport_type,
                "sport_gender": sport_gender,
                "sport_format": div["sport_format"],
                # Keep pod division rows aligned with venue_input.xlsx and the solver's
                # exact C4 resource-type matching. Generic "Court" breaks all pod games.
                "resource_type": POD_RESOURCE_EVENT_TYPE.get(sport_type, "Court"),
                "minutes_per_game": mpg,
                "planning_entries": planning,
                "confirmed_entries": confirmed,
                "provisional_entries": provisional,
                "anomaly_count": anomaly_count,
                "division_status": status,
                "notes": "",
            })

        return rows

    def _build_pod_entries_review_rows(
        self,
        roster_rows: List[Dict[str, Any]],
        validation_rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Build one review row per singles player, doubles pair, or anomaly.

        Doubles are matched by reciprocal partner_name declarations using
        normalized name comparison. Unmatched doubles surface as UnresolvedDoubles.
        Confirmed/provisional status is determined by open ERROR presence.
        """
        error_lookup = self._build_pod_error_lookup(validation_rows)

        # Separate racquet entries by format class.
        singles_rows: List[Dict[str, Any]] = []
        doubles_rows: List[Dict[str, Any]] = []
        anomaly_rows: List[Dict[str, Any]] = []

        for r in roster_rows:
            sport_type = str(r.get("sport_type") or "").strip()
            if sport_type not in RACQUET_SPORTS:
                continue
            fmt_class = self._pod_format_class(str(r.get("sport_format") or ""))
            if fmt_class == "singles":
                singles_rows.append(r)
            elif fmt_class == "doubles":
                doubles_rows.append(r)
            else:
                anomaly_rows.append(r)

        entry_rows: List[Dict[str, Any]] = []
        entry_counter = 0

        def _full_name(r: Dict[str, Any]) -> str:
            return f"{r.get('First Name', '')} {r.get('Last Name', '')}".strip()

        def _pid(r: Dict[str, Any]) -> str:
            return str(r.get("Participant ID (WP)") or r.get("ChMeetings ID") or "").strip()

        def _has_error(r: Dict[str, Any]) -> bool:
            pid = _pid(r)
            sport = str(r.get("sport_type") or "").strip()
            return bool(pid and pid not in ("0",) and sport in error_lookup.get(pid, set()))

        # Singles — one entry per participant.
        for r in singles_rows:
            entry_counter += 1
            sport_type = str(r.get("sport_type") or "").strip()
            sport_gender = str(r.get("sport_gender") or "").strip()
            division_id = self._make_division_id(sport_type, sport_gender, "singles")
            entry_rows.append({
                "entry_id": entry_counter,
                "division_id": division_id,
                "entry_type": "Singles",
                "participant_1_name": _full_name(r),
                "participant_2_name": "",
                "source_participant_ids": _pid(r),
                "church_team": str(r.get("Church Team") or ""),
                "partner_status": "N/A",
                "review_status": "NeedsReview" if _has_error(r) else "OK",
                "notes": "",
            })

        # Doubles — use canonical resolver grouped by division (sport_type + sport_gender).
        doubles_by_div: Dict[tuple, List[Dict[str, Any]]] = {}
        for r in doubles_rows:
            sport_type = str(r.get("sport_type") or "").strip()
            sport_gender = str(r.get("sport_gender") or "").strip()
            doubles_by_div.setdefault((sport_type, sport_gender), []).append(r)

        for (sport_type, sport_gender), div_rows in sorted(doubles_by_div.items()):
            division_id = self._make_division_id(sport_type, sport_gender, "doubles")

            # Build Selection objects; use index-scoped synthetic IDs when PID is absent.
            row_by_sel_id: Dict[str, Dict[str, Any]] = {}
            sel_objs: List[_DblSelection] = []
            for i, r in enumerate(div_rows):
                pid = _pid(r)
                sel_id = pid if pid else f"_div_{division_id}_idx_{i}"
                name = _full_name(r)
                partner_decl = str(r.get("partner_name") or "").strip()
                sel_objs.append(_DblSelection(
                    participant_id=sel_id,
                    name=name,
                    norm_name=_norm_name(name),
                    partner_name=partner_decl,
                    partner_norm_name=_norm_name(partner_decl),
                    sport_type=sport_type,
                    sport_format=str(r.get("sport_format") or "").strip(),
                    church_code=str(r.get("Church Team") or "").strip(),
                    group_key=division_id,
                ))
                row_by_sel_id[sel_id] = r

            confirmed_pairs, unresolved_recs = _resolve_dbl(sel_objs)

            for pair in confirmed_pairs:
                pid_a, pid_b = pair.participant_ids
                r_a = row_by_sel_id.get(pid_a)
                r_b = row_by_sel_id.get(pid_b)
                both_ok = bool(
                    r_a and not _has_error(r_a)
                    and r_b and not _has_error(r_b)
                )
                churches = ", ".join(c for c in sorted({
                    str((r_a or {}).get("Church Team") or ""),
                    str((r_b or {}).get("Church Team") or ""),
                }) if c)
                entry_counter += 1
                entry_rows.append({
                    "entry_id": entry_counter,
                    "division_id": division_id,
                    "entry_type": "DoublesPair",
                    "participant_1_name": pair.participant_names.get(pid_a, ""),
                    "participant_2_name": pair.participant_names.get(pid_b, ""),
                    "source_participant_ids": ", ".join(filter(None, [pid_a, pid_b])),
                    "church_team": churches,
                    "partner_status": "Confirmed",
                    "sport_format": pair.sport_format,
                    "review_status": "OK" if both_ok else "NeedsReview",
                    "notes": "",
                })

            for rec in unresolved_recs:
                if rec.reason == "SelfPaired":
                    note = "Participant listed themselves as their own partner"
                elif rec.reason == "NonReciprocal":
                    note = f"Partner '{rec.partner_name}' found but did not reciprocate"
                elif rec.reason == "AmbiguousPartner":
                    note = f"Partner '{rec.partner_name}' matches multiple participants"
                elif rec.reason == "MissingPartner":
                    note = "No partner declared"
                else:
                    note = f"Partner '{rec.partner_name}' not in same-division roster"
                # Recover the real PID (may differ from sel_id when synthetic).
                real_pid = _pid(row_by_sel_id.get(rec.participant_id) or {})
                entry_counter += 1
                entry_rows.append({
                    "entry_id": entry_counter,
                    "division_id": division_id,
                    "entry_type": "UnresolvedDoubles",
                    "participant_1_name": rec.name,
                    "participant_2_name": "",
                    "source_participant_ids": real_pid,
                    "church_team": rec.church_code,
                    "partner_status": rec.reason,
                    "sport_format": rec.sport_format,
                    "review_status": "NeedsReview",
                    "notes": note,
                })

        # Anomalies — non-standard format rows for racquet sports.
        for r in anomaly_rows:
            entry_counter += 1
            sport_type = str(r.get("sport_type") or "").strip()
            sport_gender = str(r.get("sport_gender") or "").strip()
            division_id = self._make_division_id(sport_type, sport_gender, "anomaly")
            entry_rows.append({
                "entry_id": entry_counter,
                "division_id": division_id,
                "entry_type": "Anomaly",
                "participant_1_name": _full_name(r),
                "participant_2_name": "",
                "source_participant_ids": _pid(r),
                "church_team": str(r.get("Church Team") or ""),
                "partner_status": "N/A",
                "review_status": "NeedsReview",
                "notes": f"Unexpected format '{r.get('sport_format', '')}' for racquet sport",
            })

        return entry_rows

    def _resolve_pod_doubles(
        self,
        roster_rows: List[Dict[str, Any]],
        validation_rows: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
        """Resolve racquet DOUBLES entries for conflict modeling (Issue #158).

        Reuses the reciprocal-partner pairing in `_build_pod_entries_review_rows`
        so confirmed pairs are resolved exactly once and never diverge.  Returns
        a tuple:

          confirmed_by_division: {division_id: [entry, ...]} where each entry is
            a confirmed doubles pair carrying a stable ``entry_id`` of the form
            ``{division_id}-E{nn}`` (e.g. ``BAD-Men-Doubles-E01``), the pair's
            participant IDs/names, and each member's normalized primary sport.
            Entries are sorted by participant IDs so the IDs are reproducible
            across re-runs of the same roster.
          unprotected: [{division_id, participant_name, reason, notes}] for
            UnresolvedDoubles entries — flagged but not conflict-protected
            because their membership is unknown.

        Singles are intentionally ignored (Decision 3: doubles first).
        """
        # division_id -> (sport_type, sport_gender) for doubles divisions only.
        div_meta: Dict[str, Tuple[str, str]] = {}
        # participant_id -> {name, primary_sport} across all racquet entries.
        pid_info: Dict[str, Dict[str, str]] = {}
        for r in roster_rows:
            sport_type = str(r.get("sport_type") or "").strip()
            if sport_type not in RACQUET_SPORTS:
                continue
            sport_gender = str(r.get("sport_gender") or "").strip()
            pid = str(r.get("Participant ID (WP)") or r.get("ChMeetings ID") or "").strip()
            if pid:
                full_name = (
                    f"{str(r.get('First Name') or '').strip()} "
                    f"{str(r.get('Last Name') or '').strip()}"
                ).strip()
                pid_info[pid] = {
                    "name": full_name or pid,
                    "primary_sport": self._normalize_primary_sport_name(
                        r.get("participant_primary_sport")
                    ),
                }
            if self._pod_format_class(str(r.get("sport_format") or "")) == "doubles":
                division_id = self._make_division_id(sport_type, sport_gender, "doubles")
                div_meta[division_id] = (sport_type, sport_gender)

        confirmed_by_division: Dict[str, List[Dict[str, Any]]] = {}
        unprotected: List[Dict[str, Any]] = []
        for row in self._build_pod_entries_review_rows(roster_rows, validation_rows):
            division_id = str(row.get("division_id") or "").strip()
            if row.get("entry_type") == "DoublesPair":
                pids = [
                    p.strip()
                    for p in str(row.get("source_participant_ids") or "").split(",")
                    if p.strip()
                ]
                pair_names = [
                    str(row.get("participant_1_name") or "").strip(),
                    str(row.get("participant_2_name") or "").strip(),
                ]
                sport_type, sport_gender = div_meta.get(division_id, ("", ""))
                confirmed_by_division.setdefault(division_id, []).append({
                    "division_id": division_id,
                    "sport_type": sport_type,
                    "sport_gender": sport_gender,
                    "sport_format": SPORT_FORMAT["DOUBLES"],
                    "participant_ids": pids,
                    "participant_names": {
                        pid: pid_info.get(pid, {}).get("name", pid) for pid in pids
                    },
                    "primary_sports": {
                        pid: pid_info.get(pid, {}).get("primary_sport", "") for pid in pids
                    },
                    "pair_names": pair_names,
                })
            elif row.get("entry_type") == "UnresolvedDoubles":
                sport_type_u, sport_gender_u = div_meta.get(division_id, ("", ""))
                raw_pid = str(row.get("source_participant_ids") or "").strip()
                unprotected.append({
                    "division_id": division_id,
                    "participant_id": raw_pid or None,
                    "participant_name": str(row.get("participant_1_name") or "").strip(),
                    "sport_type": sport_type_u,
                    "sport_format": str(row.get("sport_format") or "").strip(),
                    "sport_gender": sport_gender_u,
                    "church_code": str(row.get("church_team") or "").strip(),
                    "reason": str(row.get("partner_status") or "Unresolved").strip(),
                    "notes": str(row.get("notes") or "").strip(),
                })

        # Assign deterministic, reproducible entry IDs per division.
        for division_id, entries in confirmed_by_division.items():
            entries.sort(key=lambda e: (tuple(sorted(e["participant_ids"])), tuple(e["pair_names"])))
            for idx, entry in enumerate(entries, start=1):
                entry["entry_id"] = f"{division_id}-E{idx:02d}"
                pair_label = " / ".join(n for n in entry["pair_names"] if n)
                entry["label"] = (
                    f"{entry['entry_id']} ({pair_label})" if pair_label else entry["entry_id"]
                )

        return confirmed_by_division, unprotected

    def _resolve_pod_singles(
        self,
        roster_rows: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Resolve racquet SINGLES entries for conflict modeling (Issue #164).

        Singles membership is always known — one participant per entry, no
        partner declaration to fail — so every singles roster row becomes an
        entry.  Returns ``{division_id: [entry, ...]}`` where each entry
        carries a stable ``entry_id`` of the form ``{division_id}-S{nn}``
        (e.g. ``BAD-Men-Singles-S01``), parallel to the doubles ``-E{nn}``
        model from Issue #158.  Entries are sorted by participant ID so the
        IDs are reproducible across re-runs of the same roster.

        Only the bracket's Round-1 games carry these entry IDs (assigned in
        `_build_pod_game_objects`); bye entries and post-R1 rounds remain
        unprotected because their participation depends on match results.
        """
        by_division: Dict[str, List[Dict[str, Any]]] = {}
        seen_in_div: Dict[str, set] = {}
        for r in roster_rows:
            sport_type = str(r.get("sport_type") or "").strip()
            if sport_type not in RACQUET_SPORTS:
                continue
            if self._pod_format_class(str(r.get("sport_format") or "")) != "singles":
                continue
            sport_gender = str(r.get("sport_gender") or "").strip()
            division_id = self._make_division_id(sport_type, sport_gender, "singles")
            pid = str(r.get("Participant ID (WP)") or r.get("ChMeetings ID") or "").strip()
            if pid:
                if pid in seen_in_div.setdefault(division_id, set()):
                    continue  # duplicate roster row for the same player
                seen_in_div[division_id].add(pid)
            full_name = (
                f"{str(r.get('First Name') or '').strip()} "
                f"{str(r.get('Last Name') or '').strip()}"
            ).strip()
            by_division.setdefault(division_id, []).append({
                "division_id": division_id,
                "sport_type": sport_type,
                "sport_gender": sport_gender,
                "sport_format": str(r.get("sport_format") or "").strip(),
                "participant_ids": [pid] if pid else [],
                "participant_names": {pid: full_name or pid} if pid else {},
                "primary_sports": {
                    pid: self._normalize_primary_sport_name(
                        r.get("participant_primary_sport")
                    )
                } if pid else {},
                "player_name": full_name,
            })

        # Assign deterministic, reproducible entry IDs per division.
        for division_id, entries in by_division.items():
            entries.sort(key=lambda e: (tuple(e["participant_ids"]), e["player_name"]))
            for idx, entry in enumerate(entries, start=1):
                entry["entry_id"] = f"{division_id}-S{idx:02d}"
                entry["label"] = (
                    f"{entry['entry_id']} ({entry['player_name']})"
                    if entry["player_name"] else entry["entry_id"]
                )

        return by_division

    # Validation issue types that persist unresolved doubles registrations.
    _POD_PARTNER_ISSUE_TYPES = frozenset({
        "missing_doubles_partner",
        "doubles_partner_unmatched",
    })

    @staticmethod
    def _expected_partner_issue_type(reason: str) -> str:
        """Map a resolver unresolved reason to its persisted issue type."""
        return (
            "missing_doubles_partner"
            if str(reason or "").strip() == "MissingPartner"
            else "doubles_partner_unmatched"
        )

    @staticmethod
    def _partner_validation_key(
        participant_id: Any,
        sport_type: Any,
        sport_format: Any,
        sport_gender: Any = "",
    ) -> Tuple[str, str, str, str]:
        """Return a canonical participant + doubles-event reconciliation key."""
        raw_format = str(sport_format or "").strip()
        if raw_format in FORMAT_MAPPINGS:
            mapped_format, mapped_gender = FORMAT_MAPPINGS[raw_format]
        elif "double" in raw_format.casefold():
            mapped_format = SPORT_FORMAT["DOUBLES"]
            mapped_gender = str(sport_gender or "").strip()
            if not mapped_gender:
                format_cf = raw_format.casefold()
                mapped_gender = next(
                    (
                        gender for gender in ("Men", "Women", "Mixed")
                        if gender.casefold() in format_cf
                    ),
                    "",
                )
        else:
            mapped_format = raw_format
            mapped_gender = str(sport_gender or "").strip()
        return (
            str(participant_id or "").strip(),
            str(sport_type or "").strip().casefold(),
            str(mapped_format or "").strip().casefold(),
            str(mapped_gender or sport_gender or "").strip().casefold(),
        )

    @classmethod
    def _reconcile_pod_validation(
        cls,
        pod_unprotected_entries: List[Dict[str, Any]],
        confirmed_by_division: Dict[str, List[Dict[str, Any]]],
        validation_rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Reconcile scheduler doubles diagnostics with persisted validation issues.

        Issue #160 acceptance criterion: every scheduler-unprotected doubles
        registration must have a corresponding OPEN partner validation issue
        (missing_doubles_partner / doubles_partner_unmatched) for the same
        participant + sport + format + gender, and confirmed pairs must not
        have one. This check
        runs on the same snapshot the scheduler consumes, so any divergence
        between WordPress validation state and roster-based resolution is
        surfaced instead of silently disagreeing.

        Side effect: annotates each unprotected entry in place with
        ``validation_issue_status`` (Matched / MismatchedIssueType /
        MissingValidationIssue / NoParticipantId) so the Conflict-Audit tab can
        show reconciliation state per entry.
        """
        # Full doubles-event key -> persisted issue details for that event.
        open_partner_issues: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
        for v in validation_rows:
            issue_type = str(v.get("Issue Type") or "").strip()
            if issue_type not in cls._POD_PARTNER_ISSUE_TYPES:
                continue
            if str(v.get("Status") or "").strip().lower() != "open":
                continue
            pid = str(v.get("Participant ID (WP)") or "").strip()
            if not pid or pid == "0":
                continue
            sport = str(v.get("sport_type") or "").strip()
            sport_format = str(v.get("sport_format") or "").strip()
            key = cls._partner_validation_key(pid, sport, sport_format)
            bucket = open_partner_issues.setdefault(
                key,
                {
                    "issue_types": set(),
                    "sport_type": sport,
                    "sport_format": sport_format,
                },
            )
            bucket["issue_types"].add(issue_type)

        missing: List[Dict[str, Any]] = []
        mismatched: List[Dict[str, Any]] = []
        matched_count = 0
        scheduler_keys: set = set()

        for entry in pod_unprotected_entries:
            pid = str(entry.get("participant_id") or "").strip()
            sport = str(entry.get("sport_type") or "").strip()
            sport_format = str(entry.get("sport_format") or "").strip()
            sport_gender = str(entry.get("sport_gender") or "").strip()
            reason = str(entry.get("reason") or "").strip()
            record = {
                "participant_id": pid or None,
                "participant_name": entry.get("participant_name", ""),
                "church_code": entry.get("church_code", ""),
                "division_id": entry.get("division_id", ""),
                "sport_type": sport,
                "sport_format": sport_format,
                "sport_gender": sport_gender,
                "reason": reason,
                "expected_issue_type": cls._expected_partner_issue_type(reason),
            }
            if not pid:
                entry["validation_issue_status"] = "NoParticipantId"
                missing.append(record)
                continue

            key = cls._partner_validation_key(
                pid, sport, sport_format, sport_gender
            )
            scheduler_keys.add(key)
            issue_types = open_partner_issues.get(key, {}).get("issue_types", set())
            if record["expected_issue_type"] in issue_types:
                matched_count += 1
                entry["validation_issue_status"] = "Matched"
            elif issue_types:
                record["open_issue_types"] = sorted(issue_types)
                entry["validation_issue_status"] = "MismatchedIssueType"
                mismatched.append(record)
            else:
                entry["validation_issue_status"] = "MissingValidationIssue"
                missing.append(record)

        # Confirmed pairs with a still-open partner issue contradict validation.
        contradictory: List[Dict[str, Any]] = []
        for division_id, entries in sorted((confirmed_by_division or {}).items()):
            for confirmed in entries:
                sport = str(confirmed.get("sport_type") or "").strip()
                sport_format = str(confirmed.get("sport_format") or "").strip()
                sport_gender = str(confirmed.get("sport_gender") or "").strip()
                for pid in confirmed.get("participant_ids", []):
                    key = cls._partner_validation_key(
                        pid, sport, sport_format, sport_gender
                    )
                    scheduler_keys.add(key)
                    bucket = open_partner_issues.get(key)
                    if bucket:
                        contradictory.append({
                            "participant_id": str(pid),
                            "participant_name": confirmed.get(
                                "participant_names", {}
                            ).get(pid, ""),
                            "division_id": division_id,
                            "sport_type": sport,
                            "sport_format": sport_format,
                            "sport_gender": sport_gender,
                            "open_issue_types": sorted(bucket["issue_types"]),
                        })

        # Open partner issues with no scheduler-side record at all (for
        # example, the participant is absent from the exported roster).
        validation_only = [
            {
                "participant_id": pid,
                "sport_type": bucket["sport_type"],
                "sport_format": bucket["sport_format"],
                "open_issue_types": sorted(bucket["issue_types"]),
            }
            for key, bucket in sorted(open_partner_issues.items())
            for pid in (key[0],)
            if key not in scheduler_keys
        ]

        problem_count = (
            len(missing)
            + len(mismatched)
            + len(contradictory)
            + len(validation_only)
        )
        reconciliation = {
            "is_clean": problem_count == 0,
            "problem_count": problem_count,
            "matched_count": matched_count,
            "missing_validation_issues": missing,
            "mismatched_issue_types": mismatched,
            "contradictory_open_issues": contradictory,
            "validation_only_issues": validation_only,
        }

        if problem_count:
            logger.warning(
                "[VAY SM] Pod doubles validation reconciliation found "
                f"{len(missing)} unprotected entrie(s) without an open partner "
                f"validation issue, {len(mismatched)} with a mismatched issue "
                f"type, {len(contradictory)} confirmed pair member(s) with "
                f"a contradictory open issue, and {len(validation_only)} "
                "validation-only issue(s). Scheduler diagnostics and the "
                "Validation-Issues tab disagree — investigate before publishing."
            )
            for record in missing:
                logger.warning(
                    "[VAY SM] Missing partner validation issue: "
                    f"participant_id={record['participant_id']} "
                    f"church={record['church_code']} "
                    f"division={record['division_id']} reason={record['reason']} "
                    f"expected_issue_type={record['expected_issue_type']}"
                )
        else:
            logger.info(
                "[VAY SM] Pod doubles validation reconciliation clean: "
                f"{matched_count} unprotected entrie(s) all have matching open "
                f"partner validation issues; {len(validation_only)} open partner "
                "issue(s) reference participants outside the exported roster."
            )

        return reconciliation

    # ── Venue capacity ───────────────────────────────────────────────────────

    def _build_venue_capacity_rows(self, roster_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows = []

        # Team sports — count churches with a complete roster
        for event_name in COURT_ESTIMATE_EVENTS:
            min_team_size = self._get_min_team_size(event_name)
            counts = self._count_estimating_teams(roster_rows, event_name, min_team_size)
            mpg = COURT_ESTIMATE_MINUTES_PER_GAME.get(event_name, COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME)
            gpg = COURT_ESTIMATE_POOL_GAMES_PER_TEAM.get(event_name, COURT_ESTIMATE_DEFAULT_POOL_GAMES_PER_TEAM)
            pool_plan = self._summarize_pool_policy(counts["n_estimating"], gpg)
            actual = len(self._make_pool_game_pairs("_", counts["n_estimating"], gpg))
            s = self._compute_court_slots(counts["n_estimating"], minutes_per_game=mpg,
                                          pool_games_per_team=gpg,
                                          actual_pool_games=actual,
                                          event_name=event_name)
            rows.append({
                "Event": event_name,
                "Potential Teams/Entries": counts["n_potential"],
                "Estimating Teams/Entries": counts["n_estimating"],
                "Teams": counts["team_codes"],
                "Target Pool Games/Team": pool_plan["target_pool_games_per_team"],
                "Actual Pool Games/Team": pool_plan["actual_pool_games_per_team"],
                "Pool Composition": pool_plan["pool_composition"],
                "BYE Slots": pool_plan["bye_slots"],
                "Minutes Per Game": s["minutes_per_game"],
                "Pool Slots": s["pool_slots"],
                "Playoff Teams": s["playoff_teams"],
                "Playoff Slots": s["playoff_slots"],
                "Third Place?": "Yes" if s["include_third_place"] else "No",
                "Third Place Slots": s["third_place_slots"],
                "Total Court Slots": s["total_slots"],
                "Estimated Court Hours": s["court_hours"],
            })

        # Bible Challenge — sequential single-classroom (Jeopardy, 3 teams/game)
        # Games never run concurrently; "court hours" = total room hours.
        bc_event = SPORT_TYPE["BIBLE_CHALLENGE"]
        bc_min = self._get_min_team_size(bc_event)
        bc_counts = self._count_estimating_teams(roster_rows, bc_event, bc_min)
        n_bc = bc_counts["n_estimating"]
        bc_can_run_rr = n_bc >= COURT_ESTIMATE_BC_TEAMS_PER_GAME
        bc_rr_games = (
            ceil(n_bc * COURT_ESTIMATE_BC_RR_GAMES_PER_TEAM / COURT_ESTIMATE_BC_TEAMS_PER_GAME)
            if bc_can_run_rr else 0
        )
        bc_has_playoff = bc_can_run_rr and n_bc >= COURT_ESTIMATE_BC_MIN_TEAMS_FOR_PLAYOFF
        bc_playoff_games = COURT_ESTIMATE_BC_PLAYOFF_GAMES if bc_has_playoff else 0
        bc_total = bc_rr_games + bc_playoff_games
        bc_hours = round(bc_total * COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE / 60, 2)
        bc_actual_gpg = COURT_ESTIMATE_BC_RR_GAMES_PER_TEAM if bc_can_run_rr else 0
        bc_note = f"Sequential, 1 classroom — {COURT_ESTIMATE_BC_TEAMS_PER_GAME} teams/game"
        if not bc_can_run_rr and n_bc > 0:
            bc_note += (
                f" (waiting for at least {COURT_ESTIMATE_BC_TEAMS_PER_GAME} teams to open "
                "the round-robin queue)"
            )
        elif not bc_has_playoff:
            bc_note += f" (< {COURT_ESTIMATE_BC_MIN_TEAMS_FOR_PLAYOFF} teams: no playoff)"
        rows.append({
            "Event": bc_event,
            "Potential Teams/Entries": bc_counts["n_potential"],
            "Estimating Teams/Entries": n_bc,
            "Teams": bc_counts["team_codes"],
            "Target Pool Games/Team": COURT_ESTIMATE_BC_RR_GAMES_PER_TEAM,
            "Actual Pool Games/Team": bc_actual_gpg,
            "Pool Composition": bc_note,
            "BYE Slots": None,
            "Minutes Per Game": COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE,
            "Pool Slots": bc_rr_games,
            "Playoff Teams": COURT_ESTIMATE_BC_MIN_TEAMS_FOR_PLAYOFF if bc_has_playoff else 0,
            "Playoff Slots": bc_playoff_games,
            "Third Place?": "No",
            "Third Place Slots": 0,
            "Total Court Slots": bc_total,
            "Estimated Court Hours": bc_hours,
        })

        # Racquet sports — count complete pairs + singles
        for sport_name in COURT_ESTIMATE_RACQUET_EVENTS:
            counts = self._count_racquet_entries(roster_rows, sport_name)
            mpg = COURT_ESTIMATE_MINUTES_PER_GAME.get(sport_name, COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME)
            s = self._compute_court_slots(counts["n_estimating"], minutes_per_game=mpg, event_name=sport_name)
            rows.append({
                "Event": sport_name,
                "Potential Teams/Entries": counts["n_potential"],
                "Estimating Teams/Entries": counts["n_estimating"],
                "Teams": counts["team_codes"],
                "Target Pool Games/Team": None,
                "Actual Pool Games/Team": None,
                "Pool Composition": "",
                "BYE Slots": None,
                "Minutes Per Game": s["minutes_per_game"],
                "Pool Slots": s["pool_slots"],
                "Playoff Teams": s["playoff_teams"],
                "Playoff Slots": s["playoff_slots"],
                "Third Place?": "Yes" if s["include_third_place"] else "No",
                "Third Place Slots": s["third_place_slots"],
                "Total Court Slots": s["total_slots"],
                "Estimated Court Hours": s["court_hours"],
            })

        return rows






























    # ── Schedule-Input JSON builders ─────────────────────────────────────────
















    # ── Pool planning ─────────────────────────────────────────────────────────











    # ── Court-schedule sketch ────────────────────────────────────────────────


    # ── Pod-Resource-Estimate helpers ────────────────────────────────────────




    # ── produce-schedule renderer ────────────────────────────────────────────

    # ── ALL-workbook readers (build-schedule-workbook input) ─────────────────


    @staticmethod
    def read_roster_validation_rows(
        xlsx_path: Optional[Path],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Parse the Roster and Validation-Issues tabs of an exported ALL workbook.

        Returns (roster_rows, validation_rows) in the list-of-dicts shape the
        scheduling builders expect.  A missing path or missing tabs degrade
        gracefully to empty lists with a WARNING — build-schedule-workbook still
        produces the Schedule-Input tab (echo of the JSON) without roster data.
        """
        if not xlsx_path or not Path(xlsx_path).exists():
            logger.warning(
                f"ALL workbook not found at {xlsx_path!r}; "
                "scheduling tabs that need roster data will be empty."
            )
            return [], []
        xlsx_path = Path(xlsx_path)
        roster_rows = ScheduleWorkbookBuilder._read_xlsx_sheet_rows(xlsx_path, "Roster")
        validation_rows = ScheduleWorkbookBuilder._read_xlsx_sheet_rows(
            xlsx_path, "Validation-Issues"
        )
        return roster_rows, validation_rows

    # ── Public entry points ──────────────────────────────────────────────────


    def write_schedule_workbook(
        self,
        output_path: Path,
        roster_rows: List[Dict[str, Any]],
        validation_rows: List[Dict[str, Any]],
        schedule_input: Dict[str, Any],
        venue_input_path: Optional[Path],
        pool_assignment_path: Optional[Path] = None,
    ) -> None:
        """Write the Schedule_Workbook xlsx with all scheduling tabs.
        Called by build-schedule-workbook command (Step 3).
        For the solver-rendered two-tab workbook, use write_schedule_output_workbook().
        When venue_input_path is None, derive resource availability from the
        schedule_input resources so offline builds stay self-consistent.
        """
        # Build workbook with pandas ExcelWriter for the DataFrame-based tabs,
        # then attach the openpyxl-native tabs using writer.book.
        venue_rows = self._build_venue_capacity_rows(roster_rows)
        venue_cols = [
            "Event", "Potential Teams/Entries", "Estimating Teams/Entries", "Teams",
            "Target Pool Games/Team", "Actual Pool Games/Team",
            "Pool Composition", "BYE Slots", "Minutes Per Game", "Pool Slots",
            "Playoff Teams", "Playoff Slots", "Third Place?",
            "Third Place Slots", "Total Court Slots", "Estimated Court Hours",
        ]

        pod_div_rows = self._build_pod_divisions_rows(roster_rows, validation_rows)
        pod_div_cols = [
            "division_id", "sport_type", "sport_gender", "sport_format",
            "resource_type", "minutes_per_game",
            "planning_entries", "confirmed_entries", "provisional_entries",
            "anomaly_count", "division_status", "notes",
        ]

        pod_entry_rows = self._build_pod_entries_review_rows(roster_rows, validation_rows)
        pod_entry_cols = [
            "entry_id", "division_id", "entry_type",
            "participant_1_name", "participant_2_name",
            "source_participant_ids", "church_team",
            "partner_status", "review_status", "notes",
        ]
        pool_assignment_rows = self._build_pool_assignment_rows(
            roster_rows,
            pool_assignment_path,
        )

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            # Venue-Estimator tab (pandas)
            df_venue = pd.DataFrame(venue_rows, columns=venue_cols)
            df_venue.to_excel(writer, sheet_name="Venue-Estimator", index=False, startrow=0)
            snapshot_note = (
                f"Roster snapshot as of {datetime.now().strftime('%Y-%m-%d')} — "
                "Estimating = complete entries; Potential = rule-aware ceiling from current "
                "registrations (including incomplete doubles pairings), capped by 2026 entry limits. "
                "Approval-agnostic. Updates with each export run."
            )
            venue_ws = writer.sheets["Venue-Estimator"]
            self._annotate_venue_estimator_tab(venue_ws, len(venue_cols))
            note_row = len(df_venue) + 3
            venue_ws.cell(row=note_row, column=1, value=snapshot_note)
            logger.debug(f"Venue-Estimator tab: {len(df_venue)} rows.")

            # Pool-Assignment tab (openpyxl native - editable seed/draw workspace)
            pool_ws = writer.book.create_sheet(title="Pool-Assignment", index=1)
            self._write_pool_assignment_tab(pool_ws, pool_assignment_rows)
            logger.debug(f"Pool-Assignment tab: {len(pool_assignment_rows)} rows.")

            # Pod-Divisions tab (pandas)
            df_pod_div = pd.DataFrame(pod_div_rows, columns=pod_div_cols)
            df_pod_div.to_excel(writer, sheet_name="Pod-Divisions", index=False)
            self._annotate_pod_divisions_tab(writer.sheets["Pod-Divisions"], len(pod_div_cols))
            logger.debug(f"Pod-Divisions tab: {len(df_pod_div)} rows.")

            # Pod-Entries-Review tab (pandas)
            df_pod_entries = pd.DataFrame(pod_entry_rows, columns=pod_entry_cols)
            df_pod_entries.to_excel(writer, sheet_name="Pod-Entries-Review", index=False)
            self._annotate_pod_entries_review_tab(
                writer.sheets["Pod-Entries-Review"], len(pod_entry_cols)
            )
            logger.debug(f"Pod-Entries-Review tab: {len(df_pod_entries)} rows.")

            # Court-Schedule-Sketch tab (openpyxl native)
            sketch_ws = writer.book.create_sheet(title="Court-Schedule-Sketch")
            self._write_court_schedule_sketch(sketch_ws, roster_rows)

            # Pod-Resource-Estimate tab (openpyxl native)
            if venue_input_path is None:
                available_by_resource = self._load_available_slots_from_schedule_input(
                    schedule_input
                )
                availability_source_label = "schedule_input.json resources"
            else:
                available_by_resource = self._load_venue_input(venue_input_path)
                availability_source_label = VENUE_INPUT_FILENAME
            pod_res_rows = self._build_pod_resource_rows(roster_rows, available_by_resource)
            pod_ws = writer.book.create_sheet(title="Pod-Resource-Estimate")
            self._write_pod_resource_estimate(
                pod_ws,
                pod_res_rows,
                available_by_resource,
                availability_source_label=availability_source_label,
            )

            # Schedule-Input tab (openpyxl native — echo of the JSON)
            si_ws = writer.book.create_sheet(title="Schedule-Input")
            self._write_schedule_input_tab(si_ws, schedule_input)

            # Gym-Allocation tab (openpyxl native — Stage-A allocator summary)
            gym_alloc_ws = writer.book.create_sheet(title="Gym-Allocation")
            self._write_gym_allocation_tab(gym_alloc_ws, schedule_input.get("gym_allocation"))

            # Summary tab (openpyxl native — operator guide / command cheat sheet)
            summary_ws = writer.book.create_sheet(title="Summary", index=0)
            self._write_summary_tab(summary_ws)
            self._stamp_known_tab_statuses(writer.book)

        logger.info(f"Schedule workbook written to: {output_path}")

    @staticmethod
    def write_schedule_output_workbook(
        output_path: Path,
        schedule_output: Dict[str, Any],
        schedule_input: Dict[str, Any],
    ) -> None:
        """Write the standalone Schedule-by-Time / Schedule-by-Sport workbook."""
        ScheduleWorkbookBuilder._write_schedule_output_report(
            Path(output_path), schedule_output, schedule_input
        )

    # ── Backward-compat class aliases — extracted to scheduling/ (Issue #152) ──
    _clean_excel_text = staticmethod(xlsx_utils._clean_excel_text)
    _float_from_excel = staticmethod(xlsx_utils._float_from_excel)
    _normalize_resource_type_name = staticmethod(xlsx_utils._normalize_resource_type_name)
    _resource_id_prefix = staticmethod(xlsx_utils._resource_id_prefix)
    _ordinal = staticmethod(xlsx_utils._ordinal)
    _day_sort_key = staticmethod(xlsx_utils._day_sort_key)
    _day_display_label = staticmethod(xlsx_utils._day_display_label)
    _coerce_excel_date = staticmethod(xlsx_utils._coerce_excel_date)
    _derive_day_labels_from_dates = staticmethod(xlsx_utils._derive_day_labels_from_dates)
    _set_excel_comment = staticmethod(xlsx_utils._set_excel_comment)
    _make_excel_note_shapes_visible = staticmethod(xlsx_utils._make_excel_note_shapes_visible)
    _stamp_tab_status_banner = staticmethod(xlsx_utils._stamp_tab_status_banner)
    _stamp_known_tab_statuses = staticmethod(xlsx_utils._stamp_known_tab_statuses)
    _annotate_header_row = staticmethod(xlsx_utils._annotate_header_row)
    _parse_hour = staticmethod(xlsx_utils._parse_hour)
    _read_xlsx_sheet_rows = staticmethod(xlsx_utils._read_xlsx_sheet_rows)
    _load_venue_input_rows = staticmethod(venue_loader._load_venue_input_rows)
    _load_playoff_slots = staticmethod(venue_loader._load_playoff_slots)
    _load_venue_date_day_map = staticmethod(venue_loader._load_venue_date_day_map)
    _split_slot_label = staticmethod(venue_loader._split_slot_label)
    _last_slot_label_on_day = staticmethod(venue_loader._last_slot_label_on_day)
    _load_gym_modes = staticmethod(venue_loader._load_gym_modes)
    _load_venue_input = staticmethod(venue_loader._load_venue_input)
    _warn_if_schedules_mismatched = staticmethod(output_report._warn_if_schedules_mismatched)
    _build_schedule_output_flat_rows = staticmethod(output_report._build_schedule_output_flat_rows)
    _write_schedule_diagnostics_tab = staticmethod(output_report._write_schedule_diagnostics_tab)
    _write_schedule_output_report = staticmethod(output_report._write_schedule_output_report)

    # ── Step 4: planning-tab renderers extracted to scheduling/planning_tabs.py (Issue #152) ──
    _write_summary_tab = staticmethod(planning_tabs._write_summary_tab)
    _build_scenario_schedule = staticmethod(planning_tabs._build_scenario_schedule)

    @classmethod
    def _annotate_venue_estimator_tab(cls, ws, n_cols: int) -> None:
        return planning_tabs._annotate_venue_estimator_tab(cls, ws, n_cols)

    @classmethod
    def _annotate_pod_divisions_tab(cls, ws, n_cols: int) -> None:
        return planning_tabs._annotate_pod_divisions_tab(cls, ws, n_cols)

    @classmethod
    def _annotate_pod_entries_review_tab(cls, ws, n_cols: int) -> None:
        return planning_tabs._annotate_pod_entries_review_tab(cls, ws, n_cols)

    @classmethod
    def _annotate_pool_assignment_tab(cls, ws, n_cols: int) -> None:
        return planning_tabs._annotate_pool_assignment_tab(cls, ws, n_cols)

    @classmethod
    def _write_schedule_input_tab(cls, ws, schedule_input: Dict[str, Any]) -> None:
        return planning_tabs._write_schedule_input_tab(cls, ws, schedule_input)

    @classmethod
    def _write_gym_allocation_tab(cls, ws, gym_allocation: Optional[Dict[str, Any]]) -> None:
        return planning_tabs._write_gym_allocation_tab(cls, ws, gym_allocation)

    def _write_court_schedule_sketch(self, ws, roster_rows: List[Dict[str, Any]]) -> None:
        return planning_tabs._write_court_schedule_sketch(self, ws, roster_rows)

    def _build_pod_resource_rows(self, roster_rows: List[Dict[str, Any]], available_by_resource: Dict[str, int]) -> List[Dict[str, Any]]:
        return planning_tabs._build_pod_resource_rows(self, roster_rows, available_by_resource)

    @classmethod
    def _write_pod_resource_estimate(self, ws, pod_rows: List[Dict[str, Any]], available_by_resource: Dict[str, int], availability_source_label: str=VENUE_INPUT_FILENAME) -> None:
        return planning_tabs._write_pod_resource_estimate(self, ws, pod_rows, available_by_resource, availability_source_label)

    # ── Step 5: Pool-Assignment state/draw logic extracted to scheduling/pool_assignment.py (Issue #152) ──
    _pool_assignments_sidecar_path = staticmethod(pool_assignment._pool_assignments_sidecar_path)
    _normalize_pool_seed = staticmethod(pool_assignment._normalize_pool_seed)
    _positive_int_or_none = staticmethod(pool_assignment._positive_int_or_none)
    _default_random_draw_orders = staticmethod(pool_assignment._default_random_draw_orders)
    _serpentine_pool_slots = staticmethod(pool_assignment._serpentine_pool_slots)
    _normalize_primary_sport_name = staticmethod(pool_assignment._normalize_primary_sport_name)
    _read_pool_assignment_rows = staticmethod(pool_assignment._read_pool_assignment_rows)

    @classmethod
    def _pool_assignment_event_prefix(cls, event_name: str) -> str:
        return pool_assignment._pool_assignment_event_prefix(cls, event_name)

    @classmethod
    def _event_sort_index(cls, event_name: str) -> int:
        return pool_assignment._event_sort_index(cls, event_name)

    @classmethod
    def _load_pool_assignment_state(cls, sidecar_path: Optional[Path]) -> Dict[Tuple[str, str], Dict[str, Any]]:
        return pool_assignment._load_pool_assignment_state(cls, sidecar_path)

    @classmethod
    def _write_pool_assignment_state(cls, sidecar_path: Path, rows: List[Dict[str, Any]]) -> None:
        return pool_assignment._write_pool_assignment_state(cls, sidecar_path, rows)

    def _build_pool_assignment_base_rows(self, roster_rows: List[Dict[str, Any]], persisted_state: Optional[Dict[Tuple[str, str], Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        return pool_assignment._build_pool_assignment_base_rows(self, roster_rows, persisted_state)

    def _pool_sizes_for_assignment(self, event_name: str, n_teams: int) -> List[int]:
        return pool_assignment._pool_sizes_for_assignment(self, event_name, n_teams)

    def _apply_pool_assignments_to_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return pool_assignment._apply_pool_assignments_to_rows(self, rows)

    def _build_pool_assignment_rows(self, roster_rows: List[Dict[str, Any]], sidecar_path: Optional[Path]) -> List[Dict[str, Any]]:
        return pool_assignment._build_pool_assignment_rows(self, roster_rows, sidecar_path)

    @classmethod
    def _solver_team_id(cls, event_name: str, team_id: str) -> str:
        return pool_assignment._solver_team_id(cls, event_name, team_id)

    @classmethod
    def _pool_assignment_placeholder_map(cls, pool_assignment_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Dict[str, Any]]]:
        return pool_assignment._pool_assignment_placeholder_map(cls, pool_assignment_rows)

    @classmethod
    def _write_pool_assignment_tab(cls, ws, pool_assignment_rows: List[Dict[str, Any]]) -> None:
        return pool_assignment._write_pool_assignment_tab(cls, ws, pool_assignment_rows)

    def refresh_pool_assignments(self, workbook_path: Path, output_path: Optional[Path] = None, sidecar_path: Optional[Path] = None) -> List[Dict[str, Any]]:
        return pool_assignment.refresh_pool_assignments(self, workbook_path, output_path, sidecar_path)

    # ── Step 6: game/resource object builders extracted to scheduling/game_builder.py (Issue #152) ──
    _pool_numeric_suffix = staticmethod(game_builder._pool_numeric_suffix)
    _build_gym_resource_objects = staticmethod(game_builder._build_gym_resource_objects)
    _build_gym_resources_from_allocator = staticmethod(game_builder._build_gym_resources_from_allocator)
    _two_game_pool_sizes = staticmethod(game_builder._two_game_pool_sizes)
    _three_game_even_pool_sizes = staticmethod(game_builder._three_game_even_pool_sizes)
    _three_game_pool_sizes = staticmethod(game_builder._three_game_pool_sizes)
    _format_pool_games_per_team = staticmethod(game_builder._format_pool_games_per_team)
    _format_pool_composition = staticmethod(game_builder._format_pool_composition)
    _summarize_pool_policy = staticmethod(game_builder._summarize_pool_policy)
    _make_legacy_pool_game_pairs = staticmethod(game_builder._make_legacy_pool_game_pairs)
    _make_pool_game_pairs = staticmethod(game_builder._make_pool_game_pairs)
    _make_playoff_ids = staticmethod(game_builder._make_playoff_ids)

    @classmethod
    def _bc_no_repeat_triplets(cls, all_rows: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]]:
        return game_builder._bc_no_repeat_triplets(cls, all_rows)

    @classmethod
    def _build_assigned_bc_game_objects(cls, pool_assignment_rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        return game_builder._build_assigned_bc_game_objects(cls, pool_assignment_rows)

    @classmethod
    def _build_assigned_soccer_game_objects(cls, roster_rows: List[Dict[str, Any]], pool_assignment_rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        return game_builder._build_assigned_soccer_game_objects(cls, roster_rows, pool_assignment_rows)

    @classmethod
    def _build_single_elim_playoff(cls, event_name: str, prefix: str, playoff_teams: int, pool_game_ids: List[str], extra_fields: Dict[str, Any], include_third: bool) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        return game_builder._build_single_elim_playoff(cls, event_name, prefix, playoff_teams, pool_game_ids, extra_fields, include_third)

    @classmethod
    def _build_assigned_gym_game_objects(cls, roster_rows: List[Dict[str, Any]], pool_assignment_rows: List[Dict[str, Any]], allow_placeholder_fallback: bool = True, excluded_events: Optional[set[str]] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        return game_builder._build_assigned_gym_game_objects(cls, roster_rows, pool_assignment_rows, allow_placeholder_fallback, excluded_events)

    @classmethod
    def _build_manual_team_sport_game_objects(cls, manual_matchup_payload: Optional[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], set[str], Optional[Dict[str, Any]]]:
        return game_builder._build_manual_team_sport_game_objects(cls, manual_matchup_payload)

    def _build_gym_game_objects(self, roster_rows: List[Dict[str, Any]], allow_placeholder_fallback: bool = True) -> List[Dict[str, Any]]:
        return game_builder._build_gym_game_objects(self, roster_rows, allow_placeholder_fallback)

    def _build_pod_game_objects(self, roster_rows: List[Dict[str, Any]], validation_rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        return game_builder._build_pod_game_objects(self, roster_rows, validation_rows)

    # ── Step 7: conflict-edge builders extracted to scheduling/conflict_edges.py (Issue #152) ──
    _team_state_to_unit = staticmethod(conflict_edges._team_state_to_unit)
    _make_shared_athlete_edge = staticmethod(conflict_edges._make_shared_athlete_edge)

    @classmethod
    def _build_core_gym_team_lookup(cls, roster_rows: List[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
        return conflict_edges._build_core_gym_team_lookup(cls, roster_rows)

    @classmethod
    def _build_gym_team_conflicts(cls, roster_rows: List[Dict[str, Any]], pool_assignment_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return conflict_edges._build_gym_team_conflicts(cls, roster_rows, pool_assignment_rows)

    def _build_cross_sport_conflicts(self, roster_rows: List[Dict[str, Any]], pool_assignment_rows: List[Dict[str, Any]], validation_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return conflict_edges._build_cross_sport_conflicts(self, roster_rows, pool_assignment_rows, validation_rows)

    # ── Step 8: schedule-input assembly extracted to scheduling/input_builder.py (Issue #152) ──
    _warn_if_resource_slot_minutes_differ_from_config = staticmethod(input_builder._warn_if_resource_slot_minutes_differ_from_config)
    _load_available_slots_from_schedule_input = staticmethod(input_builder._load_available_slots_from_schedule_input)

    def _resolve_venue_playoff_slots(self, playoff_slots: List[Dict[str, Any]], venue_rows: List[Dict[str, Any]], date_day_map: Dict[str, str], gym_modes: Dict[str, Dict[str, int]], allocator_active: bool, game_duration_by_id: Optional[Dict[str, int]] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Any], set]:
        return input_builder._resolve_venue_playoff_slots(self, playoff_slots, venue_rows, date_day_map, gym_modes, allocator_active, game_duration_by_id)

    def _build_schedule_input(self, roster_rows: List[Dict[str, Any]], validation_rows: List[Dict[str, Any]], venue_input_path: Path, pool_assignment_path: Optional[Path] = None, manual_matchup_path: Optional[Path] = None, manual_schedule_path: Optional[Path] = None, match_schedule_overrides_path: Optional[Path] = None) -> Dict[str, Any]:
        return input_builder._build_schedule_input(self, roster_rows, validation_rows, venue_input_path, pool_assignment_path, manual_matchup_path, manual_schedule_path, match_schedule_overrides_path)

    def write_schedule_input_json(self, roster_rows: List[Dict[str, Any]], validation_rows: List[Dict[str, Any]], venue_input_path: Path, json_path: Path, pool_assignment_path: Optional[Path] = None, manual_matchup_path: Optional[Path] = None, manual_schedule_path: Optional[Path] = None, match_schedule_overrides_path: Optional[Path] = None) -> Dict[str, Any]:
        return input_builder.write_schedule_input_json(self, roster_rows, validation_rows, venue_input_path, json_path, pool_assignment_path, manual_matchup_path, manual_schedule_path, match_schedule_overrides_path)
