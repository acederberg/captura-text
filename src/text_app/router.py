"""Router for uploaded documents.

Documents can only be uploaded using the command line for the moment. To provide
the necessary status for this to serve these documents, run ``text up`` to 
add your documents to a captura instance. Once this command has been run, find
your ``.text.status.yaml`` and use its contents to deploy this app.
"""

from os import path
from typing import Annotated

from app import Document
from app.depends import DependsAsyncSessionMaker, DependsSessionMaker
from app.models import User
from app.schemas import AsOutput, DocumentSchema, mwargs
from app.views.base import BaseView
from fastapi import Depends, HTTPException, Response
from fastapi.responses import PlainTextResponse
from pydantic import TypeAdapter
from sqlalchemy import select
from starlette.responses import HTMLResponse

from text_app.schemas import (
    PATH_CONFIGS_BUILDER_DEFAULT,
    BuilderConfig,
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


def text() -> BuilderConfig:
    return BuilderConfig.load(PATH_CONFIGS_BUILDER_DEFAULT)


DependsBuilder = Annotated[BuilderConfig, Depends(text, use_cache=True)]


def status(text: DependsBuilder) -> TextBuilderStatus:
    if text.status is None:
        raise HTTPException(500, detail="``status`` is required.")

    return text.status


DependsTextBuilderStatus = Annotated[TextBuilderStatus, Depends(status, use_cache=True)]


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
    def get_by_name_json(
        cls,
        sessionmaker: DependsSessionMaker,
        status: DependsTextBuilderStatus,
        *,
        name: str,
    ) -> AsOutput[DocumentSchema]:
        """Get JSON data for the document."""

        if (data := status.status.get(name)) is None:
            raise HTTPException(404, detail="No such document.")

        with sessionmaker() as session:
            q = select(Document).where(Document.uuid == data.uuid)
            document = session.scalar(q)

        document_out = DocumentSchema.model_validate(document)
        return mwargs(AsOutput, data=document_out)

    @classmethod
    def get_by_name(
        cls,
        sessionmaker: DependsSessionMaker,
        status: DependsTextBuilderStatus,
        template: DependsTemplate,
        *,
        name: str,
    ):
        """Get RST document."""

        # NOTE: These documents should be built before, not `on the fly`. Allk
        #       document building should happen outside of app run.
        data = cls.get_by_name_json(
            sessionmaker,
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
