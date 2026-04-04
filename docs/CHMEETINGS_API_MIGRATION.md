# ChMeetings API Migration Guide

**Date:** 2026-04-04  
**Scope:** Breaking changes in the ChMeetings REST API (OpenAPI v3.1.1) that affect this codebase.  
**API Spec:** https://api.chmeetings.com/openapi/v1.json  
**Spec UI:** https://api.chmeetings.com/scalar/

---

## Summary of Breaking Changes

| # | Area | Severity | File(s) Affected |
|---|------|----------|-----------------|
| 1 | `get_person()` response unwrapping | **CRITICAL** | `backend_connector.py` |
| 2 | Authentication header casing | **High** | `backend_connector.py` |
| 3 | `get_people()` pagination / explicit params | **Medium** | `backend_connector.py` |
| 4 | Group membership management | **Medium** (new opportunity) | `group_assignment.py`, `backend_connector.py` |
| 5 | `additional_fields` read path | **None** (compatible) | `participants.py` |
| 6 | `get_groups()` / `get_group_people()` | **None** (compatible) | `backend_connector.py` |

---

## 1. [CRITICAL] `get_person()` Returns a Wrapped Object

### What changed
Every single-object endpoint now returns a response envelope:

```json
{
  "status_code": 200,
  "errors": null,
  "data": { /* PersonResponseDto */ }
}
```

### Current code (BROKEN)
`backend_connector.py`, line 196:
```python
return response.json()   # returns the envelope, not the person
```

All downstream code then tries to access `.get("id")`, `.get("first_name")`, etc.
on the envelope — those fields don't exist on it, so every participant sync silently
returns empty strings and null values.

### Fix required
```python
return response.json().get("data")
```

---

## 2. [High] Authentication Header Name Casing

### What changed
The new OpenAPI spec explicitly defines the security scheme as:

```json
"ApiKey": {
  "type": "apiKey",
  "name": "apikey",     ← all lowercase
  "in": "header"
}
```

### Current code
`backend_connector.py`, line 37:
```python
self.session.headers.update({
    "accept": "application/json",
    "ApiKey": self.api_key          # "ApiKey" — title case
})
```

HTTP headers are technically case-insensitive per RFC 7230, but some server
implementations or API gateways are strict. Aligning with the spec avoids
potential 401 errors.

### Fix required
```python
self.session.headers.update({
    "accept": "application/json",
    "apikey": self.api_key          # lowercase to match spec
})
```

---

## 3. [Medium] `get_people()` Pagination and New Required Parameters

### 3a. New query parameters on `GET /api/v1/people`

The new API declares these as **required** (they have defaults, so omitting them
should still work, but being explicit is safer):

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `include_family_members` | boolean | `true` | We don't need family data — set `false` for performance |
| `include_additional_fields` | boolean | `true` | **Must be `true`** — we rely on custom fields |
| `page` | int32 | `1` | Already passed |
| `page_size` | int32 | `100` | Currently using `50`; new default is `100` |

### 3b. Pagination detection

The new response wrapper includes a proper `paging` object:

```json
{
  "data": [ ... ],
  "paging": {
    "total_count": 312,
    "page": 1,
    "page_size": 100
  },
  "status_code": 200,
  "errors": null
}
```

Current detection (`if len(people) < page_size: break`) still works, but is fragile
(breaks if the last page happens to be exactly `page_size` records). Using
`total_count` is more reliable.

### Fix required
`backend_connector.py`, `get_people()` method — replace the loop body:

```python
page_size = 100   # updated from 50
params = params or {}

while True:
    params.update({
        "page": page,
        "page_size": page_size,
        "include_additional_fields": True,
        "include_family_members": False,
    })
    try:
        response = self.session.get(
            urljoin(self.api_url, "api/v1/people"),
            params=params
        )
        response.raise_for_status()
        data = response.json()
        people = data.get("data", [])           # always a wrapped response now
        paging = data.get("paging", {})
        total_count = paging.get("total_count", 0)
        all_people.extend(people)
        logger.info(f"Fetched page {page}: {len(people)} people "
                    f"(total so far: {len(all_people)} / {total_count})")
        if len(all_people) >= total_count or not people:
            break
        page += 1
    except requests.RequestException as e:
        logger.error(f"Failed to get people on page {page}: {str(e)}")
        break
```

---

## 4. [Medium] Group Membership Management — New Direct API Available

### What changed
The new API adds two endpoints that were missing before:

```
POST   /api/v1/groups/{group_id}/memberships
DELETE /api/v1/groups/{group_id}/memberships/{person_id}
```

### Current workaround
`group_assignment.py` exports an Excel file and instructs the operator to manually
import it in ChMeetings via *Tools > Import Group*. This is a manual, error-prone
step.

