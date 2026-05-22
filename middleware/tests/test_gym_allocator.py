"""Tests for gym_allocator.py — Layer-2, Stage A greedy gym mode allocator."""
import pytest

from gym_allocator import (
    GymBlock,
    AllocationDecision,
    AllocationResult,
    EVENT_TO_MODE,
    extract_gym_blocks,
    aggregate_demand_by_mode,
    allocate,
    _court_hours,
    _switch_penalty,
    _count_switches,
)
from config import SPORT_TYPE


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _block(gym: str, open_t: str = "08:00", close_t: str = "12:00",
           day: str = "Day-1", slot: int = 60) -> GymBlock:
    return GymBlock(gym_name=gym, day=day, open_time=open_t, close_time=close_t, slot_minutes=slot)


def _venue_row(exclusive_group: str, resource_type: str = "Gym Court",
               open_t: str = "08:00", close_t: str = "12:00",
               day: str = "Day-1", slot: int = 60) -> dict:
    return {
        "resource_id": "GYM-1",
        "resource_type": resource_type,
        "label": "Court-1",
        "day": day,
        "open_time": open_t,
        "close_time": close_t,
        "slot_minutes": slot,
        "exclusive_group": exclusive_group,
    }


# ---------------------------------------------------------------------------
# extract_gym_blocks
# ---------------------------------------------------------------------------

def test_extract_gym_blocks_deduplicates_expanded_rows():
    """Quantity-expanded rows (same block, multiple courts) collapse to one GymBlock."""
    rows = [
        _venue_row("Main Gym", open_t="08:00", close_t="12:00"),
        _venue_row("Main Gym", open_t="08:00", close_t="12:00"),
        _venue_row("Main Gym", open_t="08:00", close_t="12:00"),
    ]
    blocks = extract_gym_blocks(rows)
    assert len(blocks) == 1
    assert blocks[0].gym_name == "Main Gym"


def test_extract_gym_blocks_multiple_time_windows():
    """Different time windows for the same gym each become a separate GymBlock."""
    rows = [
        _venue_row("Orange Gym", open_t="08:00", close_t="12:00"),
        _venue_row("Orange Gym", open_t="12:00", close_t="17:00"),
    ]
    blocks = extract_gym_blocks(rows)
    assert len(blocks) == 2


def test_extract_gym_blocks_skips_no_group():
    """Rows without exclusive_group (standalone resources) are not returned."""
    rows = [
        _venue_row(""),
        _venue_row("Main Gym"),
    ]
    blocks = extract_gym_blocks(rows)
    assert len(blocks) == 1
    assert blocks[0].gym_name == "Main Gym"


def test_extract_gym_blocks_multiple_gyms():
    """Rows from distinct gyms produce distinct GymBlock objects."""
    rows = [
        _venue_row("Gym A"),
        _venue_row("Gym B"),
        _venue_row("Gym A"),   # duplicate, should be deduplicated
    ]
    blocks = extract_gym_blocks(rows)
    assert len(blocks) == 2
    assert {b.gym_name for b in blocks} == {"Gym A", "Gym B"}


# ---------------------------------------------------------------------------
# aggregate_demand_by_mode
# ---------------------------------------------------------------------------

def test_aggregate_demand_basketball_maps_to_basketball_court():
    rows = [{"Event": SPORT_TYPE["BASKETBALL"], "Estimated Court Hours": 10.0}]
    demand = aggregate_demand_by_mode(rows)
    assert demand == {"Basketball Court": 10.0}


def test_aggregate_demand_volleyball_aggregates_men_and_women():
    """VB Men + VB Women court hours sum into 'Volleyball Court'."""
    rows = [
        {"Event": SPORT_TYPE["VOLLEYBALL_MEN"],   "Estimated Court Hours": 6.0},
        {"Event": SPORT_TYPE["VOLLEYBALL_WOMEN"], "Estimated Court Hours": 4.0},
    ]
    demand = aggregate_demand_by_mode(rows)
    assert demand == {"Volleyball Court": 10.0}


def test_aggregate_demand_pickleball_aggregates_regular_and_35():
    rows = [
        {"Event": SPORT_TYPE["PICKLEBALL"],    "Estimated Court Hours": 3.0},
        {"Event": SPORT_TYPE["PICKLEBALL_35"], "Estimated Court Hours": 2.0},
    ]
    demand = aggregate_demand_by_mode(rows)
    assert demand == {"Pickleball Court": 5.0}


