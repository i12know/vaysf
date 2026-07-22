# Coordinator Self-Service Walkthrough: Pool Review & QF Setup

This is a **verification record**, not a design doc: a live-staging walkthrough
(2026-07-22, plugin 1.0.71 → 1.0.92) confirming that a Sports Fest coordinator
— not just a Results-Desk manager — can review their event's pools and set up
their own Quarterfinal bracket end-to-end from the Coordinator Score Entry
dashboard. See issue [#335](https://github.com/i12know/vaysf/issues/335) for
the full bug list this pass produced, and `docs/SCHEDULING.md` for how the
underlying schedule/results data model works.

No screenshots are embedded here (not currently capturable through the
testing tooling used for this pass) — every step below was reproduced and
its outcome confirmed against the live staging site.

## Who this is for

Four coordinator personas were tested, each authorized (via
`sf2025_submit_results` + per-event authorization, not Results Desk access)
for a different event on the Coordinator Score Entry dashboard
(`/coordinator-score-entry`):

- Bible Challenge coordinator
- Basketball (Men) coordinator
- Volleyball (Men) coordinator
- Volleyball (Women) coordinator

## The one intentional manager hand-off

Before any Basketball/Volleyball coordinator can set up their QF bracket, a
Sports Fest manager must confirm cross-pool QF seeding in the Results Desk
("Confirm All Pools for QF Seeding"), including resolving any coin-toss ties.
This is deliberate — per issue #329, ranking/coin-toss authority stays
Results-Desk-only — not a gap. The Coordinator dashboard's QF Setup tab says
so plainly when seeding isn't confirmed yet: *"Ask a Sports Fest manager to
confirm QF seeding for this event in the Results Desk before setting up the
bracket here."* Bible Challenge has no equivalent hand-off: a coordinator can
confirm their own Top-9 advancement directly.

Everything else — reviewing pool standings, confirming/re-confirming
advancement, previewing the QF bracket, reordering it, and applying it to the
schedule — is coordinator self-service.

## Walkthrough: Bible Challenge coordinator

1. Coordinator opens **Coordinator Score Entry → Assigned Games**, filters to
   "Bible Challenge - Mixed Team". The **Pools Progress For Review** table
   shows the pool's 14/14 scored games, the Top-9-by-cumulative-score
   ranking, and a **Review Status** of "Ready".
2. If a manager already confirmed advancement, the row shows "Confirmed by
   \<name\>" plus a **Re-confirm Top 9** button; otherwise it shows
   **Confirm Top 9**.
3. Clicking the button re-confirms (or confirms) the pool's advancement as
   the coordinator's own account, with no Results-Desk access required.
4. Confirmed outcome: pool now shows "Confirmed by Test Coordinator", and the
   page lands back on the same dashboard (not a 404).

## Walkthrough: Basketball / Volleyball coordinator

1. Manager confirms QF seeding for the event in the Results Desk (resolving
   any coin-toss ties first if the pool ranking has an unresolved cycle).
2. Coordinator opens **Coordinator Score Entry → QF Setup**. Every
   Basketball/Volleyball event the coordinator is authorized for appears on
   this one page (not just their currently-filtered event).
3. Each event shows a bracket editor: **Slot A / Slot B** dropdowns for
   QF-1..4, pre-filled with the standard 1-vs-8 / 4-vs-5 / 3-vs-6 / 2-vs-7
   seeding from the manager's confirmed Top 8, plus a live preview table
   (Expected Row → Current Schedule status → Preview Labels).
4. Coordinator may reorder any slot via the dropdowns and click
   **Update preview** to see the custom arrangement reflected (labeled
   "Custom QF assignment (this browser only); verify before applying") before
   committing to anything.
5. Clicking **Apply QF matchup to schedule** writes the arrangement into the
   `<PREFIX>-QF-1..4` schedule rows (creating them if missing) and prewires
   Semifinal/Final/3rd-Place rows with `WIN-`/`LOSE-` placeholders. Rows
   already reported/official/under-review are left untouched.
6. Confirmed outcome for all three events (Basketball-Men, Volleyball-Men,
   Volleyball-Women): QF-1..4, Semi-1/2, Final, and 3rd-Place rows all show
   `scheduled` with real schedule IDs, and the actual game listing under
   **Assigned Games** shows the correct matchup — including a coordinator's
   manual reorder (Volleyball-Men's QF-4 was flipped from the default RPC/ANH
   to ANH/RPC and the applied row reflected exactly that).

## Bugs found and fixed during this pass

All five were found by actually clicking through the coordinator flow live on
staging, not by code review, and are detailed in the CHANGELOG entries for
1.0.89 through 1.0.92:

1. **Pool-review confirm 403'd for every coordinator.** The shared
   "Re-confirm Top 9" / "Confirm Pool Review" button, rendered on both the
   Results Desk and the Coordinator dashboard, posted to a handler that only
   accepted Results-Desk-capable users — the coordinator-facing button had
   never been wired up to the broader capability 1.0.85 introduced for QF
   Setup. Fixed with `vaysf_user_can_confirm_pool_review()`.
2. **Coin toss could never actually be recorded.** `sf_coin_toss_flip`'s
   `call` column was an unquoted reserved MySQL keyword; the raw `CREATE
   TABLE` most likely failed at table-creation time, silently, with
   `DB_VERSION` bumped anyway. Renamed to `call_side`.
3. **A fatal PHP parse error**, caught during this pass before it ever went
   live: the #333 file-split had dropped the opening `/**` off a docblock in
   `playoff-preview.php`.
4. **Coordinator dashboard 404 after a successful confirm.** Its own copy of
   the pre-1.0.75 `home_url($_SERVER['REQUEST_URI'])` return-URL doubling bug
   (never updated when 1.0.75 fixed the Results Desk's copy).
5. **Cross-event false-positive validation.** Reordering one event's QF
   bracket on the QF Setup tab (which lists every authorized event on one
   page) made an unrelated event on the same page falsely report "every QF
   row needs exactly two selected teams."

## Result

As of plugin 1.0.92 on staging, all four coordinator personas complete their
own pool-review/QF-setup job end-to-end without needing a Results-Desk
account, other than the one intentional per-event seeding confirmation a
manager performs once.
