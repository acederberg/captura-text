import asyncio
import enum
from os import path
from typing import Annotated, Dict, List

import httpx
import typer

# --------------------------------------------------------------------------- #
from app import fields, util
from app.controllers.base import Data, ResolvedDocument
from app.depends import DependsAccess, DependsRead
from app.models import Collection, uuids
from app.schemas import (
    AsOutput,
    AssignmentSchema,
    CollectionSchema,
    DocumentSchema,
    TimespanLimitParams,
    mwargs,
)
from app.views import BaseView, Request, args
from client import Config as ClientConfig
from client.config import YamlSettingsConfigDict
from client.handlers import CONSOLE, BaseHandlerData, ConsoleHandler
from client.requests import CollectionRequests
from client.requests import ContextData as ClientContextData
from client.requests import DocumentRequests, Requests, UserRequests
from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, TypeAdapter
from rich.console import Console

# --------------------------------------------------------------------------- #
# FROM extensions/text.py

COLLECTION_DESCRIPTION = "Resume and supporting documents."
LENGTH_MESSAGE: int = 1024
LENGTH_CONTENT: int = 2**15
LENGTH_FORMAT: int = 8


logger = util.get_logger("resume")


class Format(str, enum.Enum):
    md = "md"
    rst = "rst"
    tEx = "tEx"
    txt = "txt"
    docs = "docs"


FieldFormat = Annotated[
    Format,
    Field(default=Format.md, description="Text document format."),
]


FieldMessage = Annotated[
    str,
    Field(
        min_length=0,
        max_length=LENGTH_MESSAGE,
        description="Text document edit message.",
        examples=["The following changes were made to the document: ..."],
    ),
]

FieldContent = Annotated[
    str,
    Field(
        max_length=LENGTH_CONTENT,
        description="Text document content.",
        examples=[fields.EXAMPLE_CONTENT],
    ),
]
FieldTags = Annotated[
    List[str] | None,
    Field(
        max_length=8,
        description="Text document tags.",
    ),
]


class TextSchema(BaseModel):
    """How the content schema should look."""

    format: FieldFormat
    content: FieldContent
    tags: FieldTags


# --------------------------------------------------------------------------- #


def here(v: str):
    return path.join(path.dirname(__file__), v)


class ResumeItemConfig(BaseModel):
    content_file: Annotated[
        str,
        Field(
            description=(
                "This should be a path relative to the root directory or an "
                "absolute path."
            ),
        ),
    ]
    name: fields.FieldName
    description: fields.FieldDescription

    def create_content(self) -> Dict[str, int | TextSchema]:
        logger.debug("Building content for `%s`.", self.name)
        tags = ["resume"]
        with open(here(self.content_file), "r") as file:
            content = "\n".join(file.readlines())

        text = TextSchema(format=Format.rst, content=content, tags=tags)
        return dict(text=text)

    # def req_create(self, context) -> httpx.Request:
    #     return DocumentRequests.req_create(
    #         context,
    #         name=self.name,
    #         description=self.description,
    #         content=self.content_file,
    #         public=True,
    #     )
    #
    # def req_update(self, context) -> httpx.Request:
    #     return DocumentRequests.req_create(
    #         context,
    #         name=self.name,
    #         description=self.description,
    #         content=self.content_file,
    #         public=True,
    #     )
    #


class ResumeDataConfig(BaseModel):
    items: Annotated[
        List[ResumeItemConfig],
        Field(description="Resume and supporting items."),
    ]
    identifier: Annotated[
        str,
        Field(description="Document and collection identified."),
    ]


class Config(ClientConfig):
    model_config = YamlSettingsConfigDict(yaml_files=here("client.yaml"))

    data: ResumeDataConfig


class ContextData(ClientContextData):
    config: Config  # type: ignore


def typer_callback(context: typer.Context) -> None:

    config = mwargs(Config)
    context.obj = ContextData(
        config=config,
        console_handler=ConsoleHandler(config),
    )


