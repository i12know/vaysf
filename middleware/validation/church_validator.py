from collections import defaultdict
from typing import Any, Dict, List, Optional

from .name_matcher import (
    likely_name_match,
    normalized_name,
    resolvable_name_match,
    token_matches,
)
from .models import RulesManager
from config import DEFAULT_SPORT, FORMAT_MAPPINGS, GENDER, RACQUET_SPORTS, SPORT_FORMAT


class ChurchValidator:
    """Validates church-level entry limits for one church roster."""

    ISSUE_TYPES = frozenset({
        "church_entry_limit",
    })

    def __init__(self, collection: str = "SUMMER_2026"):
        self.rules_manager = RulesManager(collection)
        rules = self.rules_manager.get_rules_by_type("entry_limit")
        self.team_rules = [rule for rule in rules if rule.get("category") == "team"]
        self.format_rules = [rule for rule in rules if rule.get("category") == "format"]
        self.format_total_rules = [rule for rule in rules if rule.get("category") == "format_total"]

    def validate_church(
        self,
        church_id: Any,
        participants: List[Dict[str, Any]],
        rosters: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        issues.extend(self._check_team_limits(church_id, participants, rosters or []))
        issues.extend(self._check_format_limits(church_id, participants))
        issues.extend(self._check_format_total_limits(church_id, participants))
        return issues

    @staticmethod
    def _build_issue(
        church_id: Any,
        description: str,
        rule: Dict[str, Any],
        sport_type: str,
        sport_format: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "church_id": church_id,
            "participant_id": None,
            "issue_type": "church_entry_limit",
            "issue_description": description,
            "rule_code": rule.get("rule_code"),
            "rule_level": rule.get("rule_level"),
            "severity": rule.get("severity"),
            "sport_type": sport_type,
            "sport_format": sport_format,
            "status": "open",
        }

    @staticmethod
    def _participant_name(participant: Dict[str, Any]) -> str:
        return " ".join(
            value for value in (
                str(participant.get("first_name", "")).strip(),
                str(participant.get("last_name", "")).strip(),
            )
            if value
        ).strip()

    @staticmethod
    def _normalized_name(name: str) -> str:
        return normalized_name(name)

    @staticmethod
    def _token_matches(query_token: str, candidate_token: str) -> bool:
        return token_matches(query_token, candidate_token)

    @classmethod
    def _is_likely_name_match(cls, query_name_key: str, candidate_name_key: str) -> bool:
        return likely_name_match(query_name_key, candidate_name_key)

    @classmethod
    def _is_resolvable_name_match(cls, query_name_key: str, candidate_name_key: str) -> bool:
        return resolvable_name_match(query_name_key, candidate_name_key)

    @staticmethod
    def _parse_other_events(other_events: Any) -> List[str]:
        return [
            sport.strip()
            for sport in str(other_events or "").split(",")
            if sport.strip()
        ]

    @staticmethod
    def _selection_id(selection: Dict[str, Any]) -> str:
        participant_id = selection.get("participant_id")
        if participant_id not in (None, "", 0, "0"):
            return str(participant_id)
        return selection["participant_name_key"]

    @staticmethod
    def _team_event_label_from_roster(roster: Dict[str, Any]) -> Optional[str]:
        sport_type = str(roster.get("sport_type", "") or "").strip()
        sport_gender = str(roster.get("sport_gender", "") or "").strip()
        sport_format = str(roster.get("sport_format", "") or "").strip()

        if sport_format.casefold() != SPORT_FORMAT["TEAM"].casefold():
            return None
        if sport_type == "Basketball":
            return "Basketball - Men Team"
        if sport_type == "Volleyball":
            return f"Volleyball - {sport_gender} Team" if sport_gender else None
        if sport_type == "Bible Challenge":
            return "Bible Challenge - Mixed Team"
        if sport_type == "Soccer - Coed Exhibition":
            return "Soccer - Coed Exhibition"
        return None

    def _team_count_from_rosters(self, sport_event: str, rosters: List[Dict[str, Any]]) -> Optional[int]:
        if not rosters:
            return None

        matching_rosters = [
            roster for roster in rosters
            if self._team_event_label_from_roster(roster) == sport_event
        ]
        if not matching_rosters:
            return None

        explicit_team_orders = {
            str(roster.get("team_order")).strip()
            for roster in matching_rosters
            if roster.get("team_order") not in (None, "", 0, "0")
        }
        has_default_team = any(
            roster.get("team_order") in (None, "", 0, "0")
            for roster in matching_rosters
        )
        return len(explicit_team_orders) + (1 if has_default_team else 0)

    @staticmethod
    def _participant_selected_team_event(participant: Dict[str, Any], sport_event: str) -> bool:
        for sport_field in ("primary_sport", "secondary_sport"):
            if str(participant.get(sport_field, "") or "").strip() == sport_event:
                return True
        return sport_event in ChurchValidator._parse_other_events(participant.get("other_events"))

    def _check_team_limits(
        self,
        church_id: Any,
        participants: List[Dict[str, Any]],
        rosters: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        for rule in self.team_rules:
            sport_event = str(rule.get("sport_event", "") or "").strip()
            max_teams = int(rule["value"])
            team_count = self._team_count_from_rosters(sport_event, rosters)
            if team_count is None:
                team_count = 1 if any(
                    self._participant_selected_team_event(participant, sport_event)
                    for participant in participants
                ) else 0

            if team_count > max_teams:
                issues.append(self._build_issue(
                    church_id=church_id,
                    description=(
                        f"{sport_event} has {team_count} teams registered, "
                        f"exceeding church limit of {max_teams}"
                    ),
                    rule=rule,
                    sport_type=sport_event,
                    sport_format=SPORT_FORMAT["TEAM"],
                ))

        return issues

    def _participant_racquet_selections(self, participants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        selections: List[Dict[str, Any]] = []
        for participant in participants:
            participant_name = self._participant_name(participant)
            participant_name_key = self._normalized_name(participant_name)
            for sport_field, format_field, partner_field in (
                ("primary_sport", "primary_format", "primary_partner"),
                ("secondary_sport", "secondary_format", "secondary_partner"),
            ):
                sport = str(participant.get(sport_field, "") or "").strip()
                format_name = str(participant.get(format_field, "") or "").strip()
                if sport not in RACQUET_SPORTS or not format_name:
                    continue

                format_type, _ = FORMAT_MAPPINGS.get(format_name, (None, None))
                if not format_type:
                    continue

                partner_name = str(participant.get(partner_field, "") or "").strip()
                selections.append({
                    "participant_id": participant.get("participant_id"),
                    "participant_name": participant_name,
                    "participant_name_key": participant_name_key,
                    "sport_type": sport,
                    "sport_format": format_name,
                    "format_type": format_type,
                    "partner_name": partner_name,
                    "partner_name_key": self._normalized_name(partner_name),
                })
        return selections

    def _count_singles_entries(
        self,
        selections: List[Dict[str, Any]],
    ) -> Dict[tuple[str, str], int]:
        counts: Dict[tuple[str, str], int] = defaultdict(int)
        for selection in selections:
            if selection["format_type"] == SPORT_FORMAT["SINGLES"]:
                counts[(selection["sport_type"], selection["sport_format"])] += 1
        return counts

    def _find_reciprocal_doubles_partner(
        self,
        selection: Dict[str, Any],
        event_selections: List[Dict[str, Any]],
        used_ids: set[str],
    ) -> Optional[Dict[str, Any]]:
        partner_name_key = selection["partner_name_key"]
        if not partner_name_key:
            return None

        same_event_candidates = [
            candidate for candidate in event_selections
            if self._selection_id(candidate) not in used_ids
            and candidate is not selection
        ]

        exact_partner_candidates = [
            candidate for candidate in same_event_candidates
            if candidate["participant_name_key"] == partner_name_key
        ]
        exact_reciprocal_candidate = next(
            (
                candidate for candidate in exact_partner_candidates
                if candidate["partner_name_key"] == selection["participant_name_key"]
            ),
            None,
        )
        if exact_reciprocal_candidate:
            return exact_reciprocal_candidate

        partial_reciprocal_candidate = next(
            (
                candidate for candidate in exact_partner_candidates
                if self._is_unique_partial_reciprocal_match(candidate, selection, event_selections)
            ),
            None,
        )
        if partial_reciprocal_candidate:
            return partial_reciprocal_candidate

        partial_partner_candidates = self._resolvable_same_event_candidates(
            selection,
            same_event_candidates,
        )
        if len(partial_partner_candidates) != 1:
            return None

        candidate = partial_partner_candidates[0]
        if candidate["partner_name_key"] == selection["participant_name_key"]:
            return candidate
        if self._is_unique_partial_reciprocal_match(candidate, selection, event_selections):
            return candidate

        return None

    @staticmethod
    def _same_event_candidates(
        selection: Dict[str, Any],
        selections: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return [
            candidate for candidate in selections
            if candidate is not selection
            and candidate["sport_type"] == selection["sport_type"]
            and candidate["sport_format"] == selection["sport_format"]
        ]

    def _partial_same_event_candidates(
        self,
        selection: Dict[str, Any],
        selections: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        seen_keys: set[str] = set()

        for candidate in self._same_event_candidates(selection, selections):
            if not self._is_likely_name_match(
                selection["partner_name_key"],
                candidate["participant_name_key"],
            ):
                continue

            candidate_key = str(candidate.get("participant_id") or candidate["participant_name_key"])
            if candidate_key in seen_keys:
                continue
            seen_keys.add(candidate_key)
            candidates.append(candidate)

        return candidates

    def _resolvable_same_event_candidates(
        self,
        selection: Dict[str, Any],
        selections: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        seen_keys: set[str] = set()

        for candidate in self._same_event_candidates(selection, selections):
            if not self._is_resolvable_name_match(
                selection["partner_name_key"],
                candidate["participant_name_key"],
            ):
                continue

            candidate_key = str(candidate.get("participant_id") or candidate["participant_name_key"])
            if candidate_key in seen_keys:
                continue
            seen_keys.add(candidate_key)
            candidates.append(candidate)

        return candidates

    def _is_unique_partial_reciprocal_match(
        self,
        source_selection: Dict[str, Any],
        target_selection: Dict[str, Any],
        selections: List[Dict[str, Any]],
    ) -> bool:
        partial_candidates = self._resolvable_same_event_candidates(source_selection, selections)
        if len(partial_candidates) != 1:
            return False

        candidate = partial_candidates[0]
        if candidate.get("participant_id") and target_selection.get("participant_id"):
            return str(candidate["participant_id"]) == str(target_selection["participant_id"])
        return candidate["participant_name_key"] == target_selection["participant_name_key"]

    def _count_doubles_entries(
        self,
        selections: List[Dict[str, Any]],
    ) -> tuple[Dict[tuple[str, str], int], Dict[str, int]]:
        format_counts: Dict[tuple[str, str], int] = defaultdict(int)
        sport_totals: Dict[str, int] = defaultdict(int)

        doubles_by_event: Dict[tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        for selection in selections:
            if selection["format_type"] == SPORT_FORMAT["DOUBLES"]:
                doubles_by_event[(selection["sport_type"], selection["sport_format"])].append(selection)

        for (sport_type, format_name), event_selections in doubles_by_event.items():
            used_ids: set[str] = set()
            for selection in event_selections:
                selection_id = self._selection_id(selection)
                if selection_id in used_ids:
                    continue

                used_ids.add(selection_id)

                reciprocal_partner = self._find_reciprocal_doubles_partner(
                    selection,
                    event_selections,
                    used_ids,
                )
                if reciprocal_partner:
                    format_counts[(sport_type, format_name)] += 1
                    sport_totals[sport_type] += 1
                    used_ids.add(self._selection_id(reciprocal_partner))

        return format_counts, sport_totals

    def _check_format_limits(self, church_id: Any, participants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        selections = self._participant_racquet_selections(participants)
        singles_counts = self._count_singles_entries(selections)
        doubles_counts, _ = self._count_doubles_entries(selections)

        issues: List[Dict[str, Any]] = []
        for rule in self.format_rules:
            sport_type = str(rule.get("sport_event", "") or "").strip()
            sport_format = str(rule.get("parameter", "") or "").strip()
            max_entries = int(rule["value"])
            count = singles_counts.get((sport_type, sport_format), 0) + doubles_counts.get((sport_type, sport_format), 0)
            if count <= max_entries:
                continue

            entry_label = "teams" if "Double" in sport_format else "entries"
            issues.append(self._build_issue(
                church_id=church_id,
                description=(
                    f"{sport_type} {sport_format} has {count} {entry_label}, "
                    f"exceeding church limit of {max_entries}"
                ),
                rule=rule,
                sport_type=sport_type,
                sport_format=sport_format,
            ))

        return issues

    def _check_format_total_limits(self, church_id: Any, participants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        selections = self._participant_racquet_selections(participants)
        _, doubles_totals = self._count_doubles_entries(selections)

        issues: List[Dict[str, Any]] = []
        for rule in self.format_total_rules:
            sport_type = str(rule.get("sport_event", "") or "").strip()
            sport_format = str(rule.get("parameter", "") or "").strip()
            max_entries = int(rule["value"])
            count = doubles_totals.get(sport_type, 0)
            if count <= max_entries:
                continue

            issues.append(self._build_issue(
                church_id=church_id,
                description=(
                    f"{sport_type} {sport_format} has {count} teams registered, "
                    f"exceeding church limit of {max_entries}"
                ),
                rule=rule,
                sport_type=sport_type,
                sport_format=sport_format,
            ))

        return issues
