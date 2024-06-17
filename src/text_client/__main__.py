from client.requests.base import typerize

# --------------------------------------------------------------------------- #
from text_client import TextCommands


def main():
    # --------------------------------------------------------------------------- #

    cmd = typerize(TextCommands)
    cmd()


if __name__ == "__main__":
    main()
