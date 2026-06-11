# tests/test_doubles_resolver.py
# Tests for the canonical doubles resolver (Issue #160).
import pytest
from validation.doubles_resolver import Selection, ConfirmedPair, UnresolvedRecord, resolve_doubles


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sel(pid, name, partner="", sport_type="Badminton", sport_format="Men Double", church="RPC"):
    from validation.name_matcher import normalized_name
    return Selection(
        participant_id=str(pid),
        name=name,
        norm_name=normalized_name(name),
        partner_name=partner,
        partner_norm_name=normalized_name(partner),
        sport_type=sport_type,
        sport_format=sport_format,
        church_code=church,
    )


def _confirmed(selections):
    pairs, _ = resolve_doubles(selections)
    return pairs


def _unresolved(selections):
    _, recs = resolve_doubles(selections)
    return recs


def _reasons(unresolved_list):
    return [r.reason for r in unresolved_list]


# ── Tier 1: exact reciprocal confirmation ────────────────────────────────────

def test_exact_reciprocal_confirms_pair():
    """A <-> B with exact names: confirmed, no unresolved."""
    sels = [
        _sel(1, "Andy Nguyen", partner="Brian Tran"),
        _sel(2, "Brian Tran", partner="Andy Nguyen"),
    ]
    pairs, unresolved = resolve_doubles(sels)
    assert len(pairs) == 1
    assert set(pairs[0].participant_ids) == {"1", "2"}
    assert unresolved == []


def test_exact_reciprocal_two_pairs():
    """Two independent exact pairs both confirmed."""
    sels = [
        _sel(1, "Andy Nguyen", partner="Brian Tran"),
        _sel(2, "Brian Tran", partner="Andy Nguyen"),
        _sel(3, "Chris Pham", partner="Dan Le"),
        _sel(4, "Dan Le", partner="Chris Pham"),
    ]
    pairs, unresolved = resolve_doubles(sels)
    assert len(pairs) == 2
    assert unresolved == []


def test_token_reorder_confirms_via_t1_resolvable_reciprocal():
    """Parenthetical alias and reordered tokens resolve via resolvable_name_match."""
    sels = [
        _sel(1, "James Nguyen", partner="Gao Shan (Gary)"),
        _sel(2, "Shan Gao", partner="James Nguyen"),
    ]
    pairs, unresolved = resolve_doubles(sels)
    assert len(pairs) == 1
    assert unresolved == []


# ── Tier 2: resolvable (initial abbreviation) confirmation ────────────────────

def test_initial_abbreviation_confirms_via_t2():
    """Vivian->Jamie S / Jamie->Vivian Tran: T2 confirm (initial 'S' for Sauveur)."""
    sels = [
        _sel(1, "Vivian Tran", partner="Jamie S", sport_type="Pickleball", sport_format="Mixed Double"),
        _sel(2, "Jamie Sauveur", partner="Vivian Tran", sport_type="Pickleball", sport_format="Mixed Double"),
    ]
    pairs, unresolved = resolve_doubles(sels)
    assert len(pairs) == 1
    assert unresolved == []


def test_t2_concat_spacing_confirms_pair():
    """'Minh Thu Bui' token-concat matches 'Minhthu Bui' via T2."""
    sels = [
        _sel(1, "Anh Vo", partner="Minh Thu Bui"),
        _sel(2, "Minhthu Bui", partner="Anh Vo"),
    ]
    pairs, unresolved = resolve_doubles(sels)
    assert len(pairs) == 1
    assert unresolved == []


# ── Self-pairing rejection ─────────────────────────────────────────────────

def test_self_paired_is_rejected():
    """A player who lists their own name as partner gets SelfPaired, not confirmed."""
    sels = [_sel(1, "Andy Nguyen", partner="Andy Nguyen")]
    _, unresolved = resolve_doubles(sels)
    assert len(unresolved) == 1
    assert unresolved[0].reason == "SelfPaired"
    assert unresolved[0].participant_id == "1"


