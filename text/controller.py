import asyncio
import itertools
from os import path
from typing import Annotated, Dict, Generator, List, Tuple

import typer

# --------------------------------------------------------------------------- #
from app import fields, util
from app.schemas import (
    AsOutput,
    AssignmentSchema,
    BaseModel,
    CollectionSchema,
    DocumentSchema,
    Field,
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
    TextCollectionStatus,
    TextDataConfig,
    TextDataStatus,
    TextDocumentConfig,
    TextDocumentStatus,
)

logger = util.get_logger(__name__)


DESC_NAMES = "Document names to filter by. Uses the names specified in ``text.yaml``."
DESC_FORMAT = "Formats to filter by."


class TextOptions(BaseModel):
    names: Annotated[
        List[str] | None,
        Field(description=DESC_NAMES, default=None),
    ]
    # formats: Annotated[
    #     List[snippets.Format] | None,
    #     Field(description=DESC_FORMAT, default=None),
    # ]


class ContextData(ClientContextData):
    """The goal is to make this easy to use as a callback for typer and as a
    dependency in typer applications.
    """

    # config: Annotated[
    #     Config,
    #     Field(description="Captura client configuration."),
    # ]
    text: Annotated[
        BuilderConfig,
        Field(description="Text builder configuration."),
    ]
    options: Annotated[
        TextOptions,
        Field(description="Options from command line globals or API calls."),
    ]

    @classmethod
    def typer_callback(
        cls,
        context: typer.Context,
        text_config: Annotated[
            str,
            typer.Option("--config-text"),
        ] = PATH_CONFIGS_BUILDER_DEFAULT,
        names: Annotated[
            List[str] | None,
            typer.Option("--name", help=DESC_NAMES),
        ] = None,
        # formats: Annotated[
        #     List[snippets.Format] | None,
        #     typer.Option("--format", help=DESC_FORMAT),
        # ] = None,
    ) -> None:
        """This defines all of the global flags for typer."""

        config = mwargs(Config)
        context.obj = cls(
            config=config,
            text=BuilderConfig.load(text_config),
            console_handler=ConsoleHandler(config),
            options=TextOptions(names=names),  # , formats=formats),
        )


# NOTE: Options should be passed directly. That is, accept ``options`` as a
#       keyword argument and do not get it directly from context data. The only
#       reason it is included in context data is so that it is it may be
#       collected from the command line.
class TextController:

    # context_data: ContextData
    config: Config
    text: BuilderConfig
    data: TextDataConfig

    @property
    def status(self) -> TextDataStatus:
        status_wrapper = self.text.status
        if status_wrapper is None:
            raise ValueError("Status does not exist.")
        return status_wrapper.status

    def __init__(self, context_data: ContextData):
        # self.context_data = context_data
        self.config = context_data.config
        self.text = context_data.text
        self.data = self.text.data

    def filter_names(self, options: TextOptions) -> Generator[str, None, None]:
        names = (name for name in self.text.data.documents)
        if options.names is not None:
            names = (name for name in names if name in options.names)
        return names

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

    async def ensure(self, requests: Requests, options: TextOptions) -> TextDataStatus:

        if options.names is not None:
            raise ValueError("``ensure`` cannot yet filter by names.")

        documents_tasks = (
            self.ensure_document(requests, name) for name in self.data.documents
        )

        documents_ensured: Dict[str, TextDocumentStatus]
        documents_ensured = {v.name: v for v in await asyncio.gather(*documents_tasks)}

        collection = await self.ensure_collection(requests)

        # NOTE: Assignments. Note that create is imdempotent.
        uuid_document = list(document.uuid for document in documents_ensured.values())

        logger.debug("Creating assignments (imdempotently).")
        check_status = requests.handler.check_status
        adptr = TypeAdapter(AsOutput[List[AssignmentSchema]])
        res = await requests.a.c.create(collection.uuid, uuid_document=uuid_document)
        (_,), err = check_status(res, expect_status=201, adapter=adptr)
        if err is not None:
            raise err

        return TextDataStatus(
            identifier=self.text.data.identifier,
            documents=documents_ensured,
            collection=collection,
            path_docs=self.text.data.path_docs,
        )

    # NOTE: Only return status when status has been changed.
    async def destroy(self, requests: Requests, options: TextOptions) -> TextDataStatus:

        status = self.status
        if options.names is not None:
            raise ValueError("``destroy`` cannot yet filter by names.")

        documents_destroyed = await asyncio.gather(
            *(status.destroy_document(requests, name) for name in self.status.documents)
        )
        collection_destroyed = await status.destroy_collection(requests)

        return TextDataStatus(
            documents={status.name: status for status in documents_destroyed},
            collection=collection_destroyed,
            identifier=status.identifier,
            path_docs=status.path_docs,
        )

    async def update(self, requests: Requests, options: TextOptions) -> None:

        names = self.filter_names(options)

        status = self.status
        await asyncio.gather(
            *(status.update_document(requests, name) for name in names)
        )
        await status.update_collection(requests)
