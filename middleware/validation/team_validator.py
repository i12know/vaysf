# validation/team_validator.py
from typing import List, Dict, Any
from loguru import logger
from .models import RulesManager
from config import (SPORT_BY_CATEGORY, SPORT_CATEGORY, RACQUET_SPORTS,
                   FORMAT_MAPPINGS, SPORT_FORMAT)


class TeamValidator:
    """Validates team-composition rules for a single church's participants."""

    def __init__(self, collection: str = "SUMMER_2026"):
        self.rules_manager = RulesManager(collection)
        rules = self.rules_manager.get_rules_by_type("max_non_members")
        self.team_limit = int(next(
            r["value"] for r in rules if r.get("category") == "team"
        ))
        self.doubles_limit = int(next(
            r["value"] for r in rules if r.get("category") == "doubles"
        ))
        self.team_sports = set(SPORT_BY_CATEGORY[SPORT_CATEGORY["TEAM"]])

    def validate_church(self, church_id: Any, participants: List[Dict]) -> List[Dict]:
        """Return team-level validation issue dicts for one church."""
        issues = []
        issues.extend(self._check_team_non_members(church_id, participants))
        issues.extend(self._check_doubles_non_members(church_id, participants))
        return issues

    def _check_team_non_members(self, church_id: Any, participants: List[Dict]) -> List[Dict]:
        sport_non_members: Dict[str, List[Dict]] = {s: [] for s in self.team_sports}
        for p in participants:
            if p.get("is_church_member"):
                continue
            # Intentionally excludes "other_events" so exhibition entries
            # (e.g. "Soccer - Coed Exhibition") bypass the non-member team limit.
            for sport_field in ("primary_sport", "secondary_sport"):
                sport = p.get(sport_field, "")
                if sport in sport_non_members:
                    sport_non_members[sport].append(p)

        issues = []
        for sport, non_members in sport_non_members.items():
            if len(non_members) > self.team_limit:
                issues.append({
                    "church_id": church_id,
                    "participant_id": None,
                    "issue_type": "team_non_member_limit",
                    "issue_description": (
                        f"{sport} has {len(non_members)} non-members, "
                        f"exceeding limit of {self.team_limit}"
                    ),
                    "status": "open"
                })
        return issues

    def _check_doubles_non_members(self, church_id: Any, participants: List[Dict]) -> List[Dict]:
        # sport → format_name → list of non-member participants
        doubles_non_members: Dict[str, Dict[str, List[Dict]]] = {
            s: {} for s in RACQUET_SPORTS
        }
        for p in participants:
            if p.get("is_church_member"):
                continue
            for sport_field, format_field in (
                ("primary_sport", "primary_format"),
                ("secondary_sport", "secondary_format"),
            ):
                sport = p.get(sport_field, "")
                fmt = p.get(format_field, "")
                if sport not in RACQUET_SPORTS:
                    continue
                fmt_type, _ = FORMAT_MAPPINGS.get(fmt, (None, None))
                if fmt_type == SPORT_FORMAT["DOUBLES"]:
                    doubles_non_members[sport].setdefault(fmt, []).append(p)

        issues = []
        for sport, formats in doubles_non_members.items():
            for format_name, non_members in formats.items():
                if len(non_members) > self.doubles_limit:
                    issues.append({
                        "church_id": church_id,
                        "participant_id": None,
                        "issue_type": "doubles_non_member_limit",
                        "issue_description": (
                            f"{sport} {format_name} has {len(non_members)} non-members, "
                            f"exceeding limit of {self.doubles_limit}"
                        ),
                        "status": "open"
                    })
        return issues
