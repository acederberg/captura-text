"""Router. 

This module will attempt to figure what what will be needed to build an 
extension.

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
from pydantic import TypeAdapter
from starlette.responses import HTMLResponse

from builder import ContextData
from builder.schemas import Config, Status


def config() -> Config:
    return mwargs(Config)


DependsConfig = Annotated[Config, Depends(config, use_cache=True)]


def context(config: DependsConfig) -> ContextData:
    try:
        console_handler = ConsoleHandler(config=config)
        return ContextData(config=config, console_handler=console_handler)  # type: ignore
    except Exception as err:
        print_tb(err.__traceback__)
        print(err)
        raise err


DependsContext = Annotated[ContextData, Depends(context, use_cache=True)]


def status() -> Status:
    print("HERE")
    return mwargs(Status)


DependsStatus = Annotated[Status, Depends(status, use_cache=True)]


# NOTE: Restructured Text Should be passed in as Jinja Templates.
class ResumeView(BaseView):

    view_routes = dict(
        get_by_name_json="/{name}/json",
        get_by_name_html="/{name}",
        # "get_terd": "/terd",
    )

    # NOTE: Will require own token to function for the moment. Should match
    #       against the name provided in ``config``, not the actual name with
    #       the attached identifier.
    @classmethod
    async def get_by_name_json(
        cls,
        context: DependsContext,
        status: DependsStatus,
        name: str,
    ) -> AsOutput[DocumentSchema]:

        data = status.status.get(name)
        if data is None:
            raise HTTPException(404, detail="No such document.")

        async with httpx.AsyncClient() as client:
            requests = Requests(context, client)
            res = await requests.documents.read(data.uuid)

        # NOTE: At some point this should be written as a handler instead.
        if 200 <= res.status_code < 300:
            print(res.json())
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
    async def get_by_name_html(
        cls,
        context: DependsContext,
        status: DependsStatus,
        name: str,
    ):
        # NOTE: These documents should be built before, not `on the fly`. All
        #       document building should happen outside of app run.
        data = await cls.get_by_name_json(context, status, name)
        content = data.data.content["text"]["content"]

        parser = publish_string(content, writer_name="html")
        return HTMLResponse(str(parser.document))
