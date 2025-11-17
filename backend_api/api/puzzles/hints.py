from __future__ import annotations

from typing import Dict, Any, Tuple, Protocol, runtime_checkable
import random


# Define light-weight protocols instead of importing Django models at import time.
@runtime_checkable
class _WordLike(Protocol):
    """Minimal interface required from Word for hint computations."""
    length: int
    text: str


@runtime_checkable
class _SessionLike(Protocol):
    """Minimal interface required from GameSession for hint computations."""
    is_completed: bool
    hints_used: int
    target_word: _WordLike

    # Django model instances will provide save(); accept any compatible object.
    def save(self, *args, **kwargs) -> None: ...


MAX_HINTS_PER_SESSION = 2


def _ensure_can_use_hint(session: _SessionLike) -> None:
    """Raise ValueError if hint limit reached or session invalid.

    Note:
        Uses a duck-typed session interface to avoid importing Django models
        at module import time, preventing AppRegistryNotReady.
    """
    if session.is_completed:
        raise ValueError("Cannot use hints on a completed session.")
    if session.hints_used >= MAX_HINTS_PER_SESSION:
        raise ValueError("Maximum hints used for this session.")


def _increment_hints(session: _SessionLike) -> None:
    """Persist increment of hints_used with simple cap enforcement."""
    session.hints_used = min(session.hints_used + 1, MAX_HINTS_PER_SESSION)
    # Update only the relevant fields when backed by a Django model.
    try:
        session.save(update_fields=["hints_used", "updated_at"])
    except TypeError:
        # Fallback: some objects may not support update_fields; just call save().
        session.save()


def _pick_unrevealed_position(session: _SessionLike) -> int:
    """Pick an index that hasn't been correctly revealed yet.

    For simplicity (without deep guess analysis), choose any index
    and let the UI treat it as a reveal. To avoid repeating, we try to
    avoid positions that have already been revealed through hints by
    recording nothing in DB for now. In future steps, metadata can track
    revealed positions. For now, pick a random index uniformly.
    """
    length = session.target_word.length
    return random.randrange(0, length)


def _first_letter_position_and_value(session: _SessionLike) -> Tuple[int, str]:
    """Return position 0 and its letter for convenience."""
    return 0, session.target_word.text[0]


# PUBLIC_INTERFACE
def reveal_position(session: _SessionLike) -> Dict[str, Any]:
    """Reveal a random position and its letter from the target word.

    Enforces a simple limit of max 2 hints per session.

    Parameters:
        session: An object representing the game session. It must expose
                 attributes is_completed (bool), hints_used (int),
                 target_word with fields length (int) and text (str),
                 and a save(...) method compatible with Django models.

    Returns:
        {
            "type": "reveal_position",
            "data": { "index": int, "letter": str, "remaining": int }
        }

    Raises:
        ValueError: if the session is completed or hint quota exceeded.
    """
    _ensure_can_use_hint(session)
    idx = _pick_unrevealed_position(session)
    letter = session.target_word.text[idx]
    _increment_hints(session)
    remaining = max(0, MAX_HINTS_PER_SESSION - session.hints_used)
    return {
        "type": "reveal_position",
        "data": {"index": idx, "letter": letter, "remaining": remaining},
    }


# PUBLIC_INTERFACE
def reveal_first_letter(session: _SessionLike) -> Dict[str, Any]:
    """Reveal the first letter of the target word.

    Enforces a simple limit of max 2 hints per session.

    Parameters:
        session: An object representing the game session. It must expose
                 attributes is_completed (bool), hints_used (int),
                 target_word with fields length (int) and text (str),
                 and a save(...) method compatible with Django models.

    Returns:
        {
            "type": "reveal_first_letter",
            "data": { "index": 0, "letter": str, "remaining": int }
        }

    Raises:
        ValueError: if the session is completed or hint quota exceeded.
    """
    _ensure_can_use_hint(session)
    idx, letter = _first_letter_position_and_value(session)
    _increment_hints(session)
    remaining = max(0, MAX_HINTS_PER_SESSION - session.hints_used)
    return {
        "type": "reveal_first_letter",
        "data": {"index": idx, "letter": letter, "remaining": remaining},
    }
