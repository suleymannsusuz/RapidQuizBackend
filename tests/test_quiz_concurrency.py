"""Eşzamanlı isteklere karşı oturum satırı kilidi (select_for_update).

SQLite satır kilidi vermez, bu yüzden testler yalnızca PostgreSQL'e karşı anlamlıdır.
"""

import pytest
from django.core.cache import cache
from django.db import connection
from rest_framework.test import APIClient

from apps.quiz.models import QuizSession, SessionQuestion

from .quiz_helpers import Game, run_in_parallel

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.usefixtures("clock"),
    pytest.mark.skipif(
        connection.vendor != "postgresql", reason="Satır kilitleri yalnızca PostgreSQL'de var"
    ),
]

THREADS = 8
ROUNDS = 5


def test_simultaneous_identical_answers_score_exactly_once(playable_category):
    for _ in range(ROUNDS):
        game = Game(APIClient())
        question = game.question().json()["question"]["id"]
        choice = game.correct_choice(question)

        def answer(_index, game=game, question=question, choice=choice):
            return Game.answer(game, question, choice).status_code

        codes = run_in_parallel(answer, THREADS)

        assert sorted(codes) == [200] + [409] * (THREADS - 1), codes
        session = QuizSession.objects.get(pk=game.session_id)
        assert session.total_score == 150
        assert session.correct_count == 1
        assert session.current_index == 1


def test_simultaneous_answers_with_different_choices_close_the_question_once(playable_category):
    for _ in range(ROUNDS):
        game = Game(APIClient())
        question = game.question().json()["question"]["id"]
        choices = list(
            SessionQuestion.objects.get(session_id=game.session_id, position=0).choice_order
        )

        def answer(index, game=game, question=question, choices=choices):
            return Game.answer(game, question, choices[index % 4]).status_code

        codes = run_in_parallel(answer, THREADS)

        assert codes.count(200) == 1, codes
        assert codes.count(409) == THREADS - 1, codes
        row = SessionQuestion.objects.get(session_id=game.session_id, position=0)
        assert row.answered_at is not None
        assert QuizSession.objects.get(pk=game.session_id).current_index == 1


def test_simultaneous_score_submissions_create_exactly_one_entry(playable_category):
    from apps.leaderboard.models import ScoreEntry

    for round_number in range(ROUNDS):
        cache.clear()  # skor throttle'ı (saatte 20) bu testin konusu değil
        game = Game(APIClient())
        game.finish()

        def submit(index, game=game):
            return Game.submit_score(game, f"Oyuncu {index}").status_code

        codes = run_in_parallel(submit, THREADS)

        assert sorted(codes) == [201] + [409] * (THREADS - 1), codes
        assert ScoreEntry.objects.filter(session_id=game.session_id).count() == 1
        assert ScoreEntry.objects.count() == round_number + 1


def test_simultaneous_question_requests_serve_the_same_question_once(playable_category):
    game = Game(APIClient())

    bodies = run_in_parallel(lambda _index: Game.question(game).json(), THREADS)

    assert {body["question"]["id"] for body in bodies} == {bodies[0]["question"]["id"]}
    assert {body["position"] for body in bodies} == {0}
    assert (
        SessionQuestion.objects.filter(session_id=game.session_id, served_at__isnull=False).count()
        == 1
    )
