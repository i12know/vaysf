"""Canonical doubles partner resolver for VAY Sports Fest.

Resolves doubles partner declarations using a two-tier matching policy so that
TeamValidator and the scheduling workbook always produce the same confirmed/unresolved
split — eliminating the divergence that caused 12 missing validation issues in the
June 2026 nightly run (Issue #160).

Tier 1 (Confirm):   Two different participants, same event pool, unique candidate,
                    BOTH declarations match reciprocally via resolvable_name_match.
Tier 2 (Unresolved): One-sided, non-reciprocal, ambiguous, absent, or self-paired.
Tier 3 (Suggest):   likely_name_match populates hint text only; never confirms.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from validation.name_matcher import (
    normalized_name,
    resolvable_name_match,
    likely_name_match,
)


@dataclass
class Selection:
    """One participant's doubles registration in a specific event."""
    participant_id: str
    name: str
    norm_name: str
    partner_name: str
    partner_norm_name: str
    sport_type: str
    sport_format: str
    church_code: str = ""
    group_key: str = ""  # Event pool; defaults to "sport_type|sport_format" if empty


@dataclass
class ConfirmedPair:
    participant_ids: list[str]
    participant_names: dict[str, str]
    sport_type: str
    sport_format: str
    group_key: str
    churches: list[str]


@dataclass
class UnresolvedRecord:
    participant_id: str
    name: str
    church_code: str
    sport_type: str
    sport_format: str
    partner_name: str
    reason: str  # MissingPartner | SelfPaired | AmbiguousPartner | PartnerNotFound | NonReciprocal
    notes: str = ""
    candidate_name: str = ""  # For NonReciprocal: the candidate found (for hint text)
    suggestions: list[str] = field(default_factory=list)  # T3 hint names


def _gkey(sel: Selection) -> str:
    return sel.group_key or f"{sel.sport_type}|{sel.sport_format}"


def _t3_suggestions(partner_norm: str, peers: list[Selection]) -> list[str]:
    return [c.name for c in peers if likely_name_match(partner_norm, c.norm_name)]


def _make_pair(sel_a: Selection, sel_b: Selection) -> ConfirmedPair:
    return ConfirmedPair(
        participant_ids=[sel_a.participant_id, sel_b.participant_id],
        participant_names={
            sel_a.participant_id: sel_a.name,
            sel_b.participant_id: sel_b.name,
        },
        sport_type=sel_a.sport_type,
        sport_format=sel_a.sport_format,
        group_key=_gkey(sel_a),
        churches=sorted({sel_a.church_code, sel_b.church_code}),
    )


