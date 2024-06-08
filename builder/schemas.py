import json
from os import path
from typing import Annotated, Any, Dict, List, Self

import typer
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
)
from client import Config as ClientConfig
from client.config import YamlSettingsConfigDict
from pydantic import BaseModel, Field
from yaml_settings_pydantic import BaseYamlSettings, YamlFileConfigDict

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

    def create_content(self, filepath: str) -> Dict[str, Any]:
        logger.debug("Building content for `%s`.", filepath)
        tags = ["resume"]
        with open(filepath, "r") as file:
            content = "\n".join(file.readlines())

        text = snippets.TextSchema(
            format=snippets.Format.rst, content=content, tags=tags
        )
        return dict(text=text.model_dump(mode="json"))


class TextDataConfig(BaseHashable):
    items: Annotated[
        Dict[str, TextItemConfig],
        Field(description="Text items to add to the api as documents."),
    ]

    collection_name: Annotated[
        str,
        Field(description="The name to give this collection."),
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
        return self.items.get(name)


# --------------------------------------------------------------------------- #


class TextItemStatus(TextItemConfig):
    name: str
    uuid: fields.FieldUUID
    uuid_assignment: fields.FieldUUID


class TextDataStatus(BaseHashable):
    items: Dict[str, TextItemStatus]
    identifier: str
    collection_uuid: fields.FieldUUID
    collection_name_captura: str

    def get(self, name: str) -> TextItemStatus | None:
        return self.items.get(name)

    @classmethod
    def fromData(
        cls,
        data: TextDataConfig,
        *,
        collection: CollectionSchema,
        documents: List[DocumentSchema],
        assignments: List[AssignmentSchema],
    ) -> Self:

        identifier = data.identifier

        yucky = zip(documents, assignments, data.items.items())
        return cls(
            identifier=identifier,
            collection_uuid=collection.uuid,
            collection_name_captura=collection.name,
            items={
                name: TextItemStatus(
                    content_file=item.content_file,
                    name=doc.name,
                    uuid=doc.uuid,
                    uuid_assignment=assign.uuid,
                    description=doc.description,
                )
                for doc, assign, (name, item) in yucky
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
    def status(self) -> Status:
        return Status.load(self.path_status)

    path_docs: Annotated[str, Field(default=PATH_DOCS_DEFUALT)]
    data: Annotated[TextDataConfig, Field()]
