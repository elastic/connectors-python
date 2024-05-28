#
# Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
# or more contributor license agreements. Licensed under the Elastic License 2.0;
# you may not use this file except in compliance with the Elastic License 2.0.
#

from collections import ChainMap
from collections.abc import Mapping as MappingType
from functools import partial

from elasticsearch import ApiError
from elasticsearch import (
    NotFoundError as ElasticNotFoundError,
)
from elasticsearch.helpers import async_scan

from connectors.es.client import ESClient
from connectors.es.settings import TIMESTAMP_FIELD, Mappings, Settings
from connectors.logger import logger


class _DeepChainMap(ChainMap):
    """A view grouping multiple mappings in depth.

    In addition to the characteristics of `collections.ChainMap`, each value
    becomes a view if its type is Mapping. In that case, the view consists of
    only values prior to the first non-Mapping value found in the underlying
    mappings.

    For example, if the underlying mappings return the following values to a
    key - `dict`, `dict`, `str`, and `dict`, the value becomes a view grouping
    only the first two `dict` objects.
    """

    def __getitem__(self, key):
        value = super().__getitem__(key)
        if not isinstance(value, MappingType):
            return value

        values = []
        for m in self.maps:
            try:
                v = m[key]
            except KeyError:
                continue

            if isinstance(v, MappingType):
                values.append(v)
            else:
                break

        return type(self)(*values)

    def to_dict(self):
        """Returns a new dict by merging the underlying mappings."""
        return {k: self[k].to_dict()
                    if isinstance(self[k], type(self))
                    else self[k]
                for k in self}