def test_self_paired_does_not_confirm_with_bystander():
    """Even if a second participant shares the same name, self-pairing is still rejected."""
    sels = [
        _sel(1, "Andy Nguyen", partner="Andy Nguyen"),  # self-paired
        _sel(2, "Andy Nguyen", partner=""),             # same name, no partner
    ]
    _, unresolved = resolve_doubles(sels)
    reasons = _reasons(unresolved)
    assert "SelfPaired" in reasons


# ── MissingPartner ────────────────────────────────────────────────────────────

def test_missing_partner_declaration():
    """Empty partner_name produces MissingPartner."""
    sels = [_sel(1, "Cam Ho", partner="")]
    _, unresolved = resolve_doubles(sels)
    assert len(unresolved) == 1
    assert unresolved[0].reason == "MissingPartner"


# ── NonReciprocal (T1 exact found, no reciprocal) ─────────────────────────────

def test_nonreciprocal_t1_exact_found_other_claims():
    """A claims B, B claims C: A gets NonReciprocal (T1 found B but no reciprocal)."""
    sels = [
        _sel(1, "Andy Nguyen", partner="Brian Tran"),
        _sel(2, "Brian Tran", partner="Chris Pham"),
        _sel(3, "Chris Pham", partner="Brian Tran"),
    ]
    pairs, unresolved = resolve_doubles(sels)
    # B+C confirm; A is left
    assert len(pairs) == 1
    assert set(pairs[0].participant_ids) == {"2", "3"}
    assert len(unresolved) == 1
    rec = unresolved[0]
    assert rec.participant_id == "1"
    assert rec.reason == "NonReciprocal"
    assert rec.notes.startswith("T1")


def test_nonreciprocal_t1_both_sides_flagged():
    """A claims B, B claims C (C absent): both A and B get NonReciprocal or PartnerNotFound."""
    sels = [
        _sel(1, "Andy Nguyen", partner="Brian Tran"),
        _sel(2, "Brian Tran", partner="Chris Pham"),
    ]
    _, unresolved = resolve_doubles(sels)
    assert len(unresolved) == 2
    pids = {r.participant_id for r in unresolved}
    assert pids == {"1", "2"}
    reasons = _reasons(unresolved)
    assert "NonReciprocal" in reasons


# ── NonReciprocal (T2: resolvable found, no reciprocal) ──────────────────────

def test_compact_spacing_nonreciprocal_both_sides():
    """Truc Nhi Nguyen<->Minhthu Bui case: T2 finds candidate but reciprocal fails."""
    sels = [
        _sel(1, "Truc Nhi Nguyen", partner="Minh Thu Bui",
             sport_type="Badminton", sport_format="Women Double"),
        _sel(2, "Minhthu Bui", partner="Nhi Nguyen",
             sport_type="Badminton", sport_format="Women Double"),
    ]
    pairs, unresolved = resolve_doubles(sels)
    assert pairs == []
    assert len(unresolved) == 2
    # Participant 1: T2 NonReciprocal (found Minhthu Bui but Minhthu didn't reciprocate)
    rec1 = next(r for r in unresolved if r.participant_id == "1")
    assert rec1.reason == "NonReciprocal"
    assert rec1.notes.startswith("T2")
    # Participant 2: PartnerNotFound (T1/T2 can't find "Nhi Nguyen" as "Truc Nhi Nguyen")
    rec2 = next(r for r in unresolved if r.participant_id == "2")
    assert rec2.reason == "PartnerNotFound"
    # T3 suggestion for participant 2 should include Truc Nhi Nguyen
    assert "Truc Nhi Nguyen" in rec2.suggestions


# ── PartnerNotFound ───────────────────────────────────────────────────────────

def test_partner_not_found_no_suggestions():
    """Listed partner name with no likely matches: PartnerNotFound, no suggestions."""
    sels = [
        _sel(1, "Andy Nguyen", partner="Zara Kowalski"),
        _sel(2, "Brian Tran", partner="Andy Nguyen"),
    ]
    _, unresolved = resolve_doubles(sels)
    andy_rec = next(r for r in unresolved if r.participant_id == "1")
    assert andy_rec.reason == "PartnerNotFound"
    assert andy_rec.suggestions == []


