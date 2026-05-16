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
from collections import deque
import re
from math import ceil

from config import (
    SPORT_TYPE,
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

    The _rules_manager_cache attribute is set lazily by _get_min_team_size;
    __init__ intentionally does not touch it.
    """

    def __init__(self) -> None:
        pass

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

    def _get_min_team_size(self, event_name: str) -> int:
        """Look up minimum team size from the validation ruleset; fall back
        to COURT_ESTIMATE_MIN_TEAM_SIZE if the JSON rule is absent."""
        if not hasattr(self, "_rules_manager_cache"):
            try:
                self._rules_manager_cache = RulesManager(collection="SUMMER_2026")
            except Exception as e:
                logger.warning(f"Could not load validation rules for venue estimate: {e}")
                self._rules_manager_cache = None
        if self._rules_manager_cache is not None:
            for rule in self._rules_manager_cache.get_rules_for_sport(event_name):
                if rule.get("rule_type") == "team_size" and rule.get("category") == "min":
                    try:
                        return int(rule.get("value"))
                    except (TypeError, ValueError):
                        pass
        return int(COURT_ESTIMATE_MIN_TEAM_SIZE.get(event_name, 0))

    def _count_estimating_teams(self, roster_rows: List[Dict[str, Any]],
                                 event_name: str, min_team_size: int) -> Dict[str, Any]:
        """Return estimating/potential team counts and the qualifying church codes.

        Approval-agnostic — every roster entry counts.

        Returns a dict with:
          n_estimating  – churches with >= min_team_size entries (ready to compete)
          n_potential   – churches with >= 1 but < min_team_size entries (still forming)
          team_codes    – sorted, comma-separated list of estimating church codes
        """
        if min_team_size <= 0:
            return {"n_estimating": 0, "n_potential": 0, "team_codes": ""}
        target_type, target_gender, _ = self._decompose_event_name(event_name)
        counts_by_church: Dict[str, int] = {}
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
            church = str(r.get("Church Team") or "").strip()
            if not church:
                continue
            counts_by_church[church] = counts_by_church.get(church, 0) + 1
        estimating = sorted(c for c, n in counts_by_church.items() if n >= min_team_size)
        partial = [c for c, n in counts_by_church.items() if 0 < n < min_team_size]
        return {
            "n_estimating": len(estimating),
            "n_potential": len(estimating) + len(partial),  # all churches with >= 1 entry
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

    # ── Schedule-Input JSON builders ─────────────────────────────────────────

    def _build_gym_game_objects(
        self, roster_rows: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Return pool-play game placeholder dicts for gym sports (Basketball, VB Men, VB Women).

        Pool games carry stable placeholder team IDs (e.g. BBM-P1-T1, BBM-P1-T2)
        and non-empty pool_id values so the solver can enforce team-overlap and
        min-rest constraints even before final church assignments are known.

        Playoff games (QF/Semi/Final/3rd) are pre-assigned via the Playoff-Slots
        tab in venue_input.xlsx and are not included here.
        """
        sport_defs = [
            (SPORT_TYPE["BASKETBALL"],       "BBM"),
            (SPORT_TYPE["VOLLEYBALL_MEN"],   "VBM"),
            (SPORT_TYPE["VOLLEYBALL_WOMEN"], "VBW"),
        ]
        mpg = COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME
        games: List[Dict[str, Any]] = []

        for event_name, prefix in sport_defs:
            min_sz = self._get_min_team_size(event_name)
            counts = self._count_estimating_teams(roster_rows, event_name, min_sz)
            n_teams = counts["n_estimating"] if counts["n_estimating"] >= 2 else 8
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
                    "resource_type": GYM_RESOURCE_TYPE,
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
    def _build_gym_resource_objects(n_courts: int = 4) -> List[Dict[str, Any]]:
        """Return one resource object per (session × court) for gym sports.

        Four sessions: 1st Saturday, 1st Sunday, 2nd Saturday, 2nd Sunday.
        Time windows are taken from SCHEDULE_SKETCH_* config constants.
        close_time = last game start + slot_minutes (one slot after last start).
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
        resources: List[Dict[str, Any]] = []
        for day_label, open_time, close_time in sessions:
            for c in range(1, n_courts + 1):
                resources.append({
                    "resource_id":   f"GYM-{day_label}-{c}",
                    "resource_type": GYM_RESOURCE_TYPE,
                    "label":         f"Court-{c}",
                    "day":           day_label,
                    "open_time":     open_time,
                    "close_time":    close_time,
                    "slot_minutes":  mpg,
                    "exclusive_group": "",
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
    def _load_venue_input_rows(venue_input_path: Path) -> List[Dict[str, Any]]:
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
        resource_counts: Dict[str, int] = {}

        for _, row in df.iterrows():
            resource_type = ScheduleWorkbookBuilder._clean_excel_text(row.get("Resource Type"))
            if not resource_type:
                continue
            # Exclusive Venue Group: rows sharing a group value compete for the
            # same physical gym (only one mode active per time block). Optional
            # column — blank means the resource stands alone.
            exclusive_group = ScheduleWorkbookBuilder._clean_excel_text(
                row.get("Exclusive Venue Group")
            )
            qty = max(1, int(ScheduleWorkbookBuilder._float_from_excel(row.get("Quantity"), 1)))
            slot_min = max(1, int(ScheduleWorkbookBuilder._float_from_excel(row.get("Slot Minutes"), 60)))
            start = ScheduleWorkbookBuilder._parse_hour(row.get("Start Time"))
            last_start = ScheduleWorkbookBuilder._parse_hour(row.get("Last Start Time"))
            open_time = f"{int(start):02d}:{int(round((start % 1) * 60)):02d}"
            close_decimal = last_start + slot_min / 60.0
            close_time = f"{int(close_decimal):02d}:{int(round((close_decimal % 1) * 60)):02d}"

            abbrev = resource_type.split()[0][:3].upper()
            rc = resource_counts.get(resource_type, 0)

            for i in range(1, qty + 1):
                rc += 1
                label = (
                    f"Table-{i}" if "table" in resource_type.lower() else f"Court-{i}"
                )
                rows.append({
                    "resource_id":     f"{abbrev}-{rc}",
                    "resource_type":   resource_type,
                    "label":           label,
                    "day":             "Day-1",
                    "open_time":       open_time,
                    "close_time":      close_time,
                    "slot_minutes":    slot_min,
                    "exclusive_group": exclusive_group,
                })
            resource_counts[resource_type] = rc

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
    ) -> Dict[str, Any]:
        """Assemble the full schedule_input package consumed by OR-Tools.

        Returns a dict with keys: generated_at, gym_court_scenario, game_count,
        resource_count, games, resources, playoff_slots, gym_modes.

        Gym resources are built from the explicit SCHEDULE_SOLVER_GYM_COURTS
        constant (config.py) so the solver knows exactly which court scenario
        was chosen for this run.
        """
        gym_games = self._build_gym_game_objects(roster_rows)
        pod_games = self._build_pod_game_objects(roster_rows, validation_rows)
        all_games = gym_games + pod_games

        gym_resources = self._build_gym_resource_objects(SCHEDULE_SOLVER_GYM_COURTS)
        pod_resources = self._load_venue_input_rows(venue_input_path)
        all_resources = gym_resources + pod_resources

        playoff_slots = self._load_playoff_slots(venue_input_path)
        gym_modes = self._load_gym_modes(venue_input_path)

        return {
            "generated_at":       datetime.now().isoformat(timespec="seconds"),
            "gym_court_scenario": SCHEDULE_SOLVER_GYM_COURTS,
            "game_count":         len(all_games),
            "resource_count":     len(all_resources),
            "games":              all_games,
            "resources":          all_resources,
            "playoff_slots":      playoff_slots,
            "gym_modes":          gym_modes,
        }

    @staticmethod
    def _write_schedule_input_tab(ws, schedule_input: Dict[str, Any]) -> None:
        """Write Schedule-Input tab with Games, Resources, and Playoff-Slots sections."""
        from openpyxl.styles import PatternFill, Font, Alignment
        from openpyxl.utils import get_column_letter

        hdr_fill = PatternFill(fgColor=SCHEDULE_SKETCH_COLOR_HEADER, fill_type="solid")
        hdr_font = Font(bold=True, color="FFFFFF")
        sec_fill = PatternFill(fgColor=SCHEDULE_SKETCH_COLOR_SECTION, fill_type="solid")
        sec_font = Font(bold=True)

        game_cols = [
            "game_id", "event", "stage", "pool_id", "round",
            "team_a_id", "team_b_id", "duration_minutes",
            "resource_type", "earliest_slot", "latest_slot",
        ]
        resource_cols = [
            "resource_id", "resource_type", "label", "day",
            "open_time", "close_time", "slot_minutes", "exclusive_group",
        ]
        playoff_slot_cols = ["game_id", "event", "stage", "resource_id", "slot"]

        current_row = 1

        # Meta row
        ws.cell(row=current_row, column=1, value="generated_at").font = sec_font
        ws.cell(row=current_row, column=2, value=schedule_input["generated_at"])
        ws.cell(
            row=current_row, column=3,
            value=f"Games: {schedule_input['game_count']}  Resources: {schedule_input['resource_count']}",
        )
        current_row += 2

        def _write_section(title: str, cols: List[str], rows: List[Dict]) -> None:
            nonlocal current_row
            sec_cell = ws.cell(row=current_row, column=1, value=title)
            sec_cell.fill = sec_fill
            sec_cell.font = sec_font
            current_row += 1
            for c_idx, col in enumerate(cols, start=1):
                cell = ws.cell(row=current_row, column=c_idx, value=col)
                cell.fill = hdr_fill
                cell.font = hdr_font
                cell.alignment = Alignment(horizontal="center")
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

        _write_section("GAMES",          game_cols,          schedule_input["games"])
        _write_section("RESOURCES",      resource_cols,      schedule_input["resources"])
        _write_section("PLAYOFF-SLOTS",  playoff_slot_cols,  playoff_note_rows)
        _write_section("GYM-MODES",      gym_mode_cols,      gym_mode_rows)

        # Column widths
        col_widths = [20, 30, 10, 10, 8, 16, 16, 18, 22, 14, 12]
        for i, w in enumerate(col_widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w

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
            ws.merge_cells(
                start_row=SCENARIO_HDR_ROW, start_column=start_col,
                end_row=SCENARIO_HDR_ROW,   end_column=end_col,
            )
            # Column sub-headers
            t_cell = ws.cell(row=COL_HDR_ROW, column=start_col, value="Time")
            t_cell.font = bold_font
            for c in range(n_courts):
                ct_cell = ws.cell(row=COL_HDR_ROW, column=start_col + 1 + c, value=f"Court {c + 1}")
                ct_cell.font = bold_font
                ct_cell.alignment = center

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

    def _write_pod_resource_estimate(
        self,
        ws,
        pod_rows: List[Dict[str, Any]],
        available_by_resource: Dict[str, int],
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

        # Snapshot note
        note_row = len(pod_rows) + 3
        ws.cell(
            row=note_row, column=1,
            value=(
                f"Venue data loaded from {VENUE_INPUT_FILENAME}. "
                "Required = entries − 1 (single elimination). "
                f"Green ≥ 0 | Yellow short 1–{POD_FIT_YELLOW_MAX} | Red short {POD_FIT_YELLOW_MAX + 1}+."
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
                "team_a_id":        game.get("team_a_id", ""),
                "team_b_id":        game.get("team_b_id", ""),
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
        """Write Schedule-by-Time and Schedule-by-Sport Excel tabs from solver output.

        Tab 1 — Schedule-by-Time: grid (rows = time slots, columns = courts),
          colour-coded by sport, with session sections separated by grey rows.
        Tab 2 — Schedule-by-Sport: flat list sorted by event → stage → round,
          with auto-filter and an unscheduled section when applicable.
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
            a   = str(game.get("team_a_id") or "")
            b   = str(game.get("team_b_id") or "")
            # Show teams only when they look like real church codes (≤5 chars, no hyphens)
            if a and b and len(a) <= 5 and "-" not in a:
                return f"{gid}\n{a} vs {b}"
            return gid

        def _time_sort_key(hhmm: str) -> int:
            h, m = map(int, hhmm.split(":"))
            return h * 60 + m

        def _resource_group_key(res: Dict[str, Any]) -> Tuple[str, str, str, str, int]:
            return (
                str(res.get("day", "")),
                str(res.get("resource_type", "")),
                str(res.get("open_time", "")),
                str(res.get("close_time", "")),
                int(res.get("slot_minutes", 0) or 0),
            )

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

        def _section_label(group_key: Tuple[str, str, str, str, int]) -> str:
            day, resource_type, open_time, close_time, slot_minutes = group_key
            day_label = _DAY_DISPLAY.get(day, day)
            if (
                day in _DAY_DISPLAY
                and resource_type == GYM_RESOURCE_TYPE
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
            day_res = sorted(resource_groups[group_key], key=lambda r: r["resource_id"])
            if not day_res:
                continue

            # Section header (grey, merged)
            ws1.merge_cells(
                start_row=cur_row, start_column=1,
                end_row=cur_row, end_column=n_cols,
            )
            c = ws1.cell(row=cur_row, column=1, value=_section_label(group_key))
            c.fill, c.font, c.alignment = sec_fill, bold_font, center
            cur_row += 1

            # Column headers for this group
            ws1.cell(row=cur_row, column=1, value="Time").font = bold_font
            ws1.cell(row=cur_row, column=1).fill = sec_fill
            ws1.cell(row=cur_row, column=1).alignment = center
            for ci, res in enumerate(day_res, start=2):
                c = ws1.cell(row=cur_row, column=ci, value=res["label"])
                c.fill, c.font, c.alignment = sec_fill, bold_font, center
            cur_row += 1

            day = group_key[0]
            # Data rows — one per time slot in this uniform resource group
            for t_str in _slot_times(day_res[0]):
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
    ) -> Dict[str, Any]:
        """Build schedule_input dict and write it as JSON. Returns the dict.
        Always called by export-church-teams, regardless of whether venue_input.xlsx
        exists (graceful degradation is handled inside _build_schedule_input).
        """
        schedule_input = self._build_schedule_input(roster_rows, validation_rows, venue_input_path)
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
        venue_input_path: Path,
    ) -> None:
        """Write the Schedule_Workbook xlsx with all scheduling tabs.
        Called by build-schedule-workbook command (Step 3).
        For the solver-rendered two-tab workbook, use write_schedule_output_workbook().
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
            note_row = len(df_venue) + 3
            venue_ws.cell(row=note_row, column=1, value=snapshot_note)
            logger.debug(f"Venue-Estimator tab: {len(df_venue)} rows.")

            # Pod-Divisions tab (pandas)
            df_pod_div = pd.DataFrame(pod_div_rows, columns=pod_div_cols)
            df_pod_div.to_excel(writer, sheet_name="Pod-Divisions", index=False)
            logger.debug(f"Pod-Divisions tab: {len(df_pod_div)} rows.")

            # Pod-Entries-Review tab (pandas)
            df_pod_entries = pd.DataFrame(pod_entry_rows, columns=pod_entry_cols)
            df_pod_entries.to_excel(writer, sheet_name="Pod-Entries-Review", index=False)
            logger.debug(f"Pod-Entries-Review tab: {len(df_pod_entries)} rows.")

            # Court-Schedule-Sketch tab (openpyxl native)
            sketch_ws = writer.book.create_sheet(title="Court-Schedule-Sketch")
            self._write_court_schedule_sketch(sketch_ws, roster_rows)

            # Pod-Resource-Estimate tab (openpyxl native)
            available_by_resource = self._load_venue_input(venue_input_path)
            pod_res_rows = self._build_pod_resource_rows(roster_rows, available_by_resource)
            pod_ws = writer.book.create_sheet(title="Pod-Resource-Estimate")
            self._write_pod_resource_estimate(pod_ws, pod_res_rows, available_by_resource)

            # Schedule-Input tab (openpyxl native — echo of the JSON)
            si_ws = writer.book.create_sheet(title="Schedule-Input")
            self._write_schedule_input_tab(si_ws, schedule_input)

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
