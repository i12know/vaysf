# Season Transition Guide

This guide documents the process for transitioning the Sports Fest system from one year to the next (e.g., 2025 → 2026). It covers all three tiers: ChMeetings, the middleware, and WordPress.

## Understanding the Seasonal Data

Each Sports Fest season produces data across all three systems:

### ChMeetings (Source of Truth for Registration)
- **573+ people records** — these are permanent; people don't get deleted between seasons
- **"Team XXX" groups** (e.g., Team NHC, Team RPC) — contain that church's registrants **for the current season only**. These must be cleared between seasons.
- **"20XX Sports Fest" group** — contains pastor-approved participants for the season
- **"20XX Staff"** and **"20XX Volunteers & Church Reps"** groups — seasonal support groups
- **Church Application Form responses** — Church rep's application form for each church team with pastor contact info, etc. — these are per-church fields that carry over (they reflect the last submission, and need to be reviewed, cleanup, and transfer/correct Google Shared Folder link for each church reps)
- **Individual Application Form responses** — sport selections, church team, roles, consent — these are per-person fields that carry over (they reflect the last submission, and need to be cleanup before a new season)
- **Consent Form submissions** — old submission records should be cleared before the new season opens so the 2026/2027 form inbox starts clean
- **Completion Check List** (Boxes 1–6) — Church Rep verification status per participant, set via the "Church Rep Verification" section on each person's record, and need to be archived and reset by the middleware

### WordPress (Operations Hub)
- **sf_churches** — church records (largely stable year to year), need to be reloaded from Church Application Form
- **sf_participants** — synced from ChMeetings; contains sport selections, approval status, need to be reset.
- **sf_rosters** — sport roster entries derived from participant data, need to be reset.
- **sf_approvals** — pastor approval tokens and decisions; includes `synced_to_chmeetings` flag, need to be reset.
- **sf_validation_issues** — eligibility issues found during validation, need to be reset.
- **sf_sync_log** / **sf_email_log** — operational logs, need to be reset.

### Middleware (Local Files)
- **`data/Church Application Form.xlsx`** — Excel export of church registrations from ChMeetings, need to be replaced every year
- **`data/chm_group_import.xlsx`** — output from `assign-groups` (people needing Team group assignment)
- **`data/group_import_approved_participants.xlsx`** — legacy Excel output from approval sync (before v1.05 API-based sync)
- **`logs/`** — daily log files from sync operations, need to be reset - perhaps keep one comprehensive run from the prior year just in case comparision is needed.
- **`.env`** — contains `APPROVED_GROUP_NAME` pointing to the current season's approved group

## Season Transition Checklist

### Phase 1: Archive the Previous Season

1. **Generate final reports** for all churches:
   ```bash
   python main.py export-church-teams
   ```
   Save these to the shared Google Drive for historical reference.