def test_partner_not_found_one_t3_suggestion():
    """Short name 'Janice' can't resolvably match 'Janice Vu' but likely_name_match gives suggestion."""
    sels = [
        _sel(1, "Dean Nguyen", partner="Janice",
             sport_type="Tennis", sport_format="Mixed Double"),
        _sel(2, "Janice Vu", partner="Dean Nguyen",
             sport_type="Tennis", sport_format="Mixed Double"),
    ]
    _, unresolved = resolve_doubles(sels)
    dean_rec = next(r for r in unresolved if r.participant_id == "1")
    assert dean_rec.reason == "PartnerNotFound"
    assert "Janice Vu" in dean_rec.suggestions


def test_partner_not_found_multiple_t3_suggestions():
    """'Janice' with two Janices → PartnerNotFound, both in suggestions."""
    sels = [
        _sel(1, "Dean Nguyen", partner="Janice",
             sport_type="Pickleball", sport_format="Mixed Double"),
        _sel(2, "Janice Vu", partner="",
             sport_type="Pickleball", sport_format="Mixed Double"),
        _sel(3, "Janice Nguyen", partner="",
             sport_type="Pickleball", sport_format="Mixed Double"),
    ]
    _, unresolved = resolve_doubles(sels)
    dean_rec = next(r for r in unresolved if r.participant_id == "1")
    assert dean_rec.reason == "PartnerNotFound"
    assert "Janice Vu" in dean_rec.suggestions
    assert "Janice Nguyen" in dean_rec.suggestions


# ── AmbiguousPartner ──────────────────────────────────────────────────────────

def test_ambiguous_t1_multiple_exact_name_matches():
    """When a player's partner name matches multiple participants and none reciprocate: AmbiguousPartner."""
    sels = [
        _sel(1, "Andy Nguyen", partner="Brian Tran"),  # ambiguous: 2 Brians
        _sel(2, "Brian Tran", partner="Chris Pham"),   # Brian 2 does not list Andy
        _sel(3, "Brian Tran", partner="Dan Le"),       # Brian 3 does not list Andy
    ]
    _, unresolved = resolve_doubles(sels)
    andy_rec = next(r for r in unresolved if r.participant_id == "1")
    assert andy_rec.reason == "AmbiguousPartner"


# ── Group isolation ───────────────────────────────────────────────────────────

def test_different_sport_types_do_not_interfere():
    """Pairs in different sport_types are resolved independently."""
    sels = [
        _sel(1, "Andy Nguyen", partner="Brian Tran", sport_type="Badminton", sport_format="Men Double"),
        _sel(2, "Brian Tran", partner="Andy Nguyen", sport_type="Badminton", sport_format="Men Double"),
        _sel(3, "Andy Nguyen", partner="Brian Tran", sport_type="Tennis", sport_format="Men Double"),
        _sel(4, "Brian Tran", partner="Andy Nguyen", sport_type="Tennis", sport_format="Men Double"),
    ]
    pairs, unresolved = resolve_doubles(sels)
    assert len(pairs) == 2
    assert unresolved == []


def test_different_sport_formats_do_not_interfere():
    """Men Double and Women Double are separate pools."""
    sels = [
        _sel(1, "Andy Nguyen", partner="Brian Tran", sport_format="Men Double"),
        _sel(2, "Brian Tran", partner="Andy Nguyen", sport_format="Women Double"),
    ]
    _, unresolved = resolve_doubles(sels)
    # Cannot pair across formats → both unresolved
    assert len(unresolved) == 2


# ── Cross-church confirmation ──────────────────────────────────────────────────

def test_confirmed_pair_records_both_churches():
    """Confirmed cross-church pair carries both church codes."""
    sels = [
        _sel(1, "Andy Nguyen", partner="Brian Tran", church="RPC"),
        _sel(2, "Brian Tran", partner="Andy Nguyen", church="TLC"),
    ]
    pairs, _ = resolve_doubles(sels)
    assert len(pairs) == 1
    assert "RPC" in pairs[0].churches
    assert "TLC" in pairs[0].churches


# ── Already-confirmed exclusion in Phase 1 ───────────────────────────────────

