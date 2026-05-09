from typing import List, Dict, Any

from .models import RulesManager
from config import (SPORT_BY_CATEGORY, SPORT_CATEGORY, RACQUET_SPORTS,
                   FORMAT_MAPPINGS, SPORT_FORMAT)


class TeamValidator:
    """Validates team-composition rules for a single church's participants."""

    ISSUE_TYPES = frozenset({"team_non_member_limit", "doubles_non_member_limit"})

    def __init__(self, collection: str = "SUMMER_2026"):
        self.rules_manager = RulesManager(collection)
        rules = self.rules_manager.get_rules_by_type("max_non_members")
        self.team_rule = next(
            r for r in rules if r.get("category") == "team"
        )
        self.doubles_rule = next(
            r for r in rules if r.get("category") == "doubles"
        )
        self.team_limit = int(self.team_rule["value"])
        self.doubles_limit = int(self.doubles_rule["value"])
        self.team_sports = set(SPORT_BY_CATEGORY[SPORT_CATEGORY["TEAM"]])

    def validate_church(self, church_id: Any, participants: List[Dict]) -> List[Dict]:
        """Return team-level validation issue dicts for one church."""
        issues = []
        issues.extend(self._check_team_non_members(church_id, participants))
        issues.extend(self._check_doubles_non_members(church_id, participants))
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
    ) -> Dict[str, Any]:
        return {
            "church_id": church_id,
            "participant_id": None,
            "issue_type": issue_type,
            "issue_description": description,
            "rule_code": rule.get("rule_code"),
            "rule_level": rule.get("rule_level"),
            "severity": rule.get("severity"),
            "sport_type": sport_type,
            "sport_format": sport_format,
            "status": "open",
        }

    def _check_team_non_members(self, church_id: Any, participants: List[Dict]) -> List[Dict]:
        sport_non_members: Dict[str, List[Dict]] = {s: [] for s in self.team_sports}
        for participant in participants:
            if participant.get("is_church_member"):
                continue
            # Intentionally excludes "other_events" so exhibition entries
            # (e.g. "Soccer - Coed Exhibition") bypass the non-member team limit.
            for sport_field in ("primary_sport", "secondary_sport"):
                sport = participant.get(sport_field, "")
                if sport in sport_non_members:
                    sport_non_members[sport].append(participant)

        issues = []
        for sport, non_members in sport_non_members.items():
            if len(non_members) > self.team_limit:
                issues.append(self._build_issue(
                    church_id=church_id,
                    issue_type="team_non_member_limit",
                    description=(
                        f"{sport} has {len(non_members)} non-members, "
                        f"exceeding limit of {self.team_limit}"
                    ),
                    rule=self.team_rule,
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
