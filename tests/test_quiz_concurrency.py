"""Eşzamanlı isteklere karşı oturum satırı kilidi (select_for_update).

SQLite satır kilidi vermez, bu yüzden testler yalnızca PostgreSQL'e karşı anlamlıdır.
"""

import threading

import pytest
from django.db import connection, connections
from rest_framework.test import APIClient

from apps.quiz.models import QuizSession, SessionQuestion

from .quiz_helpers import Game

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.usefixtures("clock"),
    pytest.mark.skipif(
        connection.vendor != "postgresql", reason="Satır kilitleri yalnızca PostgreSQL'de var"
    ),
]

THREADS = 8
ROUNDS = 5


def run_in_parallel(worker, count):
    """`worker(index)` fonksiyonunu aynı anda başlayan iş parçacıklarında çalıştırır."""
    barrier = threading.Barrier(count)
    results = [None] * count
    errors = []

    def target(index):
        try:
            barrier.wait()
            results[index] = worker(index)
        except Exception as exc:  # noqa: BLE001 - test hatası olarak ana iş parçacığına taşınır
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=target, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors, errors
    return results


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


def test_simultaneous_question_requests_serve_the_same_question_once(playable_category):
    game = Game(APIClient())

    bodies = run_in_parallel(lambda _index: Game.question(game).json(), THREADS)

    assert {body["question"]["id"] for body in bodies} == {bodies[0]["question"]["id"]}
    assert {body["position"] for body in bodies} == {0}
    assert (
        SessionQuestion.objects.filter(session_id=game.session_id, served_at__isnull=False).count()
        == 1
    )
