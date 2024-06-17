import asyncio
from os import path
from typing import Annotated, Dict, Generator, List

import typer
import yaml
from app import ChildrenUser, util
from app.config import BaseHashable
from app.schemas import (
    AsOutput,
    AssignmentSchema,
    CollectionSchema,
    DocumentSchema,
    Field,
    mwargs,
)
from client import Config
from client.handlers import RequestHandlerData
from client.requests import Requests
from pydantic import Field, TypeAdapter

from text_app.schemas import (
    DESC_NAMES,
    PATH_TEXT_CONFIG,
    BuilderConfig,
    TextBuilderStatus,
    TextCollectionStatus,
    TextDataConfig,
    TextDataStatus,
    TextDocumentStatus,
    TextOptions,
    here,
)

logger = util.get_logger(__name__)

# --------------------------------------------------------------------------- #


def check_discover(requests, res, **kwargs):
    (handler_data,), err = requests.handler.check_status(res, **kwargs)
    if err is not None:
        raise err

    if handler_data.data.kind is None:
        return None
    elif len(items := handler_data.data.data) == 1:
        return items[0]
    else:
        raise ValueError("Too many results.")


async def discover_document(
    config: TextDataConfig,
    requests: Requests,
    name: str,
) -> DocumentSchema | None:
    """Try to find uuid corresponding to the identifier.

    For more on the document name on the captura side, please see the
    description of ``identifier``. To discover and create
    ``TextDataStatus``, please see ``TextDataStaus.discover``.
    """

    name_captura = f"{name}-{config.identifier}"
    adptr = TypeAdapter(AsOutput[List[DocumentSchema]])
    item = config.require(name)
    name_captura += f"-{item.format_out.name}"

    res = await requests.users.search(
        requests.context.config.profile.uuid_user,  # type: ignore
        child=ChildrenUser.documents,
        name_like=name_captura,
    )
    return check_discover(requests, res, adapter=adptr)


async def discover_collection(
    config: TextDataConfig,
    requests: Requests,
) -> CollectionSchema | None:
    name_captura = f"{config.collection.name}-{config.identifier}"
    adptr = TypeAdapter(AsOutput[List[DocumentSchema]])

    res = await requests.users.search(
        requests.context.config.profile.uuid_user,  # type: ignore
        child=ChildrenUser.collections,
        name_like=name_captura,
    )
    return check_discover(requests, res, adapter=adptr)


async def create_document(
    config: TextDataConfig,
    requests: Requests,
    name: str,
) -> DocumentSchema:
    """Upsert a document by name.

    This returns the raw data from captura. Tranformation into ``status``
    is done within ``controller`` as is bulk upsertion.
    """

    item = config.require(name)
    name_captura = f"{name}-{config.identifier}-{item.format_out.name}"
    filename = path.join(config.path_docs, item.content_file)
    content = item.create_content(filename)

    res = await requests.d.create(
        name=name_captura,
        description=item.description,
        content=content,  # type: ignore
        public=False,
    )

    handler_data: RequestHandlerData[AsOutput[CollectionSchema]]

    adptr = TypeAdapter(AsOutput[DocumentSchema])
    (handler_data,), err = requests.handler.check_status(
        res, expect_status=201, adapter=adptr
    )
    if err is not None:
        raise err

    return handler_data.data.data


async def create_collection(
    config: TextDataConfig, requests: Requests, name: str
) -> CollectionSchema:
    logger.debug("Creating collection.")
    name_captura = f"{name}-{config.identifier}"
    res = await requests.c.create(
        name=name_captura,
        content=None,
        description=config.collection.description,
        public=False,
    )

    handler_data: RequestHandlerData[AsOutput[CollectionSchema]]

    adptr = TypeAdapter(AsOutput[CollectionSchema])
    (handler_data,), err = requests.handler.check_status(
        res, expect_status=201, adapter=adptr
    )
    if err is not None:
        raise err

    return handler_data.data.data


# --------------------------------------------------------------------------- #


async def update_document(
    status: TextDataStatus,
    requests: Requests,
    name: str,
) -> None:
    """Upsert a document by name.

    This returns the raw data from captura. Tranformation into ``status``
    is done within ``controller`` as is bulk upsertion.
    """

    item = status.require(name)
    name_captura = f"{name}-{status.identifier}-{item.format_out.name}"
    status = 200
    filename = path.join(status.path_docs, item.content_file)
    content = item.create_content(filename)

    res = await requests.d.update(
        item.uuid,
        name=name_captura,
        description=item.description,
        content=content,  # type: ignore
    )

    adptr_search = TypeAdapter(AsOutput[DocumentSchema])
    (_,), err = requests.handler.check_status(
        res, expect_status=status, adapter=adptr_search
    )
    if err is not None:
        raise err

    return None


