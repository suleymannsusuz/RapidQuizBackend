import hashlib
import json

import pytest

from apps.catalog.models import Choice, Question
from apps.quiz.models import QuizSession, SessionQuestion
from apps.quiz.services import QUESTIONS_PER_SESSION, calculate_points

from .quiz_helpers import Game

# Saat her zaman dondurulur: puanlar gerçek süreye bağlı kalıp testi dengesizleştirmesin.
pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("clock")]


# --- oturum başlatma -------------------------------------------------------------------------


def test_start_session_returns_contract(api_client, playable_category):
    game = Game(api_client)

    assert game.start_response["category"] == {"slug": "yazilim", "name": "Yazılım"}
    assert game.start_response["total_questions"] == 20
    assert game.start_response["time_limit_ms"] == 5000
    assert set(game.start_response) == {
        "session_id",
        "session_token",
        "category",
        "total_questions",
        "time_limit_ms",
    }


def test_token_is_stored_only_as_sha256_hash(api_client, playable_category):
    game = Game(api_client)
    session = QuizSession.objects.get(pk=game.session_id)

    assert session.token_hash == hashlib.sha256(game.token.encode()).hexdigest()
    assert game.token not in session.token_hash
    assert len(game.token) >= 32


def test_ip_is_stored_hashed_not_raw(api_client, playable_category):
    Game(api_client)
    session = QuizSession.objects.get()

    assert "127.0.0.1" not in session.ip_hash
    assert len(session.ip_hash) == 64


def test_session_gets_20_distinct_questions_with_shuffled_complete_choice_order(
    api_client, playable_category
):
    game = Game(api_client)
    rows = list(SessionQuestion.objects.filter(session_id=game.session_id).order_by("position"))

    assert [row.position for row in rows] == list(range(20))
    assert len({row.question_id for row in rows}) == 20
    for row in rows:
        own_choices = set(
            Choice.objects.filter(question_id=row.question_id).values_list("id", flat=True)
        )
        assert sorted(row.choice_order) == sorted(own_choices)
        assert len(row.choice_order) == 4


def test_choice_order_is_not_always_the_database_order(api_client, playable_category):
    orders_differ = False
    for _ in range(3):
        game = Game(api_client)
        for row in SessionQuestion.objects.filter(session_id=game.session_id):
            if row.choice_order != sorted(row.choice_order):
                orders_differ = True
        api_client.cookies.clear()
    assert orders_differ


@pytest.mark.parametrize("platform", ["web", "ios", "android"])
def test_platform_is_recorded(api_client, playable_category, platform):
    game = Game(api_client, platform=platform)
    assert QuizSession.objects.get(pk=game.session_id).platform == platform


def test_unknown_platform_is_rejected(api_client, playable_category):
    response = api_client.post(
        "/api/v1/sessions/", {"category": "yazilim", "platform": "palm"}, format="json"
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert "platform" in response.json()["error"]["details"]


def test_unknown_category_is_not_found(api_client, playable_category):
    response = api_client.post("/api/v1/sessions/", {"category": "yok"}, format="json")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_inactive_category_is_not_found(api_client, playable_category):
    playable_category.is_active = False
    playable_category.save()
    response = api_client.post("/api/v1/sessions/", {"category": "yazilim"}, format="json")
    assert response.status_code == 404


def test_missing_category_field_is_validation_error(api_client, playable_category):
    response = api_client.post("/api/v1/sessions/", {}, format="json")
    assert response.status_code == 400
    assert "category" in response.json()["error"]["details"]


def test_category_with_too_few_questions_is_unavailable(api_client, category, make_question):
    for index in range(19):
        make_question(category, text=f"Soru {index}?")
    response = api_client.post("/api/v1/sessions/", {"category": "yazilim"}, format="json")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "category_unavailable"


def test_inactive_and_malformed_questions_never_enter_a_session(
    api_client, category, make_question
):
    for index in range(20):
        make_question(category, text=f"Soru {index}?")
    Question.objects.filter(text__in=["Soru 0?", "Soru 1?"]).update(is_active=False)
    # 3 şıklı ve doğru şıkkı olmayan sorular da elenir
    broken = make_question(category, text="Bozuk?")
    broken.choices.filter(is_correct=False).first().delete()

    response = api_client.post("/api/v1/sessions/", {"category": "yazilim"}, format="json")
    assert response.status_code == 409  # geriye yalnızca 18 geçerli soru kaldı


# --- soru sunma: sızıntı yok -----------------------------------------------------------------


def test_question_response_never_leaks_the_correct_choice(api_client, playable_category):
    game = Game(api_client)
    response = game.question()

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "position",
        "total_questions",
        "question",
        "choices",
        "time_limit_ms",
        "remaining_ms",
        "current_score",
    }
    assert set(body["question"]) == {"id", "text"}
    assert len(body["choices"]) == 4
    assert all(set(choice) == {"id", "text"} for choice in body["choices"])
    assert "correct" not in json.dumps(body).lower()
    assert body["position"] == 0
    assert body["remaining_ms"] == 5000
    assert body["current_score"] == 0


