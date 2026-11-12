"""Pure comparison logic for the ChMeetings API field inspector.

``python main.py test --system chmeetings --test-type api-inspect`` fetches the
live field definitions and a few sample people, then calls
``validate_chm_fields`` to decide whether each ``CHM_FIELDS`` entry still
matches the API. Kept free of connectors and logging so it can be unit tested.

Two kinds of ``CHM_FIELDS`` entry exist and are checked against different
sources:

* custom field labels (the default) -- must appear as a ``field_name`` in
  ``GET /api/v1/people/fields``;
* core profile keys (named in ``config.CHM_CORE_FIELD_KEYS``) -- can be
  confirmed by observing the key on a person response. Optional keys may
  be omitted, so a sample without the key cannot establish drift.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

STATUS_OK = "ok"
STATUS_MISSING = "missing"
STATUS_NOT_CHECKED = "not_checked"
STATUS_NOT_OBSERVED = "not_observed"

SOURCE_PEOPLE_FIELDS = "people_fields"
SOURCE_PERSON_RESPONSE = "person_response"


@dataclass(frozen=True)
class FieldCheck:
    key: str            # CHM_FIELDS key, e.g. "NICK_NAME"
    expected: str       # CHM_FIELDS value, e.g. "nick_name"
    is_core: bool       # True for core profile keys
    status: str
    source: str         # where it was (or would have been) looked up


def extract_custom_field_names(sections: Any) -> set[str]:
    """Collect ``field_name`` values from the ``/people/fields`` sections."""
    names: set[str] = set()
    for section in sections if isinstance(sections, list) else []:
        for field in section.get("fields", []):
            fname = field.get("field_name")
            if fname:
                names.add(fname)
    return names


def collect_person_keys(sample_people: Optional[Iterable[Mapping[str, Any]]]) -> Optional[set[str]]:
    """Union of keys across sample person responses; None if there are none."""
    people = [p for p in (sample_people or []) if isinstance(p, Mapping)]
    if not people:
        return None
    keys: set[str] = set()
    for person in people:
        keys.update(person.keys())
    return keys


def validate_chm_fields(
    chm_fields: Mapping[str, str],
    core_keys: Iterable[str],
    custom_field_names: Optional[set[str]],
    sample_people: Optional[Iterable[Mapping[str, Any]]],
) -> list[FieldCheck]:
    """Compare every ``CHM_FIELDS`` entry against the live API.

    ``custom_field_names`` is the set of labels from ``/people/fields`` (None if
    the definitions could not be fetched). ``sample_people`` are person
    responses. Core keys are ``not_checked`` without a sample and
    ``not_observed`` if no sampled response contains the key.
    """
    core = set(core_keys)
    person_keys = collect_person_keys(sample_people)
    results: list[FieldCheck] = []
    for key, expected in chm_fields.items():
        if key in core:
            known, source = person_keys, SOURCE_PERSON_RESPONSE
        else:
            known, source = custom_field_names, SOURCE_PEOPLE_FIELDS
        if known is None:
            status = STATUS_NOT_CHECKED
        elif expected in known:
            status = STATUS_OK
        else:
            status = STATUS_NOT_OBSERVED if key in core else STATUS_MISSING
        results.append(FieldCheck(key, expected, key in core, status, source))
    return results
