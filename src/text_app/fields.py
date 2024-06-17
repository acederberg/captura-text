# =========================================================================== #
import enum
from os import path
from typing import Annotated, List, Literal

from app import fields, util
from pydantic import BaseModel, Field

# FROM extensions/text.py

LENGTH_MESSAGE: int = 1024
LENGTH_CONTENT: int = 2**18
LENGTH_FORMAT: int = 8


PATH_HERE = path.realpath(path.join(path.dirname(__file__), "..", ".."))
PATH_TEXT_DOCS = util.from_env(
    "TEXT_DOCS",
    path.join(PATH_HERE, "docs"),
)

_PATH_TEXT_STATUS_DEFAULT = util.from_env("TEXT_STATUS", "")
PATH_TEXT_STATUS_DEFAULT: None | str = (
    None if not _PATH_TEXT_STATUS_DEFAULT else _PATH_TEXT_STATUS_DEFAULT
)
PATH_TEXT_CONFIG = util.from_env(
    "TEXT_CONFIG",
    path.join(PATH_TEXT_DOCS, "text.yaml"),
)


logger = util.get_logger(__name__)


class Format(str, enum.Enum):
    """It is important to consider what should and should not be stored.

    For instance it might not be great to accept arbitrary ``HTML`` inputs
    since they could be used to execute whatever code they want in the browser.

    The way things are set up now, only those running the captura text
    extension should have access to this functionality - that is, the server
    admin is responsible for the content served by this application (which
    is, for the moment, a captura client and not truely an extension).
    """

    svg = "svg"
    css = "css"
    html = "html"
    md = "md"
    rst = "rst"
    tEx = "tEx"
    txt = "txt"
    docs = "docs"


FieldFormat = Annotated[
    Format,
    Field(default=Format.md, description="Text document format."),
]
FieldFormatIn = Annotated[
    Literal[Format.rst, Format.css, Format.svg],
    Field(),
]
FieldFormatOut = Annotated[
    Literal[
        Format.rst,
        Format.css,
        Format.html,
        Format.svg,
    ],
    Field(),
]
FieldTemplateFile = Annotated[
    str | None,
    Field(description="Template to render ``html`` into.", default=None),
]

FieldIdentifier = Annotated[
    str,
    Field(
        description=(
            "This value should be a random string, for instance one "
            "generated like "
            "`python -c 'import secrets; print(secrets.token_urlsafe());'`."
            "Identifier for this batch of documents and their collection."
            "The ``collection_name`` field actually results in a collection"
            "having the name with the identifier at the end."
        )
    ),
]
FieldName = Annotated[
    str,
    Field(
        description=(
            "The name to give this object. For the actual name in "
            "captura, see ``name_captura``."
        )
    ),
]
FieldDescription = Annotated[
    str,
    Field(description="The description to give this object."),
]
FieldContentFile = Annotated[
    str,
    Field(
        description=(
            "This should be a path relative to the root directory or an "
            "absolute path."
        ),
    ),
]
FieldPathDocs = Annotated[
    str,
    Field(
        description="Path to the directory containing the documents to be rendered.",
        default=PATH_TEXT_DOCS,
        validate_default=True,
    ),
]


FieldMessage = Annotated[
    str,
    Field(
        min_length=0,
        max_length=LENGTH_MESSAGE,
        description="Text document edit message.",
        examples=["The following changes were made to the document: ..."],
    ),
]

FieldContent = Annotated[
    str,
    Field(
        max_length=LENGTH_CONTENT,
        description="Text document content.",
        examples=[fields.EXAMPLE_CONTENT],
    ),
]
FieldTags = Annotated[
    List[str] | None,
    Field(
        max_length=8,
        description="Text document tags.",
    ),
]


class TextSchema(BaseModel):
    """How the content schema should look."""

    format: FieldFormat
    content: FieldContent
    tags: FieldTags
