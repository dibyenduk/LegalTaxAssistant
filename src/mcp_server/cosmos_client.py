"""Cosmos DB client wrapper for Legal Tax Assistant."""

from __future__ import annotations

import os
from typing import Any

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceNotFoundError


class CosmosDBClient:
    """Thin wrapper around the Azure Cosmos DB SDK using Entra ID authentication."""

    def __init__(
        self,
        endpoint: str | None = None,
        database_name: str | None = None,
    ):
        self._endpoint = endpoint or os.environ.get("COSMOS_ENDPOINT", "")
        self._database_name = database_name or os.environ.get(
            "COSMOS_DATABASE", "LegalTaxAssistantDB"
        )

        if not self._endpoint:
            raise ValueError("COSMOS_ENDPOINT must be set.")

        from azure.identity import DefaultAzureCredential
        credential = DefaultAzureCredential()
        self._client = CosmosClient(self._endpoint, credential=credential)

        self._db = self._client.get_database_client(self._database_name)

    def _container(self, name: str):
        return self._db.get_container_client(name)

    # --- Generic CRUD ---

    def create_item(self, container_name: str, item: dict[str, Any]) -> dict[str, Any]:
        container = self._container(container_name)
        return container.create_item(body=item)

    def read_item(
        self, container_name: str, item_id: str, partition_key: str
    ) -> dict[str, Any] | None:
        container = self._container(container_name)
        try:
            return container.read_item(item=item_id, partition_key=partition_key)
        except CosmosResourceNotFoundError:
            return None

    def upsert_item(self, container_name: str, item: dict[str, Any]) -> dict[str, Any]:
        container = self._container(container_name)
        return container.upsert_item(body=item)

    def replace_item(
        self,
        container_name: str,
        item_id: str,
        item: dict[str, Any],
        etag: str | None = None,
    ) -> dict[str, Any]:
        container = self._container(container_name)
        kwargs: dict[str, Any] = {}
        if etag:
            kwargs["if_match"] = etag
        return container.replace_item(item=item_id, body=item, **kwargs)

    def query_items(
        self,
        container_name: str,
        query: str,
        parameters: list[dict[str, Any]] | None = None,
        partition_key: str | None = None,
    ) -> list[dict[str, Any]]:
        container = self._container(container_name)
        kwargs: dict[str, Any] = {
            "query": query,
            "enable_cross_partition_query": partition_key is None,
        }
        if parameters:
            kwargs["parameters"] = parameters
        if partition_key is not None:
            kwargs["partition_key"] = partition_key
        return list(container.query_items(**kwargs))

    def delete_item(
        self, container_name: str, item_id: str, partition_key: str
    ) -> None:
        container = self._container(container_name)
        container.delete_item(item=item_id, partition_key=partition_key)
