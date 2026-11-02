import pytest

from apps.quiz.models import QuizSession

from .quiz_helpers import Game

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("clock")]

PRIVATE_ENDPOINTS = ["question", "result"]


@pytest.mark.parametrize("token", [None, "", "yanlis-token", "A" * 43])
def test_wrong_or_missing_token_is_401_on_every_session_endpoint(
    api_client, playable_category, token
):
    game = Game(api_client)
    qid = game.question().json()["question"]["id"]

    responses = [
        game.question(token=token),
        game.result(token=token),
        game.answer(qid, game.correct_choice(qid), token=token),
    ]

    for response in responses:
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_token"


def test_token_of_another_session_does_not_grant_access(api_client, playable_category):
    mine = Game(api_client)
    theirs = Game(api_client)

    assert mine.question(token=theirs.token).status_code == 401


def test_failed_token_attempt_does_not_change_session_state(api_client, playable_category):
    game = Game(api_client)
    qid = game.question().json()["question"]["id"]

    game.answer(qid, game.correct_choice(qid), token="yanlis")

    session = QuizSession.objects.get(pk=game.session_id)
    assert session.total_score == 0
    assert session.current_index == 0


def test_unknown_session_is_404(api_client, playable_category):
    response = api_client.get(
        "/api/v1/sessions/8f0c2a7e-1b2c-4d3e-8f90-123456789abc/question/",
        HTTP_X_SESSION_TOKEN="x",
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_malformed_session_id_is_json_404(api_client, playable_category):
    response = api_client.get("/api/v1/sessions/not-a-uuid/question/", HTTP_X_SESSION_TOKEN="x")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_token_in_query_string_or_body_is_ignored(api_client, playable_category):
    game = Game(api_client)

    by_query = api_client.get(f"{game.base}/question/?token={game.token}")
    by_body = api_client.post(
        f"{game.base}/answer/",
        {"question_id": 1, "choice_id": 1, "session_token": game.token},
        format="json",
    )

    assert by_query.status_code == 401
    assert by_body.status_code == 401


# --- throttling ---------------------------------------------------------------------------------


def test_eleventh_session_start_within_a_minute_is_rate_limited(api_client, playable_category):
    for _ in range(10):
        assert (
            api_client.post("/api/v1/sessions/", {"category": "yazilim"}, format="json").status_code
            == 201
        )

    response = api_client.post("/api/v1/sessions/", {"category": "yazilim"}, format="json")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert response.json()["error"]["details"]["retry_after_seconds"] >= 1


def test_session_start_limit_resets_after_the_window(api_client, playable_category, clock):
    for _ in range(10):
        api_client.post("/api/v1/sessions/", {"category": "yazilim"}, format="json")
    assert (
        api_client.post("/api/v1/sessions/", {"category": "yazilim"}, format="json").status_code
        == 429
    )

    clock.shift(61)

    assert (
        api_client.post("/api/v1/sessions/", {"category": "yazilim"}, format="json").status_code
        == 201
    )


def test_121st_answer_request_in_a_minute_is_rate_limited(api_client, playable_category):
    game = Game(api_client)
    codes = [game.answer(1, 1, token="x").status_code for _ in range(121)]

    assert codes[:120] == [401] * 120
    assert codes[120] == 429


def test_throttle_is_per_ip_not_global(api_client, playable_category):
    for _ in range(10):
        api_client.post("/api/v1/sessions/", {"category": "yazilim"}, format="json")

    other = api_client.post(
        "/api/v1/sessions/",
        {"category": "yazilim"},
        format="json",
        REMOTE_ADDR="10.9.8.7",
    )

    assert other.status_code == 201


def test_spoofed_forwarded_for_cannot_bypass_the_limit_by_default(api_client, playable_category):
    # NUM_PROXIES=0: X-Forwarded-For yok sayılır, yalnızca REMOTE_ADDR sayılır.
    statuses = [
        api_client.post(
            "/api/v1/sessions/",
            {"category": "yazilim"},
            format="json",
            HTTP_X_FORWARDED_FOR=f"1.2.3.{index}",
        ).status_code
        for index in range(11)
    ]
    assert statuses[-1] == 429


def test_cors_preflight_allows_the_session_token_header(api_client, playable_category):
    response = api_client.options(
        "/api/v1/sessions/x/question/",
        HTTP_ORIGIN="http://localhost:5173",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-session-token",
    )
    assert "x-session-token" in response.headers["Access-Control-Allow-Headers"].lower()


def test_no_cookies_are_set_by_the_game_api(api_client, playable_category):
    game = Game(api_client)
    response = game.question()
    assert not response.cookies
    assert not api_client.cookies
