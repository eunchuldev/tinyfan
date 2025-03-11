from ..config import Config, ConfigValue
import inspect


class ResourceBase:
    def get_refs(self) -> set[Config | ConfigValue]:
        refs = set()
        for _, value in inspect.getmembers(self):
            if isinstance(value, (Config, ConfigValue)):  # or a common base 'Reference'
                refs.add(value)
            elif isinstance(value, ResourceBase):
                refs |= ResourceBase.get_refs(value)
        return refs