def test_aggregate_demand_skips_unmapped_events():
    """Unmapped events (Bible Challenge, Soccer, Track & Field) are skipped."""
    rows = [
        {"Event": SPORT_TYPE["BIBLE_CHALLENGE"], "Estimated Court Hours": 5.0},
        {"Event": SPORT_TYPE["SOCCER"],          "Estimated Court Hours": 3.0},
        {"Event": SPORT_TYPE["BASKETBALL"],      "Estimated Court Hours": 8.0},
    ]
    demand = aggregate_demand_by_mode(rows)
    assert set(demand.keys()) == {"Basketball Court"}
    assert demand["Basketball Court"] == 8.0


def test_aggregate_demand_tennis_and_table_tennis_mapped():
    """Tennis and Table Tennis can be allocated via Gym-Modes (e.g. EHS Tennis Court)."""
    rows = [
        {"Event": SPORT_TYPE["TENNIS"],          "Estimated Court Hours": 3.0},
        {"Event": SPORT_TYPE["TABLE_TENNIS"],    "Estimated Court Hours": 5.0},
        {"Event": SPORT_TYPE["TABLE_TENNIS_35"], "Estimated Court Hours": 2.0},
    ]
    demand = aggregate_demand_by_mode(rows)
    assert demand == {"Tennis Court": 3.0, "Table Tennis Table": 7.0}


def test_aggregate_demand_zero_hours_included():
    """Events with zero estimated court hours still appear in the output."""
    rows = [{"Event": SPORT_TYPE["BADMINTON"], "Estimated Court Hours": 0.0}]
    demand = aggregate_demand_by_mode(rows)
    assert "Badminton Court" in demand
    assert demand["Badminton Court"] == 0.0


def test_aggregate_demand_missing_hours_treated_as_zero():
    rows = [{"Event": SPORT_TYPE["BADMINTON"], "Estimated Court Hours": None}]
    demand = aggregate_demand_by_mode(rows)
    assert demand == {"Badminton Court": 0.0}


