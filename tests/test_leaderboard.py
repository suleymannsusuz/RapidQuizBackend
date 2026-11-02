import datetime

import pytest

from apps.catalog.models import Category

from .quiz_helpers import Game

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("clock")]

NOON = datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.UTC)


def at(hours):
    return NOON + datetime.timedelta(hours=hours)


def names(response):
    return [row["player_name"] for row in response.json()["leaderboard"]]


def test_empty_leaderboard(api_client, category):
    response = api_client.get("/api/v1/leaderboard/?category=yazilim")

    assert response.status_code == 200
    assert response.json() == {
        "category": {"slug": "yazilim", "name": "Yazılım"},
        "leaderboard": [],
    }


def test_leaderboard_is_ordered_by_score_then_time_then_finish_time(
    api_client, category, make_score
):
    make_score(category, "D-yavaş", score=2000, ms=9000, created_at=at(1))
    make_score(category, "A-puan", score=2500, ms=12000, created_at=at(5))
    make_score(category, "C-erken", score=2000, ms=8000, created_at=at(1))
    make_score(category, "B-geç", score=2000, ms=8000, created_at=at(2))
    make_score(category, "E-düşük", score=100, ms=1000, created_at=at(0))

    response = api_client.get("/api/v1/leaderboard/?category=yazilim")

    assert names(response) == ["A-puan", "C-erken", "B-geç", "D-yavaş", "E-düşük"]
    assert [row["rank"] for row in response.json()["leaderboard"]] == [1, 2, 3, 4, 5]


def test_rows_expose_exactly_the_documented_fields(api_client, category, make_score):
    make_score(category, "Mert", score=2780, correct=19)

    row = api_client.get("/api/v1/leaderboard/?category=yazilim").json()["leaderboard"][0]

    assert set(row) == {"rank", "player_name", "score", "correct_count", "created_at"}
    assert (row["rank"], row["player_name"], row["score"], row["correct_count"]) == (
        1,
        "Mert",
        2780,
        19,
    )


def test_only_the_top_ten_are_returned(api_client, category, make_score):
    for index in range(12):
        make_score(category, f"Oyuncu{index}", score=1000 + index)

    response = api_client.get("/api/v1/leaderboard/?category=yazilim")

    assert len(response.json()["leaderboard"]) == 10
    assert names(response)[0] == "Oyuncu11"
    assert names(response)[-1] == "Oyuncu2"


def test_categories_have_separate_leaderboards(api_client, category, make_score):
    other = Category.objects.create(slug="fizik", name="Fizik", color="#EC4899")
    make_score(category, "Yazılımcı", score=1500)
    make_score(other, "Fizikçi", score=3000)

    assert names(api_client.get("/api/v1/leaderboard/?category=yazilim")) == ["Yazılımcı"]
    assert names(api_client.get("/api/v1/leaderboard/?category=fizik")) == ["Fizikçi"]


def test_same_name_may_appear_multiple_times(api_client, category, make_score):
    make_score(category, "Ayşe", score=2000)
    make_score(category, "Ayşe", score=1000)

    assert names(api_client.get("/api/v1/leaderboard/?category=yazilim")) == ["Ayşe", "Ayşe"]


def test_category_parameter_is_required(api_client, category):
    response = api_client.get("/api/v1/leaderboard/")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert "category" in response.json()["error"]["details"]


def test_unknown_category_is_not_found(api_client, category):
    response = api_client.get("/api/v1/leaderboard/?category=yok")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_inactive_category_is_not_found(api_client, category):
    category.is_active = False
    category.save()
    assert api_client.get("/api/v1/leaderboard/?category=yazilim").status_code == 404


def test_leaderboard_needs_no_token_or_cookies(api_client, category):
    response = api_client.get("/api/v1/leaderboard/?category=yazilim")
    assert response.status_code == 200
    assert not response.cookies


# --- sıra hesabı --------------------------------------------------------------------------


def test_new_score_rank_counts_better_entries(api_client, playable_category, make_score):
    make_score(playable_category, "Üst1", score=3100)
    make_score(playable_category, "Üst2", score=3050)
    make_score(playable_category, "Alt", score=500)
    game = Game(api_client)
    game.finish()  # 3000 puan

    body = game.submit_score("Ayşe").json()

    assert body["rank"] == 3
    assert body["in_top_10"] is True
    assert [row["player_name"] for row in body["leaderboard"]] == ["Üst1", "Üst2", "Ayşe", "Alt"]


def test_equal_score_and_time_is_decided_by_who_finished_first(
    api_client, playable_category, make_score
):
    earlier = make_score(playable_category, "Önce", score=3000, ms=0, created_at=at(-1))
    later = make_score(playable_category, "Sonra", score=3000, ms=0, created_at=at(1))
    game = Game(api_client)
    game.finish()  # tam 3000 puan, 0 ms, saat 12:00

    body = game.submit_score("Ortada").json()

    assert body["rank"] == 2
    assert [row["player_name"] for row in body["leaderboard"]] == [
        earlier.player_name,
        "Ortada",
        later.player_name,
    ]


def test_lower_total_time_beats_an_earlier_finish_at_equal_score(
    api_client, playable_category, make_score
):
    # "Yavaş" daha önce bitirdi ama toplam süresi uzun: süre, bitiş zamanından önce gelir.
    make_score(playable_category, "Yavaş", score=3000, ms=500, created_at=at(-5))
    game = Game(api_client)
    game.finish()  # 3000 puan, 0 ms

    body = game.submit_score("Ayşe").json()

    assert body["rank"] == 1
    assert [row["player_name"] for row in body["leaderboard"]] == ["Ayşe", "Yavaş"]


def test_score_outside_top_ten_reports_rank_but_not_the_player(
    api_client, playable_category, make_score
):
    for index in range(10):
        make_score(playable_category, f"Usta{index}", score=3100 + index)
    game = Game(api_client)
    game.finish(correct=False)  # 0 puan

    body = game.submit_score("Yeni Başlayan").json()

    assert body["rank"] == 11
    assert body["in_top_10"] is False
    assert body["score"] == 0
    assert len(body["leaderboard"]) == 10
    assert "Yeni Başlayan" not in [row["player_name"] for row in body["leaderboard"]]


def test_scores_in_other_categories_do_not_affect_rank(api_client, playable_category, make_score):
    other = Category.objects.create(slug="fizik", name="Fizik", color="#EC4899")
    make_score(other, "Başka Kategori", score=3100)
    game = Game(api_client)
    game.finish()

    assert game.submit_score("Ayşe").json()["rank"] == 1
