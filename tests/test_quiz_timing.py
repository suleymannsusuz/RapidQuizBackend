import pytest

from apps.quiz.models import QuizSession, SessionQuestion

from .quiz_helpers import Game

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("clock")]


def answer_after(game, clock, delay_ms, *, correct=True):
    """Soruyu getirir, `delay_ms` bekler ve cevaplar; (soru kimliği, yanıt) döner."""
    qid = game.question().json()["question"]["id"]
    clock.shift(delay_ms / 1000)
    choice = game.correct_choice(qid) if correct else game.wrong_choice(qid)
    return qid, game.answer(qid, choice)


@pytest.mark.parametrize(
    ("delay_ms", "expected_points"),
    [(0, 150), (1000, 140), (2000, 130), (4999, 100), (5000, 100)],
)
def test_answers_within_five_seconds_get_base_plus_speed_bonus(
    api_client, playable_category, clock, delay_ms, expected_points
):
    game = Game(api_client)
    _, response = answer_after(game, clock, delay_ms)

    body = response.json()
    assert body["points"] == expected_points
    assert body["timed_out"] is False


@pytest.mark.parametrize("delay_ms", [5001, 5400, 5700])
def test_answers_inside_the_network_grace_get_base_points_without_bonus(
    api_client, playable_category, clock, delay_ms
):
    game = Game(api_client)
    _, response = answer_after(game, clock, delay_ms)

    body = response.json()
    assert body["is_correct"] is True
    assert body["points"] == 100
    assert body["timed_out"] is False


@pytest.mark.parametrize("delay_ms", [5701, 6000, 60_000])
def test_correct_answers_after_the_grace_are_timeouts_with_zero_points(
    api_client, playable_category, clock, delay_ms
):
    game = Game(api_client)
    qid, response = answer_after(game, clock, delay_ms)

    body = response.json()
    assert body["timed_out"] is True
    assert body["is_correct"] is False
    assert body["points"] == 0
    assert body["total_score"] == 0
    assert body["correct_choice_id"] == game.correct_choice(qid)
    row = SessionQuestion.objects.get(session_id=game.session_id, position=0)
    assert row.selected_choice_id is None


def test_late_answer_with_garbage_choice_is_still_just_a_timeout(
    api_client, playable_category, clock
):
    game = Game(api_client)
    qid = game.question().json()["question"]["id"]
    clock.shift(6)

    response = game.answer(qid, 999_999_999)

    assert response.status_code == 200
    assert response.json()["timed_out"] is True


def test_timed_out_question_counts_as_full_time_so_skipping_cannot_shorten_total(
    api_client, playable_category, clock
):
    game = Game(api_client)
    qid = game.question().json()["question"]["id"]
    clock.shift(0.1)

    game.answer(qid, None)  # istemci erken "süre aşımı" bildirse de

    assert QuizSession.objects.get(pk=game.session_id).total_response_ms == 5000


def test_unanswered_question_is_closed_as_timeout_when_the_next_one_is_requested(
    api_client, playable_category, clock
):
    game = Game(api_client)
    first = game.question().json()
    clock.shift(5.701)

    second = game.question().json()

    assert second["position"] == 1
    assert second["question"]["id"] != first["question"]["id"]
    assert second["remaining_ms"] == 5000
    assert second["current_score"] == 0
    row = SessionQuestion.objects.get(session_id=game.session_id, position=0)
    assert row.answered_at is not None
    assert row.selected_choice_id is None
    assert row.is_correct is False
    assert row.points == 0


def test_question_inside_the_grace_window_is_still_open(api_client, playable_category, clock):
    game = Game(api_client)
    first = game.question().json()
    clock.shift(5.4)

    again = game.question().json()

    assert again["position"] == 0
    assert again["question"]["id"] == first["question"]["id"]
    assert again["remaining_ms"] == 0


def test_abandoned_last_question_finishes_the_session_on_result(
    api_client, playable_category, clock
):
    game = Game(api_client)
    for _ in range(19):
        game.play_correct()
    game.question()
    clock.shift(6)

    result = game.result()

    assert result.status_code == 200
    assert result.json()["status"] == "finished"
    assert result.json()["correct_count"] == 19


def test_closing_a_stale_question_does_not_depend_on_who_asks_first(
    api_client, playable_category, clock
):
    game = Game(api_client)
    game.question()
    clock.shift(10)

    # Süre aşımı kapatıldıktan sonra eski soruya cevap gelirse yarışılmaz: zaten cevaplanmış.
    game.question()
    old = SessionQuestion.objects.get(session_id=game.session_id, position=0).question_id
    response = game.answer(old, game.correct_choice(old))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "already_answered"


# --- oturum ömrü ------------------------------------------------------------------------------


def test_session_older_than_ten_minutes_is_expired(api_client, playable_category, clock):
    game = Game(api_client)
    game.question()
    clock.shift(10 * 60 + 1)

    response = game.question()

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "session_expired"
    assert QuizSession.objects.get(pk=game.session_id).status == QuizSession.Status.EXPIRED


def test_expired_session_rejects_answers_and_results(api_client, playable_category, clock):
    game = Game(api_client)
    qid = game.question().json()["question"]["id"]
    clock.shift(10 * 60 + 1)

    answer = game.answer(qid, game.correct_choice(qid))
    result = game.result()

    assert answer.status_code == 410
    assert result.status_code == 410
    assert answer.json()["error"]["code"] == "session_expired"


def test_session_just_inside_ten_minutes_still_works(api_client, playable_category, clock):
    game = Game(api_client)
    clock.shift(9 * 60 + 59)
    assert game.question().status_code == 200


def test_finished_session_does_not_expire_into_a_worse_state(api_client, playable_category, clock):
    game = Game(api_client)
    for _ in range(20):
        game.play_correct()
    clock.shift(30 * 60)

    assert game.result().status_code == 200
    assert QuizSession.objects.get(pk=game.session_id).status == QuizSession.Status.FINISHED
