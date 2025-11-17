from __future__ import annotations

from django.db import models
from django.utils import timezone


# PUBLIC_INTERFACE
class TimeStampedModel(models.Model):
    """Abstract base model providing created/updated timestamps.

    Notes:
        Keep this abstract model free of any logic that would access the Django
        app registry or execute queries at module import time. Only field
        declarations and Meta options are allowed here so that importing this
        module does not trigger AppRegistryNotReady during Django startup.
    """
    created_at = models.DateTimeField(auto_now_add=True, help_text="Time when the record was created.")
    updated_at = models.DateTimeField(auto_now=True, help_text="Time when the record was last updated.")

    class Meta:
        abstract = True


# PUBLIC_INTERFACE
# Note: Do not perform any queries or app lookups at module scope. Model fields
# and Meta are safe; any dynamic logic should live in methods or AppConfig.ready().
class Word(TimeStampedModel):
    """A valid word that can be used as the target (answer) or a valid guess.

    Fields:
    - text: unique lowercased word text
    - length: derived length for quick filtering
    - is_active: whether this word can be selected as an answer
    """
    text = models.CharField(max_length=32, unique=True, db_index=True, help_text="Lowercase word text.")
    length = models.PositiveSmallIntegerField(db_index=True, help_text="Length of the word.")
    is_active = models.BooleanField(default=True, help_text="If true, can be used as an answer in new games.")

    class Meta:
        ordering = ["length", "text"]
        verbose_name = "Word"
        verbose_name_plural = "Words"

    def save(self, *args, **kwargs):
        # Normalize text, derive length on save
        if self.text:
            self.text = self.text.strip().lower()
            self.length = len(self.text)
        super().save(*args, **kwargs)

    def __str__(self) -> str:  # pragma: no cover
        return self.text


# PUBLIC_INTERFACE
# Avoid referencing other apps' models or executing queries at import-time here.
class GameSession(TimeStampedModel):
    """Represents a single play session.

    Fields:
    - target_word: the word to be guessed
    - max_attempts: maximum number of allowed guesses
    - is_completed: whether the game ended (win or loss)
    - is_won: whether player guessed correctly
    - started_at: timestamp when session started
    - ended_at: timestamp when session ended (if completed)
    - mode: gameplay mode identifier (e.g., classic, timed, daily)
    - puzzle_type: type of puzzle (e.g., word, number)
    - hints_used: number of hints consumed in this session
    - difficulty: difficulty level (1..n) for adaptive difficulty
    - time_limit_secs: optional per-session time limit in seconds
    - total_time_secs: optional total elapsed time for the session in seconds
    - player_name: optional display name for the player
    """
    MODE_CHOICES = (
        ("classic", "Classic"),
        ("timed", "Timed"),
        ("daily", "Daily"),
        ("endless", "Endless"),
    )

    target_word = models.ForeignKey(Word, on_delete=models.PROTECT, related_name="target_for_sessions")
    max_attempts = models.PositiveSmallIntegerField(default=6, help_text="Max number of guesses allowed.")
    is_completed = models.BooleanField(default=False)
    is_won = models.BooleanField(default=False)
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    # New gameplay fields (backward-compatible defaults)
    mode = models.CharField(
        max_length=16,
        choices=MODE_CHOICES,
        default="classic",
        help_text="Gameplay mode identifier.",
    )
    puzzle_type = models.CharField(
        max_length=32,
        default="word",
        help_text="Type of puzzle for this session (e.g., word, number).",
    )
    hints_used = models.IntegerField(default=0, help_text="Number of hints used in this session.")
    difficulty = models.PositiveSmallIntegerField(default=1, help_text="Difficulty level (1 = easiest).")
    time_limit_secs = models.PositiveIntegerField(null=True, blank=True, help_text="Optional time limit in seconds.")
    total_time_secs = models.PositiveIntegerField(null=True, blank=True, help_text="Optional total time spent in seconds.")
    player_name = models.CharField(max_length=64, null=True, blank=True, help_text="Optional player display name.")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Game Session"
        verbose_name_plural = "Game Sessions"

    def mark_completed(self, won: bool) -> None:
        """Mark the session completed and set win state."""
        self.is_completed = True
        self.is_won = won
        self.ended_at = timezone.now()
        self.save(update_fields=["is_completed", "is_won", "ended_at", "updated_at"])

    def __str__(self) -> str:  # pragma: no cover
        return f"Session #{self.pk} - target: {self.target_word.text}"


# PUBLIC_INTERFACE
# Keep module-scope free of DB interactions; logic belongs in methods.
class Guess(TimeStampedModel):
    """A single guess made during a game session.

    Fields:
    - session: foreign key to GameSession
    - guess_word: the guessed word text (normalized to lowercase)
    - result: feedback pattern (e.g., 'g'/'y'/'b' like Wordle) or JSON; keep simple for now
    - attempt_number: 1-based index of the guess within the session
    - is_correct: whether guess equals the target
    - metadata: optional JSON metadata about the guess (e.g., hint usage, timing)
    """
    session = models.ForeignKey(GameSession, on_delete=models.CASCADE, related_name="guesses")
    guess_word = models.CharField(max_length=32, help_text="Lowercase guess text.")
    result = models.CharField(max_length=64, blank=True, default="", help_text="Feedback pattern for the guess.")
    attempt_number = models.PositiveSmallIntegerField(help_text="1-based attempt number within the session.")
    is_correct = models.BooleanField(default=False)
    # Optional metadata for extensibility
    metadata = models.JSONField(null=True, blank=True, help_text="Optional JSON metadata for the guess.")

    class Meta:
        ordering = ["created_at"]
        unique_together = (("session", "attempt_number"),)
        verbose_name = "Guess"
        verbose_name_plural = "Guesses"

    def save(self, *args, **kwargs):
        if self.guess_word:
            self.guess_word = self.guess_word.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self) -> str:  # pragma: no cover
        return f"Guess {self.attempt_number} in session {self.session_id}: {self.guess_word}"
