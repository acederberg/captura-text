import asyncio
import traceback
from os import path
from typing import Annotated

import httpx
import typer
import uvicorn
import uvicorn.config
from app import util
from app.schemas import mwargs

# --------------------------------------------------------------------------- #
from client.handlers import CONSOLE, BaseHandlerData
from client.requests import Requests
from fastapi import FastAPI, HTTPException, Request, Response
from starlette.responses import JSONResponse

from builder import ContextData, ResumeHandler
from builder.router import ResumeView
from builder.schemas import PATH_STATUS, Status

# --------------------------------------------------------------------------- #
logger = util.get_logger(__name__)

app = FastAPI()
app.include_router(ResumeView.view_router)


async def _cmd_up(_context: typer.Context):
    # data = [item.model_dump(mode="json") for item in context.config.items]
    # context.console_handler.handle(handler_data=handler_data)  # type: ignore

    context_data: ContextData = _context.obj
    resume_handler = ResumeHandler(context_data)

    async with httpx.AsyncClient() as client:
        requests = Requests(context_data, client)
        data = await resume_handler(requests)

    handler_data = BaseHandlerData(data=data.model_dump(mode="json"))
    context_data.console_handler.handle(handler_data=handler_data)

    status = mwargs(Status, status=data)
    status.update_status_file()


def cmd_up(_context: typer.Context):
    asyncio.run(_cmd_up(_context))


def cmd_config(_context: typer.Context):
    context_data: ContextData = _context.obj

    include = {"host", "profile", "output"}
    config_data = context_data.config.model_dump(mode="json", include=include)

    handler_data = BaseHandlerData(data=config_data)
    context_data.console_handler.handle(handler_data=handler_data)


def cmd_status(_context: typer.Context):
    context_data: ContextData = _context.obj

    if not path.exists(PATH_STATUS):
        CONSOLE.print("[green]No status yet.")

    status = mwargs(Status)
    handler_data = BaseHandlerData(data=status.model_dump(mode="json"))
    context_data.console_handler.handle(handler_data=handler_data)


def cmd_run(_context: typer.Context):
    context_data: ContextData = _context.obj

    if not path.exists(PATH_STATUS):
        CONSOLE.print("[green]No status yet.")

    uvicorn.run("builder.__main__:app", reload=True)


# def cmd_render(_context: typer.Context, name: str):
#     context_data: ContextData = _context.obj
#
#     context_data: ContextData = _context.obj
#     if (item_data := context_data.config.data.get(name)) is None:
#         CONSOLE.print(f"[red]No such document with name `{name}`.")
#         raise typer.Exit(1)
#
#     parser = RstParser(name, item_data.)
#     print(parser.document)


LOGGING_CONFIG, _ = util.setup_logging()
uvicorn.config.LOGGING_CONFIG.update(LOGGING_CONFIG)


if __name__ == "__main__":

    cli = typer.Typer()
    cli.callback()(ContextData.typer_callback)
    cli.command("status")(cmd_status)
    cli.command("up")(cmd_up)
    cli.command("config")(cmd_config)
    cli.command("run")(cmd_run)
    # cli.command("render")(cmd_render)
    cli()
