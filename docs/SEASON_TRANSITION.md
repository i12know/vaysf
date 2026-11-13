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

### Phase 0: ChMeetings platform review

ChMeetings ships a release every two to three weeks, and `vaysf` sits idle for
most of the year. In the 2025–2026 off-season nobody was watching: ChMeetings
changed its API over the winter and the 2026 season opened with 77 commits of
repair (see [RETROSPECTIVE_2025.md](RETROSPECTIVE_2025.md), Act IV). Phase 0 is
the watch. It changes no data, so it is safe to run at any time.

**When to run it — twice a year:**

1. **After the season ends** (August), while the season's behaviour is still
   fresh and before the archive in Phase 1.
2. **About six weeks before registration opens**, so there is time to fix
   whatever it finds before Phase 3.

**What to do:**

1. **Read the release notes since the last review.** Start from the version in
   the last row of the review record below and read forward at
   <https://www.chmeetings.com/release-notes/>. The current version is shown in
   the ChMeetings app (on the Dashboard page as of 2026-11-13). Release notes are published
   per release (for example `2026.22`), not per patch (`2026.22.7.3`). Look
   for anything about the API, webhooks, forms and form exports, groups,
   people profile fields, merging or archiving people, families, messaging,
   rate limits, authentication and pagination.
2. **Refresh and diff the OpenAPI snapshot.** Download
   <https://api.chmeetings.com/openapi/v1.json>, diff it against
   `chmeetings_openapi_v1.json` at the repo root, and commit the new snapshot
   in its own commit with the diff summarised in the message. Check, in this
   order: removed operations; changed required parameters or request bodies on
   the endpoints the connector calls (`middleware/chmeetings/backend_connector.py`);
   renamed response schemas; then new capabilities. The Scalar reference at
   <https://api.chmeetings.com/scalar> is rendered from that same file.
