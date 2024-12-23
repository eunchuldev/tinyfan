class Env:
    name: str
    embed: bool

    def __init__(self, name: str, embed: bool = False):
        self.name = name
        self.embed = embed
