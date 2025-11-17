"""
API package initializer.

Re-exports puzzle engines, registry helpers, and hint utilities so callers can
import from api directly, e.g.:

    from api import get_engine, reveal_first_letter
"""

# PUBLIC_INTERFACE
from .puzzles import (
    ClassicEngine,
    AnagramEngine,
    EngineRegistry,
    get_engine,
    reveal_position,
    reveal_first_letter,
)

__all__ = [
    "ClassicEngine",
    "AnagramEngine",
    "EngineRegistry",
    "get_engine",
    "reveal_position",
    "reveal_first_letter",
]
