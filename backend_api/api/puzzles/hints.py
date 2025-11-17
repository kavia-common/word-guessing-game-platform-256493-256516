from __future__ import annotations

from typing import Dict, Any, Tuple
import random

from api.models import GameSession


MAX_HINTS_PER_SESSION = 2


def _ensure_can_use_hint(session: GameSession) -> None:
    """Raise ValueError if hint limit reached or session invalid."""
    if session.is_completed:
        raise ValueError("Cannot use hints on a completed session.")
    if session.hints_used >= MAX_HINTS_PER_SESSION:
        raise ValueError("Maximum hints used for this session.")


def _increment_hints(session: GameSession) -> None:
    """Persist increment of hints_used with simple cap enforcement."""
    session.hints_used = min(session.hints_used + 1, MAX_HINTS_PER_SESSION)
    session.save(update_fields=["hints_used", "updated_at"])


def _pick_unrevealed_position(session: GameSession) -> int:
    """Pick an index that hasn't been correctly revealed yet.

    For simplicity (without deep guess analysis), choose any index
    and let the UI treat it as a reveal. To avoid repeating, we try to
    avoid positions that have already been revealed through hints by
    recording nothing in DB for now. In future steps, metadata can track
    revealed positions. For now, pick a random index uniformly.
    """
    length = session.target_word.length
    return random.randrange(0, length)


def _first_letter_position_and_value(session: GameSession) -> Tuple[int, str]:
    """Return position 0 and its letter for convenience."""
    return 0, session.target_word.text[0]


# PUBLIC_INTERFACE
def reveal_position(session: GameSession) -> Dict[str, Any]:
    """Reveal a random position and its letter from the target word.

    Enforces a simple limit of max 2 hints per session.

    Returns:
        {
            "type": "reveal_position",
            "data": { "index": int, "letter": str, "remaining": int }
        }

    Raises:
        ValueError if the session is completed or hint quota exceeded.
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
def reveal_first_letter(session: GameSession) -> Dict[str, Any]:
    """Reveal the first letter of the target word.

    Enforces a simple limit of max 2 hints per session.

    Returns:
        {
            "type": "reveal_first_letter",
            "data": { "index": 0, "letter": str, "remaining": int }
        }

    Raises:
        ValueError if the session is completed or hint quota exceeded.
    """
    _ensure_can_use_hint(session)
    idx, letter = _first_letter_position_and_value(session)
    _increment_hints(session)
    remaining = max(0, MAX_HINTS_PER_SESSION - session.hints_used)
    return {
        "type": "reveal_first_letter",
        "data": {"index": idx, "letter": letter, "remaining": remaining},
    }