### What to add

Add two new methods to `ChMeetingsConnector` in `backend_connector.py`:

```python
def add_person_to_group(self, group_id: int, person_id: int) -> bool:
    """
    Add a person to a group.
    Returns True if successful (201=added, 200=already member both count as success).
    """
    try:
        response = self.session.post(
            urljoin(self.api_url, f"api/v1/groups/{group_id}/memberships"),
            json={"person_id": person_id}
        )
        response.raise_for_status()
        logger.info(f"Added person {person_id} to group {group_id} "
                    f"(status {response.status_code})")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to add person {person_id} to group {group_id}: {e}")
        return False


def remove_person_from_group(self, group_id: int, person_id: int) -> bool:
    """
    Remove a person from a group.
    Returns True if successful.
    """
    try:
        response = self.session.delete(
            urljoin(self.api_url,
                    f"api/v1/groups/{group_id}/memberships/{person_id}")
        )
        response.raise_for_status()
        logger.info(f"Removed person {person_id} from group {group_id}")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to remove person {person_id} from group {group_id}: {e}")
        return False
```

Then update `group_assignment.py` to call these methods instead of generating the
Excel file. The `APPROVED_GROUP_NAME` group sync (currently done via Selenium in
`manager.py`) can also be replaced with direct API calls.

---

## 5. [No Change] `additional_fields` Read Path Is Still Compatible

The response shape for custom fields is now a typed discriminated union, but **all
variants still include `field_name` (string) and `value` (string)**, so the existing
dict-comprehension pattern in `participants.py` works without modification:

```python
# participants.py line 391 — still valid
additional_fields = {f["field_name"]: f["value"] for f in p.get("additional_fields", [])}
```

All seven field types (`text`, `multi_line_text`, `number`, `date`, `dropdown`,
`checkbox`, `multiple_choice`) return a `value` string in responses. Dropdown and
choice types additionally return `selected_option_id` / `selected_option_ids` (IDs),
but the human-readable `value` string is still present.

No changes needed in `participants.py` for reading custom field values.

---

## 6. [No Change] `get_groups()` and `get_group_people()` Are Compatible

Both methods already defensively handle the response envelope:
- `get_groups()`: `data if isinstance(data, list) else data.get("data", [])` — the
  `isinstance(data, list)` branch is now always False (responses are always wrapped),
  but `data.get("data", [])` returns the correct list.
- `get_group_people()`: `data.get("data", []) if isinstance(data, dict) else data` —
  always takes the dict branch correctly.

No changes needed.

---

## Complete Change Checklist

### `middleware/chmeetings/backend_connector.py`

- [ ] **Line 37**: Change `"ApiKey"` header key to `"apikey"` (lowercase)
- [ ] **Line 196** (`get_person()`): Change `return response.json()` to
      `return response.json().get("data")`
- [ ] **`get_people()` method**: Add `include_additional_fields=True`,
      `include_family_members=False` to params; update pagination to use
      `paging.total_count`; increase default `page_size` from `50` to `100`
- [ ] **New method**: `add_person_to_group(group_id, person_id)`
- [ ] **New method**: `remove_person_from_group(group_id, person_id)`

### `middleware/group_assignment.py`

- [ ] Replace Excel-export workaround with direct calls to `add_person_to_group()`

### `middleware/sync/manager.py`

- [ ] (Optional) Replace Selenium-based group sync with `add_person_to_group()` for
      adding approved participants to the `APPROVED_GROUP_NAME` group

---

## New API Endpoints Available (Not Previously Used)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/people/fields` | Retrieve all custom field definitions (field_id, field_name, type, options) — useful for building `field_id` lookup tables for write operations |
| `PUT` | `/api/v1/people/{id}` | Update a person record via API (replaces Selenium workaround) |
| `POST` | `/api/v1/people` | Create a new person record via API |
| `DELETE` | `/api/v1/people/{id}` | Archive/delete a person record |
| `GET` | `/api/v1/events` | List events |
| `GET` | `/api/v1/events/{event_id}/occurrences` | List event occurrences |
| `GET` | `/api/v1/occurrences/{occurrence_id}/attendance` | Get attendance records |

---

## API Write Operations (Future Work)

If the codebase ever needs to **write** custom field values back to ChMeetings
(e.g., marking a participant as approved), note that write requests use `field_id`
(integer), **not** `field_name`:

```json
// PUT /api/v1/people/{id}
{
  "additional_fields": [
    { "field_type": "dropdown", "field_id": 12345, "selected_option_id": 67890 },
    { "field_type": "text",     "field_id": 12346, "value": "some text" }
  ]
}
```

To map `field_name` → `field_id`, call `GET /api/v1/people/fields` once at startup
and cache the mapping. This is a prerequisite for any write-back operations.
