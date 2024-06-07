# =========================================================================== #
from typing import ClassVar

from docutils.core import publish_parts, publish_string
from docutils.frontend import get_default_settings
from docutils.parsers.rst import Parser
from docutils.utils import new_document


# NOTE: Huge fucking pain in the ass: https://www.sphinx-doc.org/en/master/_modules/docutils/parsers/rst.html
# NOTE: It took way too long to find this: https://stackoverflow.com/questions/6654519/parsing-restructuredtext-into-html
#       This libraries docs are trash.
def example():
    text = (
        "example\n"
        "=================================================\n"
        "\n"
        "This is an example to make sure rst renders correctly."
    )

    html = publish_string(text, writer_name="html")
    print(html)


if __name__ == "__main__":
    example()
