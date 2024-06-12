from os import path
from typing import Annotated, Any, ClassVar, Dict, List, Literal, Self, Set

import yaml

# --------------------------------------------------------------------------- #
from app import ChildrenUser, KindObject, fields, util
from app.auth import functools
from app.config import BaseHashable
from app.schemas import (
    AsOutput,
    AssignmentSchema,
    CollectionSchema,
    DocumentSchema,
    computed_field,
    mwargs,
)
from client import Config as ClientConfig
from client.config import YamlSettingsConfigDict
from client.handlers import RequestHandlerData, TypeAdapter, typer
from client.requests import Requests
from docutils.core import publish_parts
from pydantic import Field

from text import snippets

logger = util.get_logger(__name__)

PATH_HERE = path.realpath(path.join(path.dirname(__file__), ".."))
PATH_DOCS_DEFAULT = path.join(PATH_HERE, "docs")
PATH_CONFIGS_DEFAULT = path.join(PATH_HERE, "configs")
PATH_STATUS_DEFAULT = path.join(PATH_DOCS_DEFAULT, ".text.status.yaml")
PATH_CONFIGS_DEFAULT = path.join(PATH_HERE, "configs")
PATH_CONFIGS_BUILDER_DEFAULT = path.join(PATH_DOCS_DEFAULT, "text.yaml")
PATH_CONFIGS_CLIENT_DEFAULT = path.join(PATH_CONFIGS_DEFAULT, "client.yaml")


def here(*v: str):
    return path.join(PATH_HERE, *v)


class BaseObjectConfig(BaseHashable):
    kind: ClassVar[KindObject]


class TextDocumentConfig(BaseObjectConfig):
    kind = KindObject.document

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
    format_in: Literal[snippets.Format.rst, snippets.Format.css, snippets.Format.svg]
    format_out: Literal[
        snippets.Format.rst,
        snippets.Format.css,
        snippets.Format.html,
        snippets.Format.svg,
    ]

    def create_content(self, filepath: str) -> Dict[str, Any]:
        logger.debug("Building content for `%s`.", filepath)
        tags = ["resume"]
        with open(filepath, "r") as file:
            content = "".join(file.readlines())

        match (self.format_in, self.format_out):
            case (snippets.Format.rst, snippets.Format.html):
                content = str(publish_parts(content, writer_name="html")["html_body"])
            case (
                (snippets.Format.css, snippets.Format.css)
                | (snippets.Format.rst, snippets.Format.rst)
                | (snippets.Format.svg, snippets.Format.svg)
            ):
                ...
            case _:
                msg = (
                    f"Unsupported conversion ``{self.format_in} -> {self.format_out}``."
                )
                raise ValueError(msg)

        return dict(
            text=mwargs(
                snippets.TextSchema,
                format=self.format_out,
                content=content,
                tags=tags,
            ).model_dump(mode="json")
        )


