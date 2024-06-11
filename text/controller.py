import asyncio
import itertools
from os import path
from typing import Dict, List, Tuple

import typer

# --------------------------------------------------------------------------- #
from app import fields, util
from app.schemas import (
    AsOutput,
    AssignmentSchema,
    CollectionSchema,
    DocumentSchema,
    mwargs,
)
from client.handlers import CONSOLE, ConsoleHandler, HandlerData, RequestHandlerData
from client.requests import ContextData as ClientContextData
from client.requests import Requests
from pydantic import TypeAdapter

from text import snippets
from text.schemas import (
    PATH_CONFIGS_BUILDER_DEFAULT,
    BaseObjectStatus,
    BuilderConfig,
    Config,
    TextBuilderStatus,
    TextDataConfig,
    TextDataStatus,
    TextCollectionStatus,
    TextDocumentConfig,
    TextDocumentStatus,
)

logger = util.get_logger(__name__)


class ContextData(ClientContextData):
    config: Config  # type: ignore
    text: BuilderConfig

    @classmethod
    def typer_callback(
        cls, context: typer.Context, text_config: str = PATH_CONFIGS_BUILDER_DEFAULT
    ) -> None:

        config = mwargs(Config)
        context.obj = ContextData(
            config=config,
            text=BuilderConfig.load(text_config),
            console_handler=ConsoleHandler(config),
        )


class TextController:

    context_data: ContextData
    config: Config
    text: BuilderConfig
    data: TextDataConfig
    fmt_name: str

    @property
    def status(self) -> TextDataStatus:
        status_wrapper = self.text.status
        if status_wrapper is None:
            raise ValueError()
        return status_wrapper.status

    def __init__(self, context_data: ContextData):
        self.context_data = context_data
        self.config = context_data.config
        self.text = context_data.text
        self.data = self.text.data
        self.fmt_name = f"{{}}-{self.data.identifier}"

    # NOTE: Moving discovery out of here gaurentees that status exists.
    async def ensure_collection(
        self,
        requests: Requests,
    ) -> TextCollectionStatus:
        """Update the collection in captura."""
        collection_config = self.text.data.collection
        name = collection_config.name

        collection = await self.text.data.discover_collection(requests)
        if collection is None:
            collection = await self.text.data.create_collection(requests, name)

        return TextCollectionStatus(
            name=collection_config.name,
            description=collection.description,
            name_captura=collection.name,
            uuid=collection.uuid,
            deleted=False,
        )

    async def ensure_document(
        self,
        requests: Requests,
        name: str,
    ) -> TextDocumentStatus:
        """Upsert document items. Each document should be stored in raw form
        and as html.
        """

        item = self.text.data.require(name)
        document = await self.text.data.discover_document(requests, name)
        if document is None:
            document = await self.text.data.create_document(requests, name)

        return TextDocumentStatus(
            uuid=document.uuid,
            name=name,
            name_captura=document.name,
            deleted=False,
            format_out=item.format_out,
            content_file=item.content_file,
            description=item.description,
            format_in=item.format_in,
        )

    async def ensure(self, requests: Requests) -> TextDataStatus:

        documents_tasks = (
            self.ensure_document(requests, name) for name in self.data.documents
        )

        documents: Dict[str, TextDocumentStatus]
        documents = {v.name: v for v in await asyncio.gather(*documents_tasks)}
        collection = await self.ensure_collection(requests)

        # NOTE: Assignments. Note that create is imdempotent.
        uuid_document = list(document.uuid for document in documents.values())

        logger.debug("Creating assignments (imdempotently).")
        check_status = requests.handler.check_status
        adptr = TypeAdapter(AsOutput[List[AssignmentSchema]])
        res = await requests.a.c.create(collection.uuid, uuid_document=uuid_document)
        (_,), err = check_status(res, expect_status=201, adapter=adptr)
        if err is not None:
            raise err

        data = self.text.data
        return TextDataStatus(
            identifier=data.identifier,
            documents=documents,
            collection=collection,
            path_docs=data.path_docs,
        )

    # NOTE: Only return status when status has been changed.
    async def destroy(self, requests: Requests) -> TextDataStatus:

        status = self.status
        documents_status = await asyncio.gather(
            *(status.destroy_document(requests, name) for name in status.documents)
        )
        collection_status = await status.destroy_collection(requests)

        return TextDataStatus(
            documents={status.name: status for status in documents_status},
            collection=collection_status,
            identifier=status.identifier,
            path_docs=status.path_docs,
        )

    async def update(self, requests: Requests) -> None:
        status = self.status
        await asyncio.gather(
            *(status.update_document(requests, name) for name in status.documents)
        )
        await status.update_collection(requests)
