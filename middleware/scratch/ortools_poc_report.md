    # OR-Tools CP-SAT POC — Schema Learning Report

    **Issue:** #90
    **Sport:** Basketball Men pool play
    **Status:** Solved ✓
    **This file is a checked-in artifact from the throwaway POC. It becomes
    the input spec for #87.**

    ---

    ## Sample Schedule Output

    | Game ID | Pool | Teams | Court | Slot |
    |---------|------|-------|-------|------|
    | BBM-P1-R1-G1 | P1 | ANH vs FVC | Court-1 | Sat-1-08:00 |
| BBM-P2-R3-G1 | P2 | RPC vs TLC | Court-4 | Sat-1-08:00 |
| BBM-P1-R2-G1 | P1 | ANH vs GAC | Court-1 | Sat-1-09:00 |
| BBM-P2-R2-G1 | P2 | NSD vs TLC | Court-4 | Sat-1-09:00 |
| BBM-P2-R1-G1 | P2 | NSD vs RPC | Court-1 | Sat-1-10:00 |
| BBM-P1-R3-G1 | P1 | FVC vs GAC | Court-4 | Sat-1-10:00 |

    ---

    ## OR-Tools Constructs Used

    | Construct | Purpose |
    |-----------|---------|
    | `CpModel()` | Container for all variables and constraints |
    | `model.NewBoolVar(name)` | One variable per (game, court, slot) triple |
    | `model.NewIntVar(lo, hi, name)` | `latest_slot` objective variable |
    | `model.AddExactlyOne(literals)` | C1: each game assigned to exactly one slot/court |
    | `model.AddAtMostOne(literals)` | C2: one game per (court, slot); C3: one game per (team, slot) |
    | `model.Add(expr).OnlyEnforceIf(lit)` | Conditional bound for objective tracking |
    | `model.Minimize(var)` | Pack games toward start of day |
    | `CpSolver().Solve(model)` | Solve; check `OPTIMAL` or `FEASIBLE` status |
    | `solver.Value(var)` | Extract assignment from solved model |

    ---

    ## Input Fields the Model Actually Consumed

    From each `Game` object, the solver used:

    | Field | How the solver used it |
    |-------|------------------------|
    | `game_id` | Index key; also used as variable name suffix for debugging |
    | `team_a_id` | Team-conflict constraint (C3): no two games sharing this team in same slot |
    | `team_b_id` | Same as above |
    | `duration_minutes` | Implicitly assumed == `SLOT_MINUTES` (60 min); solver treated every game as exactly 1 slot |
    | `resource_type` | Used only to select which court pool to assign from (all courts were `"Gym Court"` here) |

    Fields that were **present in the fixture but not yet used by the model**:

    | Field | Why unused | What would need it |
    |-------|------------|--------------------|
    | `event` | Only one sport in POC | Multi-sport model: separate court pools by `resource_type` |
    | `stage` | Only pool play | Playoff model: add ordering constraints (pool must finish before playoff starts) |
    | `pool_id` | Not constrained | Could enforce all pool games finish before cross-pool matchups |

    ---

    ## What Had to Be Invented (Not in #85 Output)

    | Item | Invented value | What #87 must supply |
    |------|---------------|----------------------|
    | `team_a_id` / `team_b_id` | Hard-coded church codes | #87 must emit explicit team identifiers per game |
    | `pool_id` | Hard-coded `"P1"` / `"P2"` | #87 must emit a `pool_id` or `stage_group` field |
    | `game_id` structure | `BBM-P1-R2-G1` format (event-pool-round-game) | #87 should generate IDs in this format |
    | Slot duration in slots | Assumed `duration_minutes / SLOT_MINUTES == 1` | #87 should emit `duration_minutes`; solver divides by slot resolution |
    | Court labels | Hard-coded `["Court-1" … "Court-4"]` | Venue input (`venue_input.xlsx`) must supply labeled courts per `resource_type` |
    | Day/window | Hard-coded `Sat-1 08:00–20:00` | Venue input must supply `(day, open_time, close_time)` per resource type |

    ---

    ## Constraint Gaps Discovered

    These constraints were **not modelled** in this POC but will be needed:

    1. **Multi-slot games.** A 60-min game in a 30-min slot resolution blocks 2 consecutive slots
       on the same court. Requires either: (a) keep slot resolution = game duration (current
       approach, only works if all games in a sport have the same duration), or (b) add
       "game occupies slots t through t + n_slots_needed - 1" constraints using interval
       variables (`model.NewIntervalVar`).

    2. **Cross-sport participant conflicts.** A participant registered for both Basketball and
       Table Tennis must not have games scheduled at the same time. Requires a participant →
       games mapping, which #85/#88 produce but is not yet in any solver input.

    3. **Stage ordering.** Playoff games must be scheduled after all pool games finish.
       Requires `model.Add(playoff_slot > max_pool_slot)`.

    4. **Minimum rest between games.** A team that plays at slot T should not play again at
       slot T+1. Add: for each team, consecutive-slot pairs must not both be assigned.

    5. **Court-type routing.** Basketball games must go to `Gym Court`, racquet games to
       `Racquet Court`. Requires filtering the court pool before building variables, keyed on
       `resource_type`.

    ---

    ## Recommended #87 JSON Schema (Per Game Object)

    Based on what the model actually consumed and what it had to invent:

    ```json
    {
      "game_id":          "BBM-P1-R2-G1",
      "event":            "Basketball - Men Team",
      "stage":            "Pool",
      "pool_id":          "P1",
      "round":            2,
      "team_a_id":        "ANH",
      "team_b_id":        "GAC",
      "duration_minutes": 60,
      "resource_type":    "Gym Court",
      "earliest_slot":    null,
      "latest_slot":      null
    }
    ```

    And per venue resource:

    ```json
    {
      "resource_id":    "GYM-1",
      "resource_type":  "Gym Court",
      "label":          "Court-1",
      "day":            "Sat-1",
      "open_time":      "08:00",
      "close_time":     "20:00",
      "slot_minutes":   60
    }
    ```

    ### Field notes

    - `earliest_slot` / `latest_slot` — optional hard windows per game (e.g. a church requests
      no games before 10:00). `null` means unconstrained.
    - `round` — integer; enables stage-ordering constraints without string parsing.
    - `resource_type` — must match between game and venue resource for court-routing.
    - `pool_id` — empty string `""` for playoff / final games.

    ---

    ## Key Takeaway for #87

    The model is simple (≈ 30 lines of constraint code for 6 games × 4 courts × 12 slots).
    The hard part is not the solver — it is producing clean, typed game and venue objects
    upstream. Every field listed in "What Had to Be Invented" above is a field that #87's
    scheduling-input package must emit. The solver itself is almost mechanical once the input
    schema is right.
