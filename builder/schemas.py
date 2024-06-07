import json
from os import path
from typing import Annotated, Any, Dict, List, Self

import typer
import yaml

# --------------------------------------------------------------------------- #
from app import fields, util
from app.config import BaseHashable
from app.schemas import AssignmentSchema, CollectionSchema, DocumentSchema
from client import Config as ClientConfig
from client.config import YamlSettingsConfigDict
from pydantic import BaseModel, Field
from yaml_settings_pydantic import BaseYamlSettings, YamlFileConfigDict

from builder import snippets

logger = util.get_logger(__name__)

PATH_HERE = path.realpath(path.join(path.dirname(__file__), ".."))


def here(*v: str):
    return path.join(PATH_HERE, *v)


def docs(v: str):
    return here("docs", v)


class ResumeItemConfig(BaseHashable):
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

    def create_content(self, name: str) -> Dict[str, Any]:
        logger.debug("Building content for `%s`.", name)
        tags = ["resume"]
        with open(docs(self.content_file), "r") as file:
            content = "\n".join(file.readlines())

        text = snippets.TextSchema(
            format=snippets.Format.rst, content=content, tags=tags
        )
        return dict(text=text.model_dump(mode="json"))


class ResumeDataConfig(BaseHashable):
    items: Annotated[
        Dict[str, ResumeItemConfig],
        Field(description="Resume and supporting items."),
    ]
    identifier: Annotated[
        str,
        Field(description="Document and collection identified."),
    ]

    def get(self, name: str) -> ResumeItemConfig | None:
        return self.items.get(name)


# --------------------------------------------------------------------------- #


class ResumeItemStatus(ResumeItemConfig):
    name: str
    uuid: fields.FieldUUID
    uuid_assignment: fields.FieldUUID


class ResumeDataStatus(BaseHashable):
    items: Dict[str, ResumeItemStatus]
    identifier: str
    collection_uuid: fields.FieldUUID
    collection_name: str

    def get(self, name: str) -> ResumeItemStatus | None:
        return self.items.get(name)

    @classmethod
    def fromData(
        cls,
        data: ResumeDataConfig,
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
            collection_name=collection.name,
            items={
                name: ResumeItemStatus(
                    content_file=item.content_file,
                    name=doc.name,
                    uuid=doc.uuid,
                    uuid_assignment=assign.uuid,
                    description=doc.description,
                )
                for doc, assign, (name, item) in yucky
            },
        )


PATH_STATUS = here(".status.yaml")


class Status(BaseYamlSettings):
    """Resume status in captura.

    This is created by ``builder up`` and then used by ``router.py`` to decide
    which documents to render.
    """

    model_config = YamlSettingsConfigDict(
        yaml_files={
            PATH_STATUS: YamlFileConfigDict(
                required=False,
                subpath=None,
            ),
        },
        yaml_reload=False,
    )

    status: Annotated[
        ResumeDataStatus,
        Field(description="Status of this history of resumes."),
    ]
    history: Annotated[
        List[ResumeDataStatus],
        Field(default_factory=list, description="Previous status."),
    ]

    def update_status_file(self) -> None:
        if self.status is None:
            logger.debug("No data to dump.")
            return

        if path.exists(PATH_STATUS):
            logger.debug("Loading existing data.")
            with open(PATH_STATUS, "r") as file:
                results = yaml.safe_load(file)

            status_from_file = self.__class__.model_validate(results)
            # print("======================================================")
            # print(status_from_file)
            if status_from_file.status == self.status:
                logger.debug("No changes in data.")
                return

            logger.info("Found change in status!")
            # print("======================================================")
            # print(f"{self.status = }")
            # print(f"{status_from_file.status = }")
            # raise typer.Exit(1)
            to_dump = self.__class__(
                status=self.status,
                history=[
                    status_from_file.status,
                    *status_from_file.history,
                ],
            )
        else:
            to_dump = self

        logger.info("Dumping status in `%s`.", PATH_STATUS)
        with open(PATH_STATUS, "w") as file:
            yaml.dump(to_dump.model_dump(mode="json"), file)


# --------------------------------------------------------------------------- #


class Config(ClientConfig):
    model_config = YamlSettingsConfigDict(
        yaml_files={
            here("configs/client.yaml"): YamlFileConfigDict(
                required=True,
                subpath=None,
            ),
        }
    )

    data: Annotated[ResumeDataConfig, Field()]
