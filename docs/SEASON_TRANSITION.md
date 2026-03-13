# Season Transition Guide

This guide documents the process for transitioning the Sports Fest system from one year to the next (e.g., 2025 → 2026). It covers all three tiers: ChMeetings, the middleware, and WordPress.

## Understanding the Seasonal Data

Each Sports Fest season produces data across all three systems:

### ChMeetings (Source of Truth for Registration)
- **573+ people records** — these are permanent; people don't get deleted between seasons
- **"Team XXX" groups** (e.g., Team NHC, Team RPC) — contain that church's registrants **for the current season only**. These must be cleared between seasons.
- **"20XX Sports Fest" group** — contains pastor-approved participants for the season
- **"20XX Staff"** and **"20XX Volunteers & Church Reps"** groups — seasonal support groups
- **Individual Application Form responses** — sport selections, church team, roles, consent — these are per-person fields that carry over (they reflect the last submission)
- **Completion Check List** (Boxes 1–6) — Church Rep verification status per participant, set via the "Church Rep Verification" section on each person's record

### WordPress (Operations Hub)
- **sf_churches** — church records (largely stable year to year)
- **sf_participants** — synced from ChMeetings; contains sport selections, approval status
- **sf_rosters** — sport roster entries derived from participant data
- **sf_approvals** — pastor approval tokens and decisions; includes `synced_to_chmeetings` flag
- **sf_validation_issues** — eligibility issues found during validation
- **sf_sync_log** / **sf_email_log** — operational logs

### Middleware (Local Files)
- **`data/Church Application Form.xlsx`** — Excel export of church registrations from ChMeetings
- **`data/chm_group_import.xlsx`** — output from `assign-groups` (people needing Team group assignment)
- **`data/group_import_approved_participants.xlsx`** — legacy Excel output from approval sync (before v1.05 API-based sync)
- **`logs/`** — daily log files from sync operations
- **`.env`** — contains `APPROVED_GROUP_NAME` pointing to the current season's approved group

## Season Transition Checklist

### Phase 1: Archive the Previous Season

1. **Generate final reports** for all churches:
   ```bash
   python main.py export-church-teams
   ```
   Save these to the shared Google Drive for historical reference.

2. **Back up WordPress database** — export the sf_* tables before clearing.

3. **Note the current ChMeetings group structure** (for reference):
   ```bash
   python main.py test --system chmeetings --test-type api-inspect
   ```
   The groups section in the log output will list all current groups and their IDs.

### Phase 2: Reset ChMeetings Groups

4. **Clear all "Team XXX" groups** — remove all members from each church team group (e.g., Team NHC, Team RPC, etc.). These groups contained last season's registrants. The groups themselves stay; only the memberships are removed.

   > **Why:** The `assign-groups` command checks which people have a Church Team code but are NOT in their Team group. If old members remain, the script won't flag returning participants who need re-assignment, and the groups will mix seasons.

5. **Create the new season's approved group** — e.g., "2026 Sports Fest". Do NOT delete the old "2025 Sports Fest" group; keep it for historical reference.

6. **Optionally rename or archive** "2025 Staff" and "2025 Volunteers & Church Reps" groups, and create 2026 equivalents if needed.

### Phase 3: Update Middleware Configuration

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

### Phase 5: Verify and Begin New Season

12. **Test connectivity** with updated config:
    ```bash
    python main.py test --system all --test-type connectivity
    ```

13. **Verify field mappings** still match ChMeetings:
    ```bash
    python main.py test --system chmeetings --test-type api-inspect
    ```

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
    Then import the generated `chm_group_import.xlsx` into ChMeetings.

17. **Generate approvals** and **sync to ChMeetings** as pastors approve:
    ```bash
    python main.py sync --type approvals
    ```
    This now uses the API to add approved participants directly to the "2026 Sports Fest" group (no manual Excel import needed as of v1.05).

## Known Gaps / Future Improvements

- **Clearing Team groups** is currently a manual process in ChMeetings. A future middleware command could automate this using the API.
- **WordPress table reset** is manual (SQL or phpMyAdmin). A future `main.py reset-season` command could automate the truncation with confirmation prompts.
