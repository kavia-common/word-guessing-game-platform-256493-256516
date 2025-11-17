from __future__ import annotations

from typing import List, Dict, Any

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status, permissions
from drf_yasg.utils import swagger_auto_schema

from .models import Word, GameSession, Guess
from .serializers import (
    StartGameRequestSerializer,
    StartGameResponseSerializer,
    GuessRequestSerializer,
    GuessResponseSerializer,
    SessionDetailResponseSerializer,
    LeaderboardEntrySerializer,
    compute_letter_feedback,
    feedback_to_compact,
)


def _session_status(session: GameSession) -> str:
    """Map DB flags to public status string."""
    if session.is_completed:
        return "WON" if session.is_won else "LOST"
    return "IN_PROGRESS"


def _attempts_used(session: GameSession) -> int:
    return session.guesses.count()


def _compute_score(session: GameSession) -> int:
    """Simple scoring: if won -> max_attempts - attempts_used + 1; if lost -> 0; if in-progress -> remaining attempts."""
    attempts_used = _attempts_used(session)
    if session.is_completed:
        if session.is_won:
            return max(session.max_attempts - attempts_used + 1, 1)
        return 0
    # In-progress: potential score proxy
    return max(session.max_attempts - attempts_used, 0)


# PUBLIC_INTERFACE
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def health(request):
    """Health check endpoint for the API.

    Returns:
    - 200 OK with {"message": "Server is up!"}
    """
    return Response({"message": "Server is up!"})


