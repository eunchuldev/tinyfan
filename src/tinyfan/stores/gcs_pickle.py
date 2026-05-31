from __future__ import annotations

import pickle
import re
import uuid
from collections.abc import Mapping
from typing import Any, NotRequired, TypedDict

from ..config import ConfigValue
from .base import FlowRunData, StoreBase


class GcsPickleStoreIndex(TypedDict):
    bucket: str
    name: str
    generation: NotRequired[int]


class GcsPickleStoreMetadata(TypedDict, total=False):
    blob_name: str
    prefix: str


ConfigurableString = str | ConfigValue


_GCS_EXTRA_ERROR = "GCS extra not installed. Please install with `pip install tinyfan[gcs]`."


def _new_storage_client(client_kwargs: Mapping[str, Any]) -> Any:
    try:
        from google.cloud import storage
    except ImportError as exc:
        raise ImportError(_GCS_EXTRA_ERROR) from exc

    return storage.Client(**client_kwargs)


def _resolve(value: ConfigurableString) -> str:
    if isinstance(value, ConfigValue):
        return value.get_value()
    return value


def _path_part(value: object, fallback: str) -> str:
    text = str(value if value is not None else fallback).strip()
    text = re.sub(r"[^A-Za-z0-9._=-]+", "-", text)
    return text.strip(".-") or fallback


def _join_blob_name(*parts: str) -> str:
    return "/".join(part.strip("/") for part in parts if part and part.strip("/"))


def _run_part(rundata: FlowRunData[Any, Any]) -> str:
    for key in ("data_interval_start", "ts", "ds"):
        value = rundata.get(key)
        if value is None:
            continue
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        return _path_part(value, "manual")
    return "manual"


class GcsPickleStore(StoreBase[object, GcsPickleStoreMetadata, GcsPickleStoreIndex]):
    bucket: ConfigurableString
    prefix: ConfigurableString

    def __init__(
        self,
        bucket: ConfigurableString,
        prefix: ConfigurableString = "tinyfan",
        *,
        client: Any | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        pickle_protocol: int = pickle.HIGHEST_PROTOCOL,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix
        self._client = client
        self._client_kwargs = dict(client_kwargs or {})
        self.pickle_protocol = pickle_protocol

    @staticmethod
    def id() -> str:
        return "tinyfan.gcs_pickle"

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = _new_storage_client(self._client_kwargs)
        return self._client

    def _bucket_name(self) -> str:
        bucket = _resolve(self.bucket).strip()
        if not bucket:
            raise ValueError("GCS bucket name must not be empty.")
        return bucket

    def _blob_name(self, rundata: FlowRunData[GcsPickleStoreMetadata, GcsPickleStoreIndex]) -> str:
        metadata = rundata.get("metadata")
        if isinstance(metadata, Mapping):
            blob_name = metadata.get("blob_name")
            if blob_name is not None:
                blob_name = str(blob_name).strip("/")
                if not blob_name:
                    raise ValueError("GCS blob_name metadata must not be empty.")
                return blob_name

            prefix = str(metadata.get("prefix") or _resolve(self.prefix))
        else:
            prefix = _resolve(self.prefix)

        flow_name = _path_part(rundata.get("flow_name"), "flow")
        asset_name = _path_part(rundata.get("asset_name"), "asset")
        run_id = _run_part(rundata)
        filename = f"{uuid.uuid4().hex}.pickle"
        return _join_blob_name(prefix, flow_name, asset_name, run_id, filename)

    def store(
        self,
        value: object,
        rundata: FlowRunData[GcsPickleStoreMetadata, GcsPickleStoreIndex],
    ) -> GcsPickleStoreIndex:
        bucket_name = self._bucket_name()
        blob = self._get_client().bucket(bucket_name).blob(self._blob_name(rundata))
        data = pickle.dumps(value, protocol=self.pickle_protocol)
        blob.upload_from_string(data, content_type="application/octet-stream")

        index: GcsPickleStoreIndex = {
            "bucket": bucket_name,
            "name": blob.name,
        }
        generation = getattr(blob, "generation", None)
        if generation is not None:
            index["generation"] = int(generation)
        return index

    def retrieve(
        self,
        index: GcsPickleStoreIndex,
        source_rundata: FlowRunData[GcsPickleStoreMetadata, GcsPickleStoreIndex],
        target_rundata: FlowRunData,
    ) -> object:
        del source_rundata, target_rundata

        bucket = self._get_client().bucket(index["bucket"])
        blob = bucket.blob(index["name"], generation=index.get("generation"))
        return pickle.loads(blob.download_as_bytes())
