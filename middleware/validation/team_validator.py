from typing import List, Dict, Any

from .doubles_resolver import (
    Selection,
    UnresolvedRecord,
    consolidate_doubles_selections,
    resolve_doubles,
)
from .name_matcher import normalized_name
from .models import RulesManager
from config import (SPORT_BY_CATEGORY, SPORT_CATEGORY, RACQUET_SPORTS,
                   FORMAT_MAPPINGS, SPORT_FORMAT, DEFAULT_SPORT)


class TeamValidator:
    """Validates team-composition rules for a single church's participants."""

    ISSUE_TYPES = frozenset({
        "team_min_size",
        "team_non_member_limit",
        "singles_non_member_limit",
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
        self.singles_rule = next(
            r for r in rules if r.get("category") == "singles"
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
        self.singles_limit = int(self.singles_rule["value"])
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
        issues.extend(self._check_singles_non_members(church_id, participants))
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
        return normalized_name(name)

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

    def _check_singles_non_members(self, church_id: Any, participants: List[Dict]) -> List[Dict]:
        singles_non_members: Dict[str, Dict[str, List[Dict]]] = {
            sport: {} for sport in RACQUET_SPORTS
        }
        for participant in participants:
            if participant.get("is_church_member"):
                continue

            for sport_field, format_field in (
                ("primary_sport", "primary_format"),
                ("secondary_sport", "secondary_format"),
            ):
                sport = participant.get(sport_field, "")
                fmt = participant.get(format_field, "")
                if sport not in RACQUET_SPORTS:
                    continue

                fmt_type, _ = FORMAT_MAPPINGS.get(fmt, (None, None))
                if fmt_type == SPORT_FORMAT["SINGLES"]:
                    singles_non_members[sport].setdefault(fmt, []).append(participant)

        issues = []
        for sport, formats in singles_non_members.items():
            for format_name, non_members in formats.items():
                if len(non_members) > self.singles_limit:
                    issues.append(self._build_issue(
                        church_id=church_id,
                        issue_type="singles_non_member_limit",
                        description=(
                            f"{sport} {format_name} has {len(non_members)} non-members, "
                            f"exceeding limit of {self.singles_limit}"
                        ),
                        rule=self.singles_rule,
                        sport_type=sport,
                        sport_format=format_name,
                    ))
        return issues

    def _doubles_selections(self, participants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        selections: List[Dict[str, Any]] = []
        for participant in participants:
            participant_name = self._participant_name(participant)
            participant_name_key = self._normalized_name(participant_name)
            raw_selections: List[Dict[str, Any]] = []
            for sport_field, format_field, partner_field in (
                ("primary_sport", "primary_format", "primary_partner"),
                ("secondary_sport", "secondary_format", "secondary_partner"),
            ):
                sport = str(participant.get(sport_field, "") or "").strip()
                format_name = str(participant.get(format_field, "") or "").strip()
                if sport not in RACQUET_SPORTS:
                    continue

                format_type, format_gender = FORMAT_MAPPINGS.get(format_name, (None, None))
                if format_type != SPORT_FORMAT["DOUBLES"]:
                    continue

                partner_name = str(participant.get(partner_field, "") or "").strip()
                raw_selections.append({
                    "participant_id": participant.get("participant_id"),
                    "participant_name": participant_name,
                    "participant_name_key": participant_name_key,
                    "sport_type": sport,
                    "sport_format": format_name,
                    "partner_name": partner_name,
                    "_key": (sport, format_type, format_gender),
                })

            # Consolidate duplicate primary/secondary declarations of the same
            # doubles event per participant (mirroring sf_rosters consolidation)
            # so validation resolves the same selections scheduling sees (#160).
            for selection in consolidate_doubles_selections(
                raw_selections, key_fn=lambda s: s["_key"]
            ):
                selection.pop("_key", None)
                selection["partner_name"] = str(
                    selection.get("partner_name") or ""
                ).strip()
                selection["partner_name_key"] = self._normalized_name(
                    selection["partner_name"]
                )
                selections.append(selection)

        return selections

    def _check_doubles_partner_matching(
        self, church_id: Any, participants: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        if not self.reciprocal_partner_rule:
            return []

        raw_selections = self._doubles_selections(participants)
        if not raw_selections:
            return []

        # Build Selection objects; use index-based ID when participant_id is absent.
        sel_objs = [
            Selection(
                participant_id=str(s.get("participant_id") or f"_idx_{i}"),
                name=s["participant_name"],
                norm_name=s["participant_name_key"],
                partner_name=s["partner_name"],
                partner_norm_name=s["partner_name_key"],
                sport_type=s["sport_type"],
                sport_format=s["sport_format"],
            )
            for i, s in enumerate(raw_selections)
        ]

        # Map resolver IDs back to original participant_ids for _build_issue.
        original_pid_by_sel_id = {
            sel.participant_id: raw_selections[i].get("participant_id")
            for i, sel in enumerate(sel_objs)
        }

        _, unresolved = resolve_doubles(sel_objs)

        issues: List[Dict[str, Any]] = []
        for rec in unresolved:
            if rec.reason == "MissingPartner":
                continue  # Already caught by IndividualValidator.

            issues.append(self._build_issue(
                church_id=church_id,
                issue_type="doubles_partner_unmatched",
                description=self._doubles_issue_description(rec),
                rule=self.reciprocal_partner_rule,
                sport_type=rec.sport_type,
                sport_format=rec.sport_format,
                participant_id=original_pid_by_sel_id.get(rec.participant_id),
            ))

        return issues

    @staticmethod
    def _doubles_issue_description(rec: UnresolvedRecord) -> str:
        name = rec.name
        partner = rec.partner_name
        sport = rec.sport_type
        fmt = rec.sport_format

        if rec.reason == "SelfPaired":
            return (
                f"{name} listed themselves as their own partner for "
                f"{sport} ({fmt})."
            )

        if rec.reason == "NonReciprocal" and rec.notes.startswith("T1"):
            return (
                f"{name} listed {partner} as their partner for "
                f"{sport} ({fmt}), but {partner} did not "
                f"reciprocally list {name}."
            )

        if rec.reason == "NonReciprocal":
            # T2: found via resolvable match but no reciprocal — hint at full name.
            suggestion = rec.candidate_name or (rec.suggestions[0] if rec.suggestions else partner)
            return (
                f"{name} listed {partner} as their partner for "
                f"{sport} ({fmt}), but the partner name is "
                f"ambiguous; use full name, perhaps {suggestion}."
            )

        if rec.reason == "AmbiguousPartner":
            return (
                f"{name} listed {partner} as their partner for "
                f"{sport} ({fmt}), but multiple participants match that name."
            )

        # PartnerNotFound branch.
        if len(rec.suggestions) == 1:
            return (
                f"{name} listed {partner} as their partner for "
                f"{sport} ({fmt}), but the partner name is "
                f"ambiguous; use full name, perhaps {rec.suggestions[0]}."
            )
        if rec.suggestions:
            suggestion_list = ", ".join(rec.suggestions)
            return (
                f"{name} listed {partner} as their partner for "
                f"{sport} ({fmt}), but the partner name is "
                f"ambiguous; use full name. Possible matches: {suggestion_list}."
            )
        return (
            f"{name} listed {partner} as their partner for "
            f"{sport} ({fmt}), but no participant by that "
            "name was found in the same church roster."
        )
