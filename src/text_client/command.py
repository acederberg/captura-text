import asyncio
import os
from os import path
from typing import Annotated, List, Optional

import httpx
import typer
import uvicorn
import uvicorn.config
from app import util
from app.schemas import mwargs
from client import BaseTyperizable, ContextData

# --------------------------------------------------------------------------- #
from client.handlers import CONSOLE, BaseHandlerData
from client.requests import Requests

from text_app.schemas import (
    PATH_CONFIGS_BUILDER_DEFAULT,
    BuilderConfig,
    TextBuilderStatus,
)
from text_client.controller import TextController, TextOptions, update_status_file

# --------------------------------------------------------------------------- #
logger = util.get_logger(__name__)


class TextCommands(BaseTyperizable):
    typer_check_verbage = False
    typer_decorate = False
    typer_commands = dict(
        status="status",
        up="up",
        patch="patch",
        down="down",
        config="config",
    )
    typer_children = dict()

    @classmethod
    async def _up(
        cls,
        _context: typer.Context,
        text_file: Annotated[
            str, typer.Option("--text")
        ] = PATH_CONFIGS_BUILDER_DEFAULT,
    ):
        # data = [item.model_dump(mode="json") for item in context.config.items]
        # context.console_handler.handle(handler_data=handler_data)  # type: ignore

        text = BuilderConfig.load(text_file)

        context_data: ContextData = _context.obj
        resume_handler = TextController(context_data.config, text)

        async with httpx.AsyncClient() as client:
            requests = Requests(context_data, client)
            status = await resume_handler.ensure(requests)

        handler_data = BaseHandlerData(data=status.model_dump(mode="json"))
        context_data.console_handler.handle(handler_data=handler_data)

        status = mwargs(TextBuilderStatus, status=status)
        update_status_file(status, text.path_status)

    @classmethod
    def up(cls, _context: typer.Context):
        asyncio.run(cls._up(_context))

    @classmethod
    async def _patch(
        cls,
        _context: typer.Context,
        text_file: Annotated[
            str, typer.Option("--text")
        ] = PATH_CONFIGS_BUILDER_DEFAULT,
    ):
        # data = [item.model_dump(mode="json") for item in context.config.items]
        # context.console_handler.handle(handler_data=handler_data)  # type: ignore

        context_data: ContextData = _context.obj
        text = BuilderConfig.load(text_file)
        resume_handler = TextController(context_data, text)

        async with httpx.AsyncClient() as client:
            requests = Requests(context_data, client)
            status = await resume_handler.ensure(requests, TextOptions(names=None))
            await resume_handler.update(requests, context_data.options)

        handler_data = BaseHandlerData(data=status.model_dump(mode="json"))
        context_data.console_handler.handle(handler_data=handler_data)

        status = mwargs(TextBuilderStatus, status=status)
        update_status_file(status, context_data.text.path_status)

    @classmethod
    def patch(cls, _context: typer.Context):
        asyncio.run(cls._patch(_context))

    @classmethod
    async def _down(
        cls,
        _context: typer.Context,
        text_file: Annotated[
            str, typer.Option("--text")
        ] = PATH_CONFIGS_BUILDER_DEFAULT,
    ):

        context_data: ContextData = _context.obj
        text = BuilderConfig.load(text_file)
        resume_handler = TextController(context_data, text)

        async with httpx.AsyncClient() as client:
            requests = Requests(context_data, client)
            status = await resume_handler.destroy(requests, context_data.options)

        handler_data = BaseHandlerData(data=status.model_dump(mode="json"))
        context_data.console_handler.handle(handler_data=handler_data)

        os.remove(context_data.text.path_status)

    @classmethod
    def down(cls, _context: typer.Context):
        asyncio.run(cls._down(_context))

    @classmethod
    def config(
        cls,
        _context: typer.Context,
        text_file: Annotated[
            str, typer.Option("--text")
        ] = PATH_CONFIGS_BUILDER_DEFAULT,
    ):
        context_data: ContextData = _context.obj

        if text_file is None:
            include = {"host", "profile", "output"}
            config_data = context_data.config.model_dump(mode="json", include=include)
        else:
            config_data = context_data.text.model_dump(mode="json")

        handler_data = BaseHandlerData(data=config_data)
        context_data.console_handler.handle(handler_data=handler_data)

    @classmethod
    def status(
        cls,
        _context: typer.Context,
        text_file: Annotated[
            str, typer.Option("--text")
        ] = PATH_CONFIGS_BUILDER_DEFAULT,
    ):
        context_data: ContextData = _context.obj
        text = BuilderConfig.load(text_file)

        if (status := text.status) is None:
            CONSOLE.print("[green]No status yet.")
            raise typer.Exit(1)

        handler_data = BaseHandlerData(data=status.model_dump(mode="json"))
        context_data.console_handler.handle(handler_data=handler_data)


LOGGING_CONFIG, _ = util.setup_logging()
uvicorn.config.LOGGING_CONFIG.update(LOGGING_CONFIG)


def create_command() -> typer.Typer:

    cli = typer.Typer()
    return cli()