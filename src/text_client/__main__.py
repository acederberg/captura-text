from text_client.command import TextCommands
from client.requests.base import typerize


def main():
    # --------------------------------------------------------------------------- #

    cmd = typerize(TextCommands)
    cmd()
