import typer

from .codegen import codegen


def tinyfan(
    location: str,
    embedded: bool = False,
):
    """
    Generate argocd workflow resource as yaml from tinyfan definitions
    """
    if location.endswith(".py"):
        print(codegen(location=location, embedded=True))
    else:
        print(codegen(location=location, embedded=embedded))


def main():
    return typer.run(tinyfan)


if __name__ == "__main__":
    main()
