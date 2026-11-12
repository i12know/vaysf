"""Mock-mode tests for the ChMeetings API field inspector comparison logic."""
import pytest
from loguru import logger

import main
from config import CHM_CORE_FIELD_KEYS, CHM_FIELDS
from field_inspector import (
    STATUS_MISSING,
    STATUS_NOT_CHECKED,
    STATUS_OK,
    extract_custom_field_names,
    validate_chm_fields,
)

MAPPING = {"NICK_NAME": "nick_name", "CHURCH_TEAM": "Church Team"}
CORE = {"NICK_NAME"}
SECTIONS = [{"title": "Sports Fest", "fields": [{"field_name": "Church Team"}]}]


def _status(checks, key):
    return next(c.status for c in checks if c.key == key)


def test_core_key_present_in_person_response_is_ok():
    checks = validate_chm_fields(MAPPING, CORE, {"Church Team"}, [{"first_name": "A", "nick_name": None}])
    assert _status(checks, "NICK_NAME") == STATUS_OK


def test_core_key_absent_from_person_response_is_missing():
    checks = validate_chm_fields(MAPPING, CORE, {"Church Team"}, [{"first_name": "A", "nickname": "x"}])
    assert _status(checks, "NICK_NAME") == STATUS_MISSING


def test_core_key_is_not_looked_up_in_custom_field_definitions():
    # Even if a custom field happened to be labelled "nick_name", a core key
    # is validated against the person response only.
    checks = validate_chm_fields(MAPPING, CORE, {"Church Team", "nick_name"}, [{"first_name": "A"}])
    assert _status(checks, "NICK_NAME") == STATUS_MISSING


def test_custom_label_absent_from_people_fields_is_missing():
    checks = validate_chm_fields(MAPPING, CORE, {"Some Other Field"}, [{"nick_name": "Em"}])
    assert _status(checks, "CHURCH_TEAM") == STATUS_MISSING
    assert _status(checks, "NICK_NAME") == STATUS_OK


def test_custom_label_present_in_people_fields_is_ok():
    checks = validate_chm_fields(MAPPING, CORE, extract_custom_field_names(SECTIONS), [{"nick_name": "Em"}])
    assert _status(checks, "CHURCH_TEAM") == STATUS_OK


def test_custom_label_is_not_satisfied_by_person_keys():
    checks = validate_chm_fields(MAPPING, CORE, set(), [{"Church Team": "x", "nick_name": "Em"}])
    assert _status(checks, "CHURCH_TEAM") == STATUS_MISSING


@pytest.mark.parametrize("sample", [None, [], [None, "not a person"]])
def test_no_sample_person_gives_not_checked_for_core_keys(sample):
    checks = validate_chm_fields(MAPPING, CORE, {"Church Team"}, sample)
    assert _status(checks, "NICK_NAME") == STATUS_NOT_CHECKED
    assert _status(checks, "CHURCH_TEAM") == STATUS_OK  # custom check unaffected


def test_no_field_definitions_gives_not_checked_for_custom_labels():
    checks = validate_chm_fields(MAPPING, CORE, None, [{"nick_name": "Em"}])
    assert _status(checks, "CHURCH_TEAM") == STATUS_NOT_CHECKED
    assert _status(checks, "NICK_NAME") == STATUS_OK


def test_keys_are_unioned_across_sample_people():
    checks = validate_chm_fields(MAPPING, CORE, set(), [{"first_name": "A"}, {"nick_name": "Em"}])
    assert _status(checks, "NICK_NAME") == STATUS_OK


def test_extract_custom_field_names_tolerates_junk():
    assert extract_custom_field_names(None) == set()
    assert extract_custom_field_names([{"fields": [{"field_name": ""}, {}]}]) == set()


def test_core_keys_are_real_chm_fields_entries():
    assert CHM_CORE_FIELD_KEYS <= set(CHM_FIELDS)
    assert "NICK_NAME" in CHM_CORE_FIELD_KEYS
    assert CHM_FIELDS["NICK_NAME"] == "nick_name"


# ── Wiring: the real `test --system chmeetings --test-type api-inspect` branch ──

class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeConnector:
    people = [{"id": 1, "first_name": "Emily", "last_name": "Smith", "nick_name": "Em"}]
    fail_people = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def authenticate(self):
        return True

    def get_fields(self):
        fields = [{"field_name": v} for k, v in CHM_FIELDS.items() if k not in CHM_CORE_FIELD_KEYS]
        return {"sections": [{"title": "All", "section_id": 1, "fields": fields}]}

    def get_groups(self):
        return []

    def _api_request(self, method, path, params=None):
        if self.fail_people:
            raise RuntimeError("boom")
        return _FakeResp({"data": self.people})

    def _extract_data(self, payload):
        return payload["data"]

    def get_person(self, pid):
        return self.people[0]


def _run_inspect(monkeypatch, **attrs):
    import chmeetings.backend_connector as backend

    class Connector(_FakeConnector):
        pass

    for k, v in attrs.items():
        setattr(Connector, k, v)
    monkeypatch.setattr(backend, "ChMeetingsConnector", Connector)
    messages = []
    sink_id = logger.add(lambda msg: messages.append(str(msg)), level="INFO")
    try:
        ok = main.test_connectivity(system="chmeetings", test_type="api-inspect")
    finally:
        logger.remove(sink_id)
    return ok, "".join(messages)


def test_api_inspect_no_longer_flags_nick_name(monkeypatch):
    ok, text = _run_inspect(monkeypatch)
    assert ok is True
    assert "MISSING" not in text
    assert "OK  CHM_FIELDS['NICK_NAME'] = 'nick_name'" in text
    assert "All CHM_FIELDS matched successfully." in text


def test_api_inspect_still_flags_core_drift(monkeypatch):
    ok, text = _run_inspect(monkeypatch, people=[{"id": 1, "first_name": "Emily"}])
    assert "MISSING  CHM_FIELDS['NICK_NAME']" in text
    assert "Some CHM_FIELDS did not match" in text


def test_api_inspect_reports_not_checked_when_no_people(monkeypatch):
    ok, text = _run_inspect(monkeypatch, people=[])
    assert "NOT CHECKED  CHM_FIELDS['NICK_NAME']" in text
    assert "MISSING" not in text
    assert "All CHM_FIELDS matched successfully." not in text


def test_api_inspect_people_fetch_failure_does_not_skip_custom_check(monkeypatch):
    ok, text = _run_inspect(monkeypatch, fail_people=True)
    assert ok is False
    assert "NOT CHECKED  CHM_FIELDS['NICK_NAME']" in text
    assert "OK  CHM_FIELDS['CHURCH_TEAM']" in text
