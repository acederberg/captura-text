import json
from os import path
from typing import Annotated, Any, Dict, List, Self

import yaml

# --------------------------------------------------------------------------- #
from app import fields, util
from app.schemas import AssignmentSchema, CollectionSchema, DocumentSchema
from client import Config as ClientConfig
from client.config import YamlSettingsConfigDict
from pydantic import BaseModel, Field
from yaml_settings_pydantic import YamlFileConfigDict

from builder import snippets

logger = util.get_logger(__name__)

PATH_HERE = path.realpath(path.join(path.dirname(__file__), ".."))


def here(*v: str):
    return path.join(PATH_HERE, *v)


def docs(v: str):
    return here("docs", v)


class ResumeItemConfig(BaseModel):
    content_file: Annotated[
        str,
        Field(
            description=(
                "This should be a path relative to the root directory or an "
                "absolute path."
            ),
        ),
    ]
    name: fields.FieldName
    description: fields.FieldDescription

    def create_content(self) -> Dict[str, Any]:
        logger.debug("Building content for `%s`.", self.name)
        tags = ["resume"]
        with open(docs(self.content_file), "r") as file:
            content = "\n".join(file.readlines())

        text = snippets.TextSchema(
            format=snippets.Format.rst, content=content, tags=tags
        )
        return dict(text=text.model_dump(mode="json"))


class ResumeDataConfig(BaseModel):
    items: Annotated[
        List[ResumeItemConfig],
        Field(description="Resume and supporting items."),
    ]
    identifier: Annotated[
        str,
        Field(description="Document and collection identified."),
    ]


# --------------------------------------------------------------------------- #


class ResumeItemStatus(ResumeItemConfig):
    name: str
    uuid: fields.FieldUUID
    uuid_assignment: fields.FieldUUID


class ResumeDataStatus(BaseModel):
    items: List[ResumeItemStatus]
    identifier: str
    collection_uuid: fields.FieldUUID
    collection_name: str

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

        return cls(
            identifier=identifier,
            collection_uuid=collection.uuid,
            collection_name=collection.name,
            items=list(
                ResumeItemStatus(
                    content_file=item.content_file,
                    name=doc.name,
                    uuid=doc.uuid,
                    uuid_assignment=assign.uuid,
                    description=doc.description,
                )
                for doc, assign, item in zip(documents, assignments, data.items)
            ),
        )


# --------------------------------------------------------------------------- #

PATH_STATUS = here(".status.yaml")


class Config(ClientConfig):
    model_config = YamlSettingsConfigDict(
        yaml_files={
            here("configs/client.yaml"): YamlFileConfigDict(
                required=True,
                subpath=None,
            ),
            PATH_STATUS: YamlFileConfigDict(
                required=False,
                subpath=None,
            ),
        }
    )

    data: Annotated[ResumeDataConfig, Field()]
    status: Annotated[
        ResumeDataStatus | None,
        Field(
            default=None,
            description="Status of this history of resumes.",
        ),
    ]

    def dump_status(self):
        if self.status is None:
            return

        with open("r") as file:
            yaml.dump(self.status.model_dump(mode="json"), file)
