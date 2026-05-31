from __future__ import annotations

from datetime import UTC, datetime

from tinyfan.stores.gcs_pickle import GcsPickleStore


class FakeBlob:
    def __init__(self, name: str, generation: int | None = None) -> None:
        self.name = name
        self.generation = generation
        self.content_type: str | None = None
        self.data: bytes | None = None

    def upload_from_string(self, data: bytes, content_type: str) -> None:
        self.data = data
        self.content_type = content_type
        self.generation = (self.generation or 0) + 1

    def download_as_bytes(self) -> bytes:
        assert self.data is not None
        return self.data


class FakeBucket:
    def __init__(self, name: str) -> None:
        self.name = name
        self.blobs: dict[str, FakeBlob] = {}

    def blob(self, name: str, generation: int | None = None) -> FakeBlob:
        blob = self.blobs.setdefault(name, FakeBlob(name, generation))
        blob.generation = generation or blob.generation
        return blob


class FakeClient:
    def __init__(self) -> None:
        self.buckets: dict[str, FakeBucket] = {}

    def bucket(self, name: str) -> FakeBucket:
        return self.buckets.setdefault(name, FakeBucket(name))


def test_gcs_pickle_store_roundtrip() -> None:
    client = FakeClient()
    store = GcsPickleStore("test-bucket", prefix="runs", client=client)
    value = {"hello": ["world", 1]}
    rundata = {
        "flow_name": "flow",
        "asset_name": "asset",
        "ds": "2026-05-31",
        "data_interval_start": datetime(2026, 5, 31, 12, 30, tzinfo=UTC),
    }

    index = store.store(value, rundata)

    assert index["bucket"] == "test-bucket"
    assert index["name"].startswith("runs/flow/asset/2026-05-31T12-30-00-00-00/")
    assert index["name"].endswith(".pickle")
    assert index["generation"] == 1
    assert client.bucket("test-bucket").blob(index["name"]).content_type == "application/octet-stream"
    assert store.retrieve(index, source_rundata=rundata, target_rundata={}) == value


def test_gcs_pickle_store_uses_metadata_blob_name() -> None:
    store = GcsPickleStore("test-bucket", client=FakeClient())
    rundata = {"metadata": {"blob_name": "/custom/path/value.pkl"}}

    index = store.store("value", rundata)

    assert index["name"] == "custom/path/value.pkl"
