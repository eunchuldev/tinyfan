import base64
from datetime import datetime

import pytest

from tinyfan.flowrundata import encode_rundata, load_rundata
from tinyfan.utils.exjson import dumps


def test_rundata_transport():
    parent = {
        "metadata": {"text": "\"\\\n''' {{workflow.name}} $(APP_MODE) 한글🙂"},
        "store_entry_idx": {"name": 'folder\\quoted"file'},
        "data_interval_start": datetime.fromisoformat("2026-09-16T00:00:00+09:00"),
    }
    encoded = encode_rundata(parent)
    assert "{{" not in encoded and "$" not in encoded
    assert load_rundata(dumps({"parents": {"source": encoded}})) == {"parents": {"source": parent}}
    assert load_rundata("{}") == {}
    assert load_rundata('{"parents": null}') == {"parents": None}


@pytest.mark.parametrize(
    "text",
    [
        "not JSON",
        "null",
        "[]",
        '{"parents": []}',
        '{"parents": {"source": {}}}',
        '{"parents": {"source": "%%%"}}',
        dumps({"parents": {"source": base64.b64encode(b"not JSON").decode()}}),
        dumps({"parents": {"source": base64.b64encode(b"[]").decode()}}),
        dumps({"parents": {"source": base64.b64encode(b"\xff").decode()}}),
    ],
)
def test_invalid_rundata_is_rejected(text):
    with pytest.raises((TypeError, ValueError)):
        load_rundata(text)


@pytest.mark.parametrize(
    "schedule, timezone, scheduled_time, expected_start",
    [
        ("@monthly", "UTC", "2025-03-01T00:00:00Z", "2025-02-01T00:00:00+00:00"),
        ("@monthly", "UTC", "2024-03-01T00:00:00Z", "2024-02-01T00:00:00+00:00"),
        ("@monthly", "UTC", "2026-05-01T00:00:00Z", "2026-04-01T00:00:00+00:00"),
        ("@yearly", "UTC", "2025-01-01T00:00:00Z", "2024-01-01T00:00:00+00:00"),
        ("0 0 31 * *", "UTC", "2026-05-31T00:00:00Z", "2026-03-31T00:00:00+00:00"),
        ("0 9 * * MON-FRI", "UTC", "2024-09-16T09:00:00Z", "2024-09-13T09:00:00+00:00"),
        ("@daily", "Asia/Seoul", "2026-09-15T15:00:00Z", "2026-09-15T00:00:00+09:00"),
        ("@daily", "America/New_York", "2026-03-09T04:00:00Z", "2026-03-08T00:00:00-05:00"),
        ("@daily", "America/New_York", "2026-11-02T05:00:00Z", "2026-11-01T00:00:00-04:00"),
        ("30 2 * * *", "America/New_York", "2026-03-09T06:30:00Z", "2026-03-07T02:30:00-05:00"),
        ("30 1 * * *", "America/New_York", "2026-11-01T05:30:00Z", "2026-10-31T01:30:00-04:00"),
        ("30 1 * * *", "America/New_York", "2026-11-01T06:30:00Z", "2026-11-01T01:30:00-04:00"),
        ("30 1 * * *", "America/New_York", "2026-11-02T06:30:00Z", "2026-11-01T01:30:00-05:00"),
        ("*/30 * * * *", "America/New_York", "2026-03-08T07:00:00Z", "2026-03-08T01:30:00-05:00"),
        ("*/30 * * * *", "America/New_York", "2026-11-01T06:00:00Z", "2026-11-01T01:30:00-04:00"),
        ("15 2 * * *", "Australia/Lord_Howe", "2026-10-05T02:15:00+11:00", "2026-10-03T02:15:00+10:30"),
        ("45 1 * * *", "Australia/Lord_Howe", "2026-04-05T01:45:00+10:30", "2026-04-05T01:45:00+11:00"),
        ("@daily", "Pacific/Apia", "2011-12-31T00:00:00+14:00", "2011-12-29T00:00:00-10:00"),
    ],
)
def test_calendar_interval(schedule, timezone, scheduled_time, expected_start):
    data = load_rundata(dumps({"schedule": schedule, "timezone": timezone, "scheduled_time": scheduled_time}))
    assert data["data_interval_start"].isoformat() == expected_start
    assert data["data_interval_end"].timestamp() == datetime.fromisoformat(scheduled_time).timestamp()
    assert data["data_interval_start"].timestamp() < data["data_interval_end"].timestamp()
    assert data["ds"] == expected_start[:10]
    assert data["ts"] == expected_start
    assert not {"schedule", "timezone", "scheduled_time"}.intersection(data)


@pytest.mark.parametrize("scheduled_time", ["2026-09-16T00:00:00", "not a timestamp", "{{workflow.scheduledTime}}"])
def test_invalid_scheduled_time_is_rejected(scheduled_time):
    with pytest.raises(ValueError):
        load_rundata(dumps({"schedule": "@daily", "timezone": "UTC", "scheduled_time": scheduled_time}))
