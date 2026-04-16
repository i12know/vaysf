# Test Plan v1.05: 2026 API Upgrade

**Version:** 1.05
**Date Created:** March 13, 2026
**Purpose:** Comprehensive testing guide for the 2026 API upgrade before season data transition

## Overview

This test plan documents procedures for validating all v1.05 changes against **live 2025 data** before clearing the system for 2026 season. All tests should be performed on the production systems to ensure data integrity and API compliance.

**Key Changes in v1.05:**
- Removed Selenium/browser automation (API-only approach)
- Centralized ChMeetings field name mapping via `CHM_FIELDS` constants
- API-based approval sync to ChMeetings (replaces Excel manual import)
- Fixed `get_people()` pagination `page_size` bug
- Comprehensive field mapping validation tooling

---

## Prerequisites

- Middleware running on Windows with Python 3.8+
- `.env` configured with live credentials:
  - `CHM_API_URL`, `CHM_API_KEY` (ChMeetings)
  - `WP_URL`, `WP_API_KEY` (WordPress)
  - `APPROVED_GROUP_NAME` set to current season group (e.g., "2025 Sports Fest")
- MySQL access to WordPress database (for verification queries)
- ChMeetings admin account access (to verify group memberships and field definitions)
- Access to live logs directory: `middleware/logs/`

---

## Test Categories

### Category A: Connectivity & Configuration (Smoke Tests)

#### A1: Middleware Config Validation
```bash
python main.py config --validate
```
**Expected:** All environment variables present and valid. No warnings about missing credentials.

**Verify:**
- `.env` file loads without errors
- API endpoints accessible
- Field encryption keys initialized

#### A2: System Connectivity Test
```bash
python main.py test --system all --test-type connectivity
```
**Expected:**
- ✅ ChMeetings API responds to authentication
- ✅ WordPress API responds with valid auth token
- ✅ Both systems report available and operational

**Check logs for:**
- Connection timeout errors (would indicate network issues)
- SSL certificate validation failures
- Invalid API key messages

---

### Category B: ChMeetings Field Mapping Validation

#### B1: API Field Inspector (Critical for v1.05)
```bash
python main.py test --system chmeetings --test-type api-inspect
```
**Expected Output:**
- Lists all ChMeetings groups (should include "Team XXX" groups and "2025 Sports Fest")
- Lists all custom field definitions in the registration form
- Cross-references `CHM_FIELDS` constants against live API response

**Verify Fields Present:**
- ✅ `Church Team` (used by `group_assignment.py` and `participants.py`)
- ✅ `Primary Sport` (used by participant sport mapping)
- ✅ `Secondary Sport` (optional but should be defined)
- ✅ `Primary Racquet Sport Format` (if racquet sports are offered)
- ✅ `Completion Check List` (church rep verification boxes 1-6)
- ✅ `My role is` (participant role classification)
- ✅ `Parent Info` (for youth participants)
- ✅ `Would the team's Senior Pastor say that you belong to his church?` (membership verification)

**Action if Fields Missing or Changed:**
1. Update `config.py` `CHM_FIELDS` dictionary to match live API
2. Re-run `api-inspect` to confirm
3. Re-test affected sync operations (see Category C)

