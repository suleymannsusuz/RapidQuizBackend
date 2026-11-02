import pytest

from apps.leaderboard.models import ScoreEntry
from apps.quiz.models import QuizSession

from .quiz_helpers import Game

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("clock")]


def test_finished_session_can_save_its_score(api_client, playable_category):
    game = Game(api_client)
    game.finish()

    response = game.submit_score("Ayşe")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"rank", "in_top_10", "score", "leaderboard"}
    assert body["rank"] == 1
    assert body["in_top_10"] is True
    assert body["score"] == 3000
    assert len(body["leaderboard"]) == 1
    row = body["leaderboard"][0]
    assert set(row) == {"rank", "player_name", "score", "correct_count", "created_at"}
    assert (row["rank"], row["player_name"], row["score"], row["correct_count"]) == (
        1,
        "Ayşe",
        3000,
        20,
    )

    session = QuizSession.objects.get(pk=game.session_id)
    assert session.status == QuizSession.Status.SUBMITTED
    entry = ScoreEntry.objects.get()
    assert entry.session_id == session.id
    assert entry.category_id == session.category_id
    assert (entry.score, entry.correct_count, entry.total_response_ms) == (3000, 20, 0)
    assert entry.created_at == session.finished_at


def test_client_supplied_score_fields_are_ignored(api_client, playable_category):
    game = Game(api_client)
    game.finish(correct=False)  # gerçek puan 0

    response = api_client.post(
        f"{game.base}/score/",
        {
            "player_name": "Hileci",
            "score": 99999,
            "total_score": 99999,
            "correct_count": 20,
            "total_response_ms": 1,
            "category": "fizik",
        },
        format="json",
        **game.headers(),
    )

    assert response.status_code == 201
    entry = ScoreEntry.objects.get()
    assert (entry.score, entry.correct_count) == (0, 0)
    assert entry.total_response_ms == 0  # saat dondurulduğu için cevaplar anında verildi
    assert entry.category.slug == "yazilim"  # istemci kategori de seçtiremez


def test_name_is_normalized_before_saving(api_client, playable_category):
    game = Game(api_client)
    game.finish()

    game.submit_score("  Zeynep    Su ")

    assert ScoreEntry.objects.get().player_name == "Zeynep Su"


def test_score_can_only_be_saved_once(api_client, playable_category):
    game = Game(api_client)
    game.finish()
    assert game.submit_score("Ayşe").status_code == 201

    again = game.submit_score("Başka İsim")

    assert again.status_code == 409
    assert again.json()["error"]["code"] == "score_already_submitted"
    assert ScoreEntry.objects.count() == 1
    assert ScoreEntry.objects.get().player_name == "Ayşe"


def test_unfinished_session_cannot_save_a_score(api_client, playable_category):
    game = Game(api_client)
    for _ in range(19):
        game.play_correct()

    response = game.submit_score("Acelecİ")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "session_not_finished"
    assert ScoreEntry.objects.count() == 0
    assert QuizSession.objects.get(pk=game.session_id).status == QuizSession.Status.ACTIVE


def test_brand_new_session_cannot_save_a_score(api_client, playable_category):
    game = Game(api_client)
    assert game.submit_score("Ayşe").status_code == 409
    assert ScoreEntry.objects.count() == 0


@pytest.mark.parametrize(
    "name",
    ["", "a", "x" * 21, "<script>alert(1)</script>", "Siktir", "Ali!", "   "],
)
def test_invalid_name_is_a_validation_error_and_keeps_the_score_open(
    api_client, playable_category, name
):
    game = Game(api_client)
    game.finish()

    response = game.submit_score(name)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "player_name" in error["details"]
    assert ScoreEntry.objects.count() == 0
    # Oturum hâlâ skor kaydedebilir.
    assert QuizSession.objects.get(pk=game.session_id).status == QuizSession.Status.FINISHED
    assert game.submit_score("Düzgün İsim").status_code == 201


def test_profanity_message_does_not_reveal_the_matched_word(api_client, playable_category):
    game = Game(api_client)
    game.finish()

    response = game.submit_score("Siktir")

    message = response.json()["error"]["details"]["player_name"][0]
    assert message == "Bu isim kullanılamaz."


def test_missing_player_name_is_a_validation_error(api_client, playable_category):
    game = Game(api_client)
    game.finish()

    response = api_client.post(f"{game.base}/score/", {}, format="json", **game.headers())

    assert response.status_code == 400
    assert "player_name" in response.json()["error"]["details"]


@pytest.mark.parametrize("token", [None, "", "yanlis"])
def test_wrong_token_cannot_save_a_score(api_client, playable_category, token):
    game = Game(api_client)
    game.finish()

    response = game.submit_score("Ayşe", token=token)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"
    assert ScoreEntry.objects.count() == 0


def test_another_sessions_token_cannot_save_my_score(api_client, playable_category):
    mine = Game(api_client)
    mine.finish()
    theirs = Game(api_client)

    response = mine.submit_score("Çaldım", token=theirs.token)

    assert response.status_code == 401
    assert ScoreEntry.objects.count() == 0


def test_unknown_session_is_not_found(api_client, playable_category):
    response = api_client.post(
        "/api/v1/sessions/8f0c2a7e-1b2c-4d3e-8f90-123456789abc/score/",
        {"player_name": "Ayşe"},
        format="json",
        HTTP_X_SESSION_TOKEN="x",
    )
    assert response.status_code == 404


def test_expired_session_cannot_save_a_score(api_client, playable_category, clock):
    game = Game(api_client)
    for _ in range(10):
        game.play_correct()
    clock.shift(10 * 60 + 1)

    response = game.submit_score("Geç Kaldım")

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "session_expired"
    assert ScoreEntry.objects.count() == 0


def test_finished_session_can_still_save_its_score_later(api_client, playable_category, clock):
    game = Game(api_client)
    game.finish()
    clock.shift(30 * 60)

    assert game.submit_score("Yavaş Yazan").status_code == 201


def test_abandoned_last_question_still_allows_saving_the_score(
    api_client, playable_category, clock
):
    game = Game(api_client)
    for _ in range(19):
        game.play_correct()
    game.question()  # 20. soru sunuldu ama hiç cevaplanmadı
    clock.shift(6)

    response = game.submit_score("Son Soruyu Atladım")

    assert response.status_code == 201
    assert response.json()["score"] == 19 * 150
    entry = ScoreEntry.objects.get()
    assert entry.correct_count == 19
    assert entry.total_response_ms == 5000  # süre aşımı tam süre sayılır


def test_score_submission_is_rate_limited_per_ip(api_client, playable_category):
    game = Game(api_client)
    codes = [game.submit_score("Ayşe", token="x").status_code for _ in range(21)]

    assert codes[:20] == [401] * 20
    assert codes[20] == 429


def test_session_cannot_be_played_further_after_score_is_saved(api_client, playable_category):
    game = Game(api_client)
    game.finish()
    game.submit_score("Ayşe")

    assert game.question().status_code == 409
    assert game.result().status_code == 200
    assert game.result().json()["status"] == "submitted"
