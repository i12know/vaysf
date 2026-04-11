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

## Remaining Work — Issue #60

Issue #60 tracks replacing the manual Excel-based group assignment workflow in `group_assignment.py` with direct API calls using the new `add_person_to_group()` method from Change #4.

**Current flow (workaround):**
1. Run `python main.py assign-groups`
2. System generates `chm_group_import.xlsx`
3. Admin manually imports file into ChMeetings

**Target flow (post-#60):**
1. Run `python main.py assign-groups`
2. System directly calls `add_person_to_group()` for each unassigned participant
3. No manual import step needed

See Issue #60 for implementation details and acceptance criteria.

---

## Troubleshooting API Migration Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `401 Unauthorized` despite correct API key | Header sent as `ApiKey` (mixed case) | Ensure header is lowercase `apikey` (Change #1) |
| `get_person()` returns `None` for a valid ID | Old code returned envelope instead of `.get("data")` | Upgrade to v1.05 (Change #2) |
| Only first 100 people returned | Old pagination stopped at page_size boundary | Upgrade to v1.05 pagination (Change #3) |
| Additional fields (sport, church code) missing | `include_additional_fields` not sent | Upgrade to v1.05 (Change #3) |
| `add_person_to_group()` returns `False` | Group permission issue or wrong group ID | Verify ChMeetings account has group management permission; confirm ID from URL |
