"""Skor şişirme önlemi: insan için imkânsız derecede hızlı oynanan skorlar kaydedilmez."""

import logging

import pytest

from apps.leaderboard.models import ScoreEntry
from apps.quiz.models import QuizSession

from .quiz_helpers import Game

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("clock")]


@pytest.fixture(autouse=True)
def speed_guard(settings):
    """conftest'teki kapalı varsayılanı ezer: bu dosyada önlem üretimdeki değerindedir."""
    settings.SCORE_MIN_AVG_RESPONSE_MS = 500


def play(game, clock, delay_ms, *, timeout=False):
    """20 soruyu, her birini sunulduktan `delay_ms` sonra cevaplayarak oynar."""
    for _ in range(20):
        question_id = game.question().json()["question"]["id"]
        clock.shift(delay_ms / 1000)
        choice = None if timeout else game.correct_choice(question_id)
        game.answer(question_id, choice)


def test_instant_game_is_rejected_and_not_written_to_the_leaderboard(
    api_client, playable_category, clock
):
    game = Game(api_client)
    play(game, clock, 0)  # mükemmel puan, 0 ms: tipik bot

    response = game.submit_score("Bot")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "score_rejected"
    assert "fazla hızlıydı" in error["message"]
    assert ScoreEntry.objects.count() == 0
    assert QuizSession.objects.get(pk=game.session_id).status == QuizSession.Status.FINISHED
    assert api_client.get("/api/v1/leaderboard/?category=yazilim").json()["leaderboard"] == []


def test_a_rejected_session_stays_rejected_on_retry(api_client, playable_category, clock):
    game = Game(api_client)
    play(game, clock, 100)

    codes = [game.submit_score(f"Bot{index}").status_code for index in range(3)]

    assert codes == [422, 422, 422]
    assert ScoreEntry.objects.count() == 0


def test_realistic_pace_is_accepted(api_client, playable_category, clock):
    game = Game(api_client)
    play(game, clock, 1000)

    response = game.submit_score("Ayşe")

    assert response.status_code == 201
    assert ScoreEntry.objects.get().total_response_ms == 20_000


def test_threshold_is_the_average_per_question(api_client, playable_category, clock):
    # 499 ms ortalama reddedilir, 500 ms kabul edilir (eşik dahil)
    slow_enough = Game(api_client)
    play(slow_enough, clock, 500)
    assert slow_enough.submit_score("Sınırda").status_code == 201

    too_fast = Game(api_client)
    play(too_fast, clock, 499)
    assert too_fast.submit_score("Biraz Hızlı").status_code == 422


def test_timeouts_count_as_full_time_so_they_are_never_suspicious(
    api_client, playable_category, clock
):
    game = Game(api_client)
    play(game, clock, 5000, timeout=True)  # hepsi süre aşımı: 0 puan, 100 sn

    response = game.submit_score("Çok Yavaş")

    assert response.status_code == 201
    assert response.json()["score"] == 0


def test_threshold_follows_the_setting(api_client, playable_category, clock, settings):
    settings.SCORE_MIN_AVG_RESPONSE_MS = 2000
    game = Game(api_client)
    play(game, clock, 1000)
    assert game.submit_score("Yavaş Değil").status_code == 422


def test_setting_zero_disables_the_guard(api_client, playable_category, clock, settings):
    settings.SCORE_MIN_AVG_RESPONSE_MS = 0
    game = Game(api_client)
    play(game, clock, 0)

    assert game.submit_score("Hızlı").status_code == 201


def test_rejection_is_logged_for_monitoring_without_raw_ip(
    api_client, playable_category, clock, caplog
):
    game = Game(api_client)
    play(game, clock, 50)

    with caplog.at_level(logging.WARNING, logger="apps.leaderboard.services"):
        game.submit_score("Bot")

    messages = [record.getMessage() for record in caplog.records]
    assert any("Şüpheli skor reddedildi" in message for message in messages)
    assert any(f"oturum={game.session_id}" in message for message in messages)
    assert any("ortalama=50 ms/soru" in message for message in messages)
    assert not any("127.0.0.1" in message for message in messages)


def test_invalid_name_is_still_reported_before_the_speed_check(
    api_client, playable_category, clock
):
    game = Game(api_client)
    play(game, clock, 0)

    response = game.submit_score("<b>")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
