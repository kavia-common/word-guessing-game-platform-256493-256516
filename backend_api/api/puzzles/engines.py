from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Dict, Any, Protocol

# Reuse the same feedback semantics used by serializers/views
LetterFeedback = Literal["correct", "present", "absent"]


class Engine(Protocol):
    """Protocol for puzzle engines."""

    # PUBLIC_INTERFACE
    def evaluate(self, target: str, guess: str) -> Dict[str, Any]:
        """Evaluate a guess against a target.

        Returns a dict:
        {
            "feedback": List[LetterFeedback],   # same length as target
            "is_correct": bool,
            "metadata": Dict[str, Any]          # optional engine-specific info
        }
        """


def _compute_letter_feedback(target: str, guess: str) -> List[LetterFeedback]:
    """Compute per-letter feedback similar to Wordle rules.

    - correct: correct letter in correct position
    - present: letter exists in target but different position (respect counts)
    - absent: letter not in target or already satisfied by count
    """
    t = list(target)
    g = list(guess)
    n = len(t)
    result: List[LetterFeedback] = ["absent"] * n

    remaining_counts: Dict[str, int] = {}
    for i in range(n):
        if g[i] == t[i]:
            result[i] = "correct"
        else:
            remaining_counts[t[i]] = remaining_counts.get(t[i], 0) + 1

    for i in range(n):
        if result[i] == "correct":
            continue
        ch = g[i]
        if remaining_counts.get(ch, 0) > 0:
            result[i] = "present"
            remaining_counts[ch] -= 1
        else:
            result[i] = "absent"

    return result


@dataclass
class ClassicEngine:
    """Classic word-guess engine using per-letter feedback."""

    # PUBLIC_INTERFACE
    def evaluate(self, target: str, guess: str) -> Dict[str, Any]:
        """Evaluate a classic word-guess using Wordle-like feedback."""
        target_n = target.strip().lower()
        guess_n = guess.strip().lower()
        if len(target_n) != len(guess_n):
            raise ValueError("Target and guess length must match for ClassicEngine.")

        feedback = _compute_letter_feedback(target_n, guess_n)
        is_correct = target_n == guess_n
        return {
            "feedback": feedback,
            "is_correct": is_correct,
            "metadata": {"engine": "classic"},
        }


@dataclass
class AnagramEngine:
    """Anagram puzzle engine.

    Rule: A guess is correct if it uses exactly the same multiset of letters as target
    (i.e., a permutation). For UI compatibility, we still return per-position feedback:
    - correct: letter at this position matches the same letter in the target (rare for anagram guess)
    - present: letter exists in target but at a different position (respecting counts)
    - absent: letter not present given remaining counts
    """

    # PUBLIC_INTERFACE
    def evaluate(self, target: str, guess: str) -> Dict[str, Any]:
        """Evaluate an anagram guess against the target."""
        target_n = target.strip().lower()
        guess_n = guess.strip().lower()
        if len(target_n) != len(guess_n):
            raise ValueError("Target and guess length must match for AnagramEngine.")

        # Per-position feedback using same rules to keep UI compatible
        feedback = _compute_letter_feedback(target_n, guess_n)

        # Correctness for anagram: must be a permutation (letter multiset equality)
        from collections import Counter

        is_correct = Counter(target_n) == Counter(guess_n)
        return {
            "feedback": feedback,
            "is_correct": is_correct,
            "metadata": {"engine": "anagram"},
        }
