from django.urls import path

from .views import AnswerView, QuestionView, ResultView, SessionCreateView

urlpatterns = [
    path("sessions/", SessionCreateView.as_view(), name="session-create"),
    path("sessions/<uuid:session_id>/question/", QuestionView.as_view(), name="session-question"),
    path("sessions/<uuid:session_id>/answer/", AnswerView.as_view(), name="session-answer"),
    path("sessions/<uuid:session_id>/result/", ResultView.as_view(), name="session-result"),
]