def resolve_doubles(
    selections: list[Selection],
) -> tuple[list[ConfirmedPair], list[UnresolvedRecord]]:
    """Resolve doubles partner declarations into confirmed pairs and unresolved records.

    Processing is a two-phase algorithm:
      Phase 1 — Find all confirmed pairs using T1 (exact) then T2 (resolvable) lookup
                 combined with a resolvable reciprocal check on both sides.
      Phase 2 — Diagnose every selection not in a confirmed pair and emit an
                 UnresolvedRecord with a reason code and T3 suggestion hints.

    The function is pure: it does not mutate its inputs.
    """
    # Index selections by their event pool for O(1) peer lookup.
    by_group: dict[str, list[Selection]] = {}
    for sel in selections:
        by_group.setdefault(_gkey(sel), []).append(sel)

    # Confirmation is tracked per (group_key, participant_id) so the same participant
    # can independently confirm pairs in two different event groups (e.g. Badminton
    # doubles AND Pickleball doubles in the same tournament).
    confirmed_gkpids: set[tuple[str, str]] = set()
    confirmed_pairs: list[ConfirmedPair] = []

    # ── Phase 1: find confirmed pairs ────────────────────────────────────────
    for sel in selections:
        gk = _gkey(sel)
        if (gk, sel.participant_id) in confirmed_gkpids:
            continue

        partner_norm = sel.partner_norm_name
        if not partner_norm:
            continue  # MissingPartner — handled in Phase 2
        if partner_norm == sel.norm_name:
            continue  # SelfPaired — handled in Phase 2

        # Exclude: same object, same non-empty participant_id, already confirmed
        # in this event group, or different church (cross-church pairs are never valid).
        peers_unconfirmed = [
            c for c in by_group.get(gk, [])
            if c is not sel
            and (not sel.participant_id or c.participant_id != sel.participant_id)
            and (gk, c.participant_id) not in confirmed_gkpids
            and c.church_code == sel.church_code
        ]

        # T1: exact normalized_name lookup.
        t1_cands = [c for c in peers_unconfirmed if c.norm_name == partner_norm]
        if t1_cands:
            # If T1 found anything, commit to T1 result (do not fall through to T2).
            if len(t1_cands) == 1:
                cand = t1_cands[0]
                # T1 guarantees sel→cand matches; only verify cand→sel reciprocally.
                if resolvable_name_match(cand.partner_norm_name, sel.norm_name):
                    confirmed_pairs.append(_make_pair(sel, cand))
                    confirmed_gkpids.update({(gk, sel.participant_id), (gk, cand.participant_id)})
            continue

        # T2: resolvable match (only when T1 found zero candidates).
        t2_cands = [
            c for c in peers_unconfirmed
            if resolvable_name_match(partner_norm, c.norm_name)
        ]
        if len(t2_cands) == 1:
            cand = t2_cands[0]
            if (
                resolvable_name_match(sel.partner_norm_name, cand.norm_name)
                and resolvable_name_match(cand.partner_norm_name, sel.norm_name)
            ):
                confirmed_pairs.append(_make_pair(sel, cand))
                confirmed_gkpids.update({(gk, sel.participant_id), (gk, cand.participant_id)})

    # ── Phase 2: emit unresolved records for everyone not confirmed ───────────
    unresolved: list[UnresolvedRecord] = []

    for sel in selections:
        gk = _gkey(sel)
        if (gk, sel.participant_id) in confirmed_gkpids:
            continue

        partner_norm = sel.partner_norm_name
        if not partner_norm:
            unresolved.append(UnresolvedRecord(
                participant_id=sel.participant_id,
                name=sel.name,
                church_code=sel.church_code,
                sport_type=sel.sport_type,
                sport_format=sel.sport_format,
                partner_name=sel.partner_name,
                reason="MissingPartner",
                notes="No partner declared",
            ))
            continue

        if partner_norm == sel.norm_name:
            unresolved.append(UnresolvedRecord(
                participant_id=sel.participant_id,
                name=sel.name,
                church_code=sel.church_code,
                sport_type=sel.sport_type,
                sport_format=sel.sport_format,
                partner_name=sel.partner_name,
                reason="SelfPaired",
                notes="Partner declaration matches participant's own name",
            ))
            continue

        # Use all same-church peers (including confirmed) for accurate diagnosis,
        # but still exclude rows with the same non-empty participant_id (duplicate rows).
        all_peers = [
            c for c in by_group.get(gk, [])
            if c is not sel
            and (not sel.participant_id or c.participant_id != sel.participant_id)
            and c.church_code == sel.church_code
        ]

        # T1 diagnosis.
        t1_cands = [c for c in all_peers if c.norm_name == partner_norm]
        if len(t1_cands) > 1:
            unresolved.append(UnresolvedRecord(
                participant_id=sel.participant_id,
                name=sel.name,
                church_code=sel.church_code,
                sport_type=sel.sport_type,
                sport_format=sel.sport_format,
                partner_name=sel.partner_name,
                reason="AmbiguousPartner",
                notes=f"Multiple exact matches for '{sel.partner_name}'",
            ))
            continue

        if len(t1_cands) == 1:
            cand = t1_cands[0]
            unresolved.append(UnresolvedRecord(
                participant_id=sel.participant_id,
                name=sel.name,
                church_code=sel.church_code,
                sport_type=sel.sport_type,
                sport_format=sel.sport_format,
                partner_name=sel.partner_name,
                reason="NonReciprocal",
                notes="T1: partner found but did not reciprocate",
                candidate_name=cand.name,
                suggestions=_t3_suggestions(partner_norm, all_peers),
            ))
            continue

        # T2 diagnosis.
        t2_cands = [
            c for c in all_peers
            if resolvable_name_match(partner_norm, c.norm_name)
        ]
        if len(t2_cands) > 1:
            unresolved.append(UnresolvedRecord(
                participant_id=sel.participant_id,
                name=sel.name,
                church_code=sel.church_code,
                sport_type=sel.sport_type,
                sport_format=sel.sport_format,
                partner_name=sel.partner_name,
                reason="AmbiguousPartner",
                notes=f"Multiple resolvable matches for '{sel.partner_name}'",
            ))
            continue

        if len(t2_cands) == 1:
            cand = t2_cands[0]
            unresolved.append(UnresolvedRecord(
                participant_id=sel.participant_id,
                name=sel.name,
                church_code=sel.church_code,
                sport_type=sel.sport_type,
                sport_format=sel.sport_format,
                partner_name=sel.partner_name,
                reason="NonReciprocal",
                notes="T2: partner found via resolvable match but did not reciprocate",
                candidate_name=cand.name,
                suggestions=_t3_suggestions(partner_norm, all_peers),
            ))
            continue

        # No T1 or T2 candidates: PartnerNotFound.
        unresolved.append(UnresolvedRecord(
            participant_id=sel.participant_id,
            name=sel.name,
            church_code=sel.church_code,
            sport_type=sel.sport_type,
            sport_format=sel.sport_format,
            partner_name=sel.partner_name,
            reason="PartnerNotFound",
            notes=f"No match found for '{sel.partner_name}'",
            suggestions=_t3_suggestions(partner_norm, all_peers),
        ))

    return confirmed_pairs, unresolved
