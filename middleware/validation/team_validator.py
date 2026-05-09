import unicodedata
from typing import List, Dict, Any

from .models import RulesManager
from config import (SPORT_BY_CATEGORY, SPORT_CATEGORY, RACQUET_SPORTS,
                   FORMAT_MAPPINGS, SPORT_FORMAT, DEFAULT_SPORT)


class TeamValidator:
    """Validates team-composition rules for a single church's participants."""

    ISSUE_TYPES = frozenset({
        "team_min_size",
        "team_non_member_limit",
        "doubles_non_member_limit",
        "doubles_partner_unmatched",
    })

    def __init__(self, collection: str = "SUMMER_2026"):
        self.rules_manager = RulesManager(collection)
        rules = self.rules_manager.get_rules_by_type("max_non_members")
        team_rules = [r for r in rules if r.get("category") == "team"]
        self.team_rule = next(
            r for r in team_rules if r.get("sport_event") == DEFAULT_SPORT
        )
        self.doubles_rule = next(
            r for r in rules if r.get("category") == "doubles"
        )
        self.team_rules_by_sport = {
            str(rule["sport_event"]).strip(): rule
            for rule in team_rules
            if str(rule.get("sport_event") or "").strip()
            and str(rule.get("sport_event")).strip() != DEFAULT_SPORT
        }
        partner_rules = self.rules_manager.get_rules_by_type("partner")
        self.reciprocal_partner_rule = next(
            (
                r for r in partner_rules
                if r.get("category") == "reciprocal"
                and str(r.get("value", "")).lower() == "true"
            ),
            None,
        )
        team_size_rules = self.rules_manager.get_rules_by_type("team_size")
        self.min_team_size_rules = {
            str(rule["sport_event"]).strip(): rule
            for rule in team_size_rules
            if rule.get("category") == "min"
            and str(rule.get("sport_event") or "").strip()
        }
        self.team_limit = int(self.team_rule["value"])
        self.doubles_limit = int(self.doubles_rule["value"])
        self.team_sports = set(SPORT_BY_CATEGORY[SPORT_CATEGORY["TEAM"]])
        self.team_rule_sports = (
            self.team_sports
            | set(self.team_rules_by_sport)
            | set(self.min_team_size_rules)
        )

    def validate_church(self, church_id: Any, participants: List[Dict]) -> List[Dict]:
        """Return team-level validation issue dicts for one church."""
        issues = []
        issues.extend(self._check_team_min_size(church_id, participants))
        issues.extend(self._check_team_non_members(church_id, participants))
        issues.extend(self._check_doubles_non_members(church_id, participants))
        issues.extend(self._check_doubles_partner_matching(church_id, participants))
        return issues

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
        normalized = unicodedata.normalize("NFKD", str(name or "").strip())
        without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        return " ".join(without_marks.casefold().split())

    @staticmethod
    def _token_matches(query_token: str, candidate_token: str) -> bool:
        if query_token == candidate_token:
            return True
        return len(query_token) >= 2 and candidate_token.startswith(query_token)

    @classmethod
    def _is_likely_name_match(cls, query_name_key: str, candidate_name_key: str) -> bool:
        query_tokens = [token for token in str(query_name_key or "").split() if token]
        candidate_tokens = [token for token in str(candidate_name_key or "").split() if token]
        if not query_tokens or not candidate_tokens:
            return False

        return all(
            any(cls._token_matches(query_token, candidate_token) for candidate_token in candidate_tokens)
            for query_token in query_tokens
        )

    def _pair_key(self, participant: Dict[str, Any], partner_field: str) -> tuple[str, ...]:
        participant_identity = self._participant_name(participant) or str(
            participant.get("participant_id") or participant.get("chmeetings_id") or "unknown"
        ).strip()
        partner_name = str(participant.get(partner_field, "") or "").strip()
        if partner_name:
            return tuple(sorted((participant_identity, partner_name)))
        return (participant_identity,)

    @staticmethod
    def _build_issue(
        church_id: Any,
        issue_type: str,
        description: str,
        rule: Dict[str, Any],
        sport_type: str,
        sport_format: str | None = None,
        participant_id: Any = None,
    ) -> Dict[str, Any]:
        return {
            "church_id": church_id,
            "participant_id": participant_id,
            "issue_type": issue_type,
            "issue_description": description,
            "rule_code": rule.get("rule_code"),
            "rule_level": rule.get("rule_level"),
            "severity": rule.get("severity"),
            "sport_type": sport_type,
            "sport_format": sport_format,
            "status": "open",
        }

    @staticmethod
    def _parse_other_events(other_events: Any) -> List[str]:
        return [
            sport.strip()
            for sport in str(other_events or "").split(",")
            if sport.strip()
        ]

    def _selected_team_events(
        self,
        participant: Dict[str, Any],
        allowed_sports: set[str],
    ) -> set[str]:
        selected_sports: set[str] = set()

        for sport_field in ("primary_sport", "secondary_sport"):
            sport = str(participant.get(sport_field, "") or "").strip()
            if sport in allowed_sports:
                selected_sports.add(sport)

        for sport in self._parse_other_events(participant.get("other_events")):
            if sport in allowed_sports:
                selected_sports.add(sport)

        return selected_sports

    def _team_rule_for_sport(self, sport: str) -> Dict[str, Any] | None:
        if sport in self.team_rules_by_sport:
            return self.team_rules_by_sport[sport]
        if sport in self.team_sports:
            return self.team_rule
        return None

    def _check_team_min_size(self, church_id: Any, participants: List[Dict]) -> List[Dict]:
        if not self.min_team_size_rules:
            return []

        sport_counts = {
            sport: 0 for sport in self.min_team_size_rules
        }
        tracked_sports = set(self.min_team_size_rules)

        for participant in participants:
            for sport in self._selected_team_events(participant, tracked_sports):
                sport_counts[sport] += 1

        issues = []
        for sport, participant_count in sport_counts.items():
            rule = self.min_team_size_rules[sport]
            min_size = int(rule["value"])
            if 0 < participant_count < min_size:
                issues.append(self._build_issue(
                    church_id=church_id,
                    issue_type="team_min_size",
                    description=(
                        f"{sport} has {participant_count} participants, "
                        f"below minimum size of {min_size}"
                    ),
                    rule=rule,
                    sport_type=sport,
                ))

        return issues

    def _check_team_non_members(self, church_id: Any, participants: List[Dict]) -> List[Dict]:
        sport_non_members: Dict[str, List[Dict]] = {}
        for participant in participants:
            if participant.get("is_church_member"):
                continue
            for sport in self._selected_team_events(participant, self.team_rule_sports):
                rule = self._team_rule_for_sport(sport)
                if rule:
                    sport_non_members.setdefault(sport, []).append(participant)

        issues = []
        for sport, non_members in sport_non_members.items():
            rule = self._team_rule_for_sport(sport)
            if not rule:
                continue

            team_limit = int(rule["value"])
            if len(non_members) > team_limit:
                issues.append(self._build_issue(
                    church_id=church_id,
                    issue_type="team_non_member_limit",
                    description=(
                        f"{sport} has {len(non_members)} non-members, "
                        f"exceeding limit of {team_limit}"
                    ),
                    rule=rule,
                    sport_type=sport,
                ))
        return issues

    def _check_doubles_non_members(self, church_id: Any, participants: List[Dict]) -> List[Dict]:
        # sport -> format_name -> pair_key -> list of non-member participants
        doubles_non_members: Dict[str, Dict[str, Dict[tuple[str, ...], List[Dict]]]] = {
            sport: {} for sport in RACQUET_SPORTS
        }
        for participant in participants:
            if participant.get("is_church_member"):
                continue
            for sport_field, format_field, partner_field in (
                ("primary_sport", "primary_format", "primary_partner"),
                ("secondary_sport", "secondary_format", "secondary_partner"),
            ):
                sport = participant.get(sport_field, "")
                fmt = participant.get(format_field, "")
                if sport not in RACQUET_SPORTS:
                    continue
                fmt_type, _ = FORMAT_MAPPINGS.get(fmt, (None, None))
                if fmt_type == SPORT_FORMAT["DOUBLES"]:
                    pair_key = self._pair_key(participant, partner_field)
                    doubles_non_members[sport].setdefault(fmt, {}).setdefault(pair_key, []).append(participant)

        issues = []
        for sport, formats in doubles_non_members.items():
            for format_name, pairs in formats.items():
                for pair_key, non_members in pairs.items():
                    if len(non_members) > self.doubles_limit:
                        pair_label = " / ".join(pair_key)
                        issues.append(self._build_issue(
                            church_id=church_id,
                            issue_type="doubles_non_member_limit",
                            description=(
                                f"{sport} {format_name} pair {pair_label} has "
                                f"{len(non_members)} non-members, exceeding limit of {self.doubles_limit}"
                            ),
                            rule=self.doubles_rule,
                            sport_type=sport,
                            sport_format=format_name,
                        ))
        return issues

    def _doubles_selections(self, participants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
                if sport not in RACQUET_SPORTS:
                    continue

                format_type, _ = FORMAT_MAPPINGS.get(format_name, (None, None))
                if format_type != SPORT_FORMAT["DOUBLES"]:
                    continue

                partner_name = str(participant.get(partner_field, "") or "").strip()
                selections.append({
                    "participant_id": participant.get("participant_id"),
                    "participant_name": participant_name,
                    "participant_name_key": participant_name_key,
                    "sport_type": sport,
                    "sport_format": format_name,
                    "partner_name": partner_name,
                    "partner_name_key": self._normalized_name(partner_name),
                })

        return selections

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

    def _is_unique_partial_reciprocal_match(
        self,
        source_selection: Dict[str, Any],
        target_selection: Dict[str, Any],
        selections: List[Dict[str, Any]],
    ) -> bool:
        partial_candidates = self._partial_same_event_candidates(source_selection, selections)
        if len(partial_candidates) != 1:
            return False

        candidate = partial_candidates[0]
        if candidate.get("participant_id") and target_selection.get("participant_id"):
            return str(candidate["participant_id"]) == str(target_selection["participant_id"])
        return candidate["participant_name_key"] == target_selection["participant_name_key"]

    def _check_doubles_partner_matching(self, church_id: Any, participants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.reciprocal_partner_rule:
            return []

        selections = self._doubles_selections(participants)
        selections_by_name: Dict[str, List[Dict[str, Any]]] = {}
        for selection in selections:
            key = selection["participant_name_key"]
            if key:
                selections_by_name.setdefault(key, []).append(selection)

        issues: List[Dict[str, Any]] = []
        for selection in selections:
            partner_name = selection["partner_name"]
            partner_name_key = selection["partner_name_key"]
            if not partner_name_key:
                continue

            partner_candidates = [
                candidate for candidate in selections_by_name.get(partner_name_key, [])
                if candidate is not selection
            ]

            if not partner_candidates:
                partial_candidates = self._partial_same_event_candidates(selection, selections)
                if len(partial_candidates) == 1:
                    suggestion = partial_candidates[0]["participant_name"]
                    description = (
                        f"{selection['participant_name']} listed {partner_name} as their partner for "
                        f"{selection['sport_type']} ({selection['sport_format']}), but the partner name is "
                        f"ambiguous; use full name, perhaps {suggestion}."
                    )
                elif partial_candidates:
                    suggestions = ", ".join(candidate["participant_name"] for candidate in partial_candidates)
                    description = (
                        f"{selection['participant_name']} listed {partner_name} as their partner for "
                        f"{selection['sport_type']} ({selection['sport_format']}), but the partner name is "
                        f"ambiguous; use full name. Possible matches: {suggestions}."
                    )
                else:
                    description = (
                        f"{selection['participant_name']} listed {partner_name} as their partner for "
                        f"{selection['sport_type']} ({selection['sport_format']}), but no participant by that "
                        "name was found in the same church roster."
                    )
            else:
                same_event_candidates = [
                    candidate for candidate in partner_candidates
                    if candidate["sport_type"] == selection["sport_type"]
                    and candidate["sport_format"] == selection["sport_format"]
                ]
                reciprocal_candidate = next(
                    (
                        candidate for candidate in same_event_candidates
                        if candidate["partner_name_key"] == selection["participant_name_key"]
                    ),
                    None,
                )

                if reciprocal_candidate:
                    continue

                partial_reciprocal_candidate = next(
                    (
                        candidate for candidate in same_event_candidates
                        if self._is_unique_partial_reciprocal_match(candidate, selection, selections)
                    ),
                    None,
                )
                if partial_reciprocal_candidate:
                    continue

                same_event_candidate = next(
                    iter(same_event_candidates),
                    None,
                )
                if same_event_candidate:
                    description = (
                        f"{selection['participant_name']} listed {partner_name} as their partner for "
                        f"{selection['sport_type']} ({selection['sport_format']}), but {partner_name} did not "
                        f"reciprocally list {selection['participant_name']}."
                    )
                else:
                    description = (
                        f"{selection['participant_name']} listed {partner_name} as their partner for "
                        f"{selection['sport_type']} ({selection['sport_format']}), but {partner_name} is not "
                        "registered for that same doubles event."
                    )

            issues.append(self._build_issue(
                church_id=church_id,
                issue_type="doubles_partner_unmatched",
                description=description,
                rule=self.reciprocal_partner_rule,
                sport_type=selection["sport_type"],
                sport_format=selection["sport_format"],
                participant_id=selection.get("participant_id"),
            ))

        return issues