**Log Location:** `middleware/logs/sportsfest_*.log` (today's date)

---

### Category C: Data Synchronization Tests (Against Live 2025 Data)

#### C1: Church Sync (Excel → WordPress)
**Prerequisite:** Live "Church Application Form.xlsx" in `middleware/data/`

```bash
python main.py sync-churches --file "data/Church Application Form.xlsx"
```
**Expected:**
- All churches from Excel synced to WordPress `sf_churches` table
- Church codes, pastor emails, and rep emails populated
- No duplicate entries

**Verify in WordPress Admin → SportsFest → Churches:**
- Count of churches matches Excel row count
- Sample church: pastor email correct, church code matches
- Updated timestamps reflect today's sync

**SQL Verification:**
```sql
SELECT COUNT(*) FROM wp_sf_churches;
SELECT * FROM wp_sf_churches WHERE church_code = 'RPC' LIMIT 1;
```

---

#### C2: Participant Sync (All Participants)
```bash
python main.py sync --type participants
```
**Expected:**
- All active participants from ChMeetings synced to WordPress
- Sport selections parsed correctly
- Validation issues created where applicable
- No duplicate participants (based on `chmeetings_id`)

**Verify Statistics:**
- Log should show: `Participants synced: XXX created, YYY updated`
- Check for any error counts > 0
- Validation issues created for ineligible participants

**SQL Verification:**
```sql
SELECT COUNT(*) FROM wp_sf_participants;
SELECT COUNT(*) FROM wp_sf_validation_issues WHERE severity = 'ERROR';
SELECT COUNT(DISTINCT chmeetings_id) FROM wp_sf_participants;
-- Should equal total count (no duplicates)
```

**Sample Participant Check (by ChMeetings ID):**
```bash
python main.py sync --type participants --chm-id 3505203
```
(Jerry Phan from test mock data — verify this person exists in live ChMeetings)

**Expected:**
- Single participant synced/updated
- Sport selections visible in WordPress
- Any approval status updated

---

#### C3: Group Assignment (Prepare for Manual Import or API Sync)
```bash
python main.py assign-groups
```
**Expected:**
- Exports `middleware/data/chm_group_import.xlsx`
- Lists all participants with a "Church Team" code but NOT yet in their "Team XXX" group
- One row per person needing assignment

**Verify:**
- File is created and readable
- Columns: `Person Id`, `First Name`, `Last Name`, `Group Name`
- Sample group names follow pattern: "Team ABC" (where ABC = church code)

**Action:**
- Optionally import into ChMeetings: **Tools → Import Group → chm_group_import.xlsx**
- Or test the API sync method below (C4)

---

#### C4: Approval Sync — API Method (v1.05 Primary Path)
**Setup:**
1. Ensure at least one participant has `approval_status = "pending_approval"` in WordPress
2. Verify their corresponding ChMeetings record exists

```bash
python main.py sync --type approvals
```
**Expected:**
- Fetches `APPROVED_GROUP_NAME` group ID from ChMeetings
- For each approved participant:
  - Calls `add_person_to_group()` API to add them to the approved group
  - Marks approval as `synced_to_chmeetings = true` in WordPress
- No errors in log output

**Verify in ChMeetings:**
1. Open the "2025 Sports Fest" group (or configured approved group)
2. Check that approved participants now appear in the group membership
3. Count should match: (participants with `approval_status = "approved"` AND `synced_to_chmeetings = false` before sync)

**SQL Verification:**
```sql
SELECT COUNT(*) FROM wp_sf_approvals WHERE synced_to_chmeetings = 1;
SELECT COUNT(*) FROM wp_sf_approvals WHERE synced_to_chmeetings = 0;
```

---

#### C5: Approval Sync — Excel Fallback Method (Legacy Path, v1.04 Compatibility)
**Only run if API method (C4) encounters errors:**

```bash
python main.py sync --type approvals --excel-fallback
```
**Expected:**
- Creates `middleware/data/group_import_approved_participants.xlsx`
- Contains: `Person Id`, `First Name`, `Last Name`, `Group Name` (always "2025 Sports Fest")
- Does NOT call API; generates file for manual import only

**Manual Import (if needed):**
- ChMeetings → **Tools → Import Group → group_import_approved_participants.xlsx**

**Verify:**
- Check that the Excel file is created with correct format
- Do NOT import unless API sync (C4) fails

---

### Category D: Validation System Tests

#### D1: Validation Rules Load Correctly
```bash
python main.py test --system validation --test-type rules
```
**Expected:**
- Loads `validation/summer_2025.json` (or current season rules file)
- Rules contain age restrictions, gender/sport combinations, photo requirements
- No syntax errors in JSON

**Verify Rules Sections:**
- `metadata` section has current season, date, version
- `rules` array contains at least: age, gender, photo, sports format rules
- Sport type mappings match config.py `SPORT_TYPE` constants

---

#### D2: Validation Against Sample Participants
```bash
python main.py sync --type validation
```
**Expected:**
- Scans all participants against validation rules
- Creates issues for ineligible participants (age out of range, missing photo, etc.)
- Classifies issues by severity (ERROR vs WARNING)

**Verify Statistics in Log:**
- `Validation issues created: X`
- `Total ERROR severity: Y`
- `Total WARNING severity: Z`

**Sample Issue Check (SQL):**
```sql
SELECT issue_type, COUNT(*) FROM wp_sf_validation_issues
GROUP BY issue_type
ORDER BY COUNT(*) DESC LIMIT 10;

SELECT * FROM wp_sf_validation_issues
WHERE severity = 'ERROR' LIMIT 5;
```

---

### Category E: Sport Roster Generation

#### E1: Rosters Created from Participant Sports
```bash
python main.py sync --type participants  # (if not already done in C2)
```
**Expected:**
- `wp_sf_rosters` table populated with one entry per participant × sport
- Includes: sport type, sport gender, sport format, partner name (for doubles)
- Sorted and organized for team sheets

**SQL Verification:**
```sql
SELECT sport_type, sport_gender, COUNT(*) as count
FROM wp_sf_rosters
GROUP BY sport_type, sport_gender
ORDER BY count DESC;

-- Check for any rosters without participants
SELECT r.* FROM wp_sf_rosters r
LEFT JOIN wp_sf_participants p ON r.participant_id = p.participant_id
WHERE p.participant_id IS NULL;
```

---

### Category F: Report Generation

#### F1: Church Team Status Reports
```bash
python main.py export-church-teams
```
**Expected:**
- Generates Excel report for each church: `Church_Team_Status_[CODE].xlsx`
- Summary sheet: church totals (members, approved, pending, errors)
- Contacts sheet: detailed roster with approval status, validation errors
- Sport-specific tabs: Volleyball, Basketball, etc.

**Verify Sample Report (e.g., RPC):**
```bash
python main.py export-church-teams --church-code RPC
```
**Expected:**
- Single file: `Church_Team_Status_RPC.xlsx`
- Reflects only RPC church members from "Team RPC" group

**Check Excel Contents:**
- Summary shows correct counts for RPC
- All contacts have ChMeetings IDs matching the group
- Completion checklist boxes (1-6) reflected from ChMeetings `Completion Check List` field

---

#### F2: Report Accuracy Against Live Data
**Manual Verification:**
1. Open generated Excel report
2. Cross-check 5 random participants:
   - Name, email match ChMeetings
   - Sport selections match participant form
   - Approval status matches WordPress
   - Church rep checklist items match ChMeetings completion checkboxes

---

### Category G: CHM_FIELDS Constant Usage (v1.05 Verification)

#### G1: All Field Name Lookups Use CHM_FIELDS
**Code Review (run from middleware root):**
```bash
grep -n "additional_fields.get(" sync/participants.py group_assignment.py church_teams_export.py tests/test_validation.py
```
**Expected Output:**
- Every `additional_fields.get()` call uses `CHM_FIELDS["KEY"]` reference
- No hardcoded field name strings like `"Church Team"`, `"Primary Sport"`, etc.
- All references use the centralized constant

**Example Valid Line:**
```python
church_code = additional_fields.get(CHM_FIELDS["CHURCH_TEAM"], "").strip().upper()
```

**Example Invalid Line (should not exist):**
```python
church_code = additional_fields.get("Church Team", "").strip().upper()  # ❌ Hardcoded
```

#### G2: Test Coverage for CHM_FIELDS
**All unit tests pass with live data:**
```bash
cd middleware && python -m pytest tests/ -v
```
**Expected:**
- ✅ 23/23 tests pass
- ✅ No import errors for CHM_FIELDS in any test file
- ✅ Validation tests use CHM_FIELDS for sport lookups

---

### Category H: Selenium Removal Verification (v1.05)

#### H1: No Selenium Dependencies
```bash
python -c "from chmeetings.backend_connector import ChMeetingsConnector; print('✅ Import successful')"
```
**Expected:** No ImportError for selenium, webdriver, Service, etc.

#### H2: No Selenium Code Paths
**Code Review:**
```bash
grep -r "selenium\|webdriver\|Selenium\|WebDriver" middleware/
```
**Expected:** No matches (except in requirements.txt comments or docs)

#### H3: Config Has No Selenium Variables
```bash
grep "CHM_USERNAME\|CHM_PASSWORD\|CHROME\|HEADLESS\|selenium" middleware/config.py
```
**Expected:** No matches

#### H4: Requirements Has No Selenium
```bash
grep -i "selenium\|webdriver" middleware/requirements.txt
```
**Expected:** No matches

---

### Category I: Pagination Bug Fix (get_people page_size)

#### I1: Pagination Respects Caller Page Size
**Setup:** Temporarily modify `get_people()` call to request smaller page size:

```python
# In sync/participants.py or a test, add:
all_people = self.chm_connector.get_people(page_size=10)
# Expected: API called with page_size=10, not hardcoded 100
```

**Verify in Log:**
- Should show multiple pages being fetched
- API request params should include `page_size: 10`

**Alternative:** Check live log from sync with large participant count:
```bash
grep "page" middleware/logs/sportsfest_*.log | grep -i "page_size\|pagination"
```

---

## Test Execution Sequence

**Recommended order to avoid data conflicts:**

1. **Phase 1 (Smoke Tests):** A1 → A2 (5 min)
2. **Phase 2 (Field Validation):** B1 (critical blocker) (5 min)
3. **Phase 3 (Full Sync - Clean Data):** C1 → C2 → C3 (20 min)
4. **Phase 4 (Approvals):** C4 or C5 (10 min)
5. **Phase 5 (Validation & Rosters):** D1 → D2 → E1 (10 min)
6. **Phase 6 (Reports & QA):** F1 → F2 (10 min)
7. **Phase 7 (Code Verification):** G1 → G2 → H1-4 → I1 (15 min)

**Total Estimated Time:** ~75 minutes for full test suite

---

## Expected Results Summary

| Test | Expected Status | Log Verification |
|------|-----------------|------------------|
| A1 Config Validate | ✅ Pass | No errors |
| A2 Connectivity | ✅ Pass | Both systems online |
| B1 API Field Inspector | ✅ Pass | All fields found |
| C1 Church Sync | ✅ Pass | N churches synced |
| C2 Participant Sync | ✅ Pass | M participants synced, 0 errors |
| C3 Group Assignment | ✅ Pass | K people need assignment |
| C4 Approval Sync (API) | ✅ Pass | X approved → group |
| C5 Approval Sync (Excel) | ✅ Pass | File created (if fallback used) |
| D1 Validation Rules | ✅ Pass | Rules loaded |
| D2 Validation Run | ✅ Pass | Y issues created |
| E1 Rosters | ✅ Pass | Z roster entries |
| F1 Reports Generated | ✅ Pass | Church_Team_Status_*.xlsx files |
| G1-G2 CHM_FIELDS Usage | ✅ Pass | All constants used correctly |
| H1-H4 Selenium Removed | ✅ Pass | No selenium imports/code |
| I1 Page Size Fixed | ✅ Pass | Caller's page_size respected |

---

## Troubleshooting During Testing

### If B1 (API Field Inspector) Fails
- **Issue:** Fields not found in live ChMeetings
- **Action:**
  1. Check ChMeetings form structure manually (admin UI)
  2. Update `CHM_FIELDS` if labels changed
  3. Re-run api-inspect
  4. Cannot proceed to C2 until resolved

### If C2 (Participant Sync) Has Errors
- **Issue:** Participants not syncing or validation errors
- **Action:**
  1. Check log for specific participant IDs failing
  2. Run `python main.py sync --type participants --chm-id <ID>` on problem person
  3. Inspect WordPress database for duplicate chmeetings_id
  4. Check validation rules for mismatches with actual data

### If C4 (API Approval Sync) Fails
- **Issue:** add_person_to_group() returns error
- **Action:**
  1. Verify `APPROVED_GROUP_NAME` exists in ChMeetings
  2. Check group ID is correct (from B1 api-inspect output)
  3. Verify ChMeetings API key has group management permissions
  4. Fall back to C5 (Excel method) if API issue is blocking

### If F1 (Report Generation) Has Missing Data
- **Issue:** Excel report incomplete or has errors
- **Action:**
  1. Verify C1, C2, C3 all completed successfully
  2. Check Excel file for corruption (try opening in Excel)
  3. Verify photo URLs in WordPress (photo_url field)
  4. Check for participants with missing church codes

---

## Passing Criteria

✅ **All tests must pass before 2026 season transition:**

1. **No API errors** in any sync operation
2. **Zero duplicate participants** in WordPress
3. **All ChMeetings field names verified** against live API
4. **Approval sync** successfully adds participants to approved group (API or Excel)
5. **Reports generate** without errors for all churches
6. **CHM_FIELDS constants** used consistently throughout codebase
7. **All 23 unit tests pass** (`pytest`)
8. **No Selenium code** remains in middleware
9. **Pagination working** correctly with live data volume

---

## Post-Test Documentation

After completing the test suite, record:

1. **Date/Time of Tests:** _______________
2. **Tester Name:** _______________
3. **System Status:** Live 2025 Data
4. **Pass/Fail Summary:**
   - Phase 1 (Smoke): _____ / 2 tests
   - Phase 2 (Fields): _____ / 1 test
   - Phase 3 (Sync): _____ / 3 tests
   - Phase 4 (Approvals): _____ / 2 tests
   - Phase 5 (Validation): _____ / 2 tests
   - Phase 6 (Reports): _____ / 2 tests
   - Phase 7 (Code): _____ / 4 tests

5. **Critical Issues Found:** (if any)
   - Issue 1: _______________
   - Issue 2: _______________

6. **Approval to Proceed with 2026 Transition:** _____ (Yes/No)

---

## Next Steps After Test Pass

1. **Archive 2025 Data:**
   - Export final reports: `python main.py export-church-teams`
   - Back up WordPress database
   - Export all tables from `sf_*` to CSV for historical record

2. **Execute Season Transition:**
   - Follow `docs/SEASON_TRANSITION.md` step-by-step
   - Update `.env` `APPROVED_GROUP_NAME` to "2026 Sports Fest"
   - Clear Team groups in ChMeetings
   - Reset WordPress seasonal tables
   - Update validation rules file to `summer_2026.json`

3. **Post-Transition Smoke Test:**
   - Run A1 and A2 again with 2026 config
   - Verify new season group exists
   - Test single participant sync from new 2026 registrants

---

**Document Version:** 1.05
**Last Updated:** March 13, 2026
**Applicable to:** v1.05+ (API-only, CHM_FIELDS, no Selenium)

## OLD INFO:

## Testing Plan with 2025 Live Data

Here's what I'd recommend, in order from safest to most impactful:

### Step 1: Connectivity & Field Validation (read-only, safe)

```bash
python main.py test --system all --test-type connectivity
python main.py test --system chmeetings --test-type api-inspect

```

The  `api-inspect`  is brand new — it'll confirm all 11  `CHM_FIELDS`  names match what ChMeetings actually has. This is the first real validation of our field mapping constants.

### Step 2: Single Participant Sync (safe — just updates existing WP data)

Pick a known 2025 participant and re-sync them:

```bash
python main.py sync --type participants --chm-id <a_known_2025_ID>

```

This tests the  `CHM_FIELDS`  mapping end-to-end with real data. Compare the WordPress record before and after — the data should be identical since nothing changed in ChMeetings.

### Step 3: Test the API-based Approval Sync (this is the key test)

This is the big one. Before running it, check your  `.env`:

-   What is  `APPROVED_GROUP_NAME`  set to? It should be  `2025 Sports Fest`  currently.

Then check whether there are any approved-but-not-synced participants in WordPress. You can dry-test by looking at the logs:

```bash
python main.py sync --type approvals

```

**What will happen:**

-   The middleware will query WordPress for approved participants where  `synced_to_chmeetings = 0`
-   If there are any, it will try to call  `add_person_to_group()`  to add them to the "2025 Sports Fest" group in ChMeetings
-   If they're already in the group (likely, since 2025 is over), ChMeetings should handle that gracefully (either a no-op or a benign error)
-   If there are none left to sync, it'll just log "No approved participants found" and exit cleanly

Either outcome validates the new code path. If you want to test with the Excel fallback too:

```bash
python main.py sync --type approvals --excel-fallback

```

### Step 4: Verify page_size fix (optional)

```bash
python main.py sync --type participants

```

This full participant sync will exercise the fixed  `get_people()`  pagination. Watch the logs — you should see it paging through all participants correctly using whatever page_size the caller specifies.

