from django.urls import path
from .views import (
    health,
    start_game,
    submit_guess,
    get_leaderboard,
    get_session_detail,
)

urlpatterns = [
    path('health/', health, name='Health'),
    path('start-game', start_game, name='start-game'),
    path('guess', submit_guess, name='guess'),
    path('leaderboard', get_leaderboard, name='leaderboard'),
    path('session/<int:session_id>', get_session_detail, name='session-detail'),
]
