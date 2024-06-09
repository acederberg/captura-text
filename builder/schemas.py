from os import path
from typing import Annotated, Any, Dict, List, Self

import yaml

# --------------------------------------------------------------------------- #
from app import fields, util
from app.auth import functools
from app.config import BaseHashable
from app.schemas import (
    AssignmentSchema,
    CollectionSchema,
    DocumentSchema,
    computed_field,
    mwargs,
)
from client import Config as ClientConfig
from client.config import YamlSettingsConfigDict
from docutils.core import publish_parts
from pydantic import Field

from builder import snippets

logger = util.get_logger(__name__)

PATH_HERE = path.realpath(path.join(path.dirname(__file__), ".."))
PATH_DOCS_DEFUALT = path.join(PATH_HERE, "docs")
PATH_CONFIGS_DEFAULT = path.join(PATH_HERE, "configs")
PATH_STATUS_DEFUALT = path.join(PATH_DOCS_DEFUALT, ".builder.status.yaml")
PATH_CONFIGS_DEFAULT = path.join(PATH_HERE, "configs")
PATH_CONFIGS_BUILDER_DEFAULT = path.join(PATH_CONFIGS_DEFAULT, "builder.yaml")
PATH_CONFIGS_CLIENT_DEFAULT = path.join(PATH_CONFIGS_DEFAULT, "client.yaml")


def here(*v: str):
    return path.join(PATH_HERE, *v)


class TextItemConfig(BaseHashable):
    content_file: Annotated[
        str,
        Field(
            description=(
                "This should be a path relative to the root directory or an "
                "absolute path."
            ),
        ),
    ]
    description: fields.FieldDescription

    def create_content(self, filepath: str) -> Dict[snippets.Format, Dict[str, Any]]:
        # if writers is None:
        #     writers = {"html"}

        logger.debug("Building content for `%s`.", filepath)
        tags = ["resume"]
        with open(filepath, "r") as file:
            content_rst = "\n".join(file.readlines())
            content = dict(rst=content_rst)

        content_html = str(publish_parts(content_rst, writer_name="html"))
        content.update(html=content_html)

        texts = {
            snippets.Format(format): dict(
                text=mwargs(
                    snippets.TextSchema,
                    format=format,
                    content=content,
                    tags=tags,
                ).model_dump(mode="json")
            )
            for format, content in content.items()
        }
        return texts


class TextCollectionConfig(BaseHashable):
    name: Annotated[
        str,
        Field(
            description=(
                "The name to give this collection. For the actual name in "
                "captura, see ``StatusDataConfig.collection_name_captura``."
            )
        ),
    ]
    description: Annotated[
        str, Field(description="The description to give this collection.")
    ]


class TextDataConfig(BaseHashable):
    collection: TextCollectionConfig
    documents: Annotated[
        Dict[str, TextItemConfig],
        Field(description="Text documents to add to the api as documents."),
    ]

    identifier: Annotated[
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

    def get(self, name: str) -> TextItemConfig | None:
        return self.documents.get(name)


# --------------------------------------------------------------------------- #


class RenderedDocumentStatus(BaseHashable):
    name_captura: str
    uuid: fields.FieldUUID
    uuid_assignment: fields.FieldUUID
    format: snippets.Format


class TextItemStatus(TextItemConfig, RenderedDocumentStatus):
    # ``captura`` is included since display names are not included.

    renders: "List[RenderedDocumentStatus]"


class TextItemCollectionStatus(TextCollectionConfig):
    uuid: fields.FieldUUID
    name_captura: str


class TextDataStatus(BaseHashable):
    documents: Dict[str, TextItemStatus]
    collection: TextItemCollectionStatus
    identifier: str

    def get(self, name: str) -> TextItemStatus | None:
        return self.documents.get(name)

    @classmethod
    def fromData(
        cls,
        data: TextDataConfig,
        *,
        collection: CollectionSchema,
        documents: List[Dict[snippets.Format, DocumentSchema]],
        assignments: List[AssignmentSchema],
    ) -> Self:

        identifier = data.identifier

        print(documents)
        yucky = zip(documents, assignments, data.documents.items())
        return cls(
            identifier=identifier,
            collection=TextItemCollectionStatus(
                uuid=collection.uuid,
                name_captura=collection.name,
                name=data.collection.name,
                description=data.collection.description,
            ),
            documents={
                name: TextItemStatus(
                    content_file=item.content_file,
                    name_captura=(doc_rst := docs[snippets.Format.rst]).name,
                    uuid=doc_rst.uuid,
                    uuid_assignment=assign.uuid,
                    description=doc_rst.description,
                    format=snippets.Format.rst,
                    renders=[
                        RenderedDocumentStatus(
                            name_captura=doc.name,
                            uuid=doc.uuid,
                            uuid_assignment=assign.uuid,
                            format=fmt,
                        )
                        for fmt, doc in docs.items()
                        if fmt != snippets.Format.rst
                    ],
                )
                for docs, assign, (name, item) in yucky
            },
        )


class BaseYaml:
    @classmethod
    def load(cls, filepath: str) -> Self:

        with open(filepath, "r") as file:
            results = yaml.safe_load(file)

        return cls(**results)


class Status(BaseYaml, BaseHashable):
    """Text status in captura.

    This is created by ``builder up`` and then used by ``router.py`` to decide
    which documents to render.
    """

    status: Annotated[
        TextDataStatus,
        Field(description="Status of this history of resumes."),
    ]
    history: Annotated[
        List[TextDataStatus],
        Field(default_factory=list, description="Previous status."),
    ]

    def update_status_file(self, filepath: str) -> None:
        if path.exists(filepath):
            logger.debug("Loading existing data.")
            status_from_file = self.load(filepath)

            if status_from_file.status == self.status:
                logger.debug("No changes in data.")
                return

            logger.info("Found change in status!")
            to_dump = self.__class__(
                status=self.status,
                history=[
                    status_from_file.status,
                    *status_from_file.history,
                ],
            )
        else:
            to_dump = self

        logger.info("Dumping status in `%s`.", filepath)
        with open(filepath, "w") as file:
            yaml.dump(to_dump.model_dump(mode="json"), file)


# --------------------------------------------------------------------------- #


class Config(BaseYaml, ClientConfig):
    model_config = YamlSettingsConfigDict(yaml_files=PATH_CONFIGS_CLIENT_DEFAULT)


class BuilderConfig(BaseYaml, BaseHashable):
    model_config = YamlSettingsConfigDict(yaml_files=PATH_CONFIGS_BUILDER_DEFAULT)

    @computed_field
    @functools.cached_property
    def path_status(self) -> str:
        return path.join(self.path_docs, ".builder.status.yaml")

    @computed_field
    @functools.cached_property
    def status(self) -> Status | None:
        if path.exists(self.path_status):
            return Status.load(self.path_status)
        return None

    path_docs: Annotated[str, Field(default=PATH_DOCS_DEFUALT)]
    data: Annotated[TextDataConfig, Field()]