class ESManagementClient(ESClient):
    """
    Elasticsearch client with methods to manage connector-related indices.

    Additionally to regular methods of ESClient, this client provides methods to work with arbitrary indices,
    for example allowing to list indices, delete indices, wipe data from indices and such.

    ESClient should be used to provide rich clients that operate on "domains", such as:
        - specific connector
        - specific job

    This client, on the contrary, is used to manage a number of indices outside of connector protocol operations.
    """

    def __init__(self, config):
        logger.debug(f"ESManagementClient connecting to {config['host']}")
        # initialize ESIndex instance
        super().__init__(config)

    async def ensure_exists(self, indices=None):
        if indices is None:
            indices = []

        for index in indices:
            logger.debug(f"Checking index {index}")
            if not await self._retrier.execute_with_retry(
                partial(self.client.indices.exists, index=index)
            ):
                await self._retrier.execute_with_retry(
                    partial(self.client.indices.create, index=index)
                )
                logger.debug(f"Created index {index}")

    async def create_content_index(self, search_index_name, language_code):
        settings = Settings(language_code=language_code, analysis_icu=False).to_hash()
        mappings = Mappings.default_text_fields_mappings(is_connectors_index=True)

        return await self._retrier.execute_with_retry(
            partial(
                self.client.indices.create,
                index=search_index_name,
                mappings=mappings,
                settings=settings,
            )
        )

    async def ensure_content_index_mappings(self, index, mappings):
        # open = Match open, non-hidden indices. Also matches any non-hidden data stream.
        # Content indices are always non-hidden.
        response = await self._retrier.execute_with_retry(
            partial(self.client.indices.get_mapping, index=index)
        )

        if existing_mappings := response[index].get("mappings", {}):
            logger.info(
                "Index %s already has mappings. Adding non-present mappings", index
            )
            desired_mappings = _DeepChainMap(existing_mappings, mappings).to_dict()
        else:
            logger.info(
                "Index %s has no mappings or it's empty. Adding mappings...", index
            )
            desired_mappings = mappings

        try:
            await self._retrier.execute_with_retry(
                partial(
                    self.client.indices.put_mapping,
                    index=index,
                    dynamic=desired_mappings.get("dynamic", False),
                    dynamic_templates=desired_mappings.get("dynamic_templates", []),
                    properties=desired_mappings.get("properties", {}),
                )
            )
            logger.info("Successfully added mappings for index %s", index)
        except Exception as e:
            logger.warning(
                f"Could not create mappings for index {index}, encountered error {e}"
            )


    async def ensure_content_index_settings(
        self, index_name, index, language_code=None
    ):
        existing_settings = index.get("settings", {})
        settings = Settings(language_code=language_code, analysis_icu=False).to_hash()

        if "analysis" not in existing_settings.get("index", {}):
            logger.info(
                f"Index {index_name} has no settings or it's empty. Adding settings..."
            )

            # Open index, update settings, close index
            try:
                if self.serverless:
                    await self._retrier.execute_with_retry(
                        partial(
                            self.client.perform_request,
                            "PUT",
                            f"/{index_name}/_settings?reopen=true",
                            body=settings,
                            headers={
                                "accept": "application/json",
                                "content-type": "application/json",
                            },
                        )
                    )
                else:
                    await self._retrier.execute_with_retry(
                        partial(self.client.indices.close, index=index_name)
                    )

                    await self._retrier.execute_with_retry(
                        partial(
                            self.client.indices.put_settings,
                            index=index_name,
                            body=settings,
                        )
                    )

                    await self._retrier.execute_with_retry(
                        partial(self.client.indices.open, index=index_name)
                    )

                    logger.info(f"Successfully added settings for index {index_name}")
            except Exception as e:
                logger.warning(
                    f"Could not create settings for index {index_name}, encountered error {e}"
                )
        else:
            logger.debug(
                f"Index {index_name} already has settings, skipping settings creation"
            )

    async def ensure_ingest_pipeline_exists(
        self, pipeline_id, version, description, processors
    ):
        try:
            await self._retrier.execute_with_retry(
                partial(self.client.ingest.get_pipeline, id=pipeline_id)
            )
        except ElasticNotFoundError:
            await self._retrier.execute_with_retry(
                partial(
                    self.client.ingest.put_pipeline,
                    id=pipeline_id,
                    version=version,
                    description=description,
                    processors=processors,
                )
            )

    async def delete_indices(self, indices):
        await self._retrier.execute_with_retry(
            partial(self.client.indices.delete, index=indices, ignore_unavailable=True)
        )

    async def clean_index(self, index_name):
        return await self._retrier.execute_with_retry(
            partial(
                self.client.delete_by_query,
                index=index_name,
                body={"query": {"match_all": {}}},
                ignore_unavailable=True,
            )
        )

    async def list_indices(self, index="*"):
        """
        List indices using Elasticsearch.stats API. Includes the number of documents in each index.
        """
        indices = {}
        response = await self._retrier.execute_with_retry(
            partial(self.client.indices.stats, index=index)
        )

        for index in response["indices"].items():
            indices[index[0]] = {"docs_count": index[1]["primaries"]["docs"]["count"]}

        return indices

    async def list_indices_serverless(self, index="*"):
        """
        List indices in a serverless environment. This method is a workaround to the fact that
        the `indices.stats` API is not available in serverless environments.
        """

        indices = {}
        try:
            response = await self._retrier.execute_with_retry(
                partial(self.client.indices.get, index=index)
            )

            for index in response.items():
                indices[index[0]] = {}

        except ApiError as e:
            logger.error(f"Error listing indices: {e}")

        return indices

    async def index_exists(self, index_name):
        return await self._retrier.execute_with_retry(
            partial(self.client.indices.exists, index=index_name)
        )

    async def get_index(self, index_name, ignore_unavailable=False):
        return await self._retrier.execute_with_retry(
            partial(
                self.client.indices.get,
                index=index_name,
                ignore_unavailable=ignore_unavailable,
            )
        )

    async def upsert(self, _id, index_name, doc):
        return await self._retrier.execute_with_retry(
            partial(
                self.client.index,
                id=_id,
                index=index_name,
                document=doc,
            )
        )

    async def bulk_insert(self, operations, pipeline):
        return await self._retrier.execute_with_retry(
            partial(
                self.client.bulk,
                operations=operations,
                pipeline=pipeline,
            )
        )

    async def yield_existing_documents_metadata(self, index):
        """Returns an iterator on the `id` and `_timestamp` fields of all documents in an index.

        WARNING

        This function will load all ids in memory -- on very large indices,
        depending on the id length, it can be quite large.

        300,000 ids will be around 50MiB
        """
        logger.debug(f"Scanning existing index {index}")
        if not await self.index_exists(index):
            return

        async for doc in async_scan(
            client=self.client, index=index, _source=["id", TIMESTAMP_FIELD]
        ):
            source = doc["_source"]
            doc_id = source.get("id", doc["_id"])
            timestamp = source.get(TIMESTAMP_FIELD)

            yield doc_id, timestamp

    async def get_connector_secret(self, connector_secret_id):
        secret = await self._retrier.execute_with_retry(
            partial(
                self.client.perform_request,
                "GET",
                f"/_connector/_secret/{connector_secret_id}",
            )
        )
        return secret.get("value")

    async def create_connector_secret(self, secret_value):
        secret = await self._retrier.execute_with_retry(
            partial(
                self.client.perform_request,
                "POST",
                "/_connector/_secret",
                headers={
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                body={"value": secret_value},
            )
        )
        return secret.get("id")
