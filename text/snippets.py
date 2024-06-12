import enum
from typing import Annotated, List

# --------------------------------------------------------------------------- #
from app import fields, util
from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# FROM extensions/text.py

LENGTH_MESSAGE: int = 1024
LENGTH_CONTENT: int = 2**18
LENGTH_FORMAT: int = 8


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
