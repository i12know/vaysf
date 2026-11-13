# ChMeetings API Migration Guide

This document records the breaking API changes introduced by ChMeetings in 2026 and the corresponding fixes made to the middleware (Issues #56–#59). It serves as a reference for future development and troubleshooting.

## Background

In early 2026 ChMeetings updated their REST API in ways that broke the existing middleware:
- The authentication header name became case-sensitive at the gateway level.
- Most list and detail endpoints now return a JSON envelope (`{"paging": {...}, "data": [...]}` or `{"data": {...}}`) instead of bare arrays or objects.
- Pagination metadata moved inside a `paging` sub-object.

All four changes below were implemented on the `claude/prioritize-github-issues-Qprxf` branch and closed Issues #56–#59.

---

## Change #1 — Auth Header Casing (Issue #57)

### Problem
ChMeetings' API gateway stopped accepting `ApiKey` (mixed-case) and required lowercase `apikey`.

### File Changed
`chmeetings/backend_connector.py` — `ChMeetingsConnector.__init__()`

### Before
```python
self.session.headers.update({
    "accept": "application/json",
    "ApiKey": self.api_key
})
```

### After
```python
self.session.headers.update({
    "accept": "application/json",
    "apikey": self.api_key
})
```

### How to Test
Any live API call (e.g., `LIVE_TEST=true pytest tests/test_chmeetings_connector.py::test_authenticate_api`) will return HTTP 200 instead of 401 when the header is correct.

---

## Change #2 — `get_person()` Response Unwrapping (Issue #56)

### Problem
`GET /api/v1/people/{id}` now returns `{"data": {...}}` instead of the raw person object. The old code returned the whole envelope as the person record, causing `None` to propagate when callers tried to access fields.

### File Changed
`chmeetings/backend_connector.py` — `ChMeetingsConnector.get_person()`

### Before
```python
return response.json()
```

### After
```python
return response.json().get("data")
```

### How to Test
```bash
# Mock mode
pytest tests/test_chmeetings_connector.py::test_get_person -v

# Live mode (fetches the first real person from page 1)
set LIVE_TEST=true && pytest tests/test_chmeetings_connector.py::test_get_person -v -s
```

---

## Change #3 — `get_people()` Pagination Rewrite (Issue #58)

### Problem
The old implementation used `len(page_data) < page_size` as the stop condition, which broke on the last page when the count was exactly divisible by page_size. The new API response wraps all list results in `{"paging": {"total_count": N, "page": P, "page_size": S}, "data": [...]}`.

Additionally, the API now requires explicit opt-in for additional profile fields (`include_additional_fields=True`) and the new default for `include_family_members` is `True`, which we don't want.

### File Changed
`chmeetings/backend_connector.py` — `ChMeetingsConnector.get_people()`

### New Implementation
```python
def get_people(self, params=None):
    all_people = []
    page = 1
    page_size = 100
    params = params or {}

    while True:
        params.update({
            "page": page,
            "page_size": page_size,
            "include_additional_fields": True,
            "include_family_members": False,
        })
        response = self.session.get(
            urljoin(self.api_url, "api/v1/people"),
            params=params
        )
        response.raise_for_status()
        data = response.json()
        people = data.get("data", [])
        total_count = data.get("paging", {}).get("total_count", 0)
        all_people.extend(people)
        if len(all_people) >= total_count or not people:
            break
        page += 1

    return all_people
```

### Required Request Parameters

| Parameter | Value | Reason |
|-----------|-------|--------|
| `include_additional_fields` | `True` | Required to receive sport selections, church code, and consent data |
| `include_family_members` | `False` | Prevents duplicate records from family-member expansion |
| `page_size` | `100` | Maximum supported by the API |

### Tests Added
- `test_get_people_pagination` — verifies 2-page mock terminates with all 3 records after exactly 2 calls.
- `test_get_people_request_params` — verifies the three required params are sent on every request.

---

## Change #4 — Group Membership Methods (Issue #59)

### Problem
The middleware had no way to add or remove participants from ChMeetings groups via API. The workaround was generating an Excel file and importing it manually into ChMeetings — a multi-step, error-prone process.

### File Changed
`chmeetings/backend_connector.py` — new methods added after `get_group_people()`

### New Endpoints

#### `POST /api/v1/groups/{group_id}/memberships`
Add a person to a group. Returns:
- **201** — person was newly added
- **200** — person was already a member (still a success)

```python
def add_person_to_group(self, group_id: str, person_id: str) -> bool:
    response = self.session.post(
        urljoin(self.api_url, f"api/v1/groups/{group_id}/memberships"),
        json={"person_id": person_id}
    )
    response.raise_for_status()
    return True
```

#### `DELETE /api/v1/groups/{group_id}/memberships/{person_id}`
Remove a person from a group. Returns:
- **200** — removed successfully

```python
def remove_person_from_group(self, group_id: str, person_id: str) -> bool:
    response = self.session.delete(
        urljoin(self.api_url, f"api/v1/groups/{group_id}/memberships/{person_id}")
    )
    response.raise_for_status()
    return True
```

### Live Round-Trip Test

A gated live test adds a person to a group and immediately removes them, verifying membership via `get_group_people()` at each step:

```bash
# Windows CMD
set LIVE_TEST=true
set CHM_TEST_GROUP_ID=999847
set CHM_TEST_PERSON_ID=3692903
pytest tests/test_chmeetings_connector.py::test_add_person_to_group tests/test_chmeetings_connector.py::test_remove_person_from_group -v -s
```

**How to find IDs:**
- **Group ID**: From the ChMeetings URL, e.g. `?gid=999847` → group ID is `999847`
- **Person ID**: From the member profile URL, e.g. `.../MemberDashboard/3692903` → person ID is `3692903`

**Important:** Use a test group and a test person that won't affect real registration data.

---

## Change #5 — Replace Excel export workaround with direct API calls (Issue #60)

### Problem
`group_assignment.py` generated an Excel file (`chm_group_import.xlsx`) and printed a message telling the operator to manually import it in ChMeetings. Similarly, `sync_approvals_to_chmeetings()` wrote `group_import_approved_participants.xlsx` and required a manual import step for the `2025 Sports Fest` group.

### Files Changed
- `middleware/group_assignment.py` — complete rewrite of action step
- `middleware/sync/manager.py` — `sync_approvals_to_chmeetings()` rewritten; `import pandas` removed
- `middleware/main.py` — `assign-groups` subparser gets `--dry-run` flag
- `middleware/chmeetings/backend_connector.py` — 429 retry added to `add_person_to_group()`

### New flow — `assign-groups`

```bash
python main.py assign-groups           # live: assigns via API
python main.py assign-groups --dry-run # preview only, no API calls
```

- Builds `name → id` lookup from `get_groups()`
- Calls `add_person_to_group(group_id, person_id)` per unassigned person
- Writes `data/church_team_assignments.xlsx` audit file (both modes)
- Missing group (e.g. `Team OTHER` not in ChMeetings): warns and skips, does not fail
- `PermissionError` when xlsx is open in Excel: warns and continues

### New flow — `sync --type approvals`

- Looks up `APPROVED_GROUP_NAME` group via `get_groups()` — fails hard if not found
- Calls `add_person_to_group()` for each approved WP participant
- Marks `synced_to_chmeetings=True` per-person only on API success
- No Excel file generated; no manual import step

### Rate limiting

ChMeetings enforces a rate limit (~5 req/s) on group membership writes. Two safeguards added:

1. **Preventive 200 ms delay** between each `add_person_to_group()` call in both calling loops
2. **Retry with back-off** inside `add_person_to_group()` itself: on HTTP 429, waits 2 s → 5 s → 10 s before each of 3 retries; gives up and returns `False` after the third retry

### Known limitation — Issue #61

`get_approvals(synced_to_chmeetings=False)` consistently returns 0 records because the WordPress REST API endpoint does not support the `synced_to_chmeetings` filter parameter. As a result, `sf_approvals` rows are never updated to `synced_to_chmeetings=1`. This is safe (the ChMeetings add is idempotent — HTTP 200 for already-members) but wastes API calls on re-runs. Tracked in [Issue #61](https://github.com/i12know/vaysf/issues/61).

---

## Platform Review Notes (dated)

Notes from the twice-yearly review in
[SEASON_TRANSITION.md — Phase 0](SEASON_TRANSITION.md#phase-0-chmeetings-platform-review).
Newest first. Each note says where the fact comes from. "To verify live" means
nobody has yet confirmed it against the VAY SM tenant with the API key.

### 2026-11-13 — reviewed through ChMeetings 2026.22 (tenant v2026.22.7.3)

No change in this review requires a middleware fix before the 2027 season. The
five changes above still describe how the connector must talk to the API.

**Confirmed in the published OpenAPI spec** (`/openapi/v1.json`, fetched
2026-11-13 and committed as `chmeetings_openapi_v1.json`):

- **The published spec is no longer incomplete.** It has 110 paths (64 in the
  2026-07-17 snapshot) and covers People, Notes, Groups, group memberships,
  the photo upload and custom fields. The Scalar page loads this same file as
  its only source, so Scalar and the JSON no longer differ.
- **Nothing was removed.** Every operation in the 2026-07-17 snapshot is still
  present. Authentication is still the lowercase `apikey` header, and paging
  is still `paging.total_count` / `page` / `page_size`.
- **`PUT /api/v1/people/{id}` is documented as a full replacement:** "omitted
  fields will be cleared". This matches what `update_person()` already
  assumes.
- **`GET /api/v1/people`:** `page_size` is documented as 1 to 100. New optional
  filters: `person_ids` (up to 100), `group_ids` (up to 100), `ungrouped`,
  `created_from`, `created_to`, `genders`, `family_roles`, `has_email`,
  `has_mobile`, `has_photo`, `do_not_email`, `do_not_text`, `country_id`,
  `state_id`, `city_id`, `zip_code`. New optional expansion
  `include_groups=true` returns each person's groups as `{id, name}`. The
  description adds that a profile field the account has disabled is left out
  of the response instead of being returned as null.
- **`GET /api/v1/groups`:** documented as not paged and ordered by name. New
  optional `search_text`. Each group still has `id`, `name` and `created_on`,
  and now also `description`, `privacy`, `join_request_option`,
  `is_visible_to_non_members`, `is_members_visible`,
  `is_group_leaders_visible` and `is_chat_enabled`.
- **Groups can now be created, updated and deleted by API**
  (`POST /groups`, `GET|PUT|DELETE /groups/{group_id}`). `DELETE` removes the
  group together with all of its memberships and group-leader assignments, so
  it must never be used to clear a `Team XXX` group; `clear-team-groups`
  removes memberships one at a time and keeps the group and its leaders.
- **An existing person can be added to, or removed from, an organization by
  API** (`POST /organizations/{organization_id}/people`,
  `DELETE /organizations/{organization_id}/people/{person_id}`). An
  organization outside the API key's tree returns 400, not 404.
- **Webhook subscriptions can be managed by API** (`/integrations/webhooks`).
  Deliveries are signed (`ChMeetings-Webhook-Signature`, verified with the
  subscription's secret), at-least-once, and delayed: at least a minute, and
  about 4 to 5 minutes for `person.*` events.

**Confirmed in the ChMeetings help centre** (Developer API Guide, updated
2026-11-09; Configure Webhooks, updated 2026-11-12):

- **Rate limit: 100 requests per 20 seconds, for each API key from each IP
  address.** Requests over the limit get HTTP 429 with a `Retry-After` header.
  The two articles now agree; in July 2026 the Developer API Guide said 100
  per second (see the comment above `CHM_MIN_REQUEST_INTERVAL_SECONDS`).
  The connector's pacing (`CHM_MIN_REQUEST_INTERVAL_SECONDS = 0.2`) already
  matches the published limit, with no margin. The connector does not read
  `Retry-After`; it waits on its own fixed schedule.
- **Webhook events:** people created, updated, deleted; contributions created;
  contribution funds created, updated, deleted; event check-in; first-time
  check-in. There is no event for a person merge.

**Confirmed in the VAY SM tenant** (browser, 2026-11-13):

- The form IDs in `middleware/chrome_export_vaysf_forms.py` (301433 Individual
  Application Form, 301494 Consent Form) still open those forms. The
  submissions page still has an `Export` button that opens an
  `Export Submissions` dialog with a `Download` button, which is what the
  helper clicks. No file was downloaded during the check.
- Automatic profile creation from form submissions (2026.16) was tested and is
  **off by decision for 2027** (issue #351). The release notes for 2026.17 to
  2026.22 add no matching or routing controls to it.

**Confirmed live with the VAY SM API key** (2026-11-13, Phase 0 steps 2, 4
and 5; the write probe ran on a fictional profile created for the purpose and
deleted afterwards from the diocese admin view, because the VAY SM key cannot
delete people):

- **"Omitted fields will be cleared" did not happen for the fields at risk.**
  A Vietnamese name seeded in Native Name survived all six `reset-season
  --probe` PUTs and a separate PUT that left `native_name` out entirely. A
  seeded Qualification survived the six probes. After P1, which sends no
  `additional_fields`, the seeded Sports Fest fields were unchanged.
  `GET /people/{id}` returns a populated `native_name`.
- P3 cleared the targeted checklist checkbox and P4 the targeted sport
  dropdown, as designed: the probe sends clearing values (Phase 0 step 5).
- `GET /people/999999999` returns `404` with the body `Invalid Person Id`.
- The field inspector matched all 14 mapped custom fields and every
  configured field and option ID. `nick_name` was absent from the sampled
  responses although the account's **Enable Nickname** setting is **on**
  (Account Settings → Format Settings, checked in the tenant the same day).

**Where the published spec and the live API disagree** (reported 2026-11-13;
trust the live behaviour and re-test after each ChMeetings release):

| Published spec says | Live VAY SM API did |
|---|---|
| `PUT /people/{id}` is a full replacement; omitted fields are cleared | Omitted `native_name`, `qualification` and `additional_fields` were kept |
| `PersonResponseDto` has `nick_name`, not `native_name` | `native_name` is returned (also when empty); `nick_name` is not |
| A disabled profile field is omitted from responses | Nickname is enabled and still omitted |

Not yet tested: a profile with a Nickname value set. If `nick_name` appears
only when populated, the third row is an empty-value rule rather than a bug;
`native_name` coming back empty makes that inconsistent either way. Badges
read `nick_name` for the printed first name (`badges/runner.py`), so until
this is settled, do not rely on ChMeetings nicknames for badges (see #227).

**To verify live** (see the live checklist in Phase 0):

- Whether `father_name`, `education_level`, `church` and
  `talents_and_hobbies` survive `update_person()` on a profile that has them
  set. The sampled real profile omitted `father_name` and had nothing in
  these fields, so there was nothing to lose; the fictional profile did not
  seed them.
- Whether the standard fields that became lookup (list) fields in 2026.21
  (Job Title, Education Level, Qualification, School, Church, City) still
  round-trip through `PUT` as plain strings. The published schema still types
  them as strings.
- Whether a 429 from the live API carries `Retry-After`, and whether any
  rate-limit headers are sent on normal responses.
- Whether a merged, deleted, archived, removed-from-church or
  converted-to-contact person all answer `GET /people/{id}` with the same
  plain 404. The published spec documents only "404 Not Found" and has no
  merge endpoint. Until verified otherwise, keep treating 404 as "not found",
  never as "deleted".
- Whether orphaned group memberships (members returned by
  `GET /groups/people` whose `GET /people/{id}` is 404) still occur.
- Whether the new `person_ids`, `group_ids`, `include_groups` and
  `search_text` parameters behave as documented for the VAY SM key.

---

## Troubleshooting API Migration Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `401 Unauthorized` despite correct API key | Header sent as `ApiKey` (mixed case) | Ensure header is lowercase `apikey` (Change #1) |
| `get_person()` returns `None` for a valid ID | Old code returned envelope instead of `.get("data")` | Upgrade to v1.05 (Change #2) |
| Only first 100 people returned | Old pagination stopped at page_size boundary | Upgrade to v1.05 pagination (Change #3) |
| Additional fields (sport, church code) missing | `include_additional_fields` not sent | Upgrade to v1.05 (Change #3) |
| `add_person_to_group()` returns `False` | Group permission issue or wrong group ID | Verify ChMeetings account has group management permission; confirm ID from URL |