async def update_collection(
    status: TextDataStatus,
    requests: Requests,
) -> None:
    """Upsert a document by name.

    This returns the raw data from captura. Tranformation into ``status``
    is done within ``controller`` as is bulk upsertion.
    """
    name_captura = f"{status.collection.name}-{status.identifier}"

    status = 200

    res = await requests.c.update(
        status.collection.uuid,
        name=name_captura,
        description=status.collection.description,
    )

    adptr = TypeAdapter(AsOutput[CollectionSchema])
    (_,), err = requests.handler.check_status(res, expect_status=status, adapter=adptr)
    if err is not None:
        raise err


async def destroy_document(
    status: TextDataStatus,
    requests: Requests,
    name: str,
) -> TextDocumentStatus:
    item = status.require(name)
    res = await requests.d.delete(item.uuid)
    (_,), err = requests.handler.check_status(res)
    if err is not None:
        raise err

    out = item.model_copy()
    out.deleted = True
    return out


async def destroy_collection(
    status: TextDataStatus, requests: Requests
) -> TextCollectionStatus:
    res = await requests.c.delete(status.collection.uuid)
    (_,), err = requests.handler.check_status(res)
    if err is not None:
        raise err

    out = status.collection.model_copy()
    out.deleted = True
    return out


def update_status_file(status: TextBuilderStatus, filepath: str) -> None:
    if path.exists(filepath):
        logger.debug("Loading existing data.")
        status_from_file = status.load(filepath)

        if status_from_file.status == status.status:
            logger.debug("No changes in data.")
            return

        logger.info("Found change in status!")
        to_dump = status.__class__(
            status=status.status,
            history=[
                status_from_file.status,
                *status_from_file.history,
            ],
        )
    else:
        to_dump = status

    logger.info("Dumping status in `%s`.", filepath)
    with open(filepath, "w") as file:
        yaml.dump(to_dump.model_dump(mode="json"), file)


# --------------------------------------------------------------------------- #


class TextContextData(BaseHashable):
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
        ] = PATH_TEXT_CONFIG,
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

        context.obj = cls(
            text=BuilderConfig.load(text_config),
            options=TextOptions(names=names),
        )


# NOTE: Options should be passed directly. That is, accept ``options`` as a
#       keyword argument and do not get it directly from context data. The only
#       reason it is included in context data is so that it is it may be
#       collected from the command line.
class TextController:

    config: Config
    text: BuilderConfig
    data: TextDataConfig

    @property
    def status(self) -> TextDataStatus:
        status_wrapper = self.text.status
        if status_wrapper is None:
            raise ValueError("Status does not exist.")
        return status_wrapper.status

    def __init__(self, config: Config, text: BuilderConfig):
        self.config = config
        self.text = text
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

        collection = await discover_collection(self.text.data, requests)
        if collection is None:
            collection = await create_collection(self.text.data, requests, name)

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
        document = await discover_document(self.text.data, requests, name)
        if document is None:
            document = await create_document(self.text.data, requests, name)

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

    async def ensure(
        self, requests: Requests, options: TextOptions | None = None
    ) -> TextDataStatus:

        options = mwargs(TextOptions) if options is None else options
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

        options = mwargs(TextOptions) if options is None else options
        if options.names is not None:
            raise ValueError("``destroy`` cannot yet filter by names.")

        documents_destroyed = await asyncio.gather(
            *(
                destroy_document(self.status, requests, name)
                for name in self.status.documents
            )
        )
        collection_destroyed = await destroy_collection(self.status, requests)

        return TextDataStatus(
            documents={status.name: status for status in documents_destroyed},
            collection=collection_destroyed,
            identifier=status.identifier,
            path_docs=status.path_docs,
        )

    async def update(self, requests: Requests, options: TextOptions) -> None:

        names = self.filter_names(options)

        options = mwargs(TextOptions) if options is None else options

        status = self.status
        await asyncio.gather(
            *(update_document(status, requests, name) for name in names)
        )
        await update_collection(status, requests)
