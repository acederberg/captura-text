import asyncio
from typing import Annotated

import httpx
import typer
from app import util

# --------------------------------------------------------------------------- #
from client.handlers import BaseHandlerData
from client.requests import Requests

from builder import ContextData, ResumeHandler

# --------------------------------------------------------------------------- #
logger = util.get_logger(__name__)


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


def cmd_up(_context: typer.Context):
    asyncio.run(_cmd_up(_context))


def cmd_config(
    _context: typer.Context, data: Annotated[bool, typer.Option("--data/--all")] = True
):
    context_data: ContextData = _context.obj

    include = {"data", "host", "profile", "output"} if not data else {"data"}
    config_data = context_data.config.model_dump(mode="json", include=include)

    handler_data = BaseHandlerData(data=config_data)
    context_data.console_handler.handle(handler_data=handler_data)


if __name__ == "__main__":

    cli = typer.Typer()
    cli.callback()(ContextData.typer_callback)
    cli.command("up")(cmd_up)
    cli.command("config")(cmd_config)
    cli()
