"""Router for uploaded documents.

Documents can only be uploaded using the command line for the moment. To provide
the necessary status for this to serve these documents, run ``text up`` to 
add your documents to a captura instance. Once this command has been run, find
your ``.text.status.yaml`` and use its contents to deploy this app.
"""

# =========================================================================== #
from functools import cache
from os import path

from app.schemas import AsOutput, DocumentSchema, T_Output, mwargs
from app.views.base import BaseView

# --------------------------------------------------------------------------- #
from text_app import depends


# NOTE: ALL rendering should be done using the command line for now until I
#       have time to add posting, etc.
class TextView(BaseView):

    view_routes = dict(
        get_by_name_json="/{name}/json",
        get_by_name="/{name}",
    )

    @classmethod
    def get_by_name_json(
        cls, data: depends.DependsGetByNameJson
    ) -> AsOutput[DocumentSchema]:
        return data

    @classmethod
    def get_by_name(cls, response: depends.DependsGetByName):
        return response