2. **Archive and reset all Sports Fest custom fields** on every VAY-SM member:
   ```bash
   python main.py reset-season --year 2025
   ```
   This writes a structured archive note to each person's ChMeetings profile and
   clears all Sports Fest and Church Rep Verification fields in one pass.
   See [USAGE.md — Season Reset](USAGE.md#season-reset-year-end-archive-and-field-clear)
   for the recommended single-person and small-group test steps before running on
   the full VAY-SM group.

3. **Back up WordPress database** — export the sf_* tables before clearing.

4. **Note the current ChMeetings group structure** (for reference):
   ```bash
   python main.py test --system chmeetings --test-type api-inspect
   ```
   The groups section in the log output will list all current groups and their IDs.

### Phase 2: Reset ChMeetings Groups

4. **Clear all "Team XXX" groups** — remove all members from each church team group (e.g., Team NHC, Team RPC, etc.). These groups contained last season's registrants. The groups themselves stay; only the memberships are removed.

   Recommended sequence:
   ```bash
   python main.py clear-team-groups --church-code RPC --dry-run
   python main.py clear-team-groups --church-code RPC --execute
   python main.py clear-team-groups --dry-run
   python main.py clear-team-groups --execute
   ```

   Operational note from 2026 testing: clearing a Team group removes the member list, but any assigned **Group Leaders** remain attached to that group. That is the desired behavior — do not treat remaining Group Leaders as a failed cleanup.

   > **Why:** The `assign-groups` command checks which people have a Church Team code but are NOT in their Team group. If old members remain, the script won't flag returning participants who need re-assignment, and the groups will mix seasons.

5. **Create the new season's approved group** — e.g., "2026 Sports Fest". Do NOT delete the old "2025 Sports Fest" group; rename it "x 2025 Sports Fest" for historical reference.

6. **Optionally rename or archive** "2025 Staff" and "2025 Volunteers & Church Reps" groups, and create 2026 equivalents if needed.

7. **Prepare the ChMeetings forms for the new season**:
   - Enable the **Church Application Form** so church reps can begin signing up for the new season
   - As new church application records come in, transfer forward any church-specific operational data that is not re-entered cleanly each year, especially Google Shared Folder links and similar admin notes
   - After the needed information is transferred, clear the old Church Application Form records so the active list reflects only the new season
   - Clear old submission records from the **Individual Application Form**
   - Clear old submission records from the **Consent Form**

### Phase 3: Update Middleware Configuration

IMPORTANT DEV. NOTE: Since ChMeetings are in active development, it would be wise to spend a week upgrading the system to take advantage of the new capability from them.

7. **Update `.env`**:
   ```
   APPROVED_GROUP_NAME=2026 Sports Fest
   ```

8. **Create new validation rules** — copy and update the rules file:
   - Copy `validation/summer_2025.json` → `validation/summer_2026.json`
   - Update `metadata.version`, `metadata.collection`, `metadata.event_date`, `metadata.description`
   - Review and adjust any rule values (age limits, sport changes, etc.)
   - Update `config.py` to reference the new rules file

9. **Update `SPORTS_FEST_DATE`** in `config.py` if it exists, or the event date used for age calculations.

10. **Clear old data files** (optional):
    - Archive `data/chm_group_import.xlsx` and `data/group_import_approved_participants.xlsx`
    - Old logs can be archived or left in place (they rotate automatically)

### Phase 4: Reset WordPress Data

11. **Clear seasonal WordPress tables** — the following tables contain per-season data and should be truncated or archived for the new season:
    - `sf_participants` — will be re-populated from ChMeetings sync
    - `sf_rosters` — will be re-created from participant sport selections
    - `sf_approvals` — new approval tokens will be generated
    - `sf_validation_issues` — will be re-created during validation
    - `sf_email_log` — can be cleared or archived

    > **Note:** `sf_churches` can usually be kept, since churches tend to return. Update the Church Application Form Excel and re-sync if church details change.

    Operational note from the 2026 reset:
    - If you want a completely clean season start, it is safe to truncate `sf_churches` too, then immediately reload churches from the latest `Church Application Form.xlsx`
    - Do **not** try to import the Excel file directly with phpMyAdmin; the sheet columns do not map cleanly to the WordPress table schema
    - Preferred reload command:
      ```bash
      cd middleware
      python main.py sync-churches --file "data/Church Application Form.xlsx"
      ```
    - Verified on 2026-05-02: after truncating the Sports Fest tables, this command recreated 19 churches with `created=19, updated=0, errors=0`

### Phase 5: Verify and Begin New Season

NOTE: At this point, Admin manually create the new season group ("2026 Sports Fest"), set up the initial Group Leaders for it, then rename the old Sports Fest group with an "x" prefix for archival. (ChMeetings listed groups by alphabetical order so "x 2025 Sports Fest" would fell off to the bottom of the group list.)

12. **Test connectivity** with updated config:
    ```bash
    python main.py test --system all --test-type connectivity
    ```

13. **Verify field mappings** still match ChMeetings:
    ```bash
    python main.py test --system chmeetings --test-type api-inspect
    ```

    Current 2026 checkpoint from the 2026-05-02 live inspect:
    - `Primary Sport` includes `Table Tennis 35+` as option_id `330427`
    - `Secondary Sport` includes `Table Tennis 35+` as option_id `330428`

    If the form changes again for 2027, update `middleware/config.py` before the
    first participant sync or WordPress DB insertion test. Do not assume these
    option IDs are stable across field recreation.

14. **Sync churches** from the new season's Excel:
    ```bash
    python main.py sync-churches --file "data/Church Application Form.xlsx"
    ```

15. **Begin participant syncs** as registrations come in:
    ```bash
    python main.py sync --type participants
    ```

16. **Run group assignments** periodically to add new registrants to their Team groups:
    ```bash
    python main.py assign-groups
    ```
    This now uses the API directly and writes `church_team_assignments.xlsx` as an audit log. No manual ChMeetings import is needed.

17. **Generate approvals** and **sync to ChMeetings** as pastors approve:
    ```bash
    python main.py sync --type approvals
    ```
    This now uses the API to add approved participants directly to the "2026 Sports Fest" group (no manual Excel import needed as of v1.05).

## Admin Operator Notes

Use this section as the living runbook for tedious or easy-to-forget season rollover steps discovered during a real transition. Keep entries practical and operator-facing.

Suggested format for each note:

- **When it applies** - what phase, screen, or trigger caused this step
- **What to do** - the exact manual action in ChMeetings, WordPress, or local middleware
- **Why it matters** - what breaks or becomes confusing if skipped
- **How to verify** - the quick check that confirms the step worked

Starter checklist for future notes:

- ChMeetings screens or filters that were non-obvious during the rollover
- Group cleanup steps that are safe to repeat and steps that are not
- Manual prerequisites that must happen before running `reset-season`
- Manual prerequisites that must happen before the first `sync --type participants`
- WordPress cleanup or backup steps that were easy to miss
- Any one-time 2026 lessons that should become permanent process notes for 2027+

Current 2026 lesson to preserve:

- **When it applies** - right after ChMeetings form edits and before the first live participant sync of a new season
- **What to do** - run `python main.py test --system chmeetings --test-type api-inspect` and confirm that any newly added sport choices appear in the live `Primary Sport` and `Secondary Sport` option lists
- **Why it matters** - the middleware maps ChMeetings dropdown option IDs in `middleware/config.py`; if ChMeetings recreates or renumbers options, sync can silently drift from the registration form
- **How to verify** - compare the live option IDs in the inspect output against `SF_PRIMARY_SPORT_OPTIONS` and `SF_SECONDARY_SPORT_OPTIONS`; for 2026, `Table Tennis 35+` was confirmed as `330427` / `330428`

- **When it applies** - right after truncating/resetting the seasonal WordPress tables for a brand-new season
- **What to do** - reload churches through the middleware with `python main.py sync-churches --file "data/Church Application Form.xlsx"`
- **Why it matters** - phpMyAdmin imports the spreadsheet poorly because the church application columns are not a clean 1:1 match for `sf_churches`; the middleware already knows how to map the Excel into WordPress correctly
- **How to verify** - the sync log should show each church as `Creating church XYZ` on a clean DB and finish with zero errors; in 2026 the first clean reload created 19 churches successfully

- **When it applies** - after the previous season is archived and before opening registration for the next season
- **What to do** - enable the new season's Church Application Form, transfer forward any important per-church admin details from old records into the new church records, then clear old Church Application, Individual Application, and Consent Form submission records
- **Why it matters** - ChMeetings form submission lists otherwise stay cluttered with stale season data, and some operational details like Google Shared Folder links may be lost if they are not copied forward before cleanup
- **How to verify** - the Church Application Form shows only current-season church submissions, the old per-church notes have been copied where needed, and the Individual/Consent form submission lists are empty before the first new-season registrations arrive

## Known Gaps / Future Improvements

- **WordPress table reset** is manual (SQL or phpMyAdmin). A future command could automate the truncation with confirmation prompts.
