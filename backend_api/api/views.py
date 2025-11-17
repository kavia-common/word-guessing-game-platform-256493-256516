from __future__ import annotations

from typing import List, Dict, Any, Tuple

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status, permissions
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .models import Word, GameSession, Guess
from .serializers import (
    StartGameRequestSerializer,
    StartGameResponseSerializer,
    GuessRequestSerializer,
    GuessResponseSerializer,
    SessionDetailResponseSerializer,
    LeaderboardEntrySerializer,
    HintRequestSerializer,
    HintResponseSerializer,
    feedback_to_compact,
)
from api.puzzles import get_engine, reveal_position, reveal_first_letter


def _normalize_keys(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Accept common camelCase keys from frontend and convert to snake_case expected by serializers.
    This is defensive compatibility; frontend should be updated to send snake_case.

    Supported conversions:
      sessionId -> session_id
      wordLength -> word_length
      maxAttempts -> max_attempts
      timeLimitSecs -> time_limit_secs
      puzzleType -> puzzle_type
      playerName -> player_name
      attemptNumber -> attempt_number
    """
    if not isinstance(payload, dict):
        return payload

    mapping = {
        "sessionId": "session_id",
        "wordLength": "word_length",
        "maxAttempts": "max_attempts",
        "timeLimitSecs": "time_limit_secs",
        "puzzleType": "puzzle_type",
        "playerName": "player_name",
        "attemptNumber": "attempt_number",
    }
    out = dict(payload)
    for k, v in list(payload.items()):
        if k in mapping and mapping[k] not in out:
            out[mapping[k]] = v
    return out


def _session_status(session: GameSession) -> str:
    """Map DB flags to public status string."""
    if session.is_completed:
        return "WON" if session.is_won else "LOST"
    return "IN_PROGRESS"


def _attempts_used(session: GameSession) -> int:
    return session.guesses.count()


def _compute_base_score(session: GameSession) -> int:
    """Base scoring before adjustments."""
    attempts_used = _attempts_used(session)
    if session.is_completed:
        if session.is_won:
            return max(session.max_attempts - attempts_used + 1, 1)
        return 0
    # In-progress: potential score proxy
    return max(session.max_attempts - attempts_used, 0)


def _compute_time_bonus(session: GameSession) -> int:
    """Compute a simple time bonus for timed mode."""
    if session.mode != "timed":
        return 0
    if session.time_limit_secs is None or session.total_time_secs is None:
        return 0
    remaining = max(session.time_limit_secs - session.total_time_secs, 0)
    # Simple scaling: 1 point per 10 seconds remaining
    return remaining // 10


def _compute_hint_penalty(session: GameSession) -> int:
    """Compute a penalty based on hints used."""
    return session.hints_used * 1  # 1 point penalty per hint


def _compute_score_breakdown(session: GameSession) -> Tuple[int, int, int, int]:
    """Return (score, base, hint_penalty, time_bonus)."""
    base = _compute_base_score(session)
    time_bonus = _compute_time_bonus(session)
    hint_penalty = _compute_hint_penalty(session)
    score = max(base + time_bonus - hint_penalty, 0)
    return score, base, hint_penalty, time_bonus


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
- mode (optional, default 'classic')
- puzzle_type (optional, default 'classic')
- difficulty (optional, default 1)
- time_limit_secs (optional, for timed mode)
- player_name (optional)

Response:
- session_id, word_length, max_attempts, attempts_used, status
- mode, puzzle_type, difficulty, time_limit_secs, hints_used, total_time_secs
""",
    request_body=StartGameRequestSerializer,
    responses={200: StartGameResponseSerializer},
    tags=["game"],
)
@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def start_game(request):
    """Start a new game session with mode and puzzle type support.

    Parameters:
    - word_length: Optional integer specifying the length of the target word.
    - max_attempts: Optional integer specifying the number of allowed attempts.
    - mode: Optional gameplay mode (classic default).
    - puzzle_type: Optional engine type (classic default).
    - difficulty: Optional difficulty level.
    - time_limit_secs: Optional time limit for timed mode.

    Returns:
    - JSON with session metadata including session_id and status.
    """
    data_in = _normalize_keys(request.data or {})
    serializer = StartGameRequestSerializer(data=data_in)
    serializer.is_valid(raise_exception=True)
    vd = serializer.validated_data

    word_length = vd.get("word_length", 5)
    max_attempts = vd.get("max_attempts", 6)
    mode = vd.get("mode", "classic") or "classic"
    # Backward compatibility: default puzzle_type to "classic" (though model default is "word")
    puzzle_type = vd.get("puzzle_type", "classic") or "classic"
    difficulty = vd.get("difficulty", 1)
    time_limit_secs = vd.get("time_limit_secs")
    player_name = vd.get("player_name")

    # Select a random active word of the given length
    target = Word.objects.filter(length=word_length, is_active=True).order_by("?").first()
    if not target:
        return Response(
            {"error": "No words available for requested length."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Basic adaptive hook (placeholder): adjust max_attempts by difficulty
    # e.g., higher difficulty lowers attempts slightly (min 1)
    adjusted_max_attempts = max(1, min(10, max_attempts - max(0, difficulty - 1) // 3))

    session = GameSession.objects.create(
        target_word=target,
        max_attempts=adjusted_max_attempts,
        mode=mode or "classic",
        puzzle_type=puzzle_type or "classic",
        difficulty=difficulty,
        time_limit_secs=time_limit_secs if mode == "timed" else None,
        player_name=player_name,
    )

    resp = {
        "session_id": session.id,
        "word_length": target.length,
        "max_attempts": session.max_attempts,
        "attempts_used": 0,
        "status": _session_status(session),
        "mode": session.mode,
        "puzzle_type": session.puzzle_type,
        "difficulty": session.difficulty,
        "time_limit_secs": session.time_limit_secs,
        "hints_used": session.hints_used,
        "total_time_secs": session.total_time_secs,
    }
    return Response(StartGameResponseSerializer(resp).data, status=status.HTTP_200_OK)


# PUBLIC_INTERFACE
@swagger_auto_schema(
    method="post",
    operation_id="submit_guess",
    operation_summary="Submit a guess for a session",
    operation_description="""
Submit a guess against a given session. Validates session state and length,
routes evaluation via the selected puzzle engine, updates attempts and status.

Request body:
- session_id (int, required)
- guess (string, required)

Response includes the feedback list, updated status, and score with breakdown.
""",
    request_body=GuessRequestSerializer,
    responses={200: GuessResponseSerializer},
    tags=["game"],
)
@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def submit_guess(request):
    """Submit a guess for a specific session, evaluated by engine registry.

    Returns feedback for each letter and updates the session if won/lost.
    """
    data_in = _normalize_keys(request.data or {})
    serializer = GuessRequestSerializer(data=data_in)
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

    # Route via engine registry
    engine_cls = get_engine(session.puzzle_type or "classic")
    engine = engine_cls()
    try:
        eval_result = engine.evaluate(target_text, guess_text)
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    feedback = eval_result.get("feedback", [])
    compact = feedback_to_compact(feedback)
    is_correct = bool(eval_result.get("is_correct"))
    attempt_number = attempts_used + 1

    with transaction.atomic():
        Guess.objects.create(
            session=session,
            guess_word=guess_text,
            result=compact,
            attempt_number=attempt_number,
            is_correct=is_correct,
            metadata=eval_result.get("metadata") or {},
        )

        # Update session state if completed
        if is_correct:
            # Calculate total time if timed
            if session.mode == "timed" and session.total_time_secs is None:
                # naive calc: difference from started_at to now
                session.total_time_secs = int((timezone.now() - session.started_at).total_seconds())
            session.mark_completed(True)
        else:
            # If after this guess we exhausted attempts -> lost
            if attempt_number >= session.max_attempts:
                if session.mode == "timed" and session.total_time_secs is None:
                    session.total_time_secs = int((timezone.now() - session.started_at).total_seconds())
                session.mark_completed(False)

    session.refresh_from_db()
    attempts_used = _attempts_used(session)
    score, base, hint_penalty, time_bonus = _compute_score_breakdown(session)
    resp = {
        "session_id": session.id,
        "attempt_number": attempt_number,
        "guess": guess_text,
        "feedback": feedback,
        "is_correct": is_correct,
        "attempts_used": attempts_used,
        "max_attempts": session.max_attempts,
        "status": _session_status(session),
        "score": score,
        "base_score": base,
        "hint_penalty": hint_penalty,
        "time_bonus": time_bonus,
    }
    return Response(GuessResponseSerializer(resp).data, status=status.HTTP_200_OK)


# PUBLIC_INTERFACE
@swagger_auto_schema(
    method="post",
    operation_id="request_hint",
    operation_summary="Request a hint for a session",
    operation_description="""
Request a hint for the provided session. Enforces per-session hint limits.

Request body:
- session_id (int, required)
- type (string, optional: reveal_position | reveal_first_letter; default reveal_position)

Response:
- type (hint type), data payload with 'index', 'letter', and 'remaining' hints.
""",
    request_body=HintRequestSerializer,
    responses={200: HintResponseSerializer},
    tags=["game", "hints"],
)
@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def request_hint(request):
    """Provide a hint for the given session, enforcing session-level limits."""
    data_in = _normalize_keys(request.data or {})
    serializer = HintRequestSerializer(data=data_in)
    serializer.is_valid(raise_exception=True)
    session: GameSession = serializer.validated_data["session"]
    hint_type: str = serializer.validated_data.get("type") or "reveal_position"

    try:
        if hint_type == "reveal_first_letter":
            payload = reveal_first_letter(session)
        else:
            payload = reveal_position(session)
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    resp = {
        "session_id": session.id,
        "type": payload.get("type"),
        "data": payload.get("data"),
    }
    return Response(HintResponseSerializer(resp).data, status=status.HTTP_200_OK)


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

    score, _, _, _ = _compute_score_breakdown(session)
    resp = {
        "session_id": session.id,
        "word_length": session.target_word.length,
        "max_attempts": session.max_attempts,
        "attempts_used": _attempts_used(session),
        "status": _session_status(session),
        "guesses": guesses,
        "score": score,
        "mode": session.mode,
        "puzzle_type": session.puzzle_type,
        "difficulty": session.difficulty,
        "time_limit_secs": session.time_limit_secs,
        "hints_used": session.hints_used,
        "total_time_secs": session.total_time_secs,
    }
    return Response(SessionDetailResponseSerializer(resp).data, status=status.HTTP_200_OK)


# PUBLIC_INTERFACE
@swagger_auto_schema(
    method="get",
    operation_id="leaderboard",
    operation_summary="Get leaderboard of completed sessions",
    operation_description="""
Returns a leaderboard of completed sessions with optional filters:

Query params:
- mode (optional): classic | timed | daily | endless
- puzzle_type (optional): classic | anagram

Sorted by score (desc), then earliest completion.

Response fields:
- session_id, attempts_used, max_attempts, score, ended_at
- mode, puzzle_type, difficulty, time_limit_secs, hints_used, total_time_secs
""",
    manual_parameters=[
        openapi.Parameter("mode", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=False),
        openapi.Parameter("puzzle_type", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=False),
    ],
    responses={200: LeaderboardEntrySerializer(many=True)},
    tags=["game"],
)
@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def get_leaderboard(request):
    """Leaderboard based on completed sessions with filters for mode and puzzle_type."""
    qs = GameSession.objects.filter(is_completed=True).select_related("target_word")
    mode = (request.GET.get("mode") or "").strip().lower()
    puzzle_type = (request.GET.get("puzzle_type") or "").strip().lower()
    if mode:
        qs = qs.filter(mode=mode)
    if puzzle_type:
        qs = qs.filter(puzzle_type=puzzle_type)

    # Build entries with computed score and attempts used
    entries: List[Dict[str, Any]] = []
    for s in qs:
        attempts_used = s.guesses.count()
        score, _, _, _ = _compute_score_breakdown(s)
        entries.append(
            {
                "session_id": s.id,
                "attempts_used": attempts_used,
                "max_attempts": s.max_attempts,
                "score": score,
                "ended_at": s.ended_at or timezone.now(),
                "mode": s.mode,
                "puzzle_type": s.puzzle_type,
                "difficulty": s.difficulty,
                "time_limit_secs": s.time_limit_secs,
                "hints_used": s.hints_used,
                "total_time_secs": s.total_time_secs,
            }
        )

    # Sort by score desc, then ended_at asc for more stable ordering
    entries.sort(key=lambda e: (-e["score"], e["ended_at"]))

    serializer = LeaderboardEntrySerializer(entries, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


# PUBLIC_INTERFACE
@swagger_auto_schema(
    method="get",
    operation_id="get_modes",
    operation_summary="List available modes",
    operation_description="Returns supported modes.",
    tags=["meta"],
    responses={200: openapi.Response("OK", schema=openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(type=openapi.TYPE_STRING)))},
)
@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def get_modes(request):
    """List available gameplay modes."""
    return Response(["classic", "timed", "daily", "endless"], status=status.HTTP_200_OK)


# PUBLIC_INTERFACE
@swagger_auto_schema(
    method="get",
    operation_id="get_puzzle_types",
    operation_summary="List available puzzle types",
    operation_description="Returns supported puzzle types.",
    tags=["meta"],
    responses={200: openapi.Response("OK", schema=openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(type=openapi.TYPE_STRING)))},
)
@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def get_puzzle_types(request):
    """List available puzzle engine types."""
    return Response(["classic", "anagram"], status=status.HTTP_200_OK)


# PUBLIC_INTERFACE
@swagger_auto_schema(
    method="post",
    operation_id="diagnostics_validate",
    operation_summary="Diagnostics: validate payloads",
    operation_description="""
Validate payloads against serializers to diagnose 400 errors.

Request body:
- endpoint (string): one of start-game | guess | hint
- payload (object): payload to validate (camelCase or snake_case accepted)

Response:
- valid (bool)
- errors (object|null)
- normalized_payload (object)
""",
    tags=["diagnostics"],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "endpoint": openapi.Schema(type=openapi.TYPE_STRING),
            "payload": openapi.Schema(type=openapi.TYPE_OBJECT),
        },
        required=["endpoint", "payload"],
    ),
    responses={200: openapi.Response("OK")},
)
@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def diagnostics_validate(request):
    """
    Diagnostics endpoint to validate a payload against known serializers and
    return detailed validation errors. Helps identify snake_case vs camelCase
    mismatches and enum/range violations without performing any DB writes.
    """
    body = request.data or {}
    endpoint = (body.get("endpoint") or "").strip()
    payload = body.get("payload") or {}
    normalized = _normalize_keys(payload)

    serializer_map = {
        "start-game": StartGameRequestSerializer,
        "guess": GuessRequestSerializer,
        "hint": HintRequestSerializer,
        # allow alternate names
        "start_game": StartGameRequestSerializer,
        "request_hint": HintRequestSerializer,
        "submit_guess": GuessRequestSerializer,
    }
    s_cls = serializer_map.get(endpoint)
    if not s_cls:
        return Response(
            {"valid": False, "errors": {"endpoint": "Unknown endpoint."}, "normalized_payload": normalized},
            status=status.HTTP_400_BAD_REQUEST,
        )

    s = s_cls(data=normalized)
    ok = s.is_valid()
    return Response(
        {
            "valid": ok,
            "errors": None if ok else s.errors,
            "normalized_payload": normalized,
        },
        status=status.HTTP_200_OK,
    )
