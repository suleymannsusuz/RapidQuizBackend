from django.urls import path

from .views import LeaderboardView, ScoreSubmitView

urlpatterns = [
    path("sessions/<uuid:session_id>/score/", ScoreSubmitView.as_view(), name="session-score"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
]