def test_game_survives_an_admin_replacing_a_choice_mid_session(api_client, playable_category):
    game = Game(api_client)
    qid = game.question().json()["question"]["id"]
    Choice.objects.filter(question_id=qid, is_correct=False).first().delete()
    replacement = Choice.objects.create(question_id=qid, text="Yeni şık", is_correct=False)

    body = game.question().json()

    assert len(body["choices"]) == 4
    assert replacement.id in [choice["id"] for choice in body["choices"]]
    answer = game.answer(qid, game.correct_choice(qid))
    assert answer.status_code == 200
    assert answer.json()["is_correct"] is True


def test_choices_follow_the_session_order(api_client, playable_category):
    game = Game(api_client)
    body = game.question().json()
    row = SessionQuestion.objects.get(session_id=game.session_id, position=0)
    assert [choice["id"] for choice in body["choices"]] == row.choice_order


def test_asking_the_same_question_twice_does_not_reset_the_clock(
    api_client, playable_category, clock
):
    game = Game(api_client)
    first = game.question().json()
    clock.shift(1.5)
    second = game.question().json()

    assert second["question"]["id"] == first["question"]["id"]
    assert first["remaining_ms"] == 5000
    assert second["remaining_ms"] == 3500
    row = SessionQuestion.objects.get(session_id=game.session_id, position=0)
    assert row.served_at is not None


def test_next_question_is_not_served_while_current_is_unanswered(api_client, playable_category):
    game = Game(api_client)
    first = game.question().json()
    again = game.question().json()

    assert again["position"] == 0
    assert again["question"]["id"] == first["question"]["id"]
    # Henüz sunulmamış sonraki soruların served_at'ı boş kalır.
    assert (
        SessionQuestion.objects.filter(session_id=game.session_id, served_at__isnull=False).count()
        == 1
    )


def test_cannot_answer_a_question_that_is_not_the_current_one(api_client, playable_category):
    game = Game(api_client)
    current = game.question().json()["question"]["id"]
    later = SessionQuestion.objects.get(session_id=game.session_id, position=1).question_id
    assert later != current

    response = game.answer(later, game.correct_choice(later))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "question_mismatch"


def test_cannot_answer_a_question_that_was_never_served(api_client, playable_category):
    game = Game(api_client)
    current = SessionQuestion.objects.get(session_id=game.session_id, position=0).question_id

    response = game.answer(current, game.correct_choice(current))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "question_mismatch"


