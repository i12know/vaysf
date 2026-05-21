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
from collections import defaultdict, deque
import random
import re
from math import ceil

from config import (
    SPORT_TYPE,
    SPORT_FORMAT,
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
    SCHEDULE_SKETCH_N_COURTS,
    SCHEDULE_SKETCH_COLOR_BASKETBALL,
    SCHEDULE_SKETCH_COLOR_VB_MEN,
    SCHEDULE_SKETCH_COLOR_VB_WOMEN,
    SCHEDULE_SKETCH_COLOR_SECTION,
    SCHEDULE_SKETCH_COLOR_HEADER,
    GYM_RESOURCE_TYPE,
    GYM_RESOURCE_TYPE_BASKETBALL,
    GYM_RESOURCE_TYPE_VOLLEYBALL,
    TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE,
    SCHEDULE_SOLVER_GYM_COURTS,
    VENUE_INPUT_FILENAME,
    POD_RESOURCE_EVENT_TYPE,
    POD_FIT_COLOR_GREEN,
    POD_FIT_COLOR_YELLOW,
    POD_FIT_COLOR_RED,
    POD_FIT_YELLOW_MAX,
)
from validation.name_matcher import normalized_name as _norm_name
from validation.models import RulesManager


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

    def __init__(self) -> None:
        pass

    _GYM_CORE_SOLVER_POOL = "Gym Core"

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
            "Computed slot within the assigned pool, such as T1 or T3."
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
            "All current registrations for this event, including partial team signups or "
            "incomplete doubles pairs."
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
            "Configured planning target for pool games per team."
        ),
        "Actual Pool Games/Team": (
            "Actual pool-game planning assumption for this event. For the standard team-sport "
            "model this is the average implied by the normalized pool layout; for Bible "
            "Challenge it reflects the organizer-facing 2-games-per-team target once enough "
            "teams exist to run the Jeopardy format."
        ),
        "Pool Composition": (
            "Pool sizes used by the current planning policy, such as 4 + 3 + 3."
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
            "Schedule day key, such as Sat-1, Sun-1, Sat-2, or Sun-2."
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
    def _get_min_team_size(cls, event_name: str) -> int:
        """Look up minimum team size from the validation ruleset; fall back
        to COURT_ESTIMATE_MIN_TEAM_SIZE if the JSON rule is absent."""
        rules_manager_cache = getattr(cls, "_rules_manager_cache", None)
        rules_manager_cache_failed = bool(getattr(cls, "_rules_manager_cache_failed", False))
        if rules_manager_cache is None and not rules_manager_cache_failed:
            try:
                setattr(cls, "_rules_manager_cache", RulesManager(collection="SUMMER_2026"))
            except Exception as e:
                logger.warning(f"Could not load validation rules for venue estimate: {e}")
                setattr(cls, "_rules_manager_cache_failed", True)
        rules_manager = getattr(cls, "_rules_manager_cache", None)
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

    def _compute_court_slots(self, n_teams: int,
                              minutes_per_game: int = COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME,
                              pool_games_per_team: int = COURT_ESTIMATE_DEFAULT_POOL_GAMES_PER_TEAM,
                              actual_pool_games: Optional[int] = None) -> Dict[str, Any]:
        include_third = COURT_ESTIMATE_INCLUDE_THIRD_PLACE_GAME

        # When the caller already knows the exact game count (e.g. from
        # _make_pool_game_pairs), use it directly so the Venue-Estimator and
        # schedule_input.json stay aligned with the current pool-generation
        # policy instead of falling back to a rough ceil(n*gpg/2) estimate.
        if actual_pool_games is not None:
            pool_slots = actual_pool_games
        else:
            pool_slots = ceil((n_teams * pool_games_per_team) / 2) if n_teams > 0 else 0
        playoff_teams = self._get_playoff_teams(n_teams)
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

    def _count_racquet_entries(self, roster_rows: List[Dict[str, Any]],
                               sport_name: str) -> Dict[str, Any]:
        """Count racquet sport entries for the venue estimator.

        Estimating Entries = complete pairs floor(n_doubles / 2) + n_singles.
        Potential Entries  = total individual registrations (one person may be
                             waiting for a partner to sign up).
        """
        n_singles = 0
        n_doubles = 0
        for r in roster_rows:
            if str(r.get("sport_type") or "").strip().casefold() != sport_name.casefold():
                continue
            fmt = str(r.get("sport_format") or "").strip().casefold()
            if "singles" in fmt:
                n_singles += 1
            else:
                n_doubles += 1
        n_estimating = n_singles + (n_doubles // 2)
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

        # Doubles — attempt reciprocal pairing within each division.
        # Group by (sport_type, sport_gender) across all churches.
        doubles_by_div: Dict[tuple, List[Dict[str, Any]]] = {}
        for r in doubles_rows:
            sport_type = str(r.get("sport_type") or "").strip()
            sport_gender = str(r.get("sport_gender") or "").strip()
            doubles_by_div.setdefault((sport_type, sport_gender), []).append(r)

        for (sport_type, sport_gender), div_rows in sorted(doubles_by_div.items()):
            division_id = self._make_division_id(sport_type, sport_gender, "doubles")
            name_to_rows: Dict[str, List[Dict[str, Any]]] = {}
            for r in div_rows:
                key = _norm_name(_full_name(r))
                if key:
                    name_to_rows.setdefault(key, []).append(r)

            paired_pids: set = set()

            for r in div_rows:
                pid_a = _pid(r)
                if pid_a and pid_a in paired_pids:
                    continue

                name_a = _full_name(r)
                partner_decl = str(r.get("partner_name") or "").strip()

                if not partner_decl:
                    entry_counter += 1
                    entry_rows.append({
                        "entry_id": entry_counter,
                        "division_id": division_id,
                        "entry_type": "UnresolvedDoubles",
                        "participant_1_name": name_a,
                        "participant_2_name": "",
                        "source_participant_ids": pid_a,
                        "church_team": str(r.get("Church Team") or ""),
                        "partner_status": "MissingPartner",
                        "review_status": "NeedsReview",
                        "notes": "No partner declared",
                    })
                    if pid_a:
                        paired_pids.add(pid_a)
                    continue

                partner_key = _norm_name(partner_decl)
                candidates = name_to_rows.get(partner_key, [])

                # Look for a reciprocal candidate not yet paired.
                name_a_key = _norm_name(name_a)
                reciprocal = next(
                    (
                        c for c in candidates
                        if _pid(c) not in paired_pids
                        and _norm_name(str(c.get("partner_name") or "")) == name_a_key
                    ),
                    None,
                )

                if reciprocal:
                    pid_b = _pid(reciprocal)
                    entry_counter += 1
                    both_ok = not _has_error(r) and not _has_error(reciprocal)
                    churches = ", ".join(sorted({
                        str(r.get("Church Team") or ""),
                        str(reciprocal.get("Church Team") or ""),
                    }))
                    entry_rows.append({
                        "entry_id": entry_counter,
                        "division_id": division_id,
                        "entry_type": "DoublesPair",
                        "participant_1_name": name_a,
                        "participant_2_name": _full_name(reciprocal),
                        "source_participant_ids": ", ".join(filter(None, [pid_a, pid_b])),
                        "church_team": churches,
                        "partner_status": "Confirmed",
                        "review_status": "OK" if both_ok else "NeedsReview",
                        "notes": "",
                    })
                    if pid_a:
                        paired_pids.add(pid_a)
                    if pid_b:
                        paired_pids.add(pid_b)
                else:
                    # Partner not found or non-reciprocal.
                    if candidates:
                        reason = "NonReciprocal"
                        note = f"Partner '{partner_decl}' found but does not list this player back"
                    else:
                        reason = "PartnerNotFound"
                        note = f"Partner '{partner_decl}' not in same-division roster"
                    entry_counter += 1
                    entry_rows.append({
                        "entry_id": entry_counter,
                        "division_id": division_id,
                        "entry_type": "UnresolvedDoubles",
                        "participant_1_name": name_a,
                        "participant_2_name": "",
                        "source_participant_ids": pid_a,
                        "church_team": str(r.get("Church Team") or ""),
                        "partner_status": reason,
                        "review_status": "NeedsReview",
                        "notes": note,
                    })
                    if pid_a:
                        paired_pids.add(pid_a)

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
                                          actual_pool_games=actual)
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
            s = self._compute_court_slots(counts["n_estimating"], minutes_per_game=mpg)
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

    @staticmethod
    def _pool_assignments_sidecar_path(base_dir: Path) -> Path:
        """Return the default sidecar file used to persist editable pool seeds."""
        return Path(base_dir) / "pool_assignments.json"

    @staticmethod
    def _normalize_pool_seed(value: Any) -> Optional[int]:
        """Normalize blank/zero-like seed input to None, else return a positive int."""
        if value in (None, "", "0", 0):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _positive_int_or_none(value: Any) -> Optional[int]:
        """Return a positive int when possible; otherwise None."""
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @classmethod
    def _pool_assignment_event_prefix(cls, event_name: str) -> str:
        """Return the placeholder prefix used for one pool-assignment event."""
        for known_event, prefix in cls._POOL_ASSIGNMENT_EVENT_DEFS:
            if known_event == event_name:
                return prefix
        return event_name[:3].upper()

    @classmethod
    def _event_sort_index(cls, event_name: str) -> int:
        """Return a stable event ordering for the Pool-Assignment tab."""
        for idx, (known_event, _) in enumerate(cls._POOL_ASSIGNMENT_EVENT_DEFS):
            if known_event == event_name:
                return idx
        return len(cls._POOL_ASSIGNMENT_EVENT_DEFS)

    @classmethod
    def _load_pool_assignment_state(
        cls,
        sidecar_path: Optional[Path],
    ) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """Load persisted seed/draw metadata keyed by (event, team_id)."""
        if not sidecar_path:
            return {}
        sidecar_path = Path(sidecar_path)
        if not sidecar_path.exists():
            return {}

        try:
            payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(
                f"Could not parse pool-assignment sidecar '{sidecar_path}': {exc}. "
                "Ignoring persisted seeds for this build."
            )
            return {}

        rows = payload.get("rows", []) if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            logger.warning(
                f"Pool-assignment sidecar '{sidecar_path}' has invalid rows content. "
                "Ignoring persisted seeds for this build."
            )
            return {}

        state: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            event_name = str(row.get("Event") or row.get("event") or "").strip()
            team_id = str(row.get("Team ID") or row.get("team_id") or "").strip()
            if not event_name or not team_id:
                continue
            state[(event_name, team_id)] = {
                "Seed": cls._normalize_pool_seed(row.get("Seed", row.get("seed"))),
                "Random Draw Order": cls._positive_int_or_none(
                    row.get("Random Draw Order", row.get("random_draw_order"))
                ),
                "Notes": str(row.get("Notes", row.get("notes")) or "").strip(),
            }
        return state

    @classmethod
    def _write_pool_assignment_state(
        cls,
        sidecar_path: Path,
        rows: List[Dict[str, Any]],
    ) -> None:
        """Persist editable Pool-Assignment state to a JSON sidecar."""
        payload_rows: List[Dict[str, Any]] = []
        for row in rows:
            event_name = str(row.get("Event") or "").strip()
            team_id = str(row.get("Team ID") or "").strip()
            if not event_name or not team_id:
                continue
            payload_rows.append({
                "event": event_name,
                "church_code": str(row.get("Church Team") or "").strip(),
                "team_order": str(row.get("Team Order") or "").strip(),
                "team_id": team_id,
                "seed": cls._normalize_pool_seed(row.get("Seed")),
                "random_draw_order": cls._positive_int_or_none(
                    row.get("Random Draw Order")
                ),
                "notes": str(row.get("Notes") or "").strip(),
            })

        sidecar_path = Path(sidecar_path)
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "rows": payload_rows,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _build_pool_assignment_base_rows(
        self,
        roster_rows: List[Dict[str, Any]],
        persisted_state: Optional[Dict[Tuple[str, str], Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Build one Pool-Assignment row per eligible core gym team."""
        persisted_state = persisted_state or {}
        rows: List[Dict[str, Any]] = []

        for event_name, _prefix in self._POOL_ASSIGNMENT_EVENT_DEFS:
            min_team_size = self._get_min_team_size(event_name)
            target_type, target_gender, _target_format = self._decompose_event_name(event_name)

            counts_by_key: Dict[Tuple[str, str], int] = {}
            for roster_row in roster_rows:
                r_type = str(roster_row.get("sport_type") or "").strip()
                r_gender = str(roster_row.get("sport_gender") or "").strip()
                r_format = str(roster_row.get("sport_format") or "").strip()
                if (
                    r_type.casefold() != target_type.casefold()
                    and r_type.casefold() != event_name.casefold()
                ):
                    continue
                if target_gender and r_gender.casefold() != target_gender.casefold():
                    continue
                if r_format and r_format.casefold() != SPORT_FORMAT["TEAM"].casefold():
                    continue

                church_code = str(roster_row.get("Church Team") or "").strip().upper()
                if not church_code:
                    continue
                team_order = str(roster_row.get("team_order") or "").strip().upper()
                counts_by_key[(church_code, team_order)] = (
                    counts_by_key.get((church_code, team_order), 0) + 1
                )

            for (church_code, team_order), roster_count in sorted(counts_by_key.items()):
                if roster_count < min_team_size:
                    continue

                team_id = church_code if not team_order else f"{church_code}-{team_order}"
                persisted = persisted_state.get((event_name, team_id), {})
                rows.append({
                    "Event": event_name,
                    "Church Team": church_code,
                    "Team Order": team_order,
                    "Team ID": team_id,
                    "Team Label": team_id,
                    "Team Source": "ExplicitTeamOrder" if team_order else "ChurchLevel",
                    "Roster Count": roster_count,
                    "Min Team Size": min_team_size,
                    "Seed": persisted.get("Seed"),
                    "Random Draw Order": persisted.get("Random Draw Order"),
                    "Draw Position": None,
                    "Pool ID": "",
                    "Pool Slot": "",
                    "Assignment Basis": "",
                    "Notes": persisted.get("Notes", ""),
                })

        return rows

    @staticmethod
    def _default_random_draw_orders(
        event_name: str,
        team_ids: List[str],
    ) -> Dict[str, int]:
        """Return a stable pseudo-random ordering for unseeded teams."""
        ordered_ids = sorted(team_ids)
        rng = random.Random(f"vaysf-pool-draw|{event_name}|{'|'.join(ordered_ids)}")
        rng.shuffle(ordered_ids)
        return {team_id: idx for idx, team_id in enumerate(ordered_ids, start=1)}

    @staticmethod
    def _serpentine_pool_slots(pool_sizes: List[int]) -> List[Tuple[str, str]]:
        """Return pool slots in serpentine fill order."""
        slots: List[Tuple[str, str]] = []
        if not pool_sizes:
            return slots

        max_size = max(pool_sizes)
        for slot_idx in range(1, max_size + 1):
            eligible = [pool_idx for pool_idx, size in enumerate(pool_sizes, start=1) if size >= slot_idx]
            if slot_idx % 2 == 0:
                eligible = list(reversed(eligible))
            for pool_idx in eligible:
                slots.append((f"P{pool_idx}", f"T{slot_idx}"))
        return slots

    def _pool_sizes_for_assignment(
        self,
        event_name: str,
        n_teams: int,
    ) -> List[int]:
        """Return the pool sizes implied by the current placeholder-pool policy."""
        if n_teams < 2:
            return []

        prefix = self._pool_assignment_event_prefix(event_name)
        gpg = COURT_ESTIMATE_POOL_GAMES_PER_TEAM.get(
            event_name, COURT_ESTIMATE_DEFAULT_POOL_GAMES_PER_TEAM
        )
        pairs = self._make_pool_game_pairs(prefix, n_teams, gpg)
        slot_ids_by_pool: Dict[str, set] = {}
        for team_a_id, team_b_id, pool_id in pairs:
            for team_id in (team_a_id, team_b_id):
                match = re.search(r"-P\d+-T(\d+)$", str(team_id))
                if not match:
                    continue
                slot_ids_by_pool.setdefault(pool_id, set()).add(int(match.group(1)))

        if not slot_ids_by_pool:
            return [n_teams]

        def _pool_key(pool_id: str) -> int:
            try:
                return int(str(pool_id).replace("P", ""))
            except ValueError:
                return 0

        return [
            len(slot_ids_by_pool[pool_id])
            for pool_id in sorted(slot_ids_by_pool.keys(), key=_pool_key)
        ]

    def _apply_pool_assignments_to_rows(
        self,
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Compute draw order and pool placement for Pool-Assignment rows."""
        normalized_rows = [dict(row) for row in rows]
        grouped_rows: Dict[str, List[Dict[str, Any]]] = {}
        for row in normalized_rows:
            event_name = str(row.get("Event") or "").strip()
            team_id = str(row.get("Team ID") or "").strip()
            if not event_name or not team_id:
                continue
            row["Seed"] = self._normalize_pool_seed(row.get("Seed"))
            row["Random Draw Order"] = self._positive_int_or_none(row.get("Random Draw Order"))
            row["Notes"] = str(row.get("Notes") or "").strip()
            grouped_rows.setdefault(event_name, []).append(row)

        output_rows: List[Dict[str, Any]] = []
        for event_name, _prefix in self._POOL_ASSIGNMENT_EVENT_DEFS:
            event_rows = grouped_rows.get(event_name, [])
            if not event_rows:
                continue

            duplicate_seed_values = {
                seed
                for seed in {
                    row.get("Seed")
                    for row in event_rows
                    if row.get("Seed") is not None
                }
                if sum(1 for row in event_rows if row.get("Seed") == seed) > 1
            }
            if duplicate_seed_values:
                duplicates = ", ".join(
                    f"{seed}: "
                    + "/".join(
                        sorted(
                            str(row.get("Team ID") or "").strip()
                            for row in event_rows
                            if row.get("Seed") == seed
                        )
                    )
                    for seed in sorted(duplicate_seed_values)
                )
                logger.warning(
                    f"Pool-Assignment duplicate seeds detected for event '{event_name}': "
                    f"{duplicates}"
                )

            existing_draw_orders = {
                row["Team ID"]: row["Random Draw Order"]
                for row in event_rows
                if self._positive_int_or_none(row.get("Random Draw Order")) is not None
            }
            next_draw_order = max(existing_draw_orders.values(), default=0)
            missing_draw_ids = [
                str(row.get("Team ID") or "").strip()
                for row in event_rows
                if str(row.get("Team ID") or "").strip() not in existing_draw_orders
            ]
            if missing_draw_ids:
                for team_id in sorted(
                    missing_draw_ids,
                    key=lambda value: self._default_random_draw_orders(event_name, missing_draw_ids)[value],
                ):
                    next_draw_order += 1
                    existing_draw_orders[team_id] = next_draw_order

            for row in event_rows:
                row["Random Draw Order"] = existing_draw_orders.get(
                    str(row.get("Team ID") or "").strip()
                )

            seeded_rows = sorted(
                [row for row in event_rows if row.get("Seed") is not None],
                key=lambda row: (int(row["Seed"]), str(row.get("Team ID") or "")),
            )
            unseeded_rows = sorted(
                [row for row in event_rows if row.get("Seed") is None],
                key=lambda row: (
                    int(row.get("Random Draw Order") or 0),
                    str(row.get("Team ID") or ""),
                ),
            )
            ordered_rows = seeded_rows + unseeded_rows

            if len(ordered_rows) < 2:
                for draw_position, row in enumerate(ordered_rows, start=1):
                    row["Draw Position"] = draw_position
                    row["Pool ID"] = ""
                    row["Pool Slot"] = ""
                    row["Assignment Basis"] = "WaitingForMoreTeams"
                output_rows.extend(ordered_rows)
                continue

            pool_sizes = self._pool_sizes_for_assignment(event_name, len(ordered_rows))
            slots = self._serpentine_pool_slots(pool_sizes)
            if len(slots) != len(ordered_rows):
                logger.warning(
                    f"Pool-assignment slot count mismatch for event '{event_name}': "
                    f"{len(slots)} slots for {len(ordered_rows)} teams. Leaving pool cells blank."
                )
                for draw_position, row in enumerate(ordered_rows, start=1):
                    row["Draw Position"] = draw_position
                    row["Pool ID"] = ""
                    row["Pool Slot"] = ""
                    row["Assignment Basis"] = (
                        "SeededDuplicate"
                        if row.get("Seed") in duplicate_seed_values
                        else ("Seeded" if row.get("Seed") is not None else "RandomDraw")
                    )
                output_rows.extend(ordered_rows)
                continue

            for draw_position, (row, slot) in enumerate(zip(ordered_rows, slots), start=1):
                row["Draw Position"] = draw_position
                row["Pool ID"] = slot[0]
                row["Pool Slot"] = slot[1]
                row["Assignment Basis"] = (
                    "SeededDuplicate"
                    if row.get("Seed") in duplicate_seed_values
                    else ("Seeded" if row.get("Seed") is not None else "RandomDraw")
                )

            output_rows.extend(ordered_rows)

        return sorted(
            output_rows,
            key=lambda row: (
                self._event_sort_index(str(row.get("Event") or "")),
                int(row.get("Draw Position") or 0),
                str(row.get("Team ID") or ""),
            ),
        )

    def _build_pool_assignment_rows(
        self,
        roster_rows: List[Dict[str, Any]],
        sidecar_path: Optional[Path],
    ) -> List[Dict[str, Any]]:
        """Build Pool-Assignment rows from roster data plus persisted seed state."""
        persisted_state = self._load_pool_assignment_state(sidecar_path)
        base_rows = self._build_pool_assignment_base_rows(roster_rows, persisted_state)
        return self._apply_pool_assignments_to_rows(base_rows)

    @staticmethod
    def _normalize_primary_sport_name(value: Any) -> str:
        """Normalize a declared primary sport value for conflict weighting."""
        return str(value or "").strip()

    @classmethod
    def _solver_team_id(cls, event_name: str, team_id: str) -> str:
        """Return an event-scoped internal team id safe for cross-sport solving."""
        return f"{cls._pool_assignment_event_prefix(event_name)}::{team_id}"

    @classmethod
    def _pool_assignment_placeholder_map(
        cls,
        pool_assignment_rows: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Return {event: {PREFIX-Px-Ty: team metadata}} from assigned pool rows."""
        grouped: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for row in pool_assignment_rows:
            event_name = str(row.get("Event") or "").strip()
            pool_id = str(row.get("Pool ID") or "").strip()
            pool_slot = str(row.get("Pool Slot") or "").strip()
            team_id = str(row.get("Team ID") or "").strip()
            if not event_name or not pool_id or not pool_slot or not team_id:
                continue
            prefix = cls._pool_assignment_event_prefix(event_name)
            placeholder_id = f"{prefix}-{pool_id}-{pool_slot}"
            display_label = str(row.get("Team Label") or team_id).strip() or team_id
            grouped.setdefault(event_name, {})[placeholder_id] = {
                "solver_team_id": cls._solver_team_id(event_name, team_id),
                "display_label": display_label,
                "team_id": team_id,
                "pool_id": pool_id,
                "pool_slot": pool_slot,
            }
        return grouped

    @classmethod
    def _build_core_gym_team_lookup(
        cls,
        roster_rows: List[Dict[str, Any]],
    ) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """Return team membership metadata keyed by (event_name, team_id)."""
        team_lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for event_name, _prefix in cls._POOL_ASSIGNMENT_EVENT_DEFS:
            min_team_size = cls._get_min_team_size(event_name)
            target_type, target_gender, _target_format = cls._decompose_event_name(event_name)
            provisional: Dict[Tuple[str, str], Dict[str, Any]] = {}

            for roster_row in roster_rows:
                r_type = str(roster_row.get("sport_type") or "").strip()
                r_gender = str(roster_row.get("sport_gender") or "").strip()
                r_format = str(roster_row.get("sport_format") or "").strip()
                if (
                    r_type.casefold() != target_type.casefold()
                    and r_type.casefold() != event_name.casefold()
                ):
                    continue
                if target_gender and r_gender.casefold() != target_gender.casefold():
                    continue
                if r_format and r_format.casefold() != SPORT_FORMAT["TEAM"].casefold():
                    continue

                church_code = str(roster_row.get("Church Team") or "").strip().upper()
                if not church_code:
                    continue
                team_order = str(roster_row.get("team_order") or "").strip().upper()
                team_id = church_code if not team_order else f"{church_code}-{team_order}"
                key = (event_name, team_id)
                team_state = provisional.setdefault(
                    key,
                    {
                        "event": event_name,
                        "team_id": team_id,
                        "solver_team_id": cls._solver_team_id(event_name, team_id),
                        "display_label": team_id,
                        "participant_ids": set(),
                        "participant_names": {},
                        "primary_sports": {},
                    },
                )
                participant_id = str(
                    roster_row.get("Participant ID (WP)")
                    or roster_row.get("ChMeetings ID")
                    or ""
                ).strip()
                if not participant_id:
                    continue

                team_state["participant_ids"].add(participant_id)
                full_name = (
                    f"{str(roster_row.get('First Name') or '').strip()} "
                    f"{str(roster_row.get('Last Name') or '').strip()}"
                ).strip()
                if full_name:
                    team_state["participant_names"][participant_id] = full_name
                team_state["primary_sports"][participant_id] = cls._normalize_primary_sport_name(
                    roster_row.get("participant_primary_sport")
                )

            for key, team_state in provisional.items():
                if len(team_state["participant_ids"]) < min_team_size:
                    continue
                team_lookup[key] = team_state

        return team_lookup

    @classmethod
    def _build_gym_team_conflicts(
        cls,
        roster_rows: List[Dict[str, Any]],
        pool_assignment_rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Return cross-sport shared-athlete edges for the current Phase 1 team sports."""
        team_lookup = cls._build_core_gym_team_lookup(roster_rows)
        if not team_lookup:
            return []

        assigned_rows = {
            (str(row.get("Event") or "").strip(), str(row.get("Team ID") or "").strip())
            for row in pool_assignment_rows
            if str(row.get("Pool ID") or "").strip() and str(row.get("Pool Slot") or "").strip()
        }
        ordered_keys = sorted(
            [key for key in team_lookup.keys() if key in assigned_rows],
            key=lambda item: (cls._event_sort_index(item[0]), item[1]),
        )

        conflicts: List[Dict[str, Any]] = []
        for idx, key_a in enumerate(ordered_keys):
            team_a = team_lookup[key_a]
            ids_a = team_a["participant_ids"]
            if not ids_a:
                continue

            for key_b in ordered_keys[idx + 1:]:
                if key_a[0] == key_b[0]:
                    continue
                team_b = team_lookup[key_b]
                shared_ids = sorted(ids_a & team_b["participant_ids"])
                if not shared_ids:
                    continue

                primary_overlap_count = 0
                shared_names: List[str] = []
                for participant_id in shared_ids:
                    primary_sport = (
                        team_a["primary_sports"].get(participant_id)
                        or team_b["primary_sports"].get(participant_id)
                        or ""
                    )
                    if primary_sport and primary_sport.casefold() in {
                        str(team_a["event"]).casefold(),
                        str(team_b["event"]).casefold(),
                    }:
                        primary_overlap_count += 1
                    shared_names.append(
                        team_a["participant_names"].get(
                            participant_id,
                            team_b["participant_names"].get(participant_id, participant_id),
                        )
                    )

                conflicts.append({
                    "team_a_id": team_a["solver_team_id"],
                    "team_a_label": team_a["display_label"],
                    "event_a": team_a["event"],
                    "team_b_id": team_b["solver_team_id"],
                    "team_b_label": team_b["display_label"],
                    "event_b": team_b["event"],
                    "shared_participant_ids": shared_ids,
                    "shared_participant_names": shared_names,
                    "shared_count": len(shared_ids),
                    "primary_overlap_count": primary_overlap_count,
                    "secondary_only_count": len(shared_ids) - primary_overlap_count,
                })

        return conflicts

    @staticmethod
    def _pool_numeric_suffix(value: str, prefix: str) -> int:
        """Extract the trailing numeric suffix from pool or pool-slot labels."""
        text = str(value or "").strip()
        if not text:
            return 0
        match = re.match(rf"^{re.escape(prefix)}(\d+)$", text)
        if match:
            return int(match.group(1))
        return 0

    @classmethod
    def _bc_pool_triplets(
        cls,
        pool_rows: List[Dict[str, Any]],
    ) -> List[Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]]:
        """Return deterministic 3-team BC Jeopardy rounds for one assigned pool."""
        ordered_rows = sorted(
            pool_rows,
            key=lambda row: (
                cls._pool_numeric_suffix(str(row.get("Pool Slot") or ""), "T"),
                str(row.get("Team ID") or ""),
            ),
        )
        n_teams = len(ordered_rows)
        if n_teams < COURT_ESTIMATE_BC_TEAMS_PER_GAME:
            return []
        if n_teams == 3:
            trio = tuple(ordered_rows[:3])
            return [trio, trio]
        if n_teams == 4:
            t1, t2, t3, t4 = ordered_rows
            return [
                (t1, t2, t4),
                (t1, t3, t4),
                (t2, t3, t4),
            ]
        if n_teams == 5:
            t1, t2, t3, t4, t5 = ordered_rows
            return [
                (t1, t2, t4),
                (t1, t3, t5),
                (t2, t4, t5),
                (t3, t4, t5),
            ]
        raise ValueError(
            f"Unexpected BC pool size {n_teams}; expected 3, 4, or 5 teams."
        )

    @classmethod
    def _build_assigned_bc_game_objects(
        cls,
        pool_assignment_rows: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Return BC queue games and precedence using the assigned BC pool draw."""
        event_name = SPORT_TYPE["BIBLE_CHALLENGE"]
        prefix = cls._pool_assignment_event_prefix(event_name)
        bc_rows = [
            row
            for row in pool_assignment_rows
            if str(row.get("Event") or "").strip() == event_name
            and str(row.get("Pool ID") or "").strip()
            and str(row.get("Pool Slot") or "").strip()
        ]
        if len(bc_rows) < COURT_ESTIMATE_BC_TEAMS_PER_GAME:
            return [], []

        rows_by_pool: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in bc_rows:
            rows_by_pool[str(row.get("Pool ID") or "").strip()].append(row)

        games: List[Dict[str, Any]] = []
        precedence: List[Dict[str, Any]] = []
        global_round = 0
        for pool_id in sorted(
            rows_by_pool.keys(),
            key=lambda value: cls._pool_numeric_suffix(value, "P"),
        ):
            for local_round, trio in enumerate(cls._bc_pool_triplets(rows_by_pool[pool_id]), start=1):
                global_round += 1
                solver_team_ids = [
                    cls._solver_team_id(event_name, str(row.get("Team ID") or "").strip())
                    for row in trio
                ]
                labels = [
                    str(row.get("Team Label") or row.get("Team ID") or "").strip()
                    for row in trio
                ]
                games.append({
                    "game_id": f"{prefix}-{pool_id}-RR-{local_round}",
                    "event": event_name,
                    "stage": "Pool",
                    "pool_id": pool_id,
                    "round": global_round,
                    "team_a_id": solver_team_ids[0],
                    "team_b_id": solver_team_ids[1],
                    "team_c_id": solver_team_ids[2],
                    "team_a_label": labels[0],
                    "team_b_label": labels[1],
                    "team_c_label": labels[2],
                    "duration_minutes": COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE,
                    "resource_type": TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE,
                    "earliest_slot": None,
                    "latest_slot": None,
                })

        if len(bc_rows) >= COURT_ESTIMATE_BC_MIN_TEAMS_FOR_PLAYOFF:
            semi_ids: List[str] = []
            for semi_idx in range(1, 4):
                semi_id = f"{prefix}-Semi-{semi_idx}"
                semi_ids.append(semi_id)
                games.append({
                    "game_id": semi_id,
                    "event": event_name,
                    "stage": "Semi",
                    "pool_id": "",
                    "round": semi_idx,
                    "team_a_id": f"{prefix}-Semi-{semi_idx}-A",
                    "team_b_id": f"{prefix}-Semi-{semi_idx}-B",
                    "team_c_id": f"{prefix}-Semi-{semi_idx}-C",
                    "team_a_label": f"Semi {semi_idx} Qualifier A",
                    "team_b_label": f"Semi {semi_idx} Qualifier B",
                    "team_c_label": f"Semi {semi_idx} Qualifier C",
                    "duration_minutes": COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE,
                    "resource_type": TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE,
                    "earliest_slot": None,
                    "latest_slot": None,
                })

            final_id = f"{prefix}-Final"
            games.append({
                "game_id": final_id,
                "event": event_name,
                "stage": "Final",
                "pool_id": "",
                "round": 1,
                "team_a_id": f"WIN-{semi_ids[0]}",
                "team_b_id": f"WIN-{semi_ids[1]}",
                "team_c_id": f"WIN-{semi_ids[2]}",
                "team_a_label": "Winner Semi 1",
                "team_b_label": "Winner Semi 2",
                "team_c_label": "Winner Semi 3",
                "duration_minutes": COURT_ESTIMATE_MINUTES_BIBLE_CHALLENGE,
                "resource_type": TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE,
                "earliest_slot": None,
                "latest_slot": None,
            })
            precedence.extend(
                {
                    "before_game_id": semi_id,
                    "after_game_id": final_id,
                    "min_gap_slots": 1,
                }
                for semi_id in semi_ids
            )

        return games, precedence

    @classmethod
    def _build_assigned_gym_game_objects(
        cls,
        roster_rows: List[Dict[str, Any]],
        pool_assignment_rows: List[Dict[str, Any]],
        allow_placeholder_fallback: bool = True,
    ) -> List[Dict[str, Any]]:
        """Return gym games using assigned real teams when pool assignments exist."""
        sport_defs = [
            (SPORT_TYPE["BASKETBALL"], "BBM", GYM_RESOURCE_TYPE_BASKETBALL),
            (SPORT_TYPE["VOLLEYBALL_MEN"], "VBM", GYM_RESOURCE_TYPE_VOLLEYBALL),
            (SPORT_TYPE["VOLLEYBALL_WOMEN"], "VBW", GYM_RESOURCE_TYPE_VOLLEYBALL),
        ]
        mpg = COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME
        games: List[Dict[str, Any]] = []
        placeholder_map_by_event = cls._pool_assignment_placeholder_map(pool_assignment_rows)

        for event_name, prefix, resource_type in sport_defs:
            min_team_size = cls._get_min_team_size(event_name)
            counts = cls._count_estimating_teams(roster_rows, event_name, min_team_size)
            slot_map = placeholder_map_by_event.get(event_name, {})
            if slot_map:
                n_teams = len(slot_map)
            elif counts["n_estimating"] >= 2:
                n_teams = counts["n_estimating"]
            elif allow_placeholder_fallback:
                n_teams = 8
            else:
                continue

            gpg = COURT_ESTIMATE_POOL_GAMES_PER_TEAM.get(
                event_name, COURT_ESTIMATE_DEFAULT_POOL_GAMES_PER_TEAM
            )
            pool_pairs = cls._make_pool_game_pairs(prefix, n_teams, gpg)
            for pair_idx, (team_a_id, team_b_id, pool_id) in enumerate(pool_pairs, start=1):
                team_a_meta = slot_map.get(team_a_id)
                team_b_meta = slot_map.get(team_b_id)
                if slot_map and (team_a_meta is None or team_b_meta is None):
                    logger.warning(
                        f"Pool-assignment map for event '{event_name}' is missing "
                        f"{team_a_id!r} or {team_b_id!r}; falling back to placeholders."
                    )
                games.append({
                    "game_id": f"{prefix}-{pair_idx:02d}",
                    "event": event_name,
                    "stage": "Pool",
                    "pool_id": pool_id,
                    "round": pair_idx,
                    "team_a_id": (
                        team_a_meta["solver_team_id"] if team_a_meta is not None else team_a_id
                    ),
                    "team_b_id": (
                        team_b_meta["solver_team_id"] if team_b_meta is not None else team_b_id
                    ),
                    "team_a_label": (
                        team_a_meta["display_label"] if team_a_meta is not None else team_a_id
                    ),
                    "team_b_label": (
                        team_b_meta["display_label"] if team_b_meta is not None else team_b_id
                    ),
                    "duration_minutes": mpg,
                    "resource_type": resource_type,
                    "solver_pool": cls._GYM_CORE_SOLVER_POOL,
                    "earliest_slot": None,
                    "latest_slot": None,
                })

        return games

    # ── Schedule-Input JSON builders ─────────────────────────────────────────

    def _build_gym_game_objects(
        self,
        roster_rows: List[Dict[str, Any]],
        allow_placeholder_fallback: bool = True,
    ) -> List[Dict[str, Any]]:
        """Return pool-play game placeholder dicts for gym sports (Basketball, VB Men, VB Women).

        Pool games carry stable placeholder team IDs (e.g. BBM-P1-T1, BBM-P1-T2)
        and non-empty pool_id values so the solver can enforce team-overlap and
        min-rest constraints even before final church assignments are known.

        Playoff games (QF/Semi/Final/3rd) are pre-assigned via the Playoff-Slots
        tab in venue_input.xlsx and are not included here.

        When allow_placeholder_fallback is True, sports with fewer than two
        estimating teams fall back to the legacy 8-team planning scaffold so
        offline sketching still works without venue data. When False, those
        sports are omitted from the solver input entirely.
        """
        sport_defs = [
            (SPORT_TYPE["BASKETBALL"],       "BBM", GYM_RESOURCE_TYPE_BASKETBALL),
            (SPORT_TYPE["VOLLEYBALL_MEN"],   "VBM", GYM_RESOURCE_TYPE_VOLLEYBALL),
            (SPORT_TYPE["VOLLEYBALL_WOMEN"], "VBW", GYM_RESOURCE_TYPE_VOLLEYBALL),
        ]
        mpg = COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME
        games: List[Dict[str, Any]] = []

        for event_name, prefix, resource_type in sport_defs:
            min_sz = self._get_min_team_size(event_name)
            counts = self._count_estimating_teams(roster_rows, event_name, min_sz)
            if counts["n_estimating"] >= 2:
                n_teams = counts["n_estimating"]
            elif allow_placeholder_fallback:
                n_teams = 8
            else:
                continue
            gpg = COURT_ESTIMATE_POOL_GAMES_PER_TEAM.get(
                event_name, COURT_ESTIMATE_DEFAULT_POOL_GAMES_PER_TEAM
            )

            # Pool games — stable team IDs and non-empty pool_id
            pool_pairs = self._make_pool_game_pairs(prefix, n_teams, gpg)
            for pair_idx, (team_a_id, team_b_id, pool_id) in enumerate(pool_pairs, start=1):
                games.append({
                    "game_id": f"{prefix}-{pair_idx:02d}",
                    "event": event_name,
                    "stage": "Pool",
                    "pool_id": pool_id,
                    "round": pair_idx,
                    "team_a_id": team_a_id,
                    "team_b_id": team_b_id,
                    "duration_minutes": mpg,
                    "resource_type": resource_type,
                    "earliest_slot": None,
                    "latest_slot":   None,
                })

        return games

    def _build_pod_game_objects(
        self,
        roster_rows: List[Dict[str, Any]],
        validation_rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Return single-elimination game placeholder dicts for pod (racquet) sports.

        Uses planning_entries (confirmed + provisional) from Pod-Divisions.
        Number of games per division = planning_entries − 1 (single elimination).
        Divisions with fewer than 2 planning entries are skipped.
        """
        div_rows = self._build_pod_divisions_rows(roster_rows, validation_rows)
        games: List[Dict[str, Any]] = []
        for div in div_rows:
            if div["division_status"] in ("Empty", "AnomalyOnly"):
                continue
            n_entries = div["planning_entries"]
            if n_entries < 2:
                continue
            division_id = div["division_id"]
            sport_type = div["sport_type"]
            resource_type = div["resource_type"]
            mpg = div["minutes_per_game"]
            for i in range(1, n_entries):  # n_entries - 1 games
                games.append({
                    "game_id": f"{division_id}-{i:02d}",
                    "event": sport_type,
                    "stage": "R1",
                    "pool_id": "",
                    "round": i,
                    "team_a_id": None,
                    "team_b_id": None,
                    "duration_minutes": mpg,
                    "resource_type": resource_type,
                    "earliest_slot": None,
                    "latest_slot": None,
                })
        return games

    @staticmethod
    def _build_gym_resource_objects(
        n_basketball: int = 2,
        n_volleyball: int = 2,
    ) -> List[Dict[str, Any]]:
        """Fallback gym resource builder (no venue_input.xlsx).

        Generates n_basketball + n_volleyball resources per session across four
        sessions (Sat-1, Sun-1, Sat-2, Sun-2) using SCHEDULE_SKETCH_* time
        windows.  Basketball courts are numbered first within each session,
        volleyball courts second.
        """
        mpg = COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME
        close_sat = f"{SCHEDULE_SKETCH_SATURDAY_LAST_GAME + mpg // 60:02d}:00"
        close_sun = f"{SCHEDULE_SKETCH_SUNDAY_LAST_GAME + mpg // 60:02d}:00"
        sessions = [
            ("Sat-1", f"{SCHEDULE_SKETCH_SATURDAY_START:02d}:00", close_sat),
            ("Sun-1", f"{SCHEDULE_SKETCH_SUNDAY_START:02d}:00",   close_sun),
            ("Sat-2", f"{SCHEDULE_SKETCH_SATURDAY_START:02d}:00", close_sat),
            ("Sun-2", f"{SCHEDULE_SKETCH_SUNDAY_START:02d}:00",   close_sun),
        ]
        type_blocks = [
            (GYM_RESOURCE_TYPE_BASKETBALL, n_basketball),
            (GYM_RESOURCE_TYPE_VOLLEYBALL, n_volleyball),
        ]
        resources: List[Dict[str, Any]] = []
        for day_label, open_time, close_time in sessions:
            c = 0
            for rtype, count in type_blocks:
                for local in range(1, count + 1):
                    c += 1
                    resources.append({
                        "resource_id":     f"GYM-{day_label}-{c}",
                        "resource_type":   rtype,
                        "label":           f"Court-{c}",
                        "day":             day_label,
                        "open_time":       open_time,
                        "close_time":      close_time,
                        "slot_minutes":    mpg,
                        "exclusive_group": "",
                    })
        return resources

    @staticmethod
    def _build_gym_resources_from_allocator(decisions) -> List[Dict[str, Any]]:
        """Convert Stage-A AllocationDecision objects into schedule_input resources.

        Courts within each decision are numbered per-day sequentially so that
        resource IDs remain stable across re-runs with the same venue configuration.
        """
        resources: List[Dict[str, Any]] = []
        court_counter: Dict[str, int] = {}  # day → running counter

        # Sort for ID stability: day order, then open_time, then gym name.
        from gym_allocator import _DAY_ORDER
        sorted_decisions = sorted(
            decisions,
            key=lambda d: (_DAY_ORDER.get(d.day, 99), d.open_time, d.gym_name),
        )
        for decision in sorted_decisions:
            day = decision.day
            for local in range(1, decision.courts + 1):
                court_counter[day] = court_counter.get(day, 0) + 1
                n = court_counter[day]
                resources.append({
                    "resource_id":     f"GYM-{day}-{n}",
                    "resource_type":   decision.mode,
                    "label":           f"Court-{local}",
                    "day":             day,
                    "open_time":       decision.open_time,
                    "close_time":      decision.close_time,
                    "slot_minutes":    decision.slot_minutes,
                    "exclusive_group": decision.gym_name,
                })
        return resources

    @staticmethod
    def _clean_excel_text(val) -> str:
        """Normalize spreadsheet cells so blanks/NaN become an empty string."""
        if pd.isna(val):
            return ""
        return str(val).strip()

    @staticmethod
    def _float_from_excel(val, default: float) -> float:
        """Convert spreadsheet cells to float while treating blanks/NaN as a default."""
        if pd.isna(val) or val in (None, ""):
            return default
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_excel_date(val) -> Optional[datetime]:
        """Convert an Excel date-like cell to datetime, or None when unavailable."""
        if pd.isna(val) or val in (None, ""):
            return None
        if isinstance(val, datetime):
            return val
        try:
            parsed = pd.to_datetime(val)
        except Exception:
            return None
        if pd.isna(parsed):
            return None
        return parsed.to_pydatetime()

    @classmethod
    def _derive_day_labels_from_dates(cls, values: List[Any]) -> Dict[str, str]:
        """Map unique venue dates to logical labels such as Sat-1 / Sun-1."""
        unique_dates: List[datetime] = []
        seen_keys: set[str] = set()
        for value in values:
            parsed = cls._coerce_excel_date(value)
            if not parsed:
                continue
            key = parsed.date().isoformat()
            if key in seen_keys:
                continue
            seen_keys.add(key)
            unique_dates.append(parsed)

        unique_dates.sort()
        labels: Dict[str, str] = {}
        sat_idx = 0
        sun_idx = 0
        other_idx = 0
        for dt_value in unique_dates:
            weekday = dt_value.weekday()
            if weekday == 5:
                sat_idx += 1
                label = f"Sat-{sat_idx}"
            elif weekday == 6:
                sun_idx += 1
                label = f"Sun-{sun_idx}"
            else:
                other_idx += 1
                label = f"Day-{other_idx}"
            labels[dt_value.date().isoformat()] = label
        return labels

    @classmethod
    def _load_venue_input_rows(cls, venue_input_path: Path) -> List[Dict[str, Any]]:
        """Expand venue_input.xlsx into per-resource objects for schedule_input.json.

        Each row with Quantity=N emits N resource objects labelled Court-1…N or
        Table-1…N.  Returns an empty list if the file does not exist.
        """
        if not venue_input_path.exists():
            return []
        try:
            df = pd.read_excel(
                venue_input_path, sheet_name="Venue-Input", engine="openpyxl"
            )
        except Exception as e:
            logger.warning(f"Could not read venue input rows from {venue_input_path}: {e}")
            return []

        rows: List[Dict[str, Any]] = []
        # Counter keyed by (resource_type, day) for day-aware resource IDs.
        resource_counts: Dict[tuple, int] = {}
        has_day_col = "Day" in df.columns
        date_day_map = (
            ScheduleWorkbookBuilder._derive_day_labels_from_dates(df["Date"].tolist())
            if "Date" in df.columns else {}
        )

        for _, row in df.iterrows():
            resource_type = cls._clean_excel_text(row.get("Resource Type"))
            if not resource_type:
                continue
            venue_name = cls._clean_excel_text(row.get("Venue Name"))
            # Exclusive Venue Group: rows sharing a group value compete for the
            # same physical gym (only one mode active per time block). Optional
            # column — blank means the resource stands alone.
            exclusive_group = cls._clean_excel_text(
                row.get("Exclusive Venue Group")
            )
            # Day column: use explicit value when present; otherwise derive from Date.
            if has_day_col:
                day = cls._clean_excel_text(row.get("Day"))
            else:
                day = ""
            if not day:
                parsed_date = ScheduleWorkbookBuilder._coerce_excel_date(row.get("Date"))
                day = (
                    date_day_map.get(parsed_date.date().isoformat(), "")
                    if parsed_date else ""
                )
            if not day:
                day = "Day-1"
            qty = max(1, int(cls._float_from_excel(row.get("Quantity"), 1)))
            slot_min = max(1, int(cls._float_from_excel(row.get("Slot Minutes"), 60)))
            start = cls._parse_hour(row.get("Start Time"))
            last_start = cls._parse_hour(row.get("Last Start Time"))
            open_time = f"{int(start):02d}:{int(round((start % 1) * 60)):02d}"
            close_decimal = last_start + slot_min / 60.0
            close_time = f"{int(close_decimal):02d}:{int(round((close_decimal % 1) * 60)):02d}"

            abbrev = resource_type.split()[0][:3].upper()
            count_key = (resource_type, day)
            rc = resource_counts.get(count_key, 0)

            for i in range(1, qty + 1):
                rc += 1
                label = (
                    f"Table-{i}" if "table" in resource_type.lower() else f"Court-{i}"
                )
                rows.append({
                    "resource_id":     f"{abbrev}-{day}-{rc}",
                    "resource_type":   resource_type,
                    "label":           label,
                    "day":             day,
                    "open_time":       open_time,
                    "close_time":      close_time,
                    "slot_minutes":    slot_min,
                    "venue_name":      venue_name,
                    "exclusive_group": exclusive_group,
                })
            resource_counts[count_key] = rc

        logger.debug(f"Loaded {len(rows)} venue resource rows from {venue_input_path}")
        return rows

    @staticmethod
    def _load_playoff_slots(venue_input_path: Path) -> List[Dict[str, Any]]:
        """Load pre-assigned playoff game slots from the Playoff-Slots tab in venue_input.xlsx.

        Returns an empty list (with a WARNING) if the file or tab is absent.
        Expected columns: game_id, event, stage, resource_id, slot
        Optional columns: team_a_id, team_b_id, duration_minutes
        """
        if not venue_input_path.exists():
            return []
        try:
            df = pd.read_excel(venue_input_path, sheet_name="Playoff-Slots", engine="openpyxl")
        except Exception:
            logger.warning(
                "venue_input.xlsx is present but has no 'Playoff-Slots' tab — "
                "playoff games will not appear in the schedule. "
                "Add a 'Playoff-Slots' tab to include them."
            )
            return []

        required = {"game_id", "event", "stage", "resource_id", "slot"}
        cols = {str(c).strip() for c in df.columns}
        missing = required - cols
        if missing:
            logger.warning(
                f"Playoff-Slots tab is missing required columns {sorted(missing)}; "
                "playoff games will not appear in the schedule."
            )
            return []

        slots: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            game_id = ScheduleWorkbookBuilder._clean_excel_text(row.get("game_id"))
            if not game_id:
                continue
            entry: Dict[str, Any] = {
                "game_id":     game_id,
                "event":       ScheduleWorkbookBuilder._clean_excel_text(row.get("event", "")),
                "stage":       ScheduleWorkbookBuilder._clean_excel_text(row.get("stage", "")),
                "resource_id": ScheduleWorkbookBuilder._clean_excel_text(row.get("resource_id", "")),
                "slot":        ScheduleWorkbookBuilder._clean_excel_text(row.get("slot", "")),
            }
            for optional in ("team_a_id", "team_b_id", "duration_minutes"):
                val = row.get(optional)
                if val is not None and str(val).strip() not in ("", "nan"):
                    entry[optional] = ScheduleWorkbookBuilder._clean_excel_text(str(val)) if optional != "duration_minutes" else int(val)
            if entry["resource_id"] and entry["slot"]:
                slots.append(entry)
            else:
                logger.warning(f"Playoff-Slots row for {game_id!r} missing resource_id or slot; skipped.")
        return slots

    @staticmethod
    def _load_gym_modes(venue_input_path: Path) -> Dict[str, Dict[str, int]]:
        """Load per-gym mode capacities from the Gym-Modes tab in venue_input.xlsx.

        A gym that can be configured as either-or (e.g. 1 Basketball Court OR
        2 Volleyball Courts per time block) records both options on one row.
        Returns {gym_name: {resource_type: courts_per_block}}; 0 means that
        mode is not available in that gym.

        Returns an empty dict (with a WARNING) if the file or tab is absent —
        the schedule is still produced; the gym-mode capacity estimator simply
        has no mode data to work with.
        """
        # Maps a Gym-Modes column header to the resource_type it represents.
        mode_column_map = {
            "Basketball Courts": "Basketball Court",
            "Volleyball Courts": "Volleyball Court",
            "Badminton Courts":  "Badminton Court",
            "Pickleball Courts": "Pickleball Court",
            "Soccer Fields":     "Soccer Field",
        }
        if not venue_input_path.exists():
            return {}
        try:
            df = pd.read_excel(venue_input_path, sheet_name="Gym-Modes", engine="openpyxl")
        except Exception:
            logger.warning(
                "venue_input.xlsx is present but has no 'Gym-Modes' tab — "
                "gym-mode capacity estimation will be skipped. "
                "Add a 'Gym-Modes' tab to enable it."
            )
            return {}

        df = df.rename(columns=lambda c: str(c).strip())
        cols = set(df.columns)
        if "Gym Name" not in cols:
            logger.warning(
                "Gym-Modes tab is missing the 'Gym Name' column — "
                "gym-mode capacity estimation will be skipped."
            )
            return {}

        active_modes = {col: rt for col, rt in mode_column_map.items() if col in cols}
        if not active_modes:
            logger.warning(
                "Gym-Modes tab has no recognized mode columns "
                f"({sorted(mode_column_map)}); gym-mode capacity estimation "
                "will be skipped."
            )
            return {}

        gym_modes: Dict[str, Dict[str, int]] = {}
        for _, row in df.iterrows():
            gym_name = ScheduleWorkbookBuilder._clean_excel_text(row.get("Gym Name"))
            if not gym_name:
                continue
            capacities = {
                rt: int(ScheduleWorkbookBuilder._float_from_excel(row.get(col), 0))
                for col, rt in active_modes.items()
            }
            # Skip note/blank rows — a "gym" with zero capacity in every mode
            # is the documentation footer, not a real venue.
            if not any(capacities.values()):
                continue
            gym_modes[gym_name] = capacities

        logger.debug(f"Loaded {len(gym_modes)} gym mode rows from {venue_input_path}")
        return gym_modes

    def _build_schedule_input(
        self,
        roster_rows: List[Dict[str, Any]],
        validation_rows: List[Dict[str, Any]],
        venue_input_path: Path,
        pool_assignment_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Assemble the full schedule_input package consumed by OR-Tools.

        Returns a dict with keys: generated_at, gym_court_scenario, game_count,
        resource_count, games, resources, playoff_slots, gym_modes, gym_allocation.

        When venue_input.xlsx is present with a Gym-Modes tab, the Layer-2
        Stage-A greedy allocator runs and produces real gym resources keyed to
        the booked venue.  Otherwise falls back to the SCHEDULE_SOLVER_GYM_COURTS
        constant split evenly between basketball and volleyball when no explicit
        venue rows exist. If venue rows exist but the allocator cannot run, the
        explicit Venue-Input rows are used directly.
        """
        from gym_allocator import (
            aggregate_demand_by_mode, extract_gym_blocks, allocate,
        )
        gym_modes = self._load_gym_modes(venue_input_path)
        venue_rows = self._load_venue_input_rows(venue_input_path)
        gym_blocks = extract_gym_blocks(venue_rows)
        explicit_gym_resource_types = {
            GYM_RESOURCE_TYPE_BASKETBALL,
            GYM_RESOURCE_TYPE_VOLLEYBALL,
        }
        has_explicit_gym_rows = any(
            resource.get("resource_type") in explicit_gym_resource_types
            for resource in venue_rows
        )
        gym_resource_strategy = (
            "allocator"
            if gym_blocks and gym_modes
            else "direct_venue_input"
            if has_explicit_gym_rows
            else "fallback"
        )

        pool_assignment_rows = self._build_pool_assignment_rows(
            roster_rows,
            pool_assignment_path,
        )
        gym_games = self._build_assigned_gym_game_objects(
            roster_rows,
            pool_assignment_rows,
            allow_placeholder_fallback=(gym_resource_strategy == "fallback"),
        )
        bc_games, precedence = self._build_assigned_bc_game_objects(pool_assignment_rows)
        pod_games = self._build_pod_game_objects(roster_rows, validation_rows)
        all_games = gym_games + bc_games + pod_games
        team_conflicts = self._build_gym_team_conflicts(roster_rows, pool_assignment_rows)

        gym_allocation: Optional[Dict[str, Any]] = None
        if gym_resource_strategy == "allocator":
            venue_capacity_rows = self._build_venue_capacity_rows(roster_rows)
            demand = aggregate_demand_by_mode(venue_capacity_rows)
            alloc_result = allocate(demand, gym_modes, gym_blocks)
            gym_resources = self._build_gym_resources_from_allocator(alloc_result.decisions)
            direct_resources = [r for r in venue_rows if not r.get("exclusive_group")]
            all_resources = gym_resources + direct_resources
            gym_allocation = {
                "source":        "allocator",
                "decisions":     [
                    {
                        "gym_name":     d.gym_name,
                        "day":          d.day,
                        "open_time":    d.open_time,
                        "close_time":   d.close_time,
                        "mode":         d.mode,
                        "courts":       d.courts,
                        "slot_minutes": d.slot_minutes,
                    }
                    for d in alloc_result.decisions
                ],
                "mode_supply":    alloc_result.mode_supply,
                "mode_demand":    alloc_result.mode_demand,
                "mode_shortfall": alloc_result.mode_shortfall,
                "switch_count":   alloc_result.switch_count,
            }
            logger.info(
                f"Gym allocation (Stage A): {len(alloc_result.decisions)} blocks assigned, "
                f"{alloc_result.switch_count} mode switches"
            )
        elif gym_resource_strategy == "direct_venue_input":
            all_resources = venue_rows
            if gym_blocks and not gym_modes:
                reason = "grouped_rows_without_gym_modes"
                logger.warning(
                    "Gym allocation skipped: Venue-Input contains Exclusive Venue Group rows "
                    "but no Gym-Modes tab. Using Venue-Input rows directly; mutual exclusivity "
                    "is not enforced in this mode."
                )
            elif gym_modes and not gym_blocks:
                reason = "gym_modes_without_grouped_rows"
                logger.info(
                    "Gym allocation skipped: Gym-Modes tab is present but no Exclusive Venue "
                    "Group rows were found. Using Venue-Input rows directly."
                )
            else:
                reason = "explicit_venue_rows_without_allocator"
            gym_allocation = {"source": "direct_venue_input", "reason": reason}
        else:
            n_bb = SCHEDULE_SOLVER_GYM_COURTS // 2
            n_vb = SCHEDULE_SOLVER_GYM_COURTS - n_bb
            gym_resources = self._build_gym_resource_objects(n_bb, n_vb)
            all_resources = gym_resources + venue_rows
            gym_allocation = {"source": "fallback", "gym_court_scenario": SCHEDULE_SOLVER_GYM_COURTS}
            logger.info(
                f"Gym allocation: fallback mode — {n_bb} basketball + {n_vb} volleyball courts "
                f"per session (SCHEDULE_SOLVER_GYM_COURTS={SCHEDULE_SOLVER_GYM_COURTS})"
            )

        playoff_slots = self._load_playoff_slots(venue_input_path)

        if bc_games and not any(
            str(resource.get("resource_type") or "").strip() == TEAM_RESOURCE_TYPE_BIBLE_CHALLENGE
            for resource in all_resources
        ):
            logger.warning(
                "Bible Challenge games were generated but no 'BC Station' resources were found "
                "in venue_input.xlsx. Those games will be unscheduled until a BC Station row is added."
            )

        for resource in all_resources:
            if resource.get("resource_type") in (
                GYM_RESOURCE_TYPE_BASKETBALL,
                GYM_RESOURCE_TYPE_VOLLEYBALL,
            ):
                resource["solver_pool"] = self._GYM_CORE_SOLVER_POOL

        return {
            "generated_at":       datetime.now().isoformat(timespec="seconds"),
            "gym_court_scenario": SCHEDULE_SOLVER_GYM_COURTS,
            "game_count":         len(all_games),
            "resource_count":     len(all_resources),
            "games":              all_games,
            "resources":          all_resources,
            "playoff_slots":      playoff_slots,
            "gym_modes":          gym_modes,
            "gym_allocation":     gym_allocation,
            "team_conflicts":     team_conflicts,
            "precedence":         precedence,
        }

    @staticmethod
    def _write_summary_tab(ws) -> None:
        """Write an operator-facing guide for using the planning workbook."""
        from openpyxl.styles import PatternFill, Font, Alignment

        title_fill = PatternFill(fgColor=SCHEDULE_SKETCH_COLOR_HEADER, fill_type="solid")
        section_fill = PatternFill(fgColor=SCHEDULE_SKETCH_COLOR_SECTION, fill_type="solid")
        title_font = Font(bold=True, color="FFFFFF", size=14)
        section_font = Font(bold=True)
        body_font = Font(size=11)
        wrap_left = Alignment(horizontal="left", vertical="top", wrap_text=True)

        rows: List[Tuple[str, str]] = [
            (
                "What This Workbook Is",
                "This workbook is the Layer 1 planning aid for Sports Fest scheduling. "
                "Use it to estimate court demand, review pod/racquet entries, inspect "
                "resource IDs, and iterate on venue_input.xlsx before producing the final "
                "Layer 2 floor schedule.",
            ),
            (
                "What This Workbook Is Not",
                "This is not the final game timetable for coordinators on event day. "
                "The final Layer 2 output is VAYSF_Schedule_YYYY-MM-DD.xlsx, produced after "
                "running the solver.",
            ),
            (
                "Where To Start",
                "Work from the middleware folder. Start by refreshing the live exports with "
                "run-me.bat or, if you only need the scheduling artifacts, "
                "python main.py export-church-teams.",
            ),
            (
                "Required Roster Input",
                "build-schedule-workbook should read the consolidated ALL-church export "
                "(Church_Team_Status_ALL_YYYY-MM-DD.xlsx) as its roster and validation "
                "context. Do not point it at a single-church workbook if you want full "
                "Venue-Estimator / pod planning results.",
            ),
            (
                "Layer 1 Loop",
                "1. Edit middleware/data/venue_input.xlsx.\n"
                "2. Run: python main.py export-church-teams\n"
                "3. Run: python main.py build-schedule-workbook "
                "--input-xlsx \"...\\Church_Team_Status_ALL_YYYY-MM-DD.xlsx\"\n"
                "   If omitted, the command tries to auto-detect the newest ALL workbook "
                "beside schedule_input.json or in EXPORT_DIR.\n"
                "4. Review the planning tabs in this workbook.\n"
                "5. Edit the Pool-Assignment tab if you want to seed BB/VBM/VBW/BC"
                f"{'/SOC' if SOCCER_ENABLED else ''} teams, then run:\n"
                "   python main.py assign-pools --workbook \"...\\Schedule_Workbook_YYYY-MM-DD.xlsx\"\n"
                "6. Repeat until venue capacity, seeding, pod planning, and resource IDs look right.",
            ),
            (
                "Layer 2 Commands",
                "When Layer 1 looks good, run Layer 2 from the middleware folder:\n"
                "run-schedule.bat\n"
                "Or run the two commands separately:\n"
                "python main.py solve-schedule\n"
                "python main.py produce-schedule",
            ),
            (
                "Tabs In This Workbook",
                "Summary: operator guide and command cheat sheet.\n"
                "Venue-Estimator: rough demand estimate for team/racquet sports.\n"
                "Pool-Assignment: editable BB/VBM/VBW/BC"
                f"{'/SOC' if SOCCER_ENABLED else ''} seed and pool-draw workspace.\n"
                "Pod-Divisions: planned pod divisions for racquet/pod events.\n"
                "Pod-Entries-Review: detailed entry review for pod sports.\n"
                "Court-Schedule-Sketch: quick planning sketch using Layer 1 assumptions.\n"
                "Pod-Resource-Estimate: compare pod demand against available venue resources.\n"
                "Schedule-Input: readable echo of schedule_input.json, including resource IDs.\n"
                "Gym-Allocation: Stage-A Layer 2 gym-mode allocation summary.",
            ),
            (
                "Most Important Checks",
                "Use Venue-Estimator and Pod-Resource-Estimate to see whether the booked venue "
                "is large enough. Use Schedule-Input to copy exact resource_id values into the "
                "Playoff-Slots tab of venue_input.xlsx. Use Gym-Allocation to confirm how gym "
                "time blocks are being assigned across basketball and volleyball modes.",
            ),
            (
                "Where To Read More",
                "For the full operator walkthrough, open docs/SCHEDULE-HOW-TO.md. "
                "For the deeper technical reference, open docs/SCHEDULING.md.",
            ),
        ]

        ws.sheet_view.showGridLines = False
        ws.column_dimensions["A"].width = 28
        ws.column_dimensions["B"].width = 110

        ws.merge_cells("A1:B1")
        title_cell = ws["A1"]
        title_cell.value = "VAY Sports Fest — Schedule Workbook Guide"
        title_cell.fill = title_fill
        title_cell.font = title_font
        title_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 24

        ws["A2"] = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        ws["A2"].font = Font(italic=True)
        ws["A2"].alignment = wrap_left
        ws.merge_cells("A2:B2")

        current_row = 4
        for heading, body in rows:
            head_cell = ws.cell(row=current_row, column=1, value=heading)
            head_cell.fill = section_fill
            head_cell.font = section_font
            head_cell.alignment = wrap_left

            body_cell = ws.cell(row=current_row, column=2, value=body)
            body_cell.font = body_font
            body_cell.alignment = wrap_left

            line_count = max(2, body.count("\n") + 1)
            ws.row_dimensions[current_row].height = max(24, 18 * line_count)
            current_row += 1

    @staticmethod
    def _set_excel_comment(cell, note: Optional[str]) -> None:
        """Attach a standard Excel note/comment to a cell when note text exists."""
        if not note:
            return
        from openpyxl.comments import Comment

        cell.comment = Comment(note, "VAYSF")

    @classmethod
    def _annotate_header_row(
        cls,
        ws,
        row_idx: int,
        n_cols: int,
        header_notes: Dict[str, str],
        *,
        width_map: Optional[Dict[str, float]] = None,
        freeze_panes: Optional[str] = None,
        autofilter: bool = False,
    ) -> None:
        """Add consistent header comments and simple usability affordances."""
        from openpyxl.styles import Alignment
        from openpyxl.utils import get_column_letter

        if freeze_panes:
            ws.freeze_panes = freeze_panes
        if autofilter and n_cols > 0:
            ws.auto_filter.ref = f"A{row_idx}:{get_column_letter(n_cols)}{row_idx}"
        if width_map:
            for col_letter, width in width_map.items():
                ws.column_dimensions[col_letter].width = width

        for col_idx in range(1, n_cols + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            header = str(cell.value or "").strip()
            cls._set_excel_comment(cell, header_notes.get(header))
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        if row_idx not in ws.row_dimensions:
            ws.row_dimensions[row_idx].height = 30
        else:
            ws.row_dimensions[row_idx].height = max(ws.row_dimensions[row_idx].height or 0, 30)

    @classmethod
    def _annotate_venue_estimator_tab(cls, ws, n_cols: int) -> None:
        """Add operator-facing comments to the Venue-Estimator header row."""
        cls._annotate_header_row(
            ws,
            1,
            n_cols,
            cls._VENUE_ESTIMATOR_HEADER_NOTES,
            width_map={
                "A": 26,
                "B": 16,
                "C": 18,
                "D": 20,
                "E": 18,
                "F": 18,
                "G": 18,
                "H": 12,
                "I": 16,
                "J": 12,
                "K": 12,
                "L": 12,
                "M": 12,
                "N": 16,
                "O": 16,
                "P": 20,
            },
            freeze_panes="A2",
            autofilter=True,
        )

    @classmethod
    def _annotate_pod_divisions_tab(cls, ws, n_cols: int) -> None:
        """Add operator-facing Excel comments and light usability affordances."""
        cls._annotate_header_row(
            ws,
            1,
            n_cols,
            cls._POD_DIVISION_HEADER_NOTES,
            width_map={
                "A": 20,
                "B": 16,
                "C": 14,
                "D": 14,
                "E": 18,
                "F": 16,
                "G": 16,
                "H": 17,
                "I": 18,
                "J": 14,
                "K": 16,
                "L": 24,
            },
            freeze_panes="A2",
            autofilter=True,
        )

    @classmethod
    def _annotate_pod_entries_review_tab(cls, ws, n_cols: int) -> None:
        """Add operator-facing comments to the Pod-Entries-Review header row."""
        cls._annotate_header_row(
            ws,
            1,
            n_cols,
            cls._POD_ENTRY_HEADER_NOTES,
            width_map={
                "A": 10,
                "B": 20,
                "C": 20,
                "D": 22,
                "E": 22,
                "F": 18,
                "G": 12,
                "H": 18,
                "I": 16,
                "J": 36,
            },
            freeze_panes="A2",
            autofilter=True,
        )

    @classmethod
    def _annotate_pool_assignment_tab(cls, ws, n_cols: int) -> None:
        """Add operator-facing comments to the Pool-Assignment header row."""
        cls._annotate_header_row(
            ws,
            1,
            n_cols,
            cls._POOL_ASSIGNMENT_HEADER_NOTES,
            width_map={
                "A": 24,
                "B": 14,
                "C": 12,
                "D": 14,
                "E": 16,
                "F": 18,
                "G": 12,
                "H": 12,
                "I": 10,
                "J": 18,
                "K": 12,
                "L": 10,
                "M": 10,
                "N": 18,
                "O": 28,
            },
            freeze_panes="A2",
            autofilter=True,
        )

    @classmethod
    def _write_pool_assignment_tab(
        cls,
        ws,
        pool_assignment_rows: List[Dict[str, Any]],
    ) -> None:
        """Write the editable Pool-Assignment planning tab."""
        columns = cls._POOL_ASSIGNMENT_COLUMNS
        ws.append(columns)
        for row in pool_assignment_rows:
            values = []
            for column in columns:
                value = row.get(column)
                if column == "Seed" and value in (None, 0):
                    value = ""
                values.append(value)
            ws.append(values)

        cls._annotate_pool_assignment_tab(ws, len(columns))

    def refresh_pool_assignments(
        self,
        workbook_path: Path,
        output_path: Optional[Path] = None,
        sidecar_path: Optional[Path] = None,
    ) -> List[Dict[str, Any]]:
        """Refresh Pool-Assignment rows from an edited workbook and persist them."""
        from openpyxl import load_workbook

        workbook_path = Path(workbook_path)
        output_path = Path(output_path) if output_path else workbook_path
        effective_sidecar_path = (
            Path(sidecar_path)
            if sidecar_path is not None
            else self._pool_assignments_sidecar_path(output_path.parent)
        )

        sheet_rows = self._read_xlsx_sheet_rows(workbook_path, "Pool-Assignment")
        if not sheet_rows:
            raise ValueError(
                f"Workbook '{workbook_path}' has no usable Pool-Assignment sheet."
            )

        normalized_rows: List[Dict[str, Any]] = []
        for row in sheet_rows:
            event_name = str(row.get("Event") or "").strip()
            team_id = str(row.get("Team ID") or "").strip()
            if not event_name or not team_id:
                continue
            normalized_rows.append({
                "Event": event_name,
                "Church Team": str(row.get("Church Team") or "").strip(),
                "Team Order": str(row.get("Team Order") or "").strip(),
                "Team ID": team_id,
                "Team Label": str(row.get("Team Label") or team_id).strip(),
                "Team Source": str(row.get("Team Source") or "").strip(),
                "Roster Count": self._positive_int_or_none(row.get("Roster Count")) or 0,
                "Min Team Size": self._positive_int_or_none(row.get("Min Team Size")) or 0,
                "Seed": self._normalize_pool_seed(row.get("Seed")),
                "Random Draw Order": self._positive_int_or_none(row.get("Random Draw Order")),
                "Draw Position": self._positive_int_or_none(row.get("Draw Position")),
                "Pool ID": str(row.get("Pool ID") or "").strip(),
                "Pool Slot": str(row.get("Pool Slot") or "").strip(),
                "Assignment Basis": str(row.get("Assignment Basis") or "").strip(),
                "Notes": str(row.get("Notes") or "").strip(),
            })

        refreshed_rows = self._apply_pool_assignments_to_rows(normalized_rows)
        self._write_pool_assignment_state(effective_sidecar_path, refreshed_rows)

        wb = load_workbook(workbook_path)
        if "Pool-Assignment" not in wb.sheetnames:
            raise ValueError(
                f"Workbook '{workbook_path}' does not contain a Pool-Assignment sheet."
            )

        sheet_index = wb.sheetnames.index("Pool-Assignment")
        wb.remove(wb["Pool-Assignment"])
        ws = wb.create_sheet(title="Pool-Assignment", index=sheet_index)
        self._write_pool_assignment_tab(ws, refreshed_rows)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(output_path)
        logger.info(
            f"Pool-Assignment tab refreshed: {len(refreshed_rows)} rows -> {output_path}"
        )
        logger.info(f"Pool-assignment sidecar written to: {effective_sidecar_path}")
        return refreshed_rows

    @classmethod
    def _write_schedule_input_tab(cls, ws, schedule_input: Dict[str, Any]) -> None:
        """Write Schedule-Input tab with Games, Resources, and Playoff-Slots sections."""
        from openpyxl.styles import PatternFill, Font, Alignment
        from openpyxl.utils import get_column_letter

        hdr_fill = PatternFill(fgColor=SCHEDULE_SKETCH_COLOR_HEADER, fill_type="solid")
        hdr_font = Font(bold=True, color="FFFFFF")
        sec_fill = PatternFill(fgColor=SCHEDULE_SKETCH_COLOR_SECTION, fill_type="solid")
        sec_font = Font(bold=True)

        game_cols = [
            "game_id", "event", "stage", "pool_id", "round",
            "team_a_id", "team_b_id", "team_c_id", "duration_minutes",
            "resource_type", "earliest_slot", "latest_slot",
        ]
        resource_cols = [
            "resource_id", "resource_type", "label", "day",
            "open_time", "close_time", "slot_minutes", "exclusive_group",
        ]
        playoff_slot_cols = ["game_id", "event", "stage", "resource_id", "slot"]
        precedence_cols = ["before_game_id", "after_game_id", "min_gap_slots"]

        current_row = 1

        # Meta row
        ws.cell(row=current_row, column=1, value="generated_at").font = sec_font
        ws.cell(row=current_row, column=2, value=schedule_input["generated_at"])
        ws.cell(
            row=current_row, column=3,
            value=f"Games: {schedule_input['game_count']}  Resources: {schedule_input['resource_count']}",
        )
        current_row += 2

        def _write_section(
            title: str,
            cols: List[str],
            rows: List[Dict],
            header_notes: Dict[str, str],
            section_note: str,
        ) -> None:
            nonlocal current_row
            sec_cell = ws.cell(row=current_row, column=1, value=title)
            sec_cell.fill = sec_fill
            sec_cell.font = sec_font
            cls._set_excel_comment(sec_cell, section_note)
            current_row += 1
            for c_idx, col in enumerate(cols, start=1):
                cell = ws.cell(row=current_row, column=c_idx, value=col)
                cell.fill = hdr_fill
                cell.font = hdr_font
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                note = header_notes.get(col)
                if title == "GYM-MODES" and not note and col != "gym_name":
                    note = (
                        f"Maximum concurrent {col} resources this gym can provide when allocated "
                        "to that mode."
                    )
                cls._set_excel_comment(cell, note)
            ws.row_dimensions[current_row].height = max(ws.row_dimensions[current_row].height or 0, 30)
            current_row += 1
            for data_row in rows:
                for c_idx, col in enumerate(cols, start=1):
                    ws.cell(row=current_row, column=c_idx, value=data_row.get(col))
                current_row += 1
            current_row += 1  # blank separator

        playoff_slots = schedule_input.get("playoff_slots", [])
        playoff_note_rows = (
            playoff_slots if playoff_slots
            else [{"game_id": "No playoff slots loaded — add Playoff-Slots tab to venue_input.xlsx"}]
        )

        gym_modes = schedule_input.get("gym_modes", {})
        gym_mode_rtypes = sorted({rt for caps in gym_modes.values() for rt in caps})
        gym_mode_cols = ["gym_name", *gym_mode_rtypes]
        gym_mode_rows = (
            [{"gym_name": name, **caps} for name, caps in sorted(gym_modes.items())]
            if gym_modes
            else [{"gym_name": "No Gym-Modes tab loaded — add Gym-Modes tab to venue_input.xlsx"}]
        )

        cls._set_excel_comment(
            ws.cell(row=1, column=1),
            "Timestamp when schedule_input.json was generated."
        )
        cls._set_excel_comment(
            ws.cell(row=1, column=3),
            "Quick counts of total games and resources in this schedule-input snapshot."
        )

        _write_section(
            "GAMES",
            game_cols,
            schedule_input["games"],
            cls._SCHEDULE_INPUT_GAME_HEADER_NOTES,
            "Game rows the Layer 2 solver must place into resource slots.",
        )
        _write_section(
            "RESOURCES",
            resource_cols,
            schedule_input["resources"],
            cls._SCHEDULE_INPUT_RESOURCE_HEADER_NOTES,
            "Resource rows available to the Layer 2 solver.",
        )
        _write_section(
            "PLAYOFF-SLOTS",
            playoff_slot_cols,
            playoff_note_rows,
            cls._SCHEDULE_INPUT_PLAYOFF_HEADER_NOTES,
            "Optional fixed-slot playoff constraints loaded from the Playoff-Slots tab in venue_input.xlsx.",
        )
        _write_section(
            "PRECEDENCE",
            precedence_cols,
            schedule_input.get("precedence", []),
            cls._SCHEDULE_INPUT_PRECEDENCE_HEADER_NOTES,
            "Optional ordering constraints between generated games. The after_game_id "
            "must start at least min_gap_slots after before_game_id.",
        )
        _write_section(
            "GYM-MODES",
            gym_mode_cols,
            gym_mode_rows,
            {"gym_name": "Venue block / gym name from the Gym-Modes sheet."},
            "Stage-A gym capability matrix showing which sport modes each grouped gym can host.",
        )

        # Column widths
        col_widths = [20, 30, 10, 10, 8, 16, 16, 16, 18, 22, 14, 12]
        for i, w in enumerate(col_widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A4"

    @classmethod
    def _write_gym_allocation_tab(cls, ws, gym_allocation: Optional[Dict[str, Any]]) -> None:
        """Write the Gym-Allocation tab summarising the Stage-A allocator output."""
        from openpyxl.styles import PatternFill, Font, Alignment
        from openpyxl.utils import get_column_letter

        hdr_fill = PatternFill(fgColor=SCHEDULE_SKETCH_COLOR_HEADER, fill_type="solid")
        hdr_font = Font(bold=True, color="FFFFFF")
        sec_fill = PatternFill(fgColor=SCHEDULE_SKETCH_COLOR_SECTION, fill_type="solid")
        sec_font = Font(bold=True)
        cur_row = [1]  # mutable so nested fn can advance it

        def _hrow(label: str) -> None:
            cell = ws.cell(row=cur_row[0], column=1, value=label)
            cell.fill = sec_fill
            cell.font = sec_font
            cur_row[0] += 1

        def _header_row(cols: List[str]) -> None:
            for c_idx, col in enumerate(cols, start=1):
                cell = ws.cell(row=cur_row[0], column=c_idx, value=col)
                cell.fill = hdr_fill
                cell.font = hdr_font
                cell.alignment = Alignment(horizontal="center")
            cur_row[0] += 1

        def _data_row(cols: List[str], data: Dict) -> None:
            for c_idx, col in enumerate(cols, start=1):
                ws.cell(row=cur_row[0], column=c_idx, value=data.get(col))
            cur_row[0] += 1

        source = gym_allocation.get("source") if gym_allocation else None
        if not gym_allocation or source in ("fallback", "direct_venue_input"):
            if not gym_allocation:
                message = "Gym allocation data not available."
            elif source == "fallback":
                message = (
                    "Gym allocation not run — no Gym-Modes tab or no venue blocks with "
                    "Exclusive Venue Group found in venue_input.xlsx.  "
                    f"Fallback: {gym_allocation.get('gym_court_scenario', '?')} courts per session "
                    "(SCHEDULE_SOLVER_GYM_COURTS)."
                )
            elif gym_allocation.get("reason") == "grouped_rows_without_gym_modes":
                message = (
                    "Gym allocation not run — Venue-Input contains Exclusive Venue Group rows "
                    "but no Gym-Modes tab. Using Venue-Input rows directly, so mutual exclusivity "
                    "is not enforced."
                )
            elif gym_allocation.get("reason") == "gym_modes_without_grouped_rows":
                message = (
                    "Gym allocation not run — Gym-Modes tab is present but no Exclusive Venue "
                    "Group rows were found. Using Venue-Input rows directly."
                )
            else:
                message = "Gym allocation not run — using Venue-Input rows directly."
            ws.cell(
                row=1, column=1,
                value=message,
            )
            cls._set_excel_comment(
                ws.cell(row=1, column=1),
                "This tab only shows detailed allocation tables when grouped gym rows and Gym-Modes data are available."
            )
            ws.column_dimensions["A"].width = 80
            return

        source = gym_allocation.get("source", "unknown")
        ws.cell(row=cur_row[0], column=1, value=f"Source: {source}").font = sec_font
        ws.cell(row=cur_row[0], column=2, value=f"Mode switches: {gym_allocation.get('switch_count', '?')}")
        cls._set_excel_comment(
            ws.cell(row=cur_row[0], column=1),
            "Where this allocation summary came from. allocator means Stage-A Gym-Modes allocation was used."
        )
        cls._set_excel_comment(
            ws.cell(row=cur_row[0], column=2),
            "How many times the chosen gym mode switches between adjacent grouped venue blocks."
        )
        cur_row[0] += 2

        # Decisions
        _hrow("ALLOCATION DECISIONS")
        dec_cols = ["gym_name", "day", "open_time", "close_time", "mode", "courts", "slot_minutes"]
        _header_row(dec_cols)
        for idx, col in enumerate(dec_cols, start=1):
            cls._set_excel_comment(
                ws.cell(row=cur_row[0] - 1, column=idx),
                cls._GYM_ALLOCATION_DECISION_HEADER_NOTES.get(col),
            )
        ws.row_dimensions[cur_row[0] - 1].height = 30
        for dec in gym_allocation.get("decisions", []):
            _data_row(dec_cols, dec)
        cur_row[0] += 1

        # Demand vs supply
        _hrow("MODE DEMAND vs SUPPLY")
        ds_cols = ["mode", "demand", "supply", "shortfall"]
        _header_row(ds_cols)
        for idx, col in enumerate(ds_cols, start=1):
            cls._set_excel_comment(
                ws.cell(row=cur_row[0] - 1, column=idx),
                cls._GYM_ALLOCATION_SUPPLY_HEADER_NOTES.get(col),
            )
        ws.row_dimensions[cur_row[0] - 1].height = 30
        demand = gym_allocation.get("mode_demand", {})
        supply = gym_allocation.get("mode_supply", {})
        shortfall = gym_allocation.get("mode_shortfall", {})
        for mode in sorted(demand):
            _data_row(ds_cols, {
                "mode":      mode,
                "demand":    demand.get(mode, 0),
                "supply":    supply.get(mode, 0),
                "shortfall": shortfall.get(mode, 0),
            })

        col_widths = [22, 8, 10, 10, 22, 8, 14, 10, 10, 10]
        for i, w in enumerate(col_widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A4"

    # ── Pool planning ─────────────────────────────────────────────────────────

    @staticmethod
    def _build_scenario_schedule(
        n_courts: int,
        pool_queues: List[List[str]],
        early_playoff_queues: List[List[str]],
        final_queues: List[List[str]],
        n_sat: int,
        n_sun: int,
    ) -> List[List[List[str]]]:
        """
        Build a 4-session court schedule for a given number of courts.

        Returns a list of 4 session grids:
            grids[0] = 1st Saturday  (n_sat time slots)
            grids[1] = 1st Sunday    (n_sun time slots)
            grids[2] = 2nd Saturday  (n_sat time slots)
            grids[3] = 2nd Sunday    (n_sun time slots)
        Each grid is grids[session][time_slot][court_index] = game_id or "".

        ── Court allocation ──────────────────────────────────────────────────
        Courts are divided into contiguous "primary blocks", one per sport,
        allocated proportionally.  Remainder courts go to the first sport(s)
        (i.e., Basketball gets an extra court before Volleyball does).

        Example with 5 courts and 3 sports:
            base = 5 // 3 = 1, extras = 5 % 3 = 2
            BBM → courts [0, 1]   (base 1 + 1 extra)
            VBM → courts [2, 3]   (base 1 + 1 extra)
            VBW → courts [4]      (base 1, no extra)

        Rationale: keeps each court dedicated to one sport type, so no
        net-height adjustment or equipment swap is needed mid-court.

        ── Phase 1 — Pool fill (sat1 → sun1 → sat2) ─────────────────────────
        For every time slot, courts are visited left-to-right (court 0, 1, …):

        • If the primary sport for that court still has pool games left,
          place the next game there (primary-first rule).
        • If the primary sport has finished its pool games, the court is
          idle.  The idle court is given to whichever sport currently has
          the most remaining pool games (greedy-most-needy rule).

        Effect in 5-court scenario (equal teams, 12 pool games each):
            Slots 0–5   : BBM fills courts 0-1, VBM fills courts 2-3,
                          VBW fills court 4  (all 3 sports running in parallel)
            Slot 6+     : BBM and VBM are done; their 4 courts become idle.
                          VBW still has 6 games → claims all 4 idle courts
                          plus its own, running 5 VBW games simultaneously.
                          VBW finishes at slot 7 (≈15:00) instead of slot 11
                          (≈19:00) — the whole church leaves ~4 hours earlier.

        Pool games never spill into sun2; that session is reserved for finals.

        ── Phase 2 — Early playoffs (QF + Semis) on sat2 ───────────────────
        After pool fill, each sport's empty cells in sat2 are collected in
        (time_slot, court) order.  Early-round playoff games (QF-1…4 if 8
        playoff teams, Semi-1 and Semi-2 otherwise) are placed there.

        Playoffs are placed on the sport's primary courts only — no court
        sharing — so the same nets and equipment remain in place.

        ── Phase 3 — Finals on sun2 ─────────────────────────────────────────
        Final and 3rd-place games are placed on each sport's empty cells in
        sun2, again primary courts only.  This guarantees that championship
        games always fall on the last day of the festival, regardless of how
        pool play distributes across the earlier sessions.

        ── Changing the algorithm ───────────────────────────────────────────
        • Court count scenarios: edit SCHEDULE_SKETCH_N_COURTS in config.py.
        • Session hours: edit SCHEDULE_SKETCH_SATURDAY_START / LAST_GAME and
          SCHEDULE_SKETCH_SUNDAY_START / LAST_GAME in config.py.
        • Court allocation order: the sport order in sport_defs inside
          _write_court_schedule_sketch controls which sport gets extra courts
          (earlier in the list = higher priority for extras).
        • Pool overflow policy: replace the greedy-most-needy rule (the
          `max(range(n_sports), key=lambda i: len(pool_remaining[i]))` line)
          with any other priority function — e.g., fixed sport priority,
          round-robin, or "same-sport block only" to revert to strict blocks.
        • Playoff session assignment: swap early_playoff_queues and
          final_queues arguments, or add a third category (e.g. Semis on
          sun1) by adding a new fill phase following the same pattern.
        """
        n_sports = len(pool_queues)
        n_slots = [n_sat, n_sun, n_sat, n_sun]
        grids: List[List[List[str]]] = [
            [[""] * n_courts for _ in range(n)] for n in n_slots
        ]

        # Court block allocation
        base = n_courts // n_sports
        extras = n_courts % n_sports
        court_blocks: List[List[int]] = []
        cur = 0
        for i in range(n_sports):
            k = base + (1 if i < extras else 0)
            court_blocks.append(list(range(cur, cur + k)))
            cur += k

        court_to_primary = {c: i for i, courts in enumerate(court_blocks) for c in courts}

        # Phase 1: pool fill — primary-first, then greedy-most-needy for idle courts
        pool_remaining = [deque(q) for q in pool_queues]
        for sess_idx in range(3):  # sat1, sun1, sat2
            for t in range(n_slots[sess_idx]):
                for c in range(n_courts):
                    primary = court_to_primary[c]
                    if pool_remaining[primary]:
                        grids[sess_idx][t][c] = pool_remaining[primary].popleft()
                    else:
                        most_needy = max(range(n_sports), key=lambda i: len(pool_remaining[i]))
                        if pool_remaining[most_needy]:
                            grids[sess_idx][t][c] = pool_remaining[most_needy].popleft()

        # Phase 2: early playoffs (QF + Semi) on primary courts in sat2
        for early_q, courts in zip(early_playoff_queues, court_blocks):
            cells = [
                (2, t, c)
                for t in range(n_sat)
                for c in courts
                if not grids[2][t][c]
            ]
            for i, game_id in enumerate(early_q):
                if i < len(cells):
                    s, t, c = cells[i]
                    grids[s][t][c] = game_id

        # Phase 3: finals (Final + 3rd) on primary courts in sun2
        for final_q, courts in zip(final_queues, court_blocks):
            cells = [
                (3, t, c)
                for t in range(n_sun)
                for c in courts
                if not grids[3][t][c]
            ]
            for i, game_id in enumerate(final_q):
                if i < len(cells):
                    s, t, c = cells[i]
                    grids[s][t][c] = game_id

        return grids

    @staticmethod
    def _two_game_pool_sizes(n_teams: int) -> List[int]:
        """Return deterministic pool sizes for the normalized 2-game/team policy."""
        if n_teams < 2:
            return []
        if n_teams in (2, 3, 4, 5):
            return [n_teams]

        for n_fours in range(n_teams // 4, -1, -1):
            remainder = n_teams - (4 * n_fours)
            if remainder >= 0 and remainder % 3 == 0:
                return ([4] * n_fours) + ([3] * (remainder // 3))

        raise ValueError(f"Unable to build normalized 2-game pools for n_teams={n_teams}")

    @staticmethod
    def _summarize_pool_policy(n_teams: int, gpg: int) -> Dict[str, Any]:
        """Return operator-facing metadata for the current pool-generation policy."""
        if n_teams < 2:
            return {
                "target_pool_games_per_team": gpg,
                "actual_pool_games_per_team": 0,
                "pool_composition": "",
                "bye_slots": 0,
                "actual_pool_games": 0,
            }

        if gpg != 2:
            actual_pool_games = len(
                ScheduleWorkbookBuilder._make_legacy_pool_game_pairs("_", n_teams, gpg)
            )
            return {
                "target_pool_games_per_team": gpg,
                "actual_pool_games_per_team": None,
                "pool_composition": "",
                "bye_slots": 0,
                "actual_pool_games": actual_pool_games,
            }

        pool_sizes = ScheduleWorkbookBuilder._two_game_pool_sizes(n_teams)
        games_by_pool_size = {2: 1, 3: 3, 4: 4, 5: 5}
        return {
            "target_pool_games_per_team": gpg,
            "actual_pool_games_per_team": 1 if n_teams == 2 else 2,
            "pool_composition": " + ".join(str(size) for size in pool_sizes),
            "bye_slots": 5 * pool_sizes.count(5),
            "actual_pool_games": sum(games_by_pool_size[size] for size in pool_sizes),
        }

    @staticmethod
    def _make_legacy_pool_game_pairs(
        prefix: str, n_teams: int, gpg: int
    ) -> List[Tuple[str, str, str]]:
        """Legacy balanced round-robin fallback for non-default pool-game targets."""
        if n_teams < 2:
            return []

        target_pool_size = max(2, gpg + 1)
        n_pools = max(1, n_teams // target_pool_size)

        pools: List[List[int]] = [[] for _ in range(n_pools)]
        for i in range(n_teams):
            pools[i % n_pools].append(i + 1)

        team_id: Dict[int, str] = {}
        for p_idx, pool_teams in enumerate(pools, start=1):
            for t_idx, team_num in enumerate(pool_teams, start=1):
                team_id[team_num] = f"{prefix}-P{p_idx}-T{t_idx}"

        pairs: List[Tuple[str, str, str]] = []
        for p_idx, pool_teams in enumerate(pools, start=1):
            pool_id = f"P{p_idx}"
            for i in range(len(pool_teams)):
                for j in range(i + 1, len(pool_teams)):
                    pairs.append((
                        team_id[pool_teams[i]],
                        team_id[pool_teams[j]],
                        pool_id,
                    ))
        return pairs

    @staticmethod
    def _make_pool_game_pairs(
        prefix: str, n_teams: int, gpg: int
    ) -> List[Tuple[str, str, str]]:
        """Return (team_a_id, team_b_id, pool_id) tuples for pool-play games.

        Current Layer 1 planning normalizes team sports around exact two-game
        pool play:
        - 2 teams  -> one direct match
        - 3 teams  -> 3-team round robin
        - 4 teams  -> 4-match matrix (every team plays exactly twice)
        - 5 teams  -> 5-match cycle (every team plays exactly twice)
        - 6+ teams -> deterministic composition of 3-team and 4-team pools

        If a non-default target is requested, fall back to the older balanced
        round-robin pool builder so the helper remains backwards-compatible for
        tests and historical data exploration.

        Team IDs are stable planning placeholders: {prefix}-P{pool}-T{slot}.
        The same placeholder is reused across all games involving that team,
        allowing the solver to enforce team-overlap and min-rest constraints.
        """
        if n_teams < 2:
            return []
        if gpg != 2:
            return ScheduleWorkbookBuilder._make_legacy_pool_game_pairs(prefix, n_teams, gpg)

        template_pairs = {
            2: [(0, 1)],
            3: [(0, 1), (0, 2), (1, 2)],
            4: [(0, 1), (2, 3), (0, 2), (1, 3)],
            5: [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0)],
        }
        pool_sizes = ScheduleWorkbookBuilder._two_game_pool_sizes(n_teams)

        pairs: List[Tuple[str, str, str]] = []
        for p_idx, pool_size in enumerate(pool_sizes, start=1):
            pool_id = f"P{p_idx}"
            pool_team_ids = [
                f"{prefix}-P{p_idx}-T{slot_idx}"
                for slot_idx in range(1, pool_size + 1)
            ]
            for team_a_idx, team_b_idx in template_pairs[pool_size]:
                pairs.append((
                    pool_team_ids[team_a_idx],
                    pool_team_ids[team_b_idx],
                    pool_id,
                ))
        return pairs

    @staticmethod
    def _make_playoff_ids(
        prefix: str, playoff_teams: int, include_third: bool
    ) -> Tuple[List[str], List[str]]:
        """Return (early_ids, final_ids) split by which weekend they belong to.

        early_ids  — QF + Semi games, scheduled on 2nd Saturday.
        final_ids  — Final (+ optional 3rd-place), scheduled on 2nd Sunday.

        Bracket size is determined by playoff_teams (from COURT_ESTIMATE_PLAYOFF_RULES):
            0 teams  → no playoff games
            4 teams  → Semi-1, Semi-2 | Final [+ 3rd]
            8 teams  → QF-1…4, Semi-1, Semi-2 | Final [+ 3rd]

        To add a new bracket size (e.g. 16 teams with quarter-finals already
        called Round-of-16), extend the if/elif chain here and add matching
        rows to COURT_ESTIMATE_PLAYOFF_RULES in config.py.
        """
        early_ids: List[str] = []
        if playoff_teams >= 8:
            for i in range(1, 5):
                early_ids.append(f"{prefix}-QF-{i}")
            early_ids.extend([f"{prefix}-Semi-1", f"{prefix}-Semi-2"])
        elif playoff_teams >= 4:
            early_ids.extend([f"{prefix}-Semi-1", f"{prefix}-Semi-2"])

        final_ids: List[str] = []
        if playoff_teams >= 4:
            final_ids.append(f"{prefix}-Final")
            if include_third:
                final_ids.append(f"{prefix}-3rd")
        return early_ids, final_ids

    # ── Court-schedule sketch ────────────────────────────────────────────────

    def _write_court_schedule_sketch(
        self, ws, roster_rows: List[Dict[str, Any]]
    ) -> None:
        """
        Write the Court-Schedule-Sketch tab.

        Three scenarios (3, 4, 5 courts) are rendered side-by-side on one
        worksheet, separated by an empty column.  Game IDs are sequential
        placeholders (BBM01…, VBM01…, VBW01…); no actual team assignments
        or conflict enforcement is performed here.  This is an Excel-only
        planning artifact — no data is written to WordPress sf_schedules.
        """
        from openpyxl.styles import PatternFill, Font, Alignment

        mpg = COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME
        include_third = COURT_ESTIMATE_INCLUDE_THIRD_PLACE_GAME

        # Sports covered by this sketch (shared court type: basketball / volleyball)
        sport_defs = [
            (SPORT_TYPE["BASKETBALL"],       "BBM", SCHEDULE_SKETCH_COLOR_BASKETBALL),
            (SPORT_TYPE["VOLLEYBALL_MEN"],   "VBM", SCHEDULE_SKETCH_COLOR_VB_MEN),
            (SPORT_TYPE["VOLLEYBALL_WOMEN"], "VBW", SCHEDULE_SKETCH_COLOR_VB_WOMEN),
        ]

        # --- Compute game IDs per sport (per-sport pool games per team) ---
        sport_meta: Dict[str, Dict] = {}
        for event_name, prefix, color in sport_defs:
            min_sz = self._get_min_team_size(event_name)
            counts = self._count_estimating_teams(roster_rows, event_name, min_sz)
            n_teams = counts["n_estimating"] if counts["n_estimating"] >= 2 else 8
            gpg = COURT_ESTIMATE_POOL_GAMES_PER_TEAM.get(event_name, COURT_ESTIMATE_DEFAULT_POOL_GAMES_PER_TEAM)
            pool_plan = self._summarize_pool_policy(n_teams, gpg)
            actual = len(self._make_pool_game_pairs("_", n_teams, gpg))
            s = self._compute_court_slots(
                n_teams,
                mpg,
                pool_games_per_team=gpg,
                actual_pool_games=actual,
            )
            early_ids, final_ids = self._make_playoff_ids(
                prefix, s["playoff_teams"], include_third
            )
            sport_meta[event_name] = {
                "prefix": prefix,
                "color": color,
                "n_teams": n_teams,
                "target_pool_gpg": pool_plan["target_pool_games_per_team"],
                "actual_pool_gpg": pool_plan["actual_pool_games_per_team"],
                "pool_composition": pool_plan["pool_composition"],
                "pool_ids":   [f"{prefix}-{i:02d}" for i in range(1, s["pool_slots"] + 1)],
                "early_ids":  early_ids,   # QF + Semi → 2nd Saturday
                "final_ids":  final_ids,   # Final + 3rd → 2nd Sunday
            }

        # --- Per-sport game queues (pool overflow + dedicated playoff courts) ---
        pool_queues_by_sport          = [sport_meta[ev]["pool_ids"]  for ev, _, _ in sport_defs]
        early_playoff_queues_by_sport = [sport_meta[ev]["early_ids"] for ev, _, _ in sport_defs]
        final_queues_by_sport         = [sport_meta[ev]["final_ids"] for ev, _, _ in sport_defs]

        # --- Time slot helpers ---
        n_sat = SCHEDULE_SKETCH_SATURDAY_LAST_GAME - SCHEDULE_SKETCH_SATURDAY_START + 1
        n_sun = SCHEDULE_SKETCH_SUNDAY_LAST_GAME - SCHEDULE_SKETCH_SUNDAY_START + 1
        sat_times = [
            f"{h:02d}:00"
            for h in range(SCHEDULE_SKETCH_SATURDAY_START, SCHEDULE_SKETCH_SATURDAY_LAST_GAME + 1)
        ]
        sun_times = [
            f"{h:02d}:00"
            for h in range(SCHEDULE_SKETCH_SUNDAY_START, SCHEDULE_SKETCH_SUNDAY_LAST_GAME + 1)
        ]
        sessions = [
            ("1st Saturday", sat_times),
            ("1st Sunday",   sun_times),
            ("2nd Saturday", sat_times),
            ("2nd Sunday",   sun_times),
        ]

        # --- Styles ---
        section_fill = PatternFill(fgColor=SCHEDULE_SKETCH_COLOR_SECTION, fill_type="solid")
        hdr_fill     = PatternFill(fgColor=SCHEDULE_SKETCH_COLOR_HEADER,  fill_type="solid")
        hdr_font     = Font(bold=True, color="FFFFFF")
        bold_font    = Font(bold=True)
        center       = Alignment(horizontal="center", vertical="center")
        prefix_fill  = {
            "BBM": PatternFill(fgColor=SCHEDULE_SKETCH_COLOR_BASKETBALL, fill_type="solid"),
            "VBM": PatternFill(fgColor=SCHEDULE_SKETCH_COLOR_VB_MEN,     fill_type="solid"),
            "VBW": PatternFill(fgColor=SCHEDULE_SKETCH_COLOR_VB_WOMEN,   fill_type="solid"),
        }

        # --- Column layout ---
        # Scenario A (3 cts): col 1=Time, 2-4=Courts → 4 cols; gap col 5
        # Scenario B (4 cts): col 6=Time, 7-10=Courts → 5 cols; gap col 11
        # Scenario C (5 cts): col 12=Time, 13-17=Courts → 6 cols
        n_courts_list = SCHEDULE_SKETCH_N_COURTS
        scenario_starts: List[int] = []
        cur_col = 1
        for n in n_courts_list:
            scenario_starts.append(cur_col)
            cur_col += (1 + n) + 1  # time col + court cols + gap

        INPUTS_ROW      = 1
        SCENARIO_HDR_ROW = 3
        COL_HDR_ROW     = 4
        DATA_START_ROW  = 5

        # --- Row 1: inputs summary (target/actual pool games per team) ---
        ws.cell(row=INPUTS_ROW, column=1, value="Inputs:").font = bold_font
        self._set_excel_comment(
            ws.cell(row=INPUTS_ROW, column=1),
            "Planning assumptions used to generate this Layer 1 sketch, including pool-game targets and minutes per game."
        )
        col = 2
        for ev, prefix, _ in sport_defs:
            meta = sport_meta[ev]
            ws.cell(
                row=INPUTS_ROW,
                column=col,
                value=(
                    f"{prefix} pool target/actual: "
                    f"{meta['target_pool_gpg']}/{meta['actual_pool_gpg']}"
                ),
            )
            col += 3
        ws.cell(row=INPUTS_ROW, column=col,     value=f"Minutes/game: {mpg}")
        ws.cell(row=INPUTS_ROW, column=col + 3, value=f"3rd place: {'Yes' if include_third else 'No'}")

        # --- Row 2: per-sport game counts ---
        ws.cell(row=2, column=1, value="Game totals:").font = bold_font
        self._set_excel_comment(
            ws.cell(row=2, column=1),
            "High-level game totals used in this what-if sketch. These are planning placeholders, not final assignments."
        )
        col_offset = 2
        for ev, prefix, _ in sport_defs:
            meta = sport_meta[ev]
            total = len(meta["pool_ids"]) + len(meta["early_ids"]) + len(meta["final_ids"])
            label = (
                f"{prefix}: {meta['n_teams']} teams, {total} games "
                f"({len(meta['pool_ids'])} pool, pools {meta['pool_composition']})"
            )
            ws.cell(row=2, column=col_offset, value=label)
            col_offset += 5

        # --- Pre-compute per-scenario schedules ---
        scenario_grids: Dict[int, List[List[List[str]]]] = {}
        for n_courts in n_courts_list:
            scenario_grids[n_courts] = self._build_scenario_schedule(
                n_courts,
                pool_queues_by_sport,
                early_playoff_queues_by_sport,
                final_queues_by_sport,
                n_sat, n_sun,
            )

        # --- Render scenario headers and column headers ---
        for n_courts, start_col in zip(n_courts_list, scenario_starts):
            end_col = start_col + n_courts  # time col + n court cols (inclusive)
            # Scenario header
            sc_cell = ws.cell(row=SCENARIO_HDR_ROW, column=start_col, value=f"Scenario: {n_courts} Courts")
            sc_cell.font = hdr_font
            sc_cell.fill = hdr_fill
            sc_cell.alignment = center
            self._set_excel_comment(
                sc_cell,
                f"What-if sketch assuming {n_courts} simultaneous shared gym courts across Basketball, Volleyball Men, and Volleyball Women."
            )
            ws.merge_cells(
                start_row=SCENARIO_HDR_ROW, start_column=start_col,
                end_row=SCENARIO_HDR_ROW,   end_column=end_col,
            )
            # Column sub-headers
            t_cell = ws.cell(row=COL_HDR_ROW, column=start_col, value="Time")
            t_cell.font = bold_font
            self._set_excel_comment(
                t_cell,
                "Start time for the slot within the session block."
            )
            for c in range(n_courts):
                ct_cell = ws.cell(row=COL_HDR_ROW, column=start_col + 1 + c, value=f"Court {c + 1}")
                ct_cell.font = bold_font
                ct_cell.alignment = center
                self._set_excel_comment(
                    ct_cell,
                    "Placeholder court lane in this scenario. Colored BBM/VBM/VBW IDs are Layer 1 planning placeholders, not final team assignments."
                )

        # --- Render session sections and time-slot rows ---
        current_row = DATA_START_ROW
        for sess_idx, (sess_label, times) in enumerate(sessions):
            # Section header
            for n_courts, start_col in zip(n_courts_list, scenario_starts):
                end_col = start_col + n_courts
                sh_cell = ws.cell(row=current_row, column=start_col, value=sess_label)
                sh_cell.fill = section_fill
                sh_cell.font = bold_font
                sh_cell.alignment = center
                ws.merge_cells(
                    start_row=current_row, start_column=start_col,
                    end_row=current_row,   end_column=end_col,
                )
            current_row += 1

            # Time slot rows
            for t, time_str in enumerate(times):
                for n_courts, start_col in zip(n_courts_list, scenario_starts):
                    ws.cell(row=current_row, column=start_col, value=time_str)
                    grid = scenario_grids[n_courts]
                    for c in range(n_courts):
                        game_id = grid[sess_idx][t][c]
                        cell = ws.cell(row=current_row, column=start_col + 1 + c, value=game_id)
                        if game_id:
                            fill = prefix_fill.get(game_id.split("-")[0])
                            if fill:
                                cell.fill = fill
                current_row += 1

        # --- Column widths ---
        from openpyxl.utils import get_column_letter
        for n_courts, start_col in zip(n_courts_list, scenario_starts):
            ws.column_dimensions[get_column_letter(start_col)].width = 10      # Time
            for c in range(n_courts):
                ws.column_dimensions[get_column_letter(start_col + 1 + c)].width = 12  # Courts
        ws.freeze_panes = "A5"

        total_pool  = sum(len(q) for q in pool_queues_by_sport)
        total_early = sum(len(q) for q in early_playoff_queues_by_sport)
        total_final = sum(len(q) for q in final_queues_by_sport)
        logger.debug(
            f"Court-Schedule-Sketch tab: {total_pool} pool + {total_early} early-playoff "
            f"+ {total_final} finals across {len(n_courts_list)} scenarios."
        )

    # ── Pod-Resource-Estimate helpers ────────────────────────────────────────

    @staticmethod
    def _parse_hour(val) -> float:
        """Convert a cell value to a decimal hour (e.g. datetime.time(13,0) → 13.0)."""
        import datetime as _dt
        if pd.isna(val):
            return 0.0
        if isinstance(val, _dt.time):
            return val.hour + val.minute / 60.0
        if isinstance(val, str) and ":" in val:
            try:
                hour_str, minute_str = val.split(":", 1)
                return int(hour_str) + int(minute_str) / 60.0
            except ValueError:
                return 0.0
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _load_venue_input(venue_input_path: Path) -> Dict[str, int]:
        """Read venue_input.xlsx and return {resource_type: total_available_slots}.

        Each row may have Available Slots pre-computed (formula or number).
        If Available Slots is missing/zero, falls back to computing from
        Quantity, Start Time, Last Start Time, and Slot Minutes.
        Returns an empty dict if the file does not exist.
        """
        if not venue_input_path.exists():
            return {}
        try:
            df = pd.read_excel(venue_input_path, sheet_name="Venue-Input", engine="openpyxl")
        except Exception as e:
            logger.warning(f"Could not read venue input file {venue_input_path}: {e}")
            return {}

        totals: Dict[str, int] = {}
        for _, row in df.iterrows():
            resource_type = ScheduleWorkbookBuilder._clean_excel_text(row.get("Resource Type"))
            if not resource_type:
                continue
            avail = row.get("Available Slots")
            if pd.isna(avail) or not avail:
                # Formula wasn't cached — compute from component columns.
                qty       = ScheduleWorkbookBuilder._float_from_excel(row.get("Quantity"), 0)
                start     = ScheduleWorkbookBuilder._parse_hour(row.get("Start Time"))
                last_start = ScheduleWorkbookBuilder._parse_hour(row.get("Last Start Time"))
                slot_min  = ScheduleWorkbookBuilder._float_from_excel(row.get("Slot Minutes"), 1)
                if slot_min > 0 and qty > 0 and last_start >= start:
                    avail = qty * ((last_start - start) * 60 / slot_min + 1)
                else:
                    avail = 0
            totals[resource_type] = totals.get(resource_type, 0) + int(
                ScheduleWorkbookBuilder._float_from_excel(avail, 0)
            )
        logger.debug(f"Loaded venue input: {totals}")
        return totals

    @staticmethod
    def _load_available_slots_from_schedule_input(
        schedule_input: Dict[str, Any],
    ) -> Dict[str, int]:
        """Summarize total available slots per resource_type from schedule_input."""
        totals: Dict[str, int] = {}
        for res in schedule_input.get("resources", []):
            resource_type = ScheduleWorkbookBuilder._clean_excel_text(
                res.get("resource_type")
            )
            if not resource_type:
                continue
            open_time = ScheduleWorkbookBuilder._clean_excel_text(res.get("open_time"))
            close_time = ScheduleWorkbookBuilder._clean_excel_text(res.get("close_time"))
            slot_min = int(res.get("slot_minutes", 0) or 0)
            if not open_time or not close_time or slot_min <= 0:
                continue
            start = ScheduleWorkbookBuilder._parse_hour(open_time)
            close = ScheduleWorkbookBuilder._parse_hour(close_time)
            if close < start:
                continue
            available = int(((close - start) * 60 / slot_min))
            totals[resource_type] = totals.get(resource_type, 0) + max(available, 0)
        logger.debug(f"Derived availability from schedule_input resources: {totals}")
        return totals

    def _build_pod_resource_rows(
        self,
        roster_rows: List[Dict[str, Any]],
        available_by_resource: Dict[str, int],
    ) -> List[Dict[str, Any]]:
        """Build Pod-Resource-Estimate output rows.

        Required slots use single-elimination: entries - 1
        (doubles counted as complete pairs, same as _count_racquet_entries).
        """
        rows = []
        for sport_name in COURT_ESTIMATE_RACQUET_EVENTS:
            counts = self._count_racquet_entries(roster_rows, sport_name)
            n = counts["n_estimating"]
            resource_type = POD_RESOURCE_EVENT_TYPE.get(sport_name, "")
            required = max(0, n - 1)
            available = available_by_resource.get(resource_type, 0)
            surplus = available - required
            if not available_by_resource:
                fit_status = "No venue data"
            elif surplus >= 0:
                fit_status = "Green"
            elif surplus >= -POD_FIT_YELLOW_MAX:
                fit_status = "Yellow"
            else:
                fit_status = "Red"
            rows.append({
                "Event":              sport_name,
                "Resource Type":      resource_type,
                "Entries / Teams":    n,
                "Required Slots":     required,
                "Available Slots":    available,
                "Surplus / Shortage": surplus,
                "Fit Status":         fit_status,
            })
        return rows

    @classmethod
    def _write_pod_resource_estimate(
        self,
        ws,
        pod_rows: List[Dict[str, Any]],
        available_by_resource: Dict[str, int],
        availability_source_label: str = VENUE_INPUT_FILENAME,
    ) -> None:
        """Write Pod-Resource-Estimate tab content with colour-coded Fit Status."""
        from openpyxl.styles import PatternFill, Font, Alignment

        cols = ["Event", "Resource Type", "Entries / Teams",
                "Required Slots", "Available Slots", "Surplus / Shortage", "Fit Status"]

        header_fill = PatternFill("solid", fgColor=SCHEDULE_SKETCH_COLOR_HEADER)
        header_font = Font(color="FFFFFF", bold=True)

        # Header row
        for c_idx, col in enumerate(cols, start=1):
            cell = ws.cell(row=1, column=c_idx, value=col)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")
            self._set_excel_comment(cell, self._POD_RESOURCE_HEADER_NOTES.get(col))
        ws.row_dimensions[1].height = 30

        fit_colors = {
            "Green":  POD_FIT_COLOR_GREEN,
            "Yellow": POD_FIT_COLOR_YELLOW,
            "Red":    POD_FIT_COLOR_RED,
        }

        if not available_by_resource:
            notice = (
                "No venue input loaded — "
                f"create {VENUE_INPUT_FILENAME} from the template and re-run the export"
            )
            if availability_source_label != VENUE_INPUT_FILENAME:
                notice = f"No availability data loaded from {availability_source_label}."
            ws.cell(row=2, column=1, value=notice)
            for c_idx, col in enumerate(cols, start=1):
                row_cell = ws.cell(row=2, column=c_idx)
                if c_idx == 1:
                    row_cell.value = notice
                else:
                    row_cell.value = None

        for r_idx, row in enumerate(pod_rows, start=2):
            for c_idx, col in enumerate(cols, start=1):
                cell = ws.cell(row=r_idx, column=c_idx, value=row[col])
                if col in ("Entries / Teams", "Required Slots", "Available Slots",
                           "Surplus / Shortage"):
                    cell.alignment = Alignment(horizontal="right")
                if col == "Fit Status":
                    color = fit_colors.get(row["Fit Status"])
                    if color:
                        cell.fill = PatternFill("solid", fgColor=color)
                    cell.alignment = Alignment(horizontal="center")

        # Column widths
        ws.column_dimensions["A"].width = 26
        ws.column_dimensions["B"].width = 22
        for letter in ["C", "D", "E", "F", "G"]:
            ws.column_dimensions[letter].width = 16
        ws.freeze_panes = "A2"

        # Snapshot note
        note_row = len(pod_rows) + 3
        ws.cell(
            row=note_row, column=1,
            value=(
                f"Available slots loaded from {availability_source_label}. "
                "Required = entries − 1 (single elimination). "
                f"Green ≥ 0 | Yellow short 1–{POD_FIT_YELLOW_MAX} | Red short {POD_FIT_YELLOW_MAX + 1}+."
            ),
        )
        if availability_source_label != VENUE_INPUT_FILENAME:
            ws.cell(
                row=note_row + 1,
                column=1,
                value=(
                    f"Offline build: available slots derived from {availability_source_label}."
                ),
            )
        logger.debug(f"Pod-Resource-Estimate tab: {len(pod_rows)} rows.")

    # ── produce-schedule renderer ────────────────────────────────────────────

    @staticmethod
    def _warn_if_schedules_mismatched(
        schedule_output: Dict[str, Any],
        schedule_input: Dict[str, Any],
    ) -> bool:
        """Warn if schedule_output assignments reference game IDs absent from schedule_input.

        Returns True when the files are consistent, False when orphaned game IDs are found.
        Orphaned IDs typically mean --input and --constraint came from different runs, which
        causes produce-schedule to silently render rows with blank event/stage fields (B5).
        """
        known_ids = (
            {g["game_id"] for g in schedule_input.get("games", [])}
            | {ps["game_id"] for ps in schedule_input.get("playoff_slots", [])}
        )
        assignment_ids = {
            a["game_id"] for a in schedule_output.get("assignments", [])
        }
        orphaned = assignment_ids - known_ids
        if orphaned:
            logger.warning(
                f"{len(orphaned)} assignment game_id(s) not found in schedule_input — "
                "--input and --constraint may be from different runs. "
                "Affected rows will render with blank event/stage. "
                f"Orphaned IDs: {sorted(orphaned)}"
            )
            return False
        return True

    @staticmethod
    def _build_schedule_output_flat_rows(
        schedule_output: Dict[str, Any],
        schedule_input: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Build sorted flat-list rows for the Schedule-by-Sport tab.

        Each row joins one assignment from schedule_output with game metadata
        from schedule_input.  Rows are sorted by event → stage order → round → slot.
        """
        ScheduleWorkbookBuilder._warn_if_schedules_mismatched(schedule_output, schedule_input)
        game_meta = {g["game_id"]: g for g in schedule_input.get("games", [])}
        res_meta  = {r["resource_id"]: r for r in schedule_input.get("resources", [])}
        _STAGE_ORDER = {"Pool": 0, "R1": 1, "QF": 2, "Semi": 3, "Final": 4, "3rd": 5}
        _DAY_DISPLAY = {
            "Sat-1": "1st Sat", "Sun-1": "1st Sun",
            "Sat-2": "2nd Sat", "Sun-2": "2nd Sun",
        }
        rows: List[Dict[str, Any]] = []
        for a in schedule_output.get("assignments", []):
            gid  = a["game_id"]
            rid  = a["resource_id"]
            slot = a["slot"]
            # Fall back to the assignment dict itself for playoff games whose
            # game_id is not in schedule_input games (they carry event/stage fields).
            game = game_meta.get(gid, a)
            res  = res_meta.get(rid, {})
            time_part = slot.rsplit("-", maxsplit=1)[-1] if "-" in slot else slot
            rows.append({
                "game_id":          gid,
                "event":            game.get("event", ""),
                "stage":            game.get("stage", ""),
                "round":            game.get("round", ""),
                "team_a_id":        game.get("team_a_label", game.get("team_a_id", "")),
                "team_b_id":        game.get("team_b_label", game.get("team_b_id", "")),
                "team_c_id":        game.get("team_c_label", game.get("team_c_id", "")),
                "resource_label":   res.get("label", rid),
                "day":              _DAY_DISPLAY.get(res.get("day", ""), res.get("day", "")),
                "slot":             time_part,
                "duration_minutes": game.get("duration_minutes", ""),
            })
        rows.sort(key=lambda r: (
            r["event"],
            _STAGE_ORDER.get(str(r["stage"]), 99),
            int(r["round"]) if isinstance(r["round"], int) else 0,
            r["slot"],
        ))
        return rows

    @staticmethod
    def _write_schedule_output_report(
        filepath: Path,
        schedule_output: Dict[str, Any],
        schedule_input: Dict[str, Any],
    ) -> None:
        """Write Schedule-by-Time, Schedule-by-Sport, and Conflict-Audit tabs.

        Tab 1 — Schedule-by-Time: grid (rows = time slots, columns = courts),
          colour-coded by sport, with session sections separated by grey rows.
        Tab 2 — Schedule-by-Sport: flat list sorted by event → stage → round,
          with auto-filter and an unscheduled section when applicable.
        Tab 3 — Conflict-Audit: cross-sport shared-athlete audit rows when available.
        """
        from openpyxl import Workbook
        from openpyxl.styles import PatternFill, Font, Alignment
        from openpyxl.utils import get_column_letter

        game_meta: Dict[str, Dict[str, Any]] = {
            g["game_id"]: g for g in schedule_input.get("games", [])
        }
        res_meta: Dict[str, Dict[str, Any]] = {
            r["resource_id"]: r for r in schedule_input.get("resources", [])
        }
        assign_map: Dict[Tuple[str, str], Dict[str, Any]] = {
            (a["resource_id"], a["slot"]): game_meta.get(a["game_id"], {"game_id": a["game_id"]})
            for a in schedule_output.get("assignments", [])
        }

        solved_at     = schedule_output.get("solved_at", "")
        status        = schedule_output.get("status", "")
        n_assigned    = len(schedule_output.get("assignments", []))
        n_unscheduled = len(schedule_output.get("unscheduled", []))
        snapshot      = (
            f"Generated: {solved_at}  |  Status: {status}  |  "
            f"Scheduled: {n_assigned}  |  Unscheduled: {n_unscheduled}"
        )

        sec_fill = PatternFill(fgColor=SCHEDULE_SKETCH_COLOR_SECTION, fill_type="solid")
        hdr_fill = PatternFill(fgColor=SCHEDULE_SKETCH_COLOR_HEADER,  fill_type="solid")
        hdr_font = Font(bold=True, color="FFFFFF")
        bold_font = Font(bold=True)
        center   = Alignment(horizontal="center", vertical="center", wrap_text=True)
        left     = Alignment(horizontal="left",   vertical="center", wrap_text=True)
        red_fill = PatternFill(fgColor="FFC7CE", fill_type="solid")

        _SPORT_COLORS: Dict[str, str] = {
            SPORT_TYPE["BASKETBALL"]:       SCHEDULE_SKETCH_COLOR_BASKETBALL,
            SPORT_TYPE["VOLLEYBALL_MEN"]:   SCHEDULE_SKETCH_COLOR_VB_MEN,
            SPORT_TYPE["VOLLEYBALL_WOMEN"]: SCHEDULE_SKETCH_COLOR_VB_WOMEN,
        }
        _DAY_ORDER   = {"Sat-1": 0, "Sun-1": 1, "Sat-2": 2, "Sun-2": 3}
        _DAY_DISPLAY = {
            "Sat-1": "1st Saturday", "Sun-1": "1st Sunday",
            "Sat-2": "2nd Saturday", "Sun-2": "2nd Sunday",
        }

        def _sport_fill(event: str) -> PatternFill:
            return PatternFill(
                fgColor=_SPORT_COLORS.get(event, "EBF1DE"), fill_type="solid"
            )

        def _slot_times(res: Dict[str, Any]) -> List[str]:
            o_h, o_m = map(int, res["open_time"].split(":"))
            c_h, c_m = map(int, res["close_time"].split(":"))
            sm        = res["slot_minutes"]
            open_min  = o_h * 60 + o_m
            close_min = c_h * 60 + c_m
            times: List[str] = []
            t = open_min
            while t + sm <= close_min:
                times.append(f"{t // 60:02d}:{t % 60:02d}")
                t += sm
            return times

        def _cell_text(game: Dict[str, Any]) -> str:
            gid = game.get("game_id", "")
            a   = str(game.get("team_a_label") or game.get("team_a_id") or "")
            b   = str(game.get("team_b_label") or game.get("team_b_id") or "")
            c   = str(game.get("team_c_label") or game.get("team_c_id") or "")
            # Show compact team labels when available; otherwise fall back to game_id only.
            if a and b and c and len(a) <= 12 and len(b) <= 12 and len(c) <= 12:
                return f"{gid}\n{a} / {b} / {c}"
            if a and b and len(a) <= 12 and len(b) <= 12:
                return f"{gid}\n{a} vs {b}"
            return gid

        def _time_sort_key(hhmm: str) -> int:
            h, m = map(int, hhmm.split(":"))
            return h * 60 + m

        def _resource_group_key(res: Dict[str, Any]) -> Tuple[str, str, str, str, int]:
            solver_pool = str(res.get("solver_pool") or "").strip()
            day = str(res.get("day", ""))
            resource_type = str(res.get("resource_type", ""))
            slot_minutes = int(res.get("slot_minutes", 0) or 0)
            if solver_pool == ScheduleWorkbookBuilder._GYM_CORE_SOLVER_POOL:
                # Render one continuous operator-facing section per Day/resource_type
                # for the shared gym solver pool, even when the allocator produced
                # multiple overlapping time windows for the same sport.
                return (day, resource_type, "", "", slot_minutes)
            return (
                day,
                resource_type,
                str(res.get("open_time", "")),
                str(res.get("close_time", "")),
                slot_minutes,
            )

        def _group_open_close(day_res: List[Dict[str, Any]]) -> Tuple[str, str]:
            open_times = [
                str(res.get("open_time", "")).strip()
                for res in day_res
                if str(res.get("open_time", "")).strip()
            ]
            close_times = [
                str(res.get("close_time", "")).strip()
                for res in day_res
                if str(res.get("close_time", "")).strip()
            ]
            merged_open = min(open_times, key=_time_sort_key) if open_times else ""
            merged_close = max(close_times, key=_time_sort_key) if close_times else ""
            return merged_open, merged_close

        def _group_slot_times(day_res: List[Dict[str, Any]]) -> List[str]:
            return sorted(
                {
                    t_str
                    for res in day_res
                    for t_str in _slot_times(res)
                },
                key=_time_sort_key,
            )

        def _resource_header_labels(day_res: List[Dict[str, Any]]) -> Dict[str, str]:
            labels_by_resource: Dict[str, str] = {}
            base_labels: Dict[str, str] = {}
            for res in day_res:
                resource_id = str(res.get("resource_id", "")).strip()
                base_label = str(res.get("label") or resource_id).strip() or resource_id
                solver_pool = str(res.get("solver_pool") or "").strip()
                venue_name = (
                    str(res.get("exclusive_group") or "").strip()
                    or str(res.get("venue_name") or "").strip()
                )
                base_labels[resource_id] = base_label
                if (
                    venue_name
                    and solver_pool == ScheduleWorkbookBuilder._GYM_CORE_SOLVER_POOL
                ):
                    labels_by_resource[resource_id] = f"{venue_name} {base_label}"
                else:
                    labels_by_resource[resource_id] = base_label

            def _counts() -> Dict[str, int]:
                counts: Dict[str, int] = {}
                for resource_id, label in labels_by_resource.items():
                    counts[label] = counts.get(label, 0) + 1
                return counts

            duplicate_labels = {
                label for label, count in _counts().items() if count > 1
            }
            if duplicate_labels:
                for res in day_res:
                    resource_id = str(res.get("resource_id", "")).strip()
                    if labels_by_resource.get(resource_id) not in duplicate_labels:
                        continue
                    venue_name = str(res.get("venue_name") or "").strip()
                    if venue_name:
                        labels_by_resource[resource_id] = (
                            f"{venue_name} {base_labels[resource_id]}"
                        )

            duplicate_labels = {
                label for label, count in _counts().items() if count > 1
            }
            if duplicate_labels:
                for res in day_res:
                    resource_id = str(res.get("resource_id", "")).strip()
                    if labels_by_resource.get(resource_id) not in duplicate_labels:
                        continue
                    open_time = str(res.get("open_time") or "").strip()
                    close_time = str(res.get("close_time") or "").strip()
                    window = f"{open_time}-{close_time}" if open_time and close_time else resource_id
                    labels_by_resource[resource_id] = (
                        f"{labels_by_resource[resource_id]} [{window}]"
                    )

            duplicate_labels = {
                label for label, count in _counts().items() if count > 1
            }
            if duplicate_labels:
                for res in day_res:
                    resource_id = str(res.get("resource_id", "")).strip()
                    if labels_by_resource.get(resource_id) not in duplicate_labels:
                        continue
                    labels_by_resource[resource_id] = (
                        f"{labels_by_resource[resource_id]} ({resource_id})"
                    )

            return labels_by_resource

        # Group resources by uniform day/window/resource pool so pod schedules with
        # mixed slot lengths do not get collapsed into one broken "Day-1" grid.
        resource_groups: Dict[Tuple[str, str, str, str, int], List[Dict[str, Any]]] = {}
        for res in schedule_input.get("resources", []):
            resource_groups.setdefault(_resource_group_key(res), []).append(res)

        group_counts_by_day: Dict[str, int] = {}
        for day, _, _, _, _ in resource_groups.keys():
            group_counts_by_day[day] = group_counts_by_day.get(day, 0) + 1

        sorted_group_keys = sorted(
            resource_groups.keys(),
            key=lambda key: (
                _DAY_ORDER.get(key[0], 99),
                key[0],
                _time_sort_key(key[2]) if key[2] else 0,
                _time_sort_key(key[3]) if key[3] else 0,
                key[4],
                key[1],
            ),
        )
        max_resources = max((len(v) for v in resource_groups.values()), default=4)
        n_cols        = 1 + max_resources

        def _section_label(
            group_key: Tuple[str, str, str, str, int],
            day_res: List[Dict[str, Any]],
        ) -> str:
            day, resource_type, open_time, close_time, slot_minutes = group_key
            day_label = _DAY_DISPLAY.get(day, day)
            if not open_time or not close_time:
                open_time, close_time = _group_open_close(day_res)
            if (
                day in _DAY_DISPLAY
                and resource_type in (GYM_RESOURCE_TYPE, GYM_RESOURCE_TYPE_BASKETBALL, GYM_RESOURCE_TYPE_VOLLEYBALL)
                and group_counts_by_day.get(day, 0) == 1
            ):
                return day_label
            return (
                f"{day_label} — {resource_type} "
                f"({open_time}-{close_time}, {slot_minutes}m)"
            )

        wb = Workbook()

        # ── Tab 1: Schedule-by-Time ──────────────────────────────────────────
        ws1       = wb.active
        ws1.title = "Schedule-by-Time"

        # Row 1 — report title (merged)
        ws1.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
        c = ws1.cell(row=1, column=1, value="VAY Sports Fest — Schedule by Time")
        c.fill, c.font, c.alignment = hdr_fill, hdr_font, center

        ws1.freeze_panes = "A2"

        cur_row = 3
        for group_key in sorted_group_keys:
            day_res = sorted(
                resource_groups[group_key],
                key=lambda r: (
                    _time_sort_key(str(r.get("open_time") or "00:00")),
                    str(r.get("exclusive_group") or ""),
                    str(r.get("label") or ""),
                    r["resource_id"],
                ),
            )
            if not day_res:
                continue
            header_labels = _resource_header_labels(day_res)

            # Section header (grey, merged)
            ws1.merge_cells(
                start_row=cur_row, start_column=1,
                end_row=cur_row, end_column=n_cols,
            )
            c = ws1.cell(row=cur_row, column=1, value=_section_label(group_key, day_res))
            c.fill, c.font, c.alignment = sec_fill, bold_font, center
            cur_row += 1

            # Column headers for this group
            ws1.cell(row=cur_row, column=1, value="Time").font = bold_font
            ws1.cell(row=cur_row, column=1).fill = sec_fill
            ws1.cell(row=cur_row, column=1).alignment = center
            for ci, res in enumerate(day_res, start=2):
                c = ws1.cell(
                    row=cur_row,
                    column=ci,
                    value=header_labels.get(
                        str(res.get("resource_id") or "").strip(),
                        res.get("label"),
                    ),
                )
                c.fill, c.font, c.alignment = sec_fill, bold_font, center
            cur_row += 1

            day = group_key[0]
            # Data rows — one per unioned time slot in this resource group.
            for t_str in _group_slot_times(day_res):
                slot_label = f"{day}-{t_str}"
                ws1.cell(row=cur_row, column=1, value=t_str).alignment = center
                for ci, res in enumerate(day_res, start=2):
                    game = assign_map.get((res["resource_id"], slot_label))
                    cell = ws1.cell(row=cur_row, column=ci)
                    if game:
                        cell.value = _cell_text(game)
                        cell.fill  = _sport_fill(game.get("event", ""))
                    cell.alignment = center
                cur_row += 1

            cur_row += 1  # blank row between sessions

        ws1.cell(row=cur_row + 1, column=1, value=snapshot)
        ws1.column_dimensions["A"].width = 7
        for ci in range(2, n_cols + 1):
            ws1.column_dimensions[get_column_letter(ci)].width = 18

        # ── Tab 2: Schedule-by-Sport ─────────────────────────────────────────
        ws2       = wb.create_sheet("Schedule-by-Sport")
        flat_rows = ScheduleWorkbookBuilder._build_schedule_output_flat_rows(
            schedule_output, schedule_input
        )
        col_defs = [
            ("game_id",          14),
            ("event",            28),
            ("stage",             8),
            ("round",             6),
            ("team_a_id",        20),
            ("team_b_id",        20),
            ("team_c_id",        20),
            ("resource_label",   14),
            ("day",              10),
            ("slot",              8),
            ("duration_minutes", 16),
        ]
        cols = [col for col, _ in col_defs]

        for ci, (col, _) in enumerate(col_defs, start=1):
            cell = ws2.cell(row=1, column=ci, value=col)
            cell.fill, cell.font = hdr_fill, hdr_font
            cell.alignment = Alignment(horizontal="center")
        ws2.freeze_panes = "A2"
        ws2.auto_filter.ref = f"A1:{get_column_letter(len(col_defs))}1"

        for ri, row in enumerate(flat_rows, start=2):
            fill = _sport_fill(row.get("event", ""))
            for ci, col in enumerate(cols, start=1):
                cell = ws2.cell(row=ri, column=ci, value=row.get(col, ""))
                cell.fill, cell.alignment = fill, left

        # Unscheduled section at bottom
        unscheduled = schedule_output.get("unscheduled", [])
        ri = len(flat_rows) + 3
        if unscheduled:
            ws2.merge_cells(
                start_row=ri, start_column=1, end_row=ri, end_column=len(col_defs)
            )
            c = ws2.cell(
                row=ri, column=1,
                value=f"Unscheduled Games ({len(unscheduled)})",
            )
            c.fill, c.font = red_fill, Font(bold=True)
            for gid in unscheduled:
                ri += 1
                ws2.cell(row=ri, column=1, value=gid).fill = red_fill
            ri += 2

        # Pool results summary — shown when pool_results present
        pool_results = schedule_output.get("pool_results", [])
        if pool_results:
            ws2.merge_cells(
                start_row=ri, start_column=1, end_row=ri, end_column=len(col_defs)
            )
            c = ws2.cell(row=ri, column=1, value="Pool Results")
            c.fill, c.font = sec_fill, Font(bold=True)
            ri += 1
            for pr in pool_results:
                pr_status = pr.get("status", "")
                pr_fill   = red_fill if pr_status not in ("OPTIMAL", "FEASIBLE") else PatternFill(
                    fgColor="C6EFCE", fill_type="solid"
                )
                ws2.cell(row=ri, column=1, value=pr.get("resource_type", "")).fill = pr_fill
                ws2.cell(row=ri, column=2, value=pr_status).fill                   = pr_fill
                ws2.cell(row=ri, column=3, value=f"Assigned: {len(pr.get('assignments', []))}").fill  = pr_fill
                ws2.cell(row=ri, column=4, value=f"Unscheduled: {len(pr.get('unscheduled', []))}").fill = pr_fill
                ri += 1
                for diag in pr.get("diagnostics", []):
                    for line in (diag.get("missing_resource_events") or []):
                        ws2.cell(row=ri, column=2,
                                 value=f"  No resources: {line.get('event','')} ({line.get('game_count',0)} games)"
                                 ).fill = red_fill
                        ri += 1
                    if diag.get("shortage_slots", 0) > 0:
                        ws2.cell(row=ri, column=2,
                                 value=f"  Short {diag['shortage_slots']} slot(s): "
                                       f"need {diag['required_slots']}, have {diag['available_slots']}"
                                 ).fill = red_fill
                        ri += 1
            ri += 1

        ws2.cell(row=ri, column=1, value=snapshot)
        for ci, (_, width) in enumerate(col_defs, start=1):
            ws2.column_dimensions[get_column_letter(ci)].width = width

        # ── Tab 3: Conflict-Audit ────────────────────────────────────────────
        ws3 = wb.create_sheet("Conflict-Audit")
        conflict_summary = schedule_output.get("conflict_audit_summary", {}) or {}
        conflict_rows = schedule_output.get("conflict_audit", []) or []
        ws3.cell(row=1, column=1, value="Cross-Sport Conflict Audit").fill = hdr_fill
        ws3.cell(row=1, column=1).font = hdr_font

        summary_lines = [
            (
                "Summary",
                (
                    f"Edges: {conflict_summary.get('total_edges', 0)}  |  "
                    f"Separated: {conflict_summary.get('separated_edges', 0)}  |  "
                    f"Remaining: {conflict_summary.get('overlapping_edges', 0)}  |  "
                    f"Planning-only: {conflict_summary.get('planning_only_edges', 0)}  |  "
                    f"Incomplete: {conflict_summary.get('incomplete_edges', 0)}"
                ),
            ),
            (
                "Remaining Penalties",
                (
                    f"Primary: {conflict_summary.get('remaining_primary_overlap_penalty', 0)}  |  "
                    f"Secondary-only: {conflict_summary.get('remaining_secondary_overlap_penalty', 0)}"
                ),
            ),
        ]
        for row_idx, (label, value) in enumerate(summary_lines, start=3):
            ws3.cell(row=row_idx, column=1, value=label).font = bold_font
            ws3.cell(row=row_idx, column=2, value=value)

        audit_headers = [
            ("team_a_label", 16),
            ("event_a", 24),
            ("team_b_label", 16),
            ("event_b", 24),
            ("shared_count", 12),
            ("primary_overlap_count", 18),
            ("secondary_only_count", 18),
            ("status", 20),
            ("overlap_count", 14),
            ("scheduled_team_a_games", 20),
            ("scheduled_team_b_games", 20),
            ("shared_participant_names", 40),
            ("overlap_game_pairs", 48),
        ]
        header_row = 6
        for ci, (col, width) in enumerate(audit_headers, start=1):
            cell = ws3.cell(row=header_row, column=ci, value=col)
            cell.fill, cell.font, cell.alignment = hdr_fill, hdr_font, center
            ws3.column_dimensions[get_column_letter(ci)].width = width
        ws3.freeze_panes = "A7"
        ws3.auto_filter.ref = f"A{header_row}:{get_column_letter(len(audit_headers))}{header_row}"

        if conflict_rows:
            for ri3, row in enumerate(conflict_rows, start=header_row + 1):
                row_fill = red_fill if row.get("status") == "ConflictRemains" else PatternFill(
                    fgColor="C6EFCE", fill_type="solid"
                )
                if row.get("status") == "IncompleteSchedule":
                    row_fill = PatternFill(fgColor="FFF2CC", fill_type="solid")
                elif row.get("status") == "PlanningOnly":
                    row_fill = PatternFill(fgColor="DDEBF7", fill_type="solid")
                for ci, (col, _width) in enumerate(audit_headers, start=1):
                    cell = ws3.cell(row=ri3, column=ci, value=row.get(col, ""))
                    cell.fill = row_fill
                    cell.alignment = left
        else:
            ws3.cell(
                row=header_row + 1,
                column=1,
                value="No cross-sport conflict audit rows were produced for this schedule.",
            )

        wb.save(filepath)
        logger.info(f"Schedule output report written to: {filepath}")

    # ── ALL-workbook readers (build-schedule-workbook input) ─────────────────

    @staticmethod
    def _read_xlsx_sheet_rows(xlsx_path: Path, sheet_name: str) -> List[Dict[str, Any]]:
        """Read one sheet of an exported workbook into a list of row dicts.

        NaN cells are normalized to None so the scheduling builders' common
        `str(row.get(col) or "")` idiom collapses blanks to empty strings
        (a bare NaN float is truthy and would otherwise stringify to 'nan').
        Returns an empty list with a WARNING when the sheet is absent.
        """
        try:
            df = pd.read_excel(xlsx_path, sheet_name=sheet_name, engine="openpyxl")
        except Exception as e:
            logger.warning(f"Could not read '{sheet_name}' tab from {xlsx_path}: {e}")
            return []
        # astype(object) first: assigning None to a float64 column silently
        # reverts to NaN, so the column must be object-typed before the mask.
        df = df.astype(object).where(pd.notna(df), None)
        rows = df.to_dict("records")
        logger.debug(f"Read {len(rows)} rows from '{sheet_name}' tab of {xlsx_path}")
        return rows

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

    def write_schedule_input_json(
        self,
        roster_rows: List[Dict[str, Any]],
        validation_rows: List[Dict[str, Any]],
        venue_input_path: Path,
        json_path: Path,
        pool_assignment_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Build schedule_input dict and write it as JSON. Returns the dict.
        Always called by export-church-teams, regardless of whether venue_input.xlsx
        exists (graceful degradation is handled inside _build_schedule_input).
        """
        schedule_input = self._build_schedule_input(
            roster_rows,
            validation_rows,
            venue_input_path,
            pool_assignment_path=pool_assignment_path,
        )
        json_path.write_text(json.dumps(schedule_input, indent=2, default=str), encoding="utf-8")
        logger.info(
            f"Schedule-Input: {schedule_input['game_count']} games, "
            f"{schedule_input['resource_count']} resources → {json_path}"
        )
        return schedule_input

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
                "Estimating = complete entries; Potential = all registrations including partial. "
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