def test_already_confirmed_not_re_paired():
    """Once B is confirmed with C, A's claim on B yields NonReciprocal not confirmation."""
    sels = [
        _sel(1, "Andy Nguyen", partner="Brian Tran"),  # tries to claim B
        _sel(2, "Brian Tran", partner="Chris Pham"),   # B confirms with C
        _sel(3, "Chris Pham", partner="Brian Tran"),   # C confirms with B
    ]
    pairs, unresolved = resolve_doubles(sels)
    assert len(pairs) == 1
    assert set(pairs[0].participant_ids) == {"2", "3"}
    assert len(unresolved) == 1
    assert unresolved[0].participant_id == "1"


# ── group_key override ────────────────────────────────────────────────────────

def test_group_key_overrides_sport_fields():
    """When group_key is set, only participants with the same key compete."""
    from validation.name_matcher import normalized_name
    sels = [
        Selection(
            participant_id="1", name="A", norm_name=normalized_name("A"),
            partner_name="B", partner_norm_name=normalized_name("B"),
            sport_type="Badminton", sport_format="Men Double",
            group_key="group-X",
        ),
        Selection(
            participant_id="2", name="B", norm_name=normalized_name("B"),
            partner_name="A", partner_norm_name=normalized_name("A"),
            sport_type="Badminton", sport_format="Men Double",
            group_key="group-Y",  # Different group: cannot pair with sel 1.
        ),
    ]
    _, unresolved = resolve_doubles(sels)
    assert len(unresolved) == 2


# ── Regression: Bug 1 — multi-event participant ──────────────────────────────

def test_same_participant_confirms_in_two_independent_event_groups():
    """Participant 1 plays Badminton (with 2) AND Pickleball (with 3).
    Confirming in Badminton must not swallow the Pickleball selection.
    """
    sels = [
        _sel(1, "Andy Nguyen", partner="Brian Tran",   sport_type="Badminton",  sport_format="Men Double"),
        _sel(2, "Brian Tran",  partner="Andy Nguyen",  sport_type="Badminton",  sport_format="Men Double"),
        _sel(1, "Andy Nguyen", partner="Chris Pham",   sport_type="Pickleball", sport_format="Mixed Double"),
        _sel(3, "Chris Pham",  partner="Andy Nguyen",  sport_type="Pickleball", sport_format="Mixed Double"),
    ]
    pairs, unresolved = resolve_doubles(sels)

    assert len(pairs) == 2, f"Expected 2 confirmed pairs, got {len(pairs)}: {pairs}"
    group_keys = {p.group_key for p in pairs}
    assert "Badminton|Men Double" in group_keys
    assert "Pickleball|Mixed Double" in group_keys
    assert unresolved == []


# ── Regression: Bug 2 — duplicate-PID rows cannot self-pair ──────────────────

def test_duplicate_participant_id_rows_never_form_a_confirmed_pair():
    """Two distinct roster rows with the same non-empty participant_id must never
    produce a confirmed pair whose participant_ids list contains duplicates.
    """
    from validation.name_matcher import normalized_name

    # Simulate a bad export where the same PID appears on two rows with names
    # that would otherwise match each other's partner declarations.
    dup_pid = "42"
    sels = [
        Selection(
            participant_id=dup_pid,
            name="Andy Nguyen",
            norm_name=normalized_name("Andy Nguyen"),
            partner_name="Brian Tran",
            partner_norm_name=normalized_name("Brian Tran"),
            sport_type="Badminton",
            sport_format="Men Double",
        ),
        Selection(
            participant_id=dup_pid,
            name="Brian Tran",
            norm_name=normalized_name("Brian Tran"),
            partner_name="Andy Nguyen",
            partner_norm_name=normalized_name("Andy Nguyen"),
            sport_type="Badminton",
            sport_format="Men Double",
        ),
    ]
    pairs, unresolved = resolve_doubles(sels)

    # No confirmed pair should have duplicate IDs.
    for pair in pairs:
        assert len(set(pair.participant_ids)) == len(pair.participant_ids), (
            f"Pair with duplicate IDs formed: {pair.participant_ids}"
        )
    # Both rows should be reported as unresolved (PartnerNotFound since same-ID
    # peers are excluded from candidate lookups).
    assert len(unresolved) == 2
