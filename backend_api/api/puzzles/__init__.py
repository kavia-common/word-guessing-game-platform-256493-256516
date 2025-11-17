"""
Puzzle engines and hint utilities.

Exports:
- EngineRegistry and get_engine for resolving puzzle engines
- ClassicEngine and AnagramEngine engine classes
- reveal_position and reveal_first_letter hint helpers

These modules are framework-agnostic and can be reused by views or services
without importing request objects.
"""

from .engines import ClassicEngine, AnagramEngine
from .registry import EngineRegistry, get_engine
from .hints import reveal_position, reveal_first_letter

__all__ = [
    "ClassicEngine",
    "AnagramEngine",
    "EngineRegistry",
    "get_engine",
    "reveal_position",
    "reveal_first_letter",
]