# PUBLIC_INTERFACE
@swagger_auto_schema(
    method="post",
    operation_id="start_game",
    operation_summary="Start a new game session",
    operation_description="""
Create a new game session selecting a random active word with the requested length.

Request body:
- word_length (int, optional, default 5): target word length
- max_attempts (int, optional, default 6)

Response:
- session_id, word_length, max_attempts, attempts_used, status
""",
    request_body=StartGameRequestSerializer,
    responses={200: StartGameResponseSerializer},
    tags=["game"],
)
@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def start_game(request):
    """Start a new game session.

    Parameters:
    - word_length: Optional integer specifying the length of the target word.
    - max_attempts: Optional integer specifying the number of allowed attempts.

    Returns:
    - JSON with session metadata including session_id and status.
    """
    serializer = StartGameRequestSerializer(data=request.data or {})
    serializer.is_valid(raise_exception=True)
    word_length = serializer.validated_data.get("word_length", 5)
    max_attempts = serializer.validated_data.get("max_attempts", 6)

    # Select a random active word of the given length
    target = Word.objects.filter(length=word_length, is_active=True).order_by("?").first()
    if not target:
        return Response(
            {"error": "No words available for requested length."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    session = GameSession.objects.create(target_word=target, max_attempts=max_attempts)

    resp = {
        "session_id": session.id,
        "word_length": target.length,
        "max_attempts": max_attempts,
        "attempts_used": 0,
        "status": _session_status(session),
    }
    return Response(StartGameResponseSerializer(resp).data, status=status.HTTP_200_OK)


# PUBLIC_INTERFACE
@swagger_auto_schema(
    method="post",
    operation_id="submit_guess",
    operation_summary="Submit a guess for a session",
    operation_description="""
Submit a guess against a given session. Validates session state and length,
computes per-letter feedback (correct/present/absent), updates attempts and status.

Request body:
- session_id (int, required)
- guess (string, required)

Response includes the feedback list, updated status, and score.
""",
    request_body=GuessRequestSerializer,
    responses={200: GuessResponseSerializer},
    tags=["game"],
)
@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def submit_guess(request):
    """Submit a guess for a specific session.

    Returns feedback for each letter and updates the session if won/lost.
    """
    serializer = GuessRequestSerializer(data=request.data or {})
    serializer.is_valid(raise_exception=True)

    session: GameSession = serializer.validated_data["session"]
    guess_text: str = serializer.validated_data["guess"]

    # Check attempts left
    attempts_used = _attempts_used(session)
    if attempts_used >= session.max_attempts:
        # Mark as lost if not already completed
        if not session.is_completed:
            session.mark_completed(False)
        return Response(
            {"error": "No attempts remaining.", "status": _session_status(session)},
            status=status.HTTP_409_CONFLICT,
        )

    target_text = session.target_word.text
    feedback = compute_letter_feedback(target_text, guess_text)
    compact = feedback_to_compact(feedback)
    is_correct = guess_text == target_text
    attempt_number = attempts_used + 1

    with transaction.atomic():
        Guess.objects.create(
            session=session,
            guess_word=guess_text,
            result=compact,
            attempt_number=attempt_number,
            is_correct=is_correct,
        )

        # Update session state if completed
        if is_correct:
            session.mark_completed(True)
        else:
            # If after this guess we exhausted attempts -> lost
            if attempt_number >= session.max_attempts:
                session.mark_completed(False)

    session.refresh_from_db()
    attempts_used = _attempts_used(session)
    resp = {
        "session_id": session.id,
        "attempt_number": attempt_number,
        "guess": guess_text,
        "feedback": feedback,
        "is_correct": is_correct,
        "attempts_used": attempts_used,
        "max_attempts": session.max_attempts,
        "status": _session_status(session),
        "score": _compute_score(session),
    }
    return Response(GuessResponseSerializer(resp).data, status=status.HTTP_200_OK)


# PUBLIC_INTERFACE
@swagger_auto_schema(
    method="get",
    operation_id="session_detail",
    operation_summary="Get session details",
    operation_description="""
Fetch the current status, attempts, and feedback for a session.

Path parameters:
- session_id (int): Session identifier.

Response:
- session metadata, list of guesses with feedback.
""",
    responses={200: SessionDetailResponseSerializer},
    tags=["game"],
)
@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def get_session_detail(request, session_id: int):
    """Retrieve a session by ID, including guess history."""
    try:
        session = GameSession.objects.select_related("target_word").get(pk=session_id)
    except GameSession.DoesNotExist:
        return Response({"error": "Session not found."}, status=status.HTTP_404_NOT_FOUND)

    guesses_qs = session.guesses.order_by("attempt_number").values(
        "attempt_number", "guess_word", "result", "is_correct", "created_at"
    )
    # Expand compact feedback
    mapping = {"g": "correct", "y": "present", "b": "absent"}
    guesses: List[Dict[str, Any]] = []
    for g in guesses_qs:
        feedback = [mapping.get(ch, "absent") for ch in (g["result"] or "")]
        guesses.append(
            {
                "attempt_number": g["attempt_number"],
                "guess": g["guess_word"],
                "feedback": feedback,
                "is_correct": g["is_correct"],
                "created_at": g["created_at"],
            }
        )

    resp = {
        "session_id": session.id,
        "word_length": session.target_word.length,
        "max_attempts": session.max_attempts,
        "attempts_used": _attempts_used(session),
        "status": _session_status(session),
        "guesses": guesses,
        "score": _compute_score(session),
    }
    return Response(SessionDetailResponseSerializer(resp).data, status=status.HTTP_200_OK)


# PUBLIC_INTERFACE
@swagger_auto_schema(
    method="get",
    operation_id="leaderboard",
    operation_summary="Get leaderboard of completed sessions",
    operation_description="""
Returns a simple leaderboard of completed sessions sorted by score (desc),
then by earliest completion.

Response fields:
- session_id, attempts_used, max_attempts, score, ended_at
""",
    responses={200: LeaderboardEntrySerializer(many=True)},
    tags=["game"],
)
@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def get_leaderboard(request):
    """Leaderboard based on completed sessions and simple scoring rules."""
    completed = GameSession.objects.filter(is_completed=True).select_related("target_word").order_by("-ended_at")

    # Build entries with computed score and attempts used
    entries: List[Dict[str, Any]] = []
    for s in completed:
        attempts_used = s.guesses.count()
        score = _compute_score(s)
        entries.append(
            {
                "session_id": s.id,
                "attempts_used": attempts_used,
                "max_attempts": s.max_attempts,
                "score": score,
                "ended_at": s.ended_at or timezone.now(),
            }
        )

    # Sort by score desc, then ended_at asc for more stable ordering
    entries.sort(key=lambda e: (-e["score"], e["ended_at"]))

    serializer = LeaderboardEntrySerializer(entries, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)
