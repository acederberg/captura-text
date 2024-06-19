# =========================================================================== #
from os import path
from typing import Annotated, Any, ClassVar, Dict, List, Self

import yaml
from app import KindObject
from app import fields as captura_fields
from app import util
from app.auth import functools
from app.config import BaseHashable
from app.schemas import computed_field, mwargs
from docutils.core import publish_parts
from pydantic import Field
from yaml_settings_pydantic import YamlSettingsConfigDict

# --------------------------------------------------------------------------- #
from text_app import fields

logger = util.get_logger(__name__)


DESC_NAMES = "Document names to filter by. Uses the names specified in ``text.yaml``."
DESC_FORMAT = "Formats to filter by."


def here(*v: str):
    return path.join(fields.PATH_HERE, *v)


class BaseObjectConfig(BaseHashable):
    kind: ClassVar[KindObject]


class TextDocumentConfig(BaseObjectConfig):
    kind = KindObject.document

    content_file: fields.FieldContentFile
    description: fields.FieldDescription
    format_in: fields.FieldFormatIn
    format_out: fields.FieldFormatOut

    def create_content(self, filepath: str) -> Dict[str, Any]:
        logger.debug("Building content for `%s`.", filepath)
        tags = ["resume"]
        with open(filepath, "r") as file:
            content = "".join(file.readlines())

        match (self.format_in, self.format_out):
            case (fields.Format.rst, fields.Format.html):
                content = str(publish_parts(content, writer_name="html")["html_body"])
            case (
                (fields.Format.css, fields.Format.css)
                | (fields.Format.rst, fields.Format.rst)
                | (fields.Format.svg, fields.Format.svg)
            ):
                ...
            case _:
                msg = (
                    f"Unsupported conversion ``{self.format_in} -> {self.format_out}``."
                )
                raise ValueError(msg)

        return dict(
            text=mwargs(
                fields.TextSchema,
                format=self.format_out,
                content=content,
                tags=tags,
            ).model_dump(mode="json")
        )


class TextCollectionConfig(BaseObjectConfig):
    kind = KindObject.collection

    name: fields.FieldName
    description: fields.FieldDescription


class TextDataConfig(BaseHashable):
    hashable_fields_exclude = {"documents"}

    path_docs: fields.FieldPathDocs
    template_file: fields.FieldTemplateFile
    identifier: fields.FieldIdentifier
    collection: TextCollectionConfig
    documents: Annotated[
        Dict[str, TextDocumentConfig],
        Field(description="Text documents to add to the api as documents."),
    ]

    def get(self, name: str) -> TextDocumentConfig | None:
        return self.documents.get(name)

    def require(self, name: str) -> TextDocumentConfig:
        v = self.get(name)
        if v is None:
            raise ValueError(f"No such text item ``{name}``.")

        return v


# --------------------------------------------------------------------------- #


class BaseObjectStatus(BaseObjectConfig):

    name_captura: captura_fields.FieldName
    uuid: captura_fields.FieldUUID
    deleted: captura_fields.FieldDeleted


class TextDocumentStatus(BaseObjectStatus, TextDocumentConfig):
    name: captura_fields.FieldName


class TextCollectionStatus(BaseObjectStatus, TextCollectionConfig): ...


class TextDataStatus(BaseHashable):
    hashable_fields_exclude = {"documents"}

    documents: Dict[str, TextDocumentStatus]
    collection: TextCollectionStatus
    path_docs: fields.FieldPathDocs
    identifier: fields.FieldIdentifier

    def get(self, name: str) -> TextDocumentStatus | None:
        return self.documents.get(name)

    def require(self, name: str) -> TextDocumentStatus:
        v = self.get(name)
        if v is None:
            raise ValueError(f"No such text item ``{name}``.")

        return v


class BaseYaml:
    @classmethod
    def load(cls, filepath: str) -> Self:

        with open(filepath, "r") as file:
            results = yaml.safe_load(file)

        return cls(**results)


class TextBuilderStatus(BaseYaml, BaseHashable):
    """Text status in captura.

    This is created by ``text up`` and then used by ``router.py`` to decide
    which documents to render.
    """

    hashable_fields_exclude = {"history"}

    status: Annotated[
        TextDataStatus,
        Field(description="Status of this history of resumes."),
    ]
    history: Annotated[
        List[TextDataStatus],
        Field(default_factory=list, description="Previous status."),
    ]


# --------------------------------------------------------------------------- #


class BuilderConfig(BaseYaml, BaseHashable):
    model_config = YamlSettingsConfigDict(yaml_files=fields.PATH_TEXT_CONFIG)

    @computed_field
    @functools.cached_property
    def path_status(self) -> str:
        if (p := fields.PATH_TEXT_STATUS_DEFAULT) is not None:
            return p
        return path.join(self.data.path_docs, ".text.status.yaml")

    @computed_field
    @functools.cached_property
    def status(self) -> TextBuilderStatus | None:
        if path.exists(self.path_status):
            return TextBuilderStatus.load(self.path_status)
        return None

    data: Annotated[TextDataConfig, Field()]


class TextOptions(BaseHashable):
    names: Annotated[
        List[str] | None,
        Field(description=DESC_NAMES, default=None),
    ]
    # formats: Annotated[
    #     List[snippets.Format] | None,
    #     Field(description=DESC_FORMAT, default=None),
    # ]
