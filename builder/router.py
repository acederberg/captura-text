"""Router for uploaded documents.

Documents can only be uploaded using the command line for the moment. To provide
the necessary status for this to serve these documents, run ``builder up`` to 
add your documents to a captura instance. Once this command has been run, find
your ``.builder.status.yaml`` and use its contents to deploy this app.
"""

from traceback import print_tb
from typing import Annotated

from app.schemas import AsOutput, DocumentSchema, mwargs
from app.views.base import BaseView
from client import Requests
from client.handlers import AssertionHandler, ConsoleHandler
from client.requests import httpx
from docutils.core import publish_string
from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import TypeAdapter
from starlette.responses import HTMLResponse

from builder.controller import ContextData
from builder.schemas import PATH_CONFIGS_BUILDER_DEFAULT, BuilderConfig, Config, Status
from builder.snippets import Format


# --------------------------------------------------------------------------- #
def config() -> Config:
    return mwargs(Config)


DependsConfig = Annotated[Config, Depends(config, use_cache=True)]


def builder() -> BuilderConfig:
    return BuilderConfig.load(PATH_CONFIGS_BUILDER_DEFAULT)


DependsBuilder = Annotated[BuilderConfig, Depends(builder, use_cache=True)]


def status(builder: DependsBuilder) -> Status:
    if builder.status is None:
        raise HTTPException(500, detail="``status`` is required.")

    return builder.status


DependsStatus = Annotated[Status, Depends(status, use_cache=True)]


def context(config: DependsConfig, builder: DependsBuilder) -> ContextData:
    try:
        console_handler = ConsoleHandler(config=config)
        return ContextData(config=config, builder=builder, console_handler=console_handler)  # type: ignore
    except Exception as err:
        print_tb(err.__traceback__)
        print(err)
        raise err


DependsContext = Annotated[ContextData, Depends(context, use_cache=True)]


# --------------------------------------------------------------------------- #


# NOTE: Restructured Text Should be passed in as Jinja Templates.
# NOTE: ALL rendering should be done using the command line for now until I
#       have time to add posting, etc.
class TextView(BaseView):

    view_routes = dict(
        get_by_name_json="/{name}/json",
        get_by_name="/{name}",
    )

    # NOTE: Will require own token to function for the moment. Should match
    #       against the name provided in ``config``, not the actual name with
    #       the attached identifier.
    @classmethod
    async def get_by_name_json(
        cls,
        context: DependsContext,
        status: DependsStatus,
        *,
        name: str,
    ) -> AsOutput[DocumentSchema]:
        """Get JSON data for the document."""

        if (data := status.status.get(name)) is None:
            raise HTTPException(404, detail="No such document.")

        async with httpx.AsyncClient() as client:
            requests = Requests(context, client)
            res = await requests.documents.read(data.uuid)

        # NOTE: At some point this should be written as a handler instead.
        if 200 <= res.status_code < 300:
            final = TypeAdapter(AsOutput[DocumentSchema]).validate_json(res.content)
            return final

        captura_detail = res.json()
        raise HTTPException(
            res.status_code,
            detail={
                "captura_detail": captura_detail,
                "captura_instance": context.config.host.host,
            },
        )

    @classmethod
    async def get_by_name(
        cls,
        context: DependsContext,
        status: DependsStatus,
        *,
        name: str,
    ):
        """Get RST document."""

        # NOTE: These documents should be built before, not `on the fly`. All
        #       document building should happen outside of app run.
        data = await cls.get_by_name_json(
            context,
            status,
            name=name,
        )
        content = data.data.content["text"]["content"]
        return HTMLResponse(content)
