"""Router for uploaded documents.

Documents can only be uploaded using the command line for the moment. To provide
the necessary status for this to serve these documents, run ``text up`` to 
add your documents to a captura instance. Once this command has been run, find
your ``.text.status.yaml`` and use its contents to deploy this app.
"""

from os import path
from traceback import print_tb
from typing import Annotated

from app.schemas import AsOutput, DocumentSchema, mwargs
from app.views.base import BaseView
from client import Requests
from client.handlers import ConsoleHandler
from client.requests import httpx
from fastapi import Depends, HTTPException, Response
from fastapi.responses import PlainTextResponse
from pydantic import TypeAdapter
from starlette.responses import HTMLResponse

from text.controller import ContextData, TextOptions
from text.schemas import (
    PATH_CONFIGS_BUILDER_DEFAULT,
    BuilderConfig,
    Config,
    TextBuilderStatus,
)

TEMPLATE = """
<html>
  <head>
    <link rel="stylesheet" type="text/css" href="/index.css">
    <link rel="shortcut icon" href="https://fastapi.tiangolo.com/img/favicon.png">
    <title>{document.description}</title>
  </head>
  <body>
    {body}
  </body>
</html>
"""


# --------------------------------------------------------------------------- #
def config() -> Config:
    return mwargs(Config)


DependsConfig = Annotated[Config, Depends(config, use_cache=True)]


def text() -> BuilderConfig:
    return BuilderConfig.load(PATH_CONFIGS_BUILDER_DEFAULT)


DependsBuilder = Annotated[BuilderConfig, Depends(text, use_cache=True)]


def status(text: DependsBuilder) -> TextBuilderStatus:
    if text.status is None:
        raise HTTPException(500, detail="``status`` is required.")

    return text.status


DependsTextBuilderStatus = Annotated[TextBuilderStatus, Depends(status, use_cache=True)]


def context(config: DependsConfig, text: DependsBuilder) -> ContextData:
    try:
        console_handler = ConsoleHandler(config=config)
        return ContextData(
            config=config,
            text=text,
            console_handler=console_handler,
            options=TextOptions(names=None),
        )  # type: ignore
    except Exception as err:
        print_tb(err.__traceback__)
        print(err)
        raise err


DependsContext = Annotated[ContextData, Depends(context, use_cache=True)]


def template(text: DependsBuilder) -> str:
    if (template_file := text.data.template_file) is None:
        return TEMPLATE

    with open(path.join(text.data.path_docs, template_file), "r") as file:
        return "".join(file.readlines())


DependsTemplate = Annotated[str, Depends(template, use_cache=True)]


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
        status: DependsTextBuilderStatus,
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
        status: DependsTextBuilderStatus,
        template: DependsTemplate,
        *,
        name: str,
    ):
        """Get RST document."""

        # NOTE: These documents should be built before, not `on the fly`. Allk
        #       document building should happen outside of app run.
        data = await cls.get_by_name_json(
            context,
            status,
            name=name,
        )

        text = data.data.content["text"]
        if (format := text["format"]) == "html":

            wrapped = template.format(document=data.data, body=text["content"])
            return HTMLResponse(wrapped)
        elif format == "svg":
            content = text["content"]
            return Response(content, media_type="image/svg+xml")
        else:
            content = text["content"]
            return PlainTextResponse(
                content, headers={"Content-Type": f"text/{format}"}
            )
