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
    - mode (optional, default 'classic'): gameplay mode, e.g., classic, timed, daily, endless
    - puzzle_type (optional, default 'classic'): engine type, e.g., classic, anagram
    - difficulty (optional, default 1): adaptive difficulty level
    - time_limit_secs (optional for timed mode)
    - player_name (optional)
    """

    word_length = serializers.IntegerField(required=False, min_value=3, max_value=10, default=5)
    max_attempts = serializers.IntegerField(required=False, min_value=1, max_value=10, default=6)
    mode = serializers.ChoiceField(
        required=False,
        choices=[("classic", "classic"), ("timed", "timed"), ("daily", "daily"), ("endless", "endless")],
        default="classic",
    )
    puzzle_type = serializers.ChoiceField(
        required=False,
        choices=[("classic", "classic"), ("anagram", "anagram")],
        default="classic",
    )
    difficulty = serializers.IntegerField(required=False, min_value=1, max_value=10, default=1)
    time_limit_secs = serializers.IntegerField(required=False, min_value=5, allow_null=True)
    player_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=64)

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        length = attrs.get("word_length", 5)
        if not Word.objects.filter(length=length, is_active=True).exists():
            raise serializers.ValidationError(f"No active words of length {length} available.")
        # Basic mode/puzzle_type compatibility checks
        mode = attrs.get("mode") or "classic"
        if mode == "timed" and not attrs.get("time_limit_secs"):
            # Provide a sensible default if omitted
            attrs["time_limit_secs"] = 60
        return attrs


# PUBLIC_INTERFACE
class StartGameResponseSerializer(serializers.Serializer):
    """Response payload for starting a new game."""

    session_id = serializers.IntegerField()
    word_length = serializers.IntegerField()
    max_attempts = serializers.IntegerField()
    attempts_used = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["IN_PROGRESS", "WON", "LOST"])
    # Extended gameplay fields
    mode = serializers.CharField()
    puzzle_type = serializers.CharField()
    difficulty = serializers.IntegerField()
    time_limit_secs = serializers.IntegerField(allow_null=True)
    hints_used = serializers.IntegerField()
    total_time_secs = serializers.IntegerField(allow_null=True)


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
    # Extended score breakdown
    base_score = serializers.IntegerField()
    hint_penalty = serializers.IntegerField()
    time_bonus = serializers.IntegerField()


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
    # Extended gameplay fields
    mode = serializers.CharField()
    puzzle_type = serializers.CharField()
    difficulty = serializers.IntegerField()
    time_limit_secs = serializers.IntegerField(allow_null=True)
    hints_used = serializers.IntegerField()
    total_time_secs = serializers.IntegerField(allow_null=True)


# PUBLIC_INTERFACE
class LeaderboardEntrySerializer(serializers.Serializer):
    """Leaderboard entry."""

    session_id = serializers.IntegerField()
    attempts_used = serializers.IntegerField()
    max_attempts = serializers.IntegerField()
    score = serializers.IntegerField()
    ended_at = serializers.DateTimeField()
    # Extended gameplay fields
    mode = serializers.CharField()
    puzzle_type = serializers.CharField()
    difficulty = serializers.IntegerField()
    time_limit_secs = serializers.IntegerField(allow_null=True)
    hints_used = serializers.IntegerField()
    total_time_secs = serializers.IntegerField(allow_null=True)


# PUBLIC_INTERFACE
class HintRequestSerializer(serializers.Serializer):
    """Request payload for a hint.

    Fields:
    - session_id: game session identifier
    - type: optional hint type (reveal_position | reveal_first_letter). If omitted, defaults to reveal_position.
    """

    session_id = serializers.IntegerField()
    type = serializers.ChoiceField(
        required=False,
        choices=[("reveal_position", "reveal_position"), ("reveal_first_letter", "reveal_first_letter")],
        default="reveal_position",
    )

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        try:
            session = GameSession.objects.select_related("target_word").get(pk=attrs["session_id"])
        except GameSession.DoesNotExist:
            raise serializers.ValidationError({"session_id": "Session not found."})

        if session.is_completed:
            raise serializers.ValidationError("Session already completed.")

        attrs["session"] = session
        return attrs


# PUBLIC_INTERFACE
class HintResponseSerializer(serializers.Serializer):
    """Response payload for a hint request."""

    session_id = serializers.IntegerField()
    type = serializers.CharField()
    data = serializers.DictField(help_text="Hint data payload with index/letter and remaining hints.")
