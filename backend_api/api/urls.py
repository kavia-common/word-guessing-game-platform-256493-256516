from django.urls import path
from .views import (
    health,
    start_game,
    submit_guess,
    get_leaderboard,
    get_session_detail,
    request_hint,
    get_modes,
    get_puzzle_types,
    diagnostics_validate,
)

urlpatterns = [
    path('health/', health, name='Health'),
    path('start-game', start_game, name='start-game'),
    path('guess', submit_guess, name='guess'),
    path('hint', request_hint, name='request-hint'),
    path('leaderboard', get_leaderboard, name='leaderboard'),
    path('session/<int:session_id>', get_session_detail, name='session-detail'),
    path('modes', get_modes, name='get-modes'),
    path('puzzle-types', get_puzzle_types, name='get-puzzle-types'),
    path('diagnostics/validate', diagnostics_validate, name='diagnostics-validate'),
]
