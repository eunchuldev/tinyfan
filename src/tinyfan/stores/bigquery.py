'''
from .base import StoreBase, FlowRunData
from typing import TypedDict, TypeVar, NotRequired
import pickle
import zlib
import base64
try:
    import google.cloud.bigquery as bq
    import pandas as pd
except ImportError:
    raise ImportError(
        "BigQuery extra not installed. Please install with `pip install tinyfan[bigquery]`"
    )

class BigqueryStoreMetadata(TypedDict):
    table_name: NotRequired[str]
    partition_col: str

UMeta = TypeVar("UMeta", bound=BigqueryStoreMetadata)

class BigqueryStore(StoreBase[pd.DataFrame, UMeta, None]):
    """
    Usage:

    .. code-block:: python
        from tinyflow import asset
        from tinyflow.store.bigquery import BigqueryStore

        bq_store = BigqueryStore()

        @asset(
            store = bq_store,
            metadata = {
                "table_name": "my_table",
                "partition_col": "date",
            }
        )
        def my_asset():
            return ""


    """
    @staticmethod
    def id() -> str:
        return "tinyfan.bigquery"

    client: bq.Client

    def __init__(self, *args, **kwargs):
        self.client = bq.Client(*args, **kwargs)

    def store(
        self,
        value: object,
        rundata: FlowRunData[UMeta, None],
    ) -> None:
        metadata = rundata.get('metadata')
        return None

    def retrieve(
        self,
        index: None,
        source_rundata: FlowRunData[UMeta, None],
        target_rundata: FlowRunData,
    ) -> object:
        del source_rundata, target_rundata
        return pickle.loads(decode(index))
'''
