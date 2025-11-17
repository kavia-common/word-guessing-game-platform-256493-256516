from __future__ import annotations

from typing import Dict, Type

from .engines import ClassicEngine, AnagramEngine


# PUBLIC_INTERFACE
class EngineRegistry:
    """Registry mapping puzzle type identifiers to engine classes."""

    _registry: Dict[str, Type] = {
        "classic": ClassicEngine,
        "anagram": AnagramEngine,
    }

    @classmethod
    def get(cls, puzzle_type: str):
        """Return an engine class for a given puzzle type, or raise KeyError."""
        key = (puzzle_type or "").strip().lower()
        if key not in cls._registry:
            raise KeyError(f"Unknown puzzle type: {puzzle_type!r}")
        return cls._registry[key]

    @classmethod
    def register(cls, puzzle_type: str, engine_cls) -> None:
        """Register or override an engine class for a given puzzle type."""
        key = (puzzle_type or "").strip().lower()
        if not key:
            raise ValueError("puzzle_type must be a non-empty string")
        cls._registry[key] = engine_cls


# PUBLIC_INTERFACE
def get_engine(puzzle_type: str):
    """Convenience function to instantiate an engine for the given puzzle_type.

    Example:
        engine = get_engine("classic")()
        result = engine.evaluate(target="apple", guess="apply")
    """
    engine_cls = EngineRegistry.get(puzzle_type)
    return engine_cls
