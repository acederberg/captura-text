import asyncio
import os
from os import path
from typing import Annotated

import httpx
import typer
import uvicorn
import uvicorn.config
from app import util
from app.schemas import AsOutput, DocumentSchema, mwargs

# --------------------------------------------------------------------------- #
from client.handlers import CONSOLE, BaseHandlerData
from client.requests import Requests
from docutils.core import publish_parts

from builder.controller import ContextData, TextController
from builder.schemas import TextBuilderStatus

# --------------------------------------------------------------------------- #
logger = util.get_logger(__name__)


async def _cmd_up(_context: typer.Context):
    # data = [item.model_dump(mode="json") for item in context.config.items]
    # context.console_handler.handle(handler_data=handler_data)  # type: ignore

    context_data: ContextData = _context.obj
    resume_handler = TextController(context_data)

    async with httpx.AsyncClient() as client:
        requests = Requests(context_data, client)
        status = await resume_handler.ensure(requests)

    handler_data = BaseHandlerData(data=status.model_dump(mode="json"))
    context_data.console_handler.handle(handler_data=handler_data)

    status = mwargs(TextBuilderStatus, status=status)
    status.update_status_file(context_data.builder.path_status)


def cmd_up(_context: typer.Context):
    asyncio.run(_cmd_up(_context))


async def _cmd_patch(_context: typer.Context):
    # data = [item.model_dump(mode="json") for item in context.config.items]
    # context.console_handler.handle(handler_data=handler_data)  # type: ignore

    context_data: ContextData = _context.obj
    resume_handler = TextController(context_data)

    async with httpx.AsyncClient() as client:
        requests = Requests(context_data, client)
        status = await resume_handler.ensure(requests)
        await resume_handler.update(requests)

    handler_data = BaseHandlerData(data=status.model_dump(mode="json"))
    context_data.console_handler.handle(handler_data=handler_data)

    status = mwargs(TextBuilderStatus, status=status)
    status.update_status_file(context_data.builder.path_status)


def cmd_patch(_context: typer.Context):
    asyncio.run(_cmd_patch(_context))


async def _cmd_down(_context: typer.Context):

    context_data: ContextData = _context.obj
    resume_handler = TextController(context_data)

    async with httpx.AsyncClient() as client:
        requests = Requests(context_data, client)
        status = await resume_handler.destroy(requests)

    handler_data = BaseHandlerData(data=status.model_dump(mode="json"))
    context_data.console_handler.handle(handler_data=handler_data)

    os.remove(context_data.builder.path_status)


def cmd_down(_context: typer.Context):
    asyncio.run(_cmd_down(_context))


def cmd_config(
    _context: typer.Context,
    builder: Annotated[bool, typer.Option("--builder/--client")] = True,
):
    context_data: ContextData = _context.obj

    if not builder:
        include = {"host", "profile", "output"}
        config_data = context_data.config.model_dump(mode="json", include=include)
    else:
        config_data = context_data.builder.model_dump(mode="json")

    handler_data = BaseHandlerData(data=config_data)
    context_data.console_handler.handle(handler_data=handler_data)


def cmd_status(_context: typer.Context):
    context_data: ContextData = _context.obj
    builder = context_data.builder

    if not path.exists(context_data.builder.path_status):
        CONSOLE.print("[green]No status yet.")
        raise typer.Exit(1)

    status = builder.status
    handler_data = BaseHandlerData(data=status.model_dump(mode="json"))
    context_data.console_handler.handle(handler_data=handler_data)


def cmd_run(_context: typer.Context):
    context_data: ContextData = _context.obj

    if not path.exists(context_data.builder.path_status):
        CONSOLE.print("[green]No status yet.")
        raise typer.Exit(1)

    uvicorn.run("builder.__main__:app", port=8000, host="0.0.0.0", reload=True)


LOGGING_CONFIG, _ = util.setup_logging()
uvicorn.config.LOGGING_CONFIG.update(LOGGING_CONFIG)


def create_command() -> typer.Typer:

    cli = typer.Typer()
    cli.callback()(ContextData.typer_callback)
    cli.command("status")(cmd_status)
    cli.command("up")(cmd_up)
    cli.command("patch")(cmd_patch)
    cli.command("down")(cmd_down)
    cli.command("config")(cmd_config)
    cli.command("run")(cmd_run)
    return cli()
