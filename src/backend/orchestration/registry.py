"""Registry engine theo EngineDescriptor để T-027/T-028 cắm vào."""

from __future__ import annotations

from collections.abc import Callable

from engines.interface import EngineDescriptor, EngineInput, EngineOutput

EngineRunner = Callable[[EngineInput], EngineOutput]


class EngineRegistry:
    def __init__(self) -> None:
        self._engines: dict[tuple[str, str], tuple[EngineDescriptor, EngineRunner]] = {}

    def register(self, descriptor: EngineDescriptor, runner: EngineRunner) -> None:
        key = (descriptor.name, descriptor.version)
        if key in self._engines:
            raise ValueError(f"engine {key[0]}@{key[1]} đã đăng ký")
        self._engines[key] = (descriptor, runner)

    def descriptor(self, name: str, version: str) -> EngineDescriptor:
        return self._lookup(name, version)[0]

    def runner(self, name: str, version: str) -> EngineRunner:
        return self._lookup(name, version)[1]

    def descriptors(self) -> list[EngineDescriptor]:
        return sorted((d for d, _ in self._engines.values()), key=lambda d: (d.name, d.version))

    def _lookup(self, name: str, version: str) -> tuple[EngineDescriptor, EngineRunner]:
        try:
            return self._engines[(name, version)]
        except KeyError:
            raise LookupError(f"engine {name}@{version} chưa đăng ký") from None


registry = EngineRegistry()
