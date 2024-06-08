import asyncio
import traceback
from os import path
from typing import Annotated, Literal

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
from fastapi import FastAPI, HTTPException, Request, Response
from starlette.responses import JSONResponse

from builder.controller import ContextData, TextController
from builder.router import TextView
from builder.schemas import Status

# --------------------------------------------------------------------------- #
logger = util.get_logger(__name__)


async def _cmd_up(_context: typer.Context):
    # data = [item.model_dump(mode="json") for item in context.config.items]
    # context.console_handler.handle(handler_data=handler_data)  # type: ignore

    context_data: ContextData = _context.obj
    resume_handler = TextController(context_data)

    async with httpx.AsyncClient() as client:
        requests = Requests(context_data, client)
        data = await resume_handler.upsert(requests)

    handler_data = BaseHandlerData(data=data.model_dump(mode="json"))
    context_data.console_handler.handle(handler_data=handler_data)

    status = mwargs(Status, status=data)
    status.update_status_file(context_data.builder.path_status)


def cmd_up(_context: typer.Context):
    asyncio.run(_cmd_up(_context))


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

    status = builder.status
    handler_data = BaseHandlerData(data=status.model_dump(mode="json"))
    context_data.console_handler.handle(handler_data=handler_data)


def cmd_run(_context: typer.Context):
    context_data: ContextData = _context.obj

    if not path.exists(context_data.builder.path_status):
        CONSOLE.print("[green]No status yet.")

    uvicorn.run("builder.__main__:app", port=8000, host="0.0.0.0", reload=True)


async def _cmd_render(_context: typer.Context, name: str):
    context_data: ContextData = _context.obj

    if (item_status := context_data.builder.status.status.get(name)) is None:
        CONSOLE.print(f"[red]No such document with name `{name}`.")
        CONSOLE.print(f"[red]RUn `python -m builder up`.")
        raise typer.Exit(1)

    async with httpx.AsyncClient() as client:
        requests = Requests(context_data, client)
        res = await requests.d.read(item_status.uuid)

    if res.status_code != 200:
        context_data.console_handler(res)

    data = AsOutput[DocumentSchema].model_validate_json(res.content)

    with open(f"{name}.html", "w") as file:
        content = data.data.content["text"]["content"]
        published = publish_parts(
            content,
            writer_name="html",
        )

        file.writelines(published["html_body"])


def cmd_render(_context: typer.Context, name: str):
    asyncio.run(_cmd_render(_context, name))


LOGGING_CONFIG, _ = util.setup_logging()
uvicorn.config.LOGGING_CONFIG.update(LOGGING_CONFIG)


def create_command() -> typer.Typer:

    cli = typer.Typer()
    cli.callback()(ContextData.typer_callback)
    cli.command("status")(cmd_status)
    cli.command("up")(cmd_up)
    cli.command("config")(cmd_config)
    cli.command("run")(cmd_run)
    cli.command("render")(cmd_render)
    return cli()