def test_aggregate_demand_skips_soccer_planning_only_event():
    """Soccer stays in planning workbooks but does not feed Stage-A allocator demand."""
    rows = [{"Event": SPORT_TYPE["SOCCER"], "Estimated Court Hours": 7.0}]
    demand = aggregate_demand_by_mode(rows)
    assert demand == {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def test_court_hours_basic():
    block = _block("G", open_t="08:00", close_t="12:00")
    assert _court_hours(block, 2) == pytest.approx(8.0)


def test_court_hours_zero_duration():
    block = _block("G", open_t="12:00", close_t="12:00")
    assert _court_hours(block, 3) == pytest.approx(0.0)


def test_switch_penalty_fresh_gym_is_zero():
    assert _switch_penalty("Gym A", "Basketball Court", []) == 0


def test_switch_penalty_same_mode_is_zero():
    d = AllocationDecision("Gym A", "Day-1", "08:00", "12:00", "Basketball Court", 2)
    assert _switch_penalty("Gym A", "Basketball Court", [d]) == 0


def test_switch_penalty_different_mode_is_one():
    d = AllocationDecision("Gym A", "Day-1", "08:00", "12:00", "Basketball Court", 2)
    assert _switch_penalty("Gym A", "Volleyball Court", [d]) == 1


def test_count_switches_no_switches():
    decisions = [
        AllocationDecision("G", "Day-1", "08:00", "12:00", "Basketball Court", 2),
        AllocationDecision("G", "Day-1", "12:00", "16:00", "Basketball Court", 2),
    ]
    assert _count_switches(decisions) == 0


def test_count_switches_one_switch():
    decisions = [
        AllocationDecision("G", "Day-1", "08:00", "12:00", "Basketball Court", 2),
        AllocationDecision("G", "Day-1", "12:00", "16:00", "Volleyball Court", 3),
    ]
    assert _count_switches(decisions) == 1


def test_count_switches_across_two_gyms():
    """Switches in different gyms are summed."""
    decisions = [
        AllocationDecision("G1", "Day-1", "08:00", "12:00", "Basketball Court", 2),
        AllocationDecision("G1", "Day-1", "12:00", "16:00", "Volleyball Court", 3),
        AllocationDecision("G2", "Day-1", "08:00", "12:00", "Badminton Court", 6),
        AllocationDecision("G2", "Day-1", "12:00", "16:00", "Pickleball Court", 8),
    ]
    assert _count_switches(decisions) == 2


# ---------------------------------------------------------------------------
# allocate — demand fits
# ---------------------------------------------------------------------------

def test_allocate_demand_fits_exactly():
    """One gym, one block, one mode — demand equals supply."""
    # Block: 08:00–12:00 (4 h), 2 courts → 8 court-hours
    demand = {"Basketball Court": 8.0}
    gym_modes = {"Main Gym": {"Basketball Court": 2}}
    blocks = [_block("Main Gym")]  # 08:00–12:00 = 4 h × 2 courts = 8 ch

    result = allocate(demand, gym_modes, blocks)

    assert len(result.decisions) == 1
    assert result.decisions[0].mode == "Basketball Court"
    assert result.decisions[0].courts == 2
    assert result.mode_supply["Basketball Court"] == pytest.approx(8.0)
    assert result.mode_shortfall["Basketball Court"] == pytest.approx(0.0)
    assert result.switch_count == 0


def test_allocate_demand_less_than_one_block():
    """Demand smaller than one block still claims the whole block (no partial blocks)."""
    demand = {"Basketball Court": 2.0}
    gym_modes = {"Main Gym": {"Basketball Court": 2}}
    blocks = [_block("Main Gym")]  # 4 h × 2 courts = 8 ch available

    result = allocate(demand, gym_modes, blocks)

    assert len(result.decisions) == 1
    # Supply overshoots demand (whole block claimed); shortfall is 0
    assert result.mode_supply["Basketball Court"] == pytest.approx(8.0)
    assert result.mode_shortfall["Basketball Court"] == pytest.approx(0.0)


def test_allocate_multiple_blocks_multiple_modes():
    """Two modes each get their own block from the same gym."""
    # Gym has morning (BB) and afternoon (VB) blocks
    demand = {"Basketball Court": 4.0, "Volleyball Court": 8.0}
    gym_modes = {"Arena": {"Basketball Court": 1, "Volleyball Court": 2}}
    blocks = [
        _block("Arena", open_t="08:00", close_t="12:00"),   # 4 h
        _block("Arena", open_t="12:00", close_t="16:00"),   # 4 h
    ]

    result = allocate(demand, gym_modes, blocks)

    assert len(result.decisions) == 2
    modes_assigned = {d.mode for d in result.decisions}
    assert "Basketball Court" in modes_assigned
    assert "Volleyball Court" in modes_assigned


# ---------------------------------------------------------------------------
# allocate — demand exceeds capacity
# ---------------------------------------------------------------------------

def test_allocate_demand_exceeds_capacity_reports_shortfall():
    """When no gym can supply a mode, shortfall equals demand."""
    demand = {"Soccer Field": 12.0}
    gym_modes = {"Main Gym": {"Basketball Court": 2}}   # no soccer
    blocks = [_block("Main Gym")]

    result = allocate(demand, gym_modes, blocks)

    assert len(result.decisions) == 0
    assert result.mode_shortfall["Soccer Field"] == pytest.approx(12.0)
    assert result.mode_supply["Soccer Field"] == pytest.approx(0.0)


def test_allocate_partial_coverage_reports_partial_shortfall():
    """One block covers half the demand; shortfall reflects the remainder."""
    # Demand = 16 ch, one block provides 8 ch
    demand = {"Basketball Court": 16.0}
    gym_modes = {"Main Gym": {"Basketball Court": 2}}
    blocks = [_block("Main Gym")]  # 4 h × 2 = 8 ch

    result = allocate(demand, gym_modes, blocks)

    assert result.mode_shortfall["Basketball Court"] == pytest.approx(8.0)
    assert result.mode_supply["Basketball Court"] == pytest.approx(8.0)


def test_allocate_empty_demand_returns_empty_result():
    """No demand → no decisions, no shortfall."""
    gym_modes = {"Main Gym": {"Basketball Court": 2}}
    blocks = [_block("Main Gym")]

    result = allocate({}, gym_modes, blocks)

    assert result.decisions == []
    assert result.switch_count == 0
    assert result.mode_shortfall == {}


def test_allocate_empty_blocks_returns_full_shortfall():
    """No venue blocks → full shortfall for every mode."""
    demand = {"Basketball Court": 8.0, "Volleyball Court": 4.0}
    gym_modes = {"Main Gym": {"Basketball Court": 2, "Volleyball Court": 3}}

    result = allocate(demand, gym_modes, [])

    assert result.mode_shortfall["Basketball Court"] == pytest.approx(8.0)
    assert result.mode_shortfall["Volleyball Court"] == pytest.approx(4.0)
    assert result.decisions == []


# ---------------------------------------------------------------------------
# allocate — priority ordering
# ---------------------------------------------------------------------------

def test_allocate_priority_uses_supply_pressure_not_raw_demand():
    """A tighter-supply mode can claim the earlier block even with lower raw demand."""
    # Main Gym: 2 Volleyball courts vs 1 Basketball court.
    # Morning block (4 h): Volleyball → 2×4=8 ch, Basketball → 1×4=4 ch.
    # Afternoon block (4 h): same capacities.
    # Volleyball demand (6 ch) has ample total supply (16 ch).
    # Basketball demand (4 ch) exactly matches one block of supply (8 ch total),
    # so the scarcity-aware allocator takes Basketball first and leaves Volleyball
    # the later block.
    demand = {"Volleyball Court": 6.0, "Basketball Court": 4.0}
    gym_modes = {"Main Gym": {"Basketball Court": 1, "Volleyball Court": 2}}
    blocks = [
        _block("Main Gym", open_t="08:00", close_t="12:00"),
        _block("Main Gym", open_t="12:00", close_t="16:00"),
    ]

    result = allocate(demand, gym_modes, blocks)

    vb_decisions = [d for d in result.decisions if d.mode == "Volleyball Court"]
    bb_decisions = [d for d in result.decisions if d.mode == "Basketball Court"]
    assert len(vb_decisions) >= 1
    assert len(bb_decisions) >= 1
    assert bb_decisions[0].open_time == "08:00"
    assert vb_decisions[0].open_time == "12:00"


def test_allocate_priority_order_by_demand_descending():
    """Modes with more demand are served before modes with less demand."""
    demand = {
        "Basketball Court": 20.0,
        "Volleyball Court": 5.0,
        "Badminton Court": 2.0,
    }
    # Only one block (8 ch) — only the highest-demand mode can be satisfied.
    gym_modes = {
        "Multi Gym": {
            "Basketball Court": 2,
            "Volleyball Court": 2,
            "Badminton Court": 2,
        }
    }
    blocks = [_block("Multi Gym")]  # 4 h × 2 = 8 ch

    result = allocate(demand, gym_modes, blocks)

    # The block is claimed by Basketball (highest demand).
    assert len(result.decisions) == 1
    assert result.decisions[0].mode == "Basketball Court"
    # Volleyball and Badminton have full shortfall.
    assert result.mode_shortfall["Volleyball Court"] == pytest.approx(5.0)
    assert result.mode_shortfall["Badminton Court"] == pytest.approx(2.0)


def test_allocate_prioritizes_scarcer_mode_and_preserves_flexible_gym():
    """A single-gym mode should claim the flexible gym before a multi-gym mode does."""
    demand = {"Basketball Court": 4.0, "Volleyball Court": 4.0}
    gym_modes = {
        "Gym A": {"Basketball Court": 2, "Volleyball Court": 1},
        "Gym B": {"Basketball Court": 1},
    }
    blocks = [_block("Gym A"), _block("Gym B")]

    result = allocate(demand, gym_modes, blocks)

    assert result.mode_shortfall["Basketball Court"] == pytest.approx(0.0)
    assert result.mode_shortfall["Volleyball Court"] == pytest.approx(0.0)
    assigned = {(d.gym_name, d.mode) for d in result.decisions}
    assert ("Gym A", "Volleyball Court") in assigned
    assert ("Gym B", "Basketball Court") in assigned


# ---------------------------------------------------------------------------
# allocate — structural exclusivity
# ---------------------------------------------------------------------------

def test_allocate_structural_exclusivity_no_block_assigned_twice():
    """No GymBlock appears in two AllocationDecisions."""
    demand = {"Basketball Court": 4.0, "Volleyball Court": 4.0}
    gym_modes = {"Main Gym": {"Basketball Court": 1, "Volleyball Court": 2}}
    blocks = [_block("Main Gym")]  # single block — only one mode can claim it

    result = allocate(demand, gym_modes, blocks)

    block_ids = [
        (d.gym_name, d.day, d.open_time, d.close_time)
        for d in result.decisions
    ]
    assert len(block_ids) == len(set(block_ids)), "A block was assigned to two modes"


def test_allocate_two_gyms_each_gets_one_mode():
    """Two separate gyms each get exactly one mode — zero switches."""
    demand = {"Basketball Court": 4.0, "Volleyball Court": 4.0}
    gym_modes = {
        "Gym A": {"Basketball Court": 1, "Volleyball Court": 0},
        "Gym B": {"Basketball Court": 0, "Volleyball Court": 2},
    }
    blocks = [_block("Gym A"), _block("Gym B")]

    result = allocate(demand, gym_modes, blocks)

    gym_a_modes = {d.mode for d in result.decisions if d.gym_name == "Gym A"}
    gym_b_modes = {d.mode for d in result.decisions if d.gym_name == "Gym B"}
    assert gym_a_modes == {"Basketball Court"}
    assert gym_b_modes == {"Volleyball Court"}
    assert result.switch_count == 0


# ---------------------------------------------------------------------------
# allocate — switch minimization
# ---------------------------------------------------------------------------

def test_allocate_switch_minimization_prefers_fresh_gym_over_flip():
    """When courts are equal, allocator avoids a mode flip by choosing a fresh gym."""
    # Gym A morning is already allocated to Volleyball.
    # Gym B is fresh.
    # Both gyms offer 1 Basketball Court.
    # Basketball should claim Gym B (no switch) rather than Gym A afternoon (switch).
    vb_decision = AllocationDecision(
        "Gym A", "Day-1", "08:00", "12:00", "Volleyball Court", 2
    )
    existing = [vb_decision]

    demand = {"Basketball Court": 4.0}
    gym_modes = {
        "Gym A": {"Basketball Court": 1, "Volleyball Court": 2},
        "Gym B": {"Basketball Court": 1, "Volleyball Court": 0},
    }
    # Available blocks: Gym A afternoon, Gym B morning (both 4 h × 1 court = 4 ch)
    available_blocks = [
        _block("Gym A", open_t="12:00", close_t="16:00"),
        _block("Gym B", open_t="08:00", close_t="12:00"),
    ]

    # Build result from scratch to simulate existing decisions already in place.
    # We test directly via allocate(), which starts with an empty decisions list.
    # To verify switch minimization, run allocate with Volleyball already claimed.
    result = allocate(
        {"Basketball Court": 4.0, "Volleyball Court": 8.0},
        gym_modes,
        [
            _block("Gym A", open_t="08:00", close_t="12:00"),
            _block("Gym A", open_t="12:00", close_t="16:00"),
            _block("Gym B", open_t="08:00", close_t="12:00"),
        ],
    )

    # Volleyball (8 ch) claims Gym A morning (2 courts × 4 h = 8 ch → satisfied).
    # Basketball (4 ch) should then prefer Gym B (fresh, 0 switch) over Gym A afternoon.
    bb_decisions = [d for d in result.decisions if d.mode == "Basketball Court"]
    assert len(bb_decisions) >= 1
    # Basketball should have been placed on Gym B, not Gym A
    bb_gyms = {d.gym_name for d in bb_decisions}
    assert "Gym B" in bb_gyms, (
        f"Expected Basketball to use Gym B (no switch), but got: {bb_gyms}"
    )
    assert result.switch_count == 0


def test_allocate_switch_count_single_gym_two_modes():
    """A gym whose blocks go to two different modes reports exactly one switch."""
    demand = {"Basketball Court": 4.0, "Volleyball Court": 4.0}
    gym_modes = {
        "Only Gym": {"Basketball Court": 1, "Volleyball Court": 1},
    }
    # Two blocks in the same gym, one per mode.
    blocks = [
        _block("Only Gym", open_t="08:00", close_t="12:00"),
        _block("Only Gym", open_t="12:00", close_t="16:00"),
    ]

    result = allocate(demand, gym_modes, blocks)

    # Both modes need to be served; since there is only one gym, one switch is unavoidable.
    assert result.switch_count == 1
    assert result.mode_shortfall["Basketball Court"] == pytest.approx(0.0)
    assert result.mode_shortfall["Volleyball Court"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# allocate — preferred gym selection (most courts first)
# ---------------------------------------------------------------------------

def test_allocate_prefers_gym_with_more_courts():
    """Among two eligible gyms, the one with more courts for the mode is used first."""
    demand = {"Badminton Court": 6.0}
    gym_modes = {
        "Small Gym": {"Badminton Court": 2},
        "Orange Gym": {"Badminton Court": 6},
    }
    blocks = [
        _block("Small Gym"),
        _block("Orange Gym"),
    ]

    result = allocate(demand, gym_modes, blocks)

    # Orange Gym (6 courts × 4 h = 24 ch) satisfies demand on the first block.
    assert result.decisions[0].gym_name == "Orange Gym"
    assert result.mode_shortfall["Badminton Court"] == pytest.approx(0.0)
