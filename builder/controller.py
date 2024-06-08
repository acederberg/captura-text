import asyncio
from os import path
from typing import List

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

from builder import snippets
from builder.schemas import (
    PATH_CONFIGS_BUILDER_DEFAULT,
    BuilderConfig,
    Config,
    TextDataConfig,
    TextDataStatus,
    TextItemConfig,
)

logger = util.get_logger(__name__)


class ContextData(ClientContextData):
    config: Config  # type: ignore
    builder: BuilderConfig

    @classmethod
    def typer_callback(
        cls, context: typer.Context, builder_config: str = PATH_CONFIGS_BUILDER_DEFAULT
    ) -> None:

        config = mwargs(Config)
        context.obj = ContextData(
            config=config,
            builder=BuilderConfig.load(builder_config),
            console_handler=ConsoleHandler(config),
        )


class TextController:

    context_data: ContextData
    config: Config
    builder: BuilderConfig
    data: TextDataConfig
    fmt_name: str

    def __init__(self, context_data: ContextData):
        self.context_data = context_data
        self.config = context_data.config
        self.builder = context_data.builder
        self.data = self.builder.data
        self.fmt_name = f"{{}}-{self.data.identifier}"

    async def upsert_collection(
        self,
        requests: Requests,
    ) -> CollectionSchema:
        """Update the collection in captura."""

        profile = self.config.profile
        check_status = requests.handler.check_status
        assert profile is not None

        # NOTE: Look for name matching tags.
        logger.debug("Checking collection status.")
        name = self.fmt_name.format("resume")
        res = await requests.u.search(
            profile.uuid_user,
            child=fields.ChildrenUser.collections,
            name_like=name,
        )

        handler_data_search: RequestHandlerData[AsOutput[List[CollectionSchema]]]
        adptr = TypeAdapter(AsOutput[List[CollectionSchema]])
        (handler_data_search,), err = check_status(
            res,
            expect_status=200,
            adapter=adptr,
        )
        if err is not None:
            raise err

        # NOTE: LMAO. Create if not exists.
        match len(data := handler_data_search.data.data):
            case 0:
                logger.debug("Creating collection.")
                res = await requests.c.create(
                    name=name,
                    content=None,
                    description=snippets.COLLECTION_DESCRIPTION,
                    public=False,
                )

                handler_data: RequestHandlerData[AsOutput[CollectionSchema]]
                (handler_data,), err = check_status(
                    res, expect_status=201, adapter=adptr
                )
                if err is not None:
                    raise err

                return handler_data.data.data
            case 1:
                logger.debug("Collection already exists.")
                return data[0]
            case _:
                CONSOLE.print("[red]Too many results.")
                raise typer.Exit(1)

    async def upsert_document(
        self,
        requests: Requests,
        name: str,
        item: TextItemConfig,
    ) -> DocumentSchema:
        """Upsert document item."""

        profile = self.config.profile
        check_status = requests.handler.check_status
        assert profile is not None

        name_full = self.fmt_name.format(name)
        filename = path.join(self.builder.path_docs, item.content_file)
        logger.debug("Creating document `%s`.", name_full)
        res = await requests.u.search(
            profile.uuid_user,
            child=fields.ChildrenUser.documents,
            name_like=name_full,
        )

        handler_data_search: RequestHandlerData[AsOutput[List[DocumentSchema]]]
        adptr_search = TypeAdapter(AsOutput[List[DocumentSchema]])
        (handler_data_search,), err = check_status(
            res, expect_status=200, adapter=adptr_search
        )
        if err is not None:
            raise err

        adptr = TypeAdapter(AsOutput[DocumentSchema])
        match len(handler_data_search.data.data):
            case 0:
                logger.debug("Creating document `%s`.", name_full)
                res = await requests.d.create(
                    name=name_full,
                    description=item.description,
                    content=item.create_content(filename),
                    public=False,
                )
            case 1:
                logger.debug("Updating document `%s`.", name_full)
                res = await requests.d.update(
                    handler_data_search.data.data[0].uuid,
                    name=name_full,
                    description=item.description,
                    content=item.create_content(filename),
                )
            case _:
                print(handler_data_search.data.data)
                CONSOLE.print("[red]Too many results.")
                raise typer.Exit(1)

        handler_data: RequestHandlerData[AsOutput[DocumentSchema]]
        (handler_data,), err = check_status(res, expect_status=200, adapter=adptr)
        if err is not None:
            raise err

        return handler_data.data.data

    async def upsert(self, requests: Requests) -> TextDataStatus:

        collection = await self.upsert_collection(requests)
        documents_tasks = (
            self.upsert_document(requests, name, item)
            for name, item in self.data.items.items()
        )
        documents = await asyncio.gather(*documents_tasks)

        # NOTE: Assignments. Note that create is imdempotent.
        uuid_document = list(document.uuid for document in documents)

        logger.debug("Creating *imdempotently* assignments.")
        check_status = requests.handler.check_status
        adptr = TypeAdapter(AsOutput[List[AssignmentSchema]])
        res = await requests.a.c.create(collection.uuid, uuid_document=uuid_document)
        (data_assignments,), err = check_status(res, expect_status=201, adapter=adptr)
        if err is not None:
            raise err

        res = await requests.a.c.read(collection.uuid, uuid_document=uuid_document)
        (data_assignments,), err = check_status(res, adapter=adptr)

        return TextDataStatus.fromData(
            self.data,
            collection=collection,
            documents=documents,
            assignments=data_assignments.data.data,
        )

    # async def render_document(self, name: str) -> str:
    #
    #     output = path.join(self.context_data.builder.path_docs, "{name}.html")
    #     parser = publish_string(content, writer_name="html")
    #
    #     return
