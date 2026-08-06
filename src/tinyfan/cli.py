import typer

from typing_extensions import Annotated
from .codegen import codegen
from .config import CLI_CONFIG_STATE


def tinyfan(
    location: str,
    embedded: bool | None = None,
    arg: Annotated[list[str] | None, typer.Option(metavar="KEY=VALUE")] = None,
    import_all: Annotated[
        bool,
        typer.Option(help="Import every submodule instead of discovering modules with @asset statically."),
    ] = False,
):
    """
    Generate argocd workflow resource as yaml from tinyfan definitions
    """
    if arg is not None:
        CLI_CONFIG_STATE.cli_args.update({k: v for (k, v) in (val.split("=") for val in arg)})
    if location.endswith(".py"):
        print(codegen(location=location, embedded=embedded or True, import_all=import_all))
    else:
        print(codegen(location=location, embedded=embedded or False, import_all=import_all))


def main():
    return typer.run(tinyfan)


if __name__ == "__main__":
    main()
