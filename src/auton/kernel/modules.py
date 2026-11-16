from typing import Literal

from pydantic import BaseModel, ConfigDict


class ModuleDescriptor(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    title: str
    milestone: str
    status: Literal["ready", "planned", "disabled"]
    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    factory_entry: str | None = None
    config_schema: str | None = None
    scope: Literal["application", "session", "run"] = "application"
    version: str = "1"


def resolve_modules(modules: list[ModuleDescriptor]) -> list[str]:
    """Validate the enabled graph before any resource is started."""
    if len({module.id for module in modules}) != len(modules):
        raise ValueError("Duplicate module id")
    active = [module for module in modules if module.status == "ready"]
    providers: dict[str, str] = {}
    for module in active:
        for port in module.provides:
            if port in providers:
                raise ValueError(f"Duplicate provider for {port}")
            providers[port] = module.id
    graph: dict[str, set[str]] = {}
    for module in active:
        missing = set(module.requires) - providers.keys()
        if missing:
            raise ValueError(f"{module.id}: missing dependencies {sorted(missing)}")
        graph[module.id] = {providers[port] for port in module.requires}
    ordered: list[str] = []
    while graph:
        ready = sorted(key for key, value in graph.items() if not value)
        if not ready:
            raise ValueError("Module dependency cycle")
        ordered.extend(ready)
        graph = {key: value - set(ready) for key, value in graph.items() if key not in ready}
    return ordered