class TextCollectionConfig(BaseObjectConfig):
    kind = KindObject.collection

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
        Dict[str, TextDocumentConfig],
        Field(description="Text documents to add to the api as documents."),
    ]
    path_docs: str
    template_file: Annotated[
        str | None,
        Field(description="Template to render ``html`` into.", default=None),
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

    def get(self, name: str) -> TextDocumentConfig | None:
        return self.documents.get(name)

    def require(self, name: str) -> TextDocumentConfig:
        v = self.get(name)
        if v is None:
            raise ValueError(f"No such text item ``{name}``.")

        return v

    async def discover_document(
        self,
        requests: Requests,
        name: str,
    ) -> DocumentSchema | None:
        """Try to find uuid corresponding to the identifier.

        For more on the document name on the captura side, please see the
        description of ``identifier``. To discover and create
        ``TextDataStatus``, please see ``TextDataStaus.discover``.
        """

        name_captura = f"{name}-{self.identifier}"
        adptr = TypeAdapter(AsOutput[List[DocumentSchema]])
        item = self.require(name)
        name_captura += f"-{item.format_out.name}"

        res = await requests.users.search(
            requests.context.config.profile.uuid_user,  # type: ignore
            child=ChildrenUser.documents,
            name_like=name_captura,
        )
        return self.check_discover(requests, res, adapter=adptr)

    async def discover_collection(
        self,
        requests: Requests,
    ) -> CollectionSchema | None:
        name_captura = f"{self.collection.name}-{self.identifier}"
        adptr = TypeAdapter(AsOutput[List[DocumentSchema]])

        res = await requests.users.search(
            requests.context.config.profile.uuid_user,  # type: ignore
            child=ChildrenUser.collections,
            name_like=name_captura,
        )
        return self.check_discover(requests, res, adapter=adptr)

    def check_discover(self, requests, res, **kwargs):
        (handler_data,), err = requests.handler.check_status(res, **kwargs)
        if err is not None:
            raise err

        if handler_data.data.kind is None:
            return None
        elif len(items := handler_data.data.data) == 1:
            return items[0]
        else:
            raise ValueError("Too many results.")

    async def create_document(
        self,
        requests: Requests,
        name: str,
    ) -> DocumentSchema:
        """Upsert a document by name.

        This returns the raw data from captura. Tranformation into ``status``
        is done within ``controller`` as is bulk upsertion.
        """

        item = self.require(name)
        name_captura = f"{name}-{self.identifier}-{item.format_out.name}"
        filename = path.join(self.path_docs, item.content_file)
        content = item.create_content(filename)

        res = await requests.d.create(
            name=name_captura,
            description=item.description,
            content=content,  # type: ignore
            public=False,
        )

        handler_data: RequestHandlerData[AsOutput[CollectionSchema]]

        adptr = TypeAdapter(AsOutput[DocumentSchema])
        (handler_data,), err = requests.handler.check_status(
            res, expect_status=201, adapter=adptr
        )
        if err is not None:
            raise err

        return handler_data.data.data

    async def create_collection(
        self, requests: Requests, name: str
    ) -> CollectionSchema:
        logger.debug("Creating collection.")
        name_captura = f"{name}-{self.identifier}"
        res = await requests.c.create(
            name=name_captura,
            content=None,
            description=self.collection.description,
            public=False,
        )

        handler_data: RequestHandlerData[AsOutput[CollectionSchema]]

        adptr = TypeAdapter(AsOutput[CollectionSchema])
        (handler_data,), err = requests.handler.check_status(
            res, expect_status=201, adapter=adptr
        )
        if err is not None:
            raise err

        return handler_data.data.data


# --------------------------------------------------------------------------- #


class BaseObjectStatus(BaseObjectConfig):

    name_captura: str
    uuid: fields.FieldUUID
    deleted: Annotated[bool, Field(default=True)]


class TextDocumentStatus(BaseObjectStatus, TextDocumentConfig):
    name: str


class TextCollectionStatus(BaseObjectStatus, TextCollectionConfig): ...


class TextDataStatus(BaseHashable):
    documents: Dict[str, TextDocumentStatus]
    collection: TextCollectionStatus
    path_docs: str
    identifier: str

    def get(self, name: str) -> TextDocumentStatus | None:
        return self.documents.get(name)

    def require(self, name: str) -> TextDocumentStatus:
        v = self.get(name)
        if v is None:
            raise ValueError(f"No such text item ``{name}``.")

        return v

    async def update_document(
        self,
        requests: Requests,
        name: str,
    ) -> None:
        """Upsert a document by name.

        This returns the raw data from captura. Tranformation into ``status``
        is done within ``controller`` as is bulk upsertion.
        """

        item = self.require(name)
        name_captura = f"{name}-{self.identifier}-{item.format_out.name}"
        status = 200
        filename = path.join(self.path_docs, item.content_file)
        content = item.create_content(filename)

        res = await requests.d.update(
            item.uuid,
            name=name_captura,
            description=item.description,
            content=content,  # type: ignore
        )

        adptr_search = TypeAdapter(AsOutput[DocumentSchema])
        (_,), err = requests.handler.check_status(
            res, expect_status=status, adapter=adptr_search
        )
        if err is not None:
            raise err

        return None

    async def update_collection(
        self,
        requests: Requests,
    ) -> None:
        """Upsert a document by name.

        This returns the raw data from captura. Tranformation into ``status``
        is done within ``controller`` as is bulk upsertion.
        """
        name_captura = f"{self.collection.name}-{self.identifier}"

        status = 200

        res = await requests.c.update(
            self.collection.uuid,
            name=name_captura,
            description=self.collection.description,
        )

        adptr = TypeAdapter(AsOutput[CollectionSchema])
        (_,), err = requests.handler.check_status(
            res, expect_status=status, adapter=adptr
        )
        if err is not None:
            raise err

    async def destroy_document(
        self,
        requests: Requests,
        name: str,
    ) -> TextDocumentStatus:
        item = self.require(name)
        res = await requests.d.delete(item.uuid)
        (_,), err = requests.handler.check_status(res)
        if err is not None:
            raise err

        out = item.model_copy()
        out.deleted = True
        return out

    async def destroy_collection(self, requests: Requests) -> TextCollectionStatus:
        res = await requests.c.delete(self.collection.uuid)
        (_,), err = requests.handler.check_status(res)
        if err is not None:
            raise err

        out = self.collection.model_copy()
        out.deleted = True
        return out


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
        return path.join(self.data.path_docs, ".text.status.yaml")

    @computed_field
    @functools.cached_property
    def status(self) -> TextBuilderStatus | None:
        if path.exists(self.path_status):
            return TextBuilderStatus.load(self.path_status)
        return None

    data: Annotated[TextDataConfig, Field()]
