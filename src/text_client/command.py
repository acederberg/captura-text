# =========================================================================== #
import asyncio
import os
from typing import Annotated

import httpx
import typer
import uvicorn
import uvicorn.config
from app import util
from app.schemas import mwargs
from client import BaseTyperizable, ContextData
from client.handlers import CONSOLE, BaseHandlerData
from client.requests import Requests

# --------------------------------------------------------------------------- #
from text_app.fields import PATH_TEXT_CONFIG, PATH_TEXT_DOCS, PATH_TEXT_STATUS_DEFAULT
from text_app.schemas import BuilderConfig, TextBuilderStatus
from text_client.controller import TextController, TextOptions, update_status_file

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
        text_file: Annotated[str, typer.Option("--text")] = PATH_TEXT_CONFIG,
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
        text_file: Annotated[str, typer.Option("--text")] = PATH_TEXT_CONFIG,
    ):
        # data = [item.model_dump(mode="json") for item in context.config.items]
        # context.console_handler.handle(handler_data=handler_data)  # type: ignore

        context_data: ContextData = _context.obj
        text = BuilderConfig.load(text_file)
        resume_handler = TextController(context_data.config, text)

        async with httpx.AsyncClient() as client:
            requests = Requests(context_data, client)
            status = await resume_handler.ensure(requests, TextOptions(names=None))
            await resume_handler.update(requests, mwargs(TextOptions))

        handler_data = BaseHandlerData(data=status.model_dump(mode="json"))
        context_data.console_handler.handle(handler_data=handler_data)

        status = mwargs(TextBuilderStatus, status=status)
        update_status_file(status, text.path_status)

    @classmethod
    def patch(cls, _context: typer.Context):
        asyncio.run(cls._patch(_context))

    @classmethod
    async def _down(
        cls,
        _context: typer.Context,
        text_file: Annotated[str, typer.Option("--text")] = PATH_TEXT_CONFIG,
    ):

        context_data: ContextData = _context.obj
        text = BuilderConfig.load(text_file)
        resume_handler = TextController(context_data.config, text)

        async with httpx.AsyncClient() as client:
            requests = Requests(context_data, client)
            status = await resume_handler.destroy(requests, mwargs(TextOptions))

        handler_data = BaseHandlerData(data=status.model_dump(mode="json"))
        context_data.console_handler.handle(handler_data=handler_data)

        os.remove(text.path_status)

    @classmethod
    def down(cls, _context: typer.Context):
        asyncio.run(cls._down(_context))

    # @classmethod
    # def env():
    #
    #     CONSOLE.print_json(
    #     )

    @classmethod
    def config(
        cls,
        _context: typer.Context,
        text_file: Annotated[str, typer.Option("--text")] = PATH_TEXT_CONFIG,
        env: Annotated[bool, typer.Option("--only-env/--only-config")] = False,
    ):
        context_data: ContextData = _context.obj
        text = BuilderConfig.load(text_file)

        if not env:
            if text_file is None:
                include = {"host", "profile", "output"}
                config_data = context_data.config.model_dump(
                    mode="json", include=include
                )
            else:
                config_data = text.model_dump(mode="json")
        else:
            config_data = {
                "text_docs": PATH_TEXT_DOCS,
                "text_status_default": PATH_TEXT_STATUS_DEFAULT,
                "text_config": PATH_TEXT_CONFIG,
            }

        handler_data = BaseHandlerData(data=config_data)
        context_data.console_handler.handle(handler_data=handler_data)

    @classmethod
    def status(
        cls,
        _context: typer.Context,
        text_file: Annotated[str, typer.Option("--text")] = PATH_TEXT_CONFIG,
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