def test_question_outside_the_session_is_a_mismatch(api_client, playable_category, make_question):
    game = Game(api_client)
    game.question()
    stranger = make_question(playable_category, text="Başka soru?")

    response = game.answer(stranger.id, stranger.choices.first().id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "question_mismatch"


# --- cevap sonuçları --------------------------------------------------------------------------


def test_correct_answer_returns_points_and_total(api_client, playable_category, clock):
    game = Game(api_client)
    question, answer = game.play_correct(clock, delay_ms=2000)

    assert answer.status_code == 200
    body = answer.json()
    assert body["is_correct"] is True
    assert body["points"] == 130  # 100 + round(50 × 3000 / 5000)
    assert body["total_score"] == 130
    assert body["timed_out"] is False
    assert body["is_last"] is False
    assert body["correct_choice_id"] == game.correct_choice(question["question"]["id"])
    assert set(body) == {
        "is_correct",
        "correct_choice_id",
        "points",
        "total_score",
        "timed_out",
        "is_last",
    }


def test_wrong_answer_scores_zero_and_reveals_the_correct_choice(
    api_client, playable_category, clock
):
    game = Game(api_client)
    qid = game.question().json()["question"]["id"]
    clock.shift(1)

    body = game.answer(qid, game.wrong_choice(qid)).json()

    assert body["is_correct"] is False
    assert body["points"] == 0
    assert body["total_score"] == 0
    assert body["timed_out"] is False
    assert body["correct_choice_id"] == game.correct_choice(qid)
    assert QuizSession.objects.get(pk=game.session_id).correct_count == 0


def test_choice_from_another_question_is_rejected_and_question_stays_open(
    api_client, playable_category
):
    game = Game(api_client)
    qid = game.question().json()["question"]["id"]
    other = SessionQuestion.objects.get(session_id=game.session_id, position=1).question_id

    response = game.answer(qid, game.correct_choice(other))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    # Hatalı istek soruyu kapatmaz; doğru şıkla hâlâ cevaplanabilir.
    assert game.answer(qid, game.correct_choice(qid)).status_code == 200


def test_null_choice_is_a_timeout_with_zero_points(api_client, playable_category, clock):
    game = Game(api_client)
    qid = game.question().json()["question"]["id"]
    clock.shift(5)

    body = game.answer(qid, None).json()

    assert body["timed_out"] is True
    assert body["is_correct"] is False
    assert body["points"] == 0
    assert body["correct_choice_id"] == game.correct_choice(qid)


def test_choice_id_field_is_required_even_when_null(api_client, playable_category):
    game = Game(api_client)
    qid = game.question().json()["question"]["id"]
    response = api_client.post(
        f"{game.base}/answer/", {"question_id": qid}, format="json", **game.headers()
    )
    assert response.status_code == 400
    assert "choice_id" in response.json()["error"]["details"]


def test_second_answer_to_same_question_is_already_answered(api_client, playable_category):
    game = Game(api_client)
    qid = game.question().json()["question"]["id"]
    assert game.answer(qid, game.correct_choice(qid)).status_code == 200

    again = game.answer(qid, game.correct_choice(qid))

    assert again.status_code == 409
    assert again.json()["error"]["code"] == "already_answered"
    # Puan iki kez eklenmemiş olmalı.
    assert QuizSession.objects.get(pk=game.session_id).total_score == 150


def test_cannot_farm_points_by_resending_a_correct_answer(api_client, playable_category):
    game = Game(api_client)
    qid = game.question().json()["question"]["id"]
    choice = game.correct_choice(qid)
    codes = [game.answer(qid, choice).status_code for _ in range(5)]

    assert codes == [200, 409, 409, 409, 409]
    assert QuizSession.objects.get(pk=game.session_id).total_score == 150


# --- tam oyun ---------------------------------------------------------------------------------


def test_perfect_instant_game_scores_the_maximum_3000(api_client, playable_category, clock):
    game = Game(api_client)
    answers = []
    for _ in range(QUESTIONS_PER_SESSION):
        _, answer = game.play_correct()
        answers.append(answer.json())

    assert [a["is_last"] for a in answers] == [False] * 19 + [True]
    assert answers[-1]["total_score"] == 3000

    result = game.result()
    assert result.status_code == 200
    assert result.json() == {
        "status": "finished",
        "category": {"slug": "yazilim", "name": "Yazılım"},
        "total_questions": 20,
        "total_score": 3000,
        "correct_count": 20,
        "total_response_ms": 0,
    }
    session = QuizSession.objects.get(pk=game.session_id)
    assert session.status == QuizSession.Status.FINISHED
    assert session.finished_at is not None


def test_no_more_questions_after_the_last_one(api_client, playable_category):
    game = Game(api_client)
    for _ in range(20):
        game.play_correct()

    response = game.question()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "session_finished"


def test_last_question_cannot_be_answered_twice(api_client, playable_category):
    game = Game(api_client)
    for _ in range(19):
        game.play_correct()
    _, answer = game.play_correct()
    assert answer.json()["is_last"] is True
    last = SessionQuestion.objects.get(session_id=game.session_id, position=19).question_id

    again = game.answer(last, game.correct_choice(last))

    assert again.status_code == 409
    assert again.json()["error"]["code"] == "already_answered"


def test_result_of_unfinished_session_is_rejected(api_client, playable_category):
    game = Game(api_client)
    game.play_correct()

    response = game.result()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "session_not_finished"


def test_mixed_game_totals_add_up(api_client, playable_category, clock):
    game = Game(api_client)
    expected_score = expected_ms = correct = 0
    for index in range(QUESTIONS_PER_SESSION):
        qid = game.question().json()["question"]["id"]
        delay = 500 * (index % 5)  # 0, 500, ..., 2000 ms
        clock.shift(delay / 1000)
        if index % 3 == 0:
            game.answer(qid, game.wrong_choice(qid))
        else:
            game.answer(qid, game.correct_choice(qid))
            expected_score += calculate_points(delay, True)
            correct += 1
        expected_ms += delay

    body = game.result().json()
    assert body["total_score"] == expected_score
    assert body["correct_count"] == correct
    assert body["total_response_ms"] == expected_ms


# --- puan formülü -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("response_ms", "is_correct", "expected"),
    [
        (0, True, 150),
        (1000, True, 140),
        (2000, True, 130),
        (2500, True, 125),
        (4950, True, 101),  # 0,5 yukarı yuvarlanır
        (5000, True, 100),
        (5700, True, 100),  # ağ toleransı: bonus yok
        (0, False, 0),
        (2000, False, 0),
    ],
)
def test_calculate_points(response_ms, is_correct, expected):
    assert calculate_points(response_ms, is_correct) == expected
