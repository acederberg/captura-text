# =========================================================================== #
from functools import cache
from os import path
from typing import Annotated, Any

from app import Document
from app.config import BaseHashable
from app.depends import DependsAsyncSessionMaker, DependsSessionMaker, util
from app.models import User
from app.schemas import AsOutput, DocumentSchema, T_Output, mwargs
from app.views.base import BaseView
from fastapi import Depends, HTTPException, Response
from fastapi.responses import PlainTextResponse
from pydantic import TypeAdapter
from sqlalchemy import select
from starlette.responses import HTMLResponse

# --------------------------------------------------------------------------- #
from text_app.fields import PATH_TEXT_CONFIG
from text_app.schemas import BuilderConfig, TextBuilderStatus

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

logger = util.get_logger(__name__)

# --------------------------------------------------------------------------- #


@cache
def text() -> BuilderConfig:
    logger.info("Loading `%s` as a dependency.", PATH_TEXT_CONFIG)
    return BuilderConfig.load(PATH_TEXT_CONFIG)


DependsBuilder = Annotated[BuilderConfig, Depends(text, use_cache=True)]


@cache
def status(text: DependsBuilder) -> TextBuilderStatus:
    if text.status is None:
        raise HTTPException(500, detail="``status`` is required.")

    return text.status


DependsTextBuilderStatus = Annotated[TextBuilderStatus, Depends(status, use_cache=True)]


@cache
def template(text: DependsBuilder) -> str:
    logger.info("Loading template `%s`.", text.data.template_file)
    if (template_file := text.data.template_file) is None:
        return TEMPLATE

    with open(path.join(text.data.path_docs, template_file), "r") as file:
        return "".join(file.readlines())


DependsTemplate = Annotated[str, Depends(template, use_cache=True)]


class HashableDocumentSchema(DocumentSchema, BaseHashable):
    hashable_fields_exclude = {"content"}

    registry_exclude = True


class HashableDocumentOutput(AsOutput, BaseHashable):
    data: HashableDocumentSchema


@cache
def get_by_name_json(
    sessionmaker: DependsSessionMaker,
    status: DependsTextBuilderStatus,
    *,
    name: str,
) -> HashableDocumentOutput:
    """Get JSON data for the document."""

    logger.info("Finding captura document for text ``%s``.", name)
    if (data := status.status.get(name)) is None:
        raise HTTPException(404, detail="No such document.")

    with sessionmaker() as session:
        q = select(Document).where(Document.uuid == data.uuid)
        document = session.scalar(q)

    if document is None:
        raise HTTPException(404, detail="No such document.")

    document_out = DocumentSchema.model_validate(document)
    return mwargs(HashableDocumentOutput, data=document_out)


DependsGetByNameJson = Annotated[
    HashableDocumentOutput,
    Depends(get_by_name_json, use_cache=True),
]


@cache
def get_by_name_text(data: DependsGetByNameJson, template: DependsTemplate, name: str):
    """Get document content in browser appropriate form."""

    logger.info("Rendering browser content for text ``%s``.", name)
    if (content := data.data.content) is None or (text := content.get("text")) is None:
        raise HTTPException(500, detail="Cannot serve malformed text data.")

    if (format := text["format"]) == "html":
        wrapped = template.format(document=data.data, body=text["content"])
        return HTMLResponse(wrapped)
    elif format == "svg":
        content = text["content"]
        return Response(content, media_type="image/svg+xml")
    else:
        content = text["content"]
        return PlainTextResponse(content, headers={"Content-Type": f"text/{format}"})


DependsGetByName = Annotated[Any, Depends(get_by_name_text, use_cache=True)]
