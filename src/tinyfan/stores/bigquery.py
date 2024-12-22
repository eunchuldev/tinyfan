"""
from .base import StoreBase, PredefinedParams, Asset
import pickle
from typing import TypedDict, Literal
from google.cloud import bigquery
from pandas import DataFrame

DataType = Literal["Pandas.DataFrame", "object"]

T = DataFrame
Idx = TypedDict("Idx", {
    "project_id": str,
    "dataset_id": str,
    "table_id": str,
})
Meta = TypedDict("Meta", {
    "bq_table_id": str,
})

class BigqueryStore(StoreBase[Idx, Meta, T]):
    project_id: str
    dataset_id: str|None

    @staticmethod
    def id() -> str:
        return "tinyfan.bigquery"

    def __init__(self, project_id:str, dataset_id:str|None = None):
        self.project_id = project_id
        self.dataset_id = dataset_id

    def store(self, data: T, asset: Asset, params: PredefinedParams) -> Idx:
        client = bigquery.Client()
        ts = params.get('ts')
        table_id = asset.name
        if asset.user_metadata and 'table_id' in asset.user_metadata:
            table_id = asset.user_metadata['table_id']
        if '.' not in table_id:
            if self.dataset_id is None:
                raise ValueError(f"`{table_id}` is not valid. set the id as `<dataset-id>.<table-id>`, or provide `dataset_id` at store level.")
            table_id = self.dataset_id + '.' + table_id
        if isinstance(data, DataFrame):
            return pandas_gbq.to_gbq(data, table_id, project_id=self.project_id)
        else:
            raise ValueError(f"Unsupported data type `{type(data)}` for store `{self.id()}`", )

    def retrieve(self, index: Idx, _: dict | None = None) -> T:
        return pandas_gbq.from_gbq(index['table_id'], project_id=self.project_id)
"""
