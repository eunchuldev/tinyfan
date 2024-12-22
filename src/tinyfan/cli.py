import typer

from .codegen import codegen, DEFAULT_IMAGE


def tinyfan(location: str, embedded: bool = False, image: str = DEFAULT_IMAGE):
    """
    Generate argocd workflow resource as yaml from tinyfan definitions
    """
    if location.endswith('.py'):
        print(codegen(location=location, embedded=True, image=image))
    else:
        print(codegen(location=location, embedded=embedded, image=image))


def main():
    return typer.run(tinyfan)


if __name__ == "__main__":
    main()