class ResumeHandler:

    context_data: ContextData
    config: Config
    fmt_name: str

    def __init__(self, context_data: ContextData):
        self.context_data = context_data
        self.config = context_data.config
        self.fmt_name = f"{{}}-{self.config.data.identifier}"

    async def upsert_collection(
        self,
        requests: Requests,
    ) -> AsOutput[CollectionSchema]:

        adptr = TypeAdapter(AsOutput[List[CollectionSchema]])
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

        (data,), err = check_status(res, expect_status=200, adapter=adptr)
        if err is not None:
            raise err

        match len(data.data):
            # NOTE: Create.
            case 0:
                logger.debug("Creating collection.")
                res = await requests.c.create(
                    name=name,
                    description=COLLECTION_DESCRIPTION,
                    public=False,
                )
            # NOTE: Update.
            case 1:
                logger.debug("Collection already exists.")
            case _:
                CONSOLE.print("[red]Too many results.")
                raise typer.Exit(1)

        (data,), err = check_status(res, expect_status=200, adapter=adptr)
        if err is not None:
            raise err

        return data.data

    async def upsert_document(
        self,
        requests: Requests,
        item: ResumeItemConfig,
    ) -> AsOutput[DocumentSchema]:

        adptr = TypeAdapter(AsOutput[DocumentSchema])
        profile = self.config.profile
        check_status = requests.handler.check_status
        assert profile is not None

        name = self.fmt_name.format("resume")
        logger.debug("Creating document `%s`.", name)
        res = await requests.u.search(
            profile.uuid_user,
            child=fields.ChildrenUser.documents,
            name_like=name,
        )

        (data,), err = check_status(res, expect_status=200, adapter=adptr)
        if err is not None:
            raise err

        match len(data.data):
            case 0:
                logger.debug("Creating document `%s`.", name)
                res = await requests.d.create(
                    name=name,
                    description=item.description,
                    content=item.create_content(),
                    public=False,
                )
            case 1:
                logger.debug("Updating document `%s`.", name)
                res = await requests.d.update(
                    data.data[0].uuid,
                    name=name,
                    description=item.description,
                    content=item.create_content(),
                )

        data, err = check_status(res, expect_status=200, adapter=adptr)
        if err is not None:
            raise err

        assert len(data) == 1
        return data[0].data

    async def __call__(self, requests: Requests):

        collection = await self.upsert_collection(requests)
        documents = await asyncio.gather(
            self.upsert_document(requests, item_document)
            for item_document in self.config.data.items
        )
        uuid_document = list(item.data.uuid for item in documents)

        mkassign = requests.assignments.collections.create
        res = await mkassign(collection.data.uuid, uuid_document=uuid_document)
        assignments, err = requests.handler.check_status(
            res,
            expect_status=201,
            adapter=TypeAdapter(AsOutput[List[AssignmentSchema]]),
        )
        if err is not None:
            raise err

        return dict(
            uuid_collection=collection.data.uuid,
            uuid_document=uuid_document,
            uuid_assignment=list(item.data.uuid for item in assignments),
        )


# --------------------------------------------------------------------------- #


async def _cmd_up(_context: typer.Context):
    # data = [item.model_dump(mode="json") for item in context.config.items]
    # context.console_handler.handle(handler_data=handler_data)  # type: ignore

    context_data: ContextData = _context.obj
    resume_handler = ResumeHandler(context_data)

    async with httpx.AsyncClient() as client:
        requests = Requests(context_data, client)
        data = await resume_handler(requests)

    handler_data = BaseHandlerData(data=data)
    context_data.console_handler.handle(handler_data=handler_data)


def cmd_up(_context: typer.Context):
    asyncio.run(_cmd_up(_context))


def cmd_config(_context: typer.Context, data: bool = True):
    context_data: ContextData = _context.obj

    include = None if not data else {"data"}
    config_data = context_data.config.model_dump(mode="json", include=include)

    handler_data = BaseHandlerData(data=config_data)
    context_data.console_handler.handle(handler_data=handler_data)


if __name__ == "__main__":
    logger.setLevel("DEBUG")

    logger.debug("a")
    logger.info("a")
    logger.warning("a")
    logger.critical("a")
    cli = typer.Typer()
    cli.callback()(typer_callback)
    cli.command("up")(cmd_up)
    cli.command("config")(cmd_config)
    # cli.command("post")(post)
    # cli.command("update")(update)
    cli()
