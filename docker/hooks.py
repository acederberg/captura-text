# =========================================================================== #
from typing import Type

from app.views import AppView


def captura_plugins_app(app_view: Type[AppView]):

    # --------------------------------------------------------------------------- #
    from text_app import TextView

    app_view.view_router.include_router(TextView.view_router, prefix="/text")


def captura_plugins_client(requests):

    # --------------------------------------------------------------------------- #
    from text_client import TextCommands

    requests.typer_children.update(text=TextCommands)