3. **Re-read the two help articles that state API behaviour:** the
   [Developer API Guide](https://help.chmeetings.com/hc/en-us/articles/4407466673937-Developer-API-Guide)
   (rate limit, authentication) and
   [Configure Webhooks](https://help.chmeetings.com/hc/en-us/articles/22970829186204-Configure-Webhooks).
   If the rate limit changed, update `CHM_MIN_REQUEST_INTERVAL_SECONDS` and the
   comment above it in the connector.
4. **Run the live checklist** below against the VAY SM tenant.
5. **Record the result** as a new row in the review record, and add a dated
   note to [CHMEETINGS_API_MIGRATION.md](CHMEETINGS_API_MIGRATION.md) for every
   confirmed change in API behaviour. Mark anything not yet confirmed as
   "to verify live". If the review changes a convention shared with the other
   ChMeetings projects, open a PR against the
   [vay-chmeetings skill](https://github.com/i12know/vay-chmeetings-skill) too.

#### Live checklist (maintainer only — needs the VAY SM API key)

Run from `middleware\`. Steps 1–4 only read. Nothing here prints participant
names, emails or phone numbers except `api-inspect`, which writes two sample
people to the local log (`middleware/logs/` is gitignored — do not paste that
output into an issue or PR).

1. **Connectivity and authentication**

   ```bash
   python main.py test --system chmeetings --test-type connectivity
   ```

   Pass: the log shows `API key verified successfully with ChMeetings API` and
   `Successfully connected to ChMeetings`. A `401` means the key or the
   lowercase `apikey` header is no longer accepted.

2. **Field inspector**

   ```bash
   python main.py test --system chmeetings --test-type api-inspect
   ```

   Pass, all of:
   - every line under `FIELD MAPPING VALIDATION` is `OK`, ending with
     `All CHM_FIELDS matched successfully.` — no `MISSING`, `NOT OBSERVED` or
     `NOT CHECKED`. (`NOT OBSERVED` on `nick_name` means the Nickname profile
     field was switched off in Account Settings; ChMeetings omits disabled
     fields from the response instead of returning null.)
   - the field IDs and option IDs printed under `FIELD DEFINITIONS` match
     `SF_FIELD_IDS`, `SF_CHURCH_TEAM_OPTIONS`, `SF_PRIMARY_SPORT_OPTIONS`,
     `SF_SECONDARY_SPORT_OPTIONS` and `SF_IS_MEMBER_OPTION_IDS` in
     `middleware/config.py`;
   - each sample `additional_fields` item has `field_id`, `field_name`,
     `field_type` and `value` (participant mapping reads `field_name` and
     `value`);
   - the `GROUPS` list contains every `Team XXX` group and the season's
     approved group.

3. **Connector tests against the live API** (write tests stay skipped)

   ```bash
   set LIVE_TEST=true && pytest tests/test_chmeetings_connector.py -v -s
   ```

   Pass: no failures.

4. **Read-only sample of every endpoint the connector uses.** Start `python`
   in `middleware\` and paste:

   ```python
   from chmeetings.backend_connector import ChMeetingsConnector
   from config import Config

   c = ChMeetingsConnector()

   def get(path, **params):
       r = c._api_request("GET", path, params=params or None)
       limits = {k: v for k, v in r.headers.items()
                 if "rate" in k.lower() or k.lower() == "retry-after"}
       print(f"{r.status_code} GET {path} rate-headers={limits}")
       try:
           return r.json()
       except ValueError:
           return None

   base = dict(include_additional_fields=True, include_family_members=False,
               include_organizations=False)

   # A. People list and paging
   b = get("api/v1/people", page=1, page_size=2, **base)
   print(sorted(b), b["paging"])
   person = b["data"][0]
   print(sorted(person))

   # B. Field definitions
   f = get("api/v1/people/fields")["data"]
   print([(s.get("section_id"), s.get("title"), len(s.get("fields", [])))
          for s in f["sections"]])
   print(sorted(f["sections"][0]["fields"][0]))

   # C. Groups (not paged) and the search_text filter
   g = get("api/v1/groups")["data"]
   print(len(g), sorted(g[0]))
   teams = [x for x in g if x["name"].startswith(Config.TEAM_PREFIX + " ")]
   print(len(teams), "team groups;", Config.APPROVED_GROUP_NAME, "present:",
         any(x["name"] == Config.APPROVED_GROUP_NAME for x in g))
   print(len(get("api/v1/groups", search_text=Config.TEAM_PREFIX)["data"]),
         "groups via search_text")

   # D. Group members
   m = get("api/v1/groups/people", group_ids=teams[0]["id"])["data"]
   print(len(m), sorted(m[0]) if m else "empty group")

   # E. One person, the fields a PUT must round-trip, and their notes
   pid = person["id"]
   p = get(f"api/v1/people/{pid}")["data"]
   print(sorted(p))
   print([k for k in ("nick_name", "native_name", "job_title", "school",
                      "qualification", "education_level", "church",
                      "father_name", "talents_and_hobbies") if k in p])
   n = get(f"api/v1/people/{pid}/notes", page=1, page_size=5)
   print(sorted(n), len(n["data"]))

   # F. A person ID that does not exist
   print(get("api/v1/people/999999999"))

   # G. Key scope, webhook events, and the newer people filters
   print([(o["type"], o["name"])
          for o in get("api/v1/organizations", page=1, page_size=100)["data"]])
   print(get("api/v1/integrations/webhooks/events"))
   x = get("api/v1/people", page=1, page_size=2, person_ids=pid,
           include_groups=True, **base)
   print(x["paging"], "groups" in x["data"][0])
   c.close()
   ```

   Pass, per block:
   - **A** — `200`; top-level keys include `data` and `paging`; `paging` has
     `total_count`, `page`, `page_size`; the person has `id`, `first_name`,
     `last_name`, `email`, `mobile`, `birth_date`, `gender`, `photo`,
     `additional_fields`.
   - **B** — `200`; the `Sports Fest` and `Church Rep Verification` sections
     are listed; a field has `field_id`, `field_name`, `field_type`, `options`.
   - **C** — `200`; each group has `id` and `name`; the team-group count
     matches the number of church teams; the approved group is present. The
     `search_text` call returning at least as many groups as there are teams
     confirms the filter added in 2026.
   - **D** — `200`; each member has `person_id`, `first_name`, `last_name`,
     `email`, `mobile`, `group_id`.
   - **E** — `200`; note which of the listed keys come back. Every key that is
     set on the profile but **not** returned here cannot be preserved by
     `update_person()`, because `PUT /people/{id}` is a full replacement.
     Notes: `200`, top-level `data` is a list.
   - **F** — `404` with a JSON body. Record the body text. This is the same
     response a merged, deleted or other-tenant person gives, so it must never
     be read as "deleted".
   - **G** — organizations lists only VAY SM and its ministries (a diocese or
     sibling church here means the wrong key is in `CHM_API_KEY`); the webhook
     events list is recorded in the review; the last line prints a
     `total_count` of `1` and `True`.
   - **Rate limit** — no `429` during the run. Record any rate-limit header
     names that appear.

5. **Optional write checks — test person and test group only.** Run these when
   the review found a change to `PUT /people/{id}` or to group memberships.

   ```bash
   python main.py reset-season --year 2026 --person-id <TEST_PERSON_ID> --probe
   ```

   Pass: probes P1–P3 return `200`, and the test person's profile is unchanged
   afterwards (compare standard fields such as job title and school as well as
   the Sports Fest fields).

   The group membership round trip is the gated live test in
   [CHMEETINGS_API_MIGRATION.md](CHMEETINGS_API_MIGRATION.md#live-round-trip-test)
   (Change #4). Pass: `201` on add, `200` on remove.

6. **Operator screens (browser).** Open the Individual Application Form and
   Consent Form submission lists. Pass: the form IDs in
   `middleware/chrome_export_vaysf_forms.py` still open the right forms, the
   page has an `Export` button, and it opens an `Export Submissions` dialog
   with a `Download` button. Then confirm the form settings that are decided
   per season (for 2027: automatic profile creation stays **off**, see #351).

#### Review record

| Date | Reviewed through | Spec snapshot | Live checklist | Result | Record |
|---|---|---|---|---|---|
| 2026-11-13 | ChMeetings 2026.22 (tenant showed v2026.22.7.3); release notes read from 2026.1 | Refreshed 2026-11-13: 64 → 110 paths, nothing removed | Step 6 passed in the tenant; steps 1–5 not yet run | No breaking change found in the published spec or release notes for the endpoints `vaysf` calls. Open items are listed in the record. | [PR #401](https://github.com/i12know/vaysf/pull/401) — first Phase 0 review: ranked risks, full API change list, inventory |

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

IMPORTANT DEV. NOTE: Since ChMeetings are in active development, it would be wise to spend a week upgrading the system to take advantage of the new capability from them. The Phase 0 review above is where those new capabilities, and any breaking changes, are found and recorded.

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
    - `sf_participants` — will be re-populated from ChMeetings sync (`membership_claim_at_approval` resets to NULL automatically when the table is truncated — see note below)
    - `sf_rosters` — will be re-created from participant sport selections
    - `sf_approvals` — new approval tokens will be generated
    - `sf_validation_issues` — will be re-created during validation
    - `sf_email_log` — can be cleared or archived

    > **`membership_claim_at_approval` is per-season and resets with `sf_participants`.**
    > Added in v1.10 (Issue #78), this column freezes each participant's self-reported membership
    > claim at the moment the pastor approval email is sent. Truncating `sf_participants` discards
    > all frozen values along with the rest of the rows; new tokens in the next season re-freeze
    > them fresh. To unfreeze a single participant mid-season (e.g. an honest data-entry error by
    > the rep), set that row's `membership_claim_at_approval` to `NULL` directly in the DB; the
    > next sync treats it as unfrozen and lets the live ChMeetings value through.

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
    python main.py assign-groups --file "data/individual_application_forms.xlsx"
    ```
    This now uses the API directly and writes `church_team_assignments.xlsx` as an audit log. No manual ChMeetings import is needed. If older ChMeetings people still retain stale team fields after reset, use the current-season Individual Application export as the source filter for this command.

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

- **When it applies** - during the first live single-participant sync of a new season after the forms have been reset
- **What to do** - treat consent as driven by the Church Rep Verification checklist, not by the old standalone consent submission history; after a participant registers, confirm whether Box 2 (`2. Consent Form Signed by Self or Parents`) is checked on that person's ChMeetings record before expecting `pending_approval`
- **Why it matters** - the middleware currently maps `consent_status` from `Completion Check List`, so a participant can sync successfully into WordPress and rosters while still staying at `validated` with a `missing_consent` warning if Box 2 is not checked
- **How to verify** - on 2026-05-02, `python main.py sync --type participants --chm-id 3139537` created Timmy Ho in WordPress with two rosters and one `missing_consent` validation issue, leaving `approval_status=validated`; after checking Box 2 (and the other required Boxes 1, 3, and 4 if ready), rerun the same single-participant sync and confirm the participant advances to `pending_approval` with the consent warning cleared

- **When it applies** - after clearing old `Team XXX` memberships and before church reps begin checklist review for the new season
- **What to do** - run `python main.py assign-groups --file "data/individual_application_forms.xlsx"` using a current-season Individual Application export as the source filter
- **Why it matters** - a tenant-wide ChMeetings scan can still see historical people records with stale `Church Team` values even after the 2025 reset; the current-season export limits assignment to the actual new registrants while still letting the middleware resolve the real ChMeetings person IDs by name/email/phone
- **How to verify** - on 2026-05-02, a dry run with a 3-row export for Sam Le, Thomas Chau, and Timmy Ho found only those 3 people, and the live run added all 3 to `Team RPC` with HTTP `201` responses

- **When it applies** - right after a successful `assign-groups --file ...` live run and before repeating the same import for confirmation
- **What to do** - rerun the same export once in `--dry-run` mode
- **Why it matters** - this gives a quick idempotence check that the exact people from that export are now already in their Team groups, without risking duplicate API writes
- **How to verify** - on 2026-05-02, rerunning `python main.py assign-groups --file "S:\MyDownloads\Screenpresso\Individual Application Form (3).xlsx" --dry-run` after the live Team RPC import returned `Found 0 people needing team assignment`

- **When it applies** - when you move from a tiny spot-check export to a broader current-season Individual Application export
- **What to do** - expect the command to surface only the remaining unassigned people from that larger export, while still skipping church codes that do not have a real `Team XXX` group in ChMeetings
- **Why it matters** - this confirms the current-season file filter and the existing "already in team groups" check work together; you can safely expand from a 3-row test file to a fuller season export without re-adding the people you already imported
- **How to verify** - on 2026-05-02, after Sam Le, Thomas Chau, and Timmy Ho were already re-added to `Team RPC`, a dry run against `Individual Application Form (2).xlsx` found only 10 remaining assignments: 8 real adds and 2 `Team OTHER` skips (`Hanh Nguyen` and `Thanh Dang`)

- **When it applies** - when a current-season export count looks lower than the number of rows selected in ChMeetings Forms
- **What to do** - compare the selected-row count against the number of unique people represented in the export, and subtract anyone already in the Team group or added manually before assuming the filter missed someone
- **Why it matters** - ChMeetings Forms can include multiple submission rows for the same linked person, so the selected count in the UI is not always the same as the number of new Team assignments you should expect
- **How to verify** - on 2026-05-02, `Individual Application Form (4).xlsx` contained 13 selected RPC rows, but one was a duplicate `Julianna Faith Ramirez` submission; after subtracting the already-handled Thomas Chau, Sam Le, Timmy Ho, and the manually added Ayden Luu, the expected live assignment count was 8, which matched the dry run and live run exactly

- **When it applies** - when a form row name does not exactly match the ChMeetings person profile name
- **What to do** - if the form response has already been linked to an existing person, trust the linkage and compare email/phone before assuming the assignment matched the wrong person
- **Why it matters** - ChMeetings lets an operator link a form submission to an existing profile without overwriting the original form-submitted name, so the form list may still show the submitted name while the linked profile keeps a different legal or preferred name
- **How to verify** - on 2026-05-02, the RPC export showed `Troy Quach` on the form row, while the linked ChMeetings person assigned by `assign-groups --file` was `Khoi Quach (3319105)`; this was confirmed to be the same linked person, and the live run added that person to `Team RPC` with HTTP `201`

- **When it applies** - when you are ready to move from church-by-church spot checks to the larger same-day Individual Application batch
- **What to do** - run `assign-groups --file "current export.xlsx" --dry-run`, verify the expected names and zero missing groups, then run the same file live and immediately rerun that exact file in `--dry-run`
- **Why it matters** - this gives a safe three-step pattern for bulk current-season assignment: preview, apply, then prove idempotence on the exact same batch before moving on
- **How to verify** - on 2026-05-02, a same-day 80-row export in `Individual Application Form (5).xlsx` produced 60 pending assignments with `0` missing groups; the live run added all 60 with HTTP `201`, and the immediate rerun of that same file returned `Found 0 people needing team assignment`

- **When it applies** - during the first full `sync --type participants` run after team assignments are in place
- **What to do** - if the sync reports ChMeetings `404` errors for some Team-group member IDs, compare the API group-member count against the visible member count in the ChMeetings app before taking any cleanup action
- **Why it matters** - some `Team XXX` groups can retain orphaned API-only memberships that do not appear in the app and no longer resolve through `GET /people/{id}`; clearing the whole group would remove real current-season members along with those ghosts
- **How to verify** - on 2026-05-02, `Team NHC` returned 5 memberships by API but only showed 3 real people in the app, and `Team GLA` returned 12 by API but showed 8 in the app; the missing IDs all failed `GET /people/{id}` with `404`

- **When it applies** - after orphaned Team-group memberships have been confirmed during participant sync
- **What to do** - rerun `python main.py sync --type participants` with the current middleware so orphaned memberships are skipped as non-fatal warnings instead of counted as participant-sync errors
- **Why it matters** - this lets the full participant sync finish cleanly without risky whole-group clearing, while still processing all real current-season participants and preserving roster consistency
- **How to verify** - on 2026-05-02, the first full participant sync created 66 participants and reported 19 errors from orphaned group-member IDs; after the middleware update, the rerun completed with `Participants {'created': 0, 'updated': 69, 'errors': 0, 'skipped_missing_people': 19}` and `Rosters {'created': 0, 'deleted': 0, 'errors': 0}`

- **When it applies** - before the new season registration opens, after any ChMeetings Roles & Permissions changes were made during season cleanup
- **What to do** - in ChMeetings, go to **Account -> Users/Roles**, open the **Church Rep** role, and confirm that the **Add/Edit** checkbox is enabled for these 10 fields: `My role is`, `Church Team`, `Would the team's Senior Pastor say that you belong to his church?`, `Primary Sport`, `Primary Racquet Sport Format`, `Primary Racquet Sport Partner (if applied)`, `Secondary Sport`, `Secondary Racquet Sport Format`, `Secondary Racquet Sport Partner (if applied)`, and `Other Events`. Re-enable any that were unchecked.
- **Why it matters** - without Add/Edit permission on these fields, Church Reps can view participant sport selections but cannot make corrections on behalf of participants; the `Age verification` field intentionally stays view-only for Church Reps.
- **How to verify** - log in as a test Church Rep account and confirm you can edit a participant's `Primary Sport` and `Church Team` fields on their profile record.

## Known Gaps / Future Improvements

- **WordPress table reset** is manual (SQL or phpMyAdmin). A future command could automate the truncation with confirmation prompts.
