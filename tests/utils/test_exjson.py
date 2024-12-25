from tinyfan.utils.exjson import loads, dumps
from datetime import datetime


def test_exjson():
    date = datetime.fromisoformat("2020-01-01T00:00:00Z")
    dumped = dumps({"t": date})
    assert dumped == '{"t": {"__tinyfan_datetime__": "2020-01-01T00:00:00+00:00"}}'
    loaded = loads(dumped)
    assert type(loaded["t"]) is datetime
    assert loaded["t"] == date
