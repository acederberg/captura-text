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

from builder import snippets
from builder.schemas import (
    PATH_CONFIGS_BUILDER_DEFAULT,
    BuilderConfig,
    Config,
    Status,
    TextDataConfig,
    TextDataStatus,
    TextItemConfig,
    TextItemStatus,
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

    @property
    def status(self) -> TextDataStatus:
        status_wrapper = self.builder.status
        if status_wrapper is None:
            raise ValueError()
        return status_wrapper.status

    def __init__(self, context_data: ContextData):
        self.context_data = context_data
        self.config = context_data.config
        self.builder = context_data.builder
        self.data = self.builder.data
        self.fmt_name = f"{{}}-{self.data.identifier}"

    def check_one(self, requests: Requests, res, **kwargs):
        (data_assignments,), err = requests.handler.check_status(res, **kwargs)
        if err is not None:
            raise err

        return data_assignments.data

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
        name = self.fmt_name.format(self.builder.data.collection.name)
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

        # NOTE: Create if not exists.
        match len(data := handler_data_search.data.data):
            case 0:
                logger.debug("Creating collection.")
                res = await requests.c.create(
                    name=name,
                    content=None,
                    description=self.builder.data.collection.description,
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
    ) -> Dict[snippets.Format, DocumentSchema]:
        """Upsert document items. Each document should be stored in raw form
        and as html.
        """

        profile = self.config.profile
        check_status = requests.handler.check_status
        assert profile is not None

        fmt_name_full = self.fmt_name.format(name) + "-{}"
        filename = path.join(self.builder.path_docs, item.content_file)
        logger.debug("Creating document `%s`.", name)
        res = await requests.u.search(
            profile.uuid_user,
            child=fields.ChildrenUser.documents,
            name_like=self.fmt_name.format(name),
        )

        handler_data_search: RequestHandlerData[AsOutput[List[DocumentSchema]]]
        adptr_search = TypeAdapter(AsOutput[List[DocumentSchema]])
        (handler_data_search,), err = check_status(
            res, expect_status=200, adapter=adptr_search
        )
        if err is not None:
            raise err

        adptr = TypeAdapter(AsOutput[DocumentSchema])
        status: int
        match len(handler_data_search.data.data):
            case 0:
                logger.debug("Creating documents for `%s`.", name)
                status = 201
                tasks = (
                    requests.d.create(
                        name=fmt_name_full.format(fmt.name),
                        description=item.description,
                        content=content,  # type: ignore
                        public=False,
                    )
                    for fmt, content in item.create_content(filename).items()
                )
            case 2:
                logger.debug("Updating documents for `%s`.", name)
                status = 200
                tasks = (
                    requests.d.update(
                        uuid,
                        name=fmt_name_full.format(fmt.name),
                        description=item.description,
                        content=content,  # type: ignore
                    )
                    for (fmt, content), uuid in zip(
                        item.create_content(filename).items(),
                        (item.uuid for item in handler_data_search.data.data),
                    )
                )
            case _:
                CONSOLE.print("[red]Too many results.")
                raise typer.Exit(1)

        res = await asyncio.gather(*tasks)
        handler_datas: Tuple[RequestHandlerData[AsOutput[DocumentSchema]], ...]
        handler_datas, err = check_status(res, expect_status=status, adapter=adptr)
        if err is not None:
            raise err

        return {
            snippets.Format((data := hd.data.data).content["text"]["format"]): data
            for hd in handler_datas
        }

    async def upsert(self, requests: Requests) -> TextDataStatus:

        collection = await self.upsert_collection(requests)
        documents_tasks = (
            self.upsert_document(requests, name, item)
            for name, item in self.data.documents.items()
        )
        documents_items = await asyncio.gather(*documents_tasks)

        # NOTE: Assignments. Note that create is imdempotent.
        uuid_document = list(
            document.uuid
            for documents in documents_items
            for document in documents.values()
        )

        logger.debug("Creating *imdempotently* assignments.")
        check_status = requests.handler.check_status
        adptr = TypeAdapter(AsOutput[List[AssignmentSchema]])
        res = await requests.a.c.create(collection.uuid, uuid_document=uuid_document)
        (data_assignments,), err = check_status(res, expect_status=201, adapter=adptr)
        if err is not None:
            raise err

        res = await requests.a.c.read(collection.uuid, uuid_document=uuid_document)
        (data_assignments,), err = check_status(res, adapter=adptr)
        if err is not None:
            raise err

        return TextDataStatus.fromData(
            self.data,
            collection=collection,
            documents=documents_items,
            assignments=data_assignments.data.data,
        )

    # NOTE: Only return status when status has been changed.
    async def destroy(self, requests: Requests) -> TextDataStatus:

        status = self.status.model_copy()
        document_uuids = tuple(
            itertools.chain(
                *(
                    tuple(item.uuid for item in (*item_rst.renders, item_rst))
                    for item_rst in status.documents.values()
                )
            )
        )
        document_reqs = map(requests.d.delete, document_uuids)
        collection_req = requests.c.delete(status.collection.uuid)

        results = await asyncio.gather(collection_req, *document_reqs)
        tuple(
            map(
                lambda res: self.check_one(requests, res),
                results,
            )
        )

        return status
