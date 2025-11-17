from __future__ import annotations

from typing import List, Literal, Dict, Any

from rest_framework import serializers

from .models import GameSession, Word


LetterFeedback = Literal["correct", "present", "absent"]


def _normalize_word(value: str) -> str:
    """Normalize incoming word inputs."""
    return (value or "").strip().lower()


def _validate_guess_word(value: str) -> str:
    """Ensure guess word is alphabetic lowercase and non-empty."""
    value = _normalize_word(value)
    if not value or not value.isalpha():
        raise serializers.ValidationError("Guess must be a non-empty alphabetic string.")
    return value


def compute_letter_feedback(target: str, guess: str) -> List[LetterFeedback]:
    """Compute per-letter feedback similar to Wordle rules.

    - correct: correct letter in correct position
    - present: letter exists in target but different position (respect counts)
    - absent: letter not in target or already satisfied by count
    """
    t = list(target)
    g = list(guess)
    n = len(t)
    result: List[LetterFeedback] = ["absent"] * n

    # First pass: mark corrects and reduce available pool
    remaining_counts: Dict[str, int] = {}
    for i in range(n):
        if g[i] == t[i]:
            result[i] = "correct"
        else:
            remaining_counts[t[i]] = remaining_counts.get(t[i], 0) + 1

    # Second pass: present where applicable
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


def feedback_to_compact(feedback: List[LetterFeedback]) -> str:
    """Compact representation to store in DB (g=correct,y=present,b=absent)."""
    mapping = {"correct": "g", "present": "y", "absent": "b"}
    return "".join(mapping[x] for x in feedback)


# PUBLIC_INTERFACE
class StartGameRequestSerializer(serializers.Serializer):
    """Request payload to start a new game session.

    Fields:
    - word_length (optional, default 5): desired target word length
    - max_attempts (optional, default 6): allowed attempts
    """

    word_length = serializers.IntegerField(required=False, min_value=3, max_value=10, default=5)
    max_attempts = serializers.IntegerField(required=False, min_value=1, max_value=10, default=6)

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        length = attrs.get("word_length", 5)
        if not Word.objects.filter(length=length, is_active=True).exists():
            raise serializers.ValidationError(f"No active words of length {length} available.")
        return attrs


# PUBLIC_INTERFACE
class StartGameResponseSerializer(serializers.Serializer):
    """Response payload for starting a new game."""

    session_id = serializers.IntegerField()
    word_length = serializers.IntegerField()
    max_attempts = serializers.IntegerField()
    attempts_used = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["IN_PROGRESS", "WON", "LOST"])


# PUBLIC_INTERFACE
class GuessRequestSerializer(serializers.Serializer):
    """Request payload to submit a guess for a session."""

    session_id = serializers.IntegerField()
    guess = serializers.CharField()

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        # Validate guess content
        guess = _validate_guess_word(attrs["guess"])
        attrs["guess"] = guess

        # Validate session existence
        try:
            session = GameSession.objects.select_related("target_word").get(pk=attrs["session_id"])
        except GameSession.DoesNotExist:
            raise serializers.ValidationError({"session_id": "Session not found."})

        if session.is_completed:
            raise serializers.ValidationError("Session already completed.")

        if len(guess) != session.target_word.length:
            raise serializers.ValidationError(
                f"Guess length must be {session.target_word.length} characters."
            )

        # Optional: validate guess exists in dictionary (same length); relax if not desired
        if not Word.objects.filter(text=guess, length=session.target_word.length).exists():
            # Allow non-dictionary guesses by commenting out the error below.
            raise serializers.ValidationError("Guess word is not in the allowed dictionary.")

        attrs["session"] = session
        return attrs


# PUBLIC_INTERFACE
class GuessResponseSerializer(serializers.Serializer):
    """Response payload after submitting a guess."""

    session_id = serializers.IntegerField()
    attempt_number = serializers.IntegerField()
    guess = serializers.CharField()
    feedback = serializers.ListField(child=serializers.ChoiceField(choices=["correct", "present", "absent"]))
    is_correct = serializers.BooleanField()
    attempts_used = serializers.IntegerField()
    max_attempts = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["IN_PROGRESS", "WON", "LOST"])
    score = serializers.IntegerField()


# PUBLIC_INTERFACE
class SessionDetailResponseSerializer(serializers.Serializer):
    """Response payload for retrieving session details."""

    session_id = serializers.IntegerField()
    word_length = serializers.IntegerField()
    max_attempts = serializers.IntegerField()
    attempts_used = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["IN_PROGRESS", "WON", "LOST"])
    guesses = serializers.ListField(
        child=serializers.DictField(), help_text="List of guesses with feedback."
    )
    # score can be computed if completed or ongoing (based on attempts remaining)
    score = serializers.IntegerField()


# PUBLIC_INTERFACE
class LeaderboardEntrySerializer(serializers.Serializer):
    """Leaderboard entry."""

    session_id = serializers.IntegerField()
    attempts_used = serializers.IntegerField()
    max_attempts = serializers.IntegerField()
    score = serializers.IntegerField()
    ended_at = serializers.DateTimeField()
