import enum
from typing import Annotated, List

# --------------------------------------------------------------------------- #
from app import fields, util
from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# FROM extensions/text.py

COLLECTION_DESCRIPTION = "Resume and supporting documents."
LENGTH_MESSAGE: int = 1024
LENGTH_CONTENT: int = 2**15
LENGTH_FORMAT: int = 8


logger = util.get_logger(__name__)


class Format(str, enum.Enum):
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
