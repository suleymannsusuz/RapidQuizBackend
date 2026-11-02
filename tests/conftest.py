import datetime

import pytest
import time_machine
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.catalog.models import Category, Choice, Question


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    """Throttle sayaçları testler arasında sızmasın."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def clock():
    """Dondurulmuş saat; `clock.shift(milliseconds=...)` ile ilerletilir."""
    start = datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.UTC)
    with time_machine.travel(start, tick=False) as traveller:
        yield traveller


@pytest.fixture
def category(db):
    return Category.objects.create(slug="yazilim", name="Yazılım", color="#3B82F6", sort_order=1)


@pytest.fixture
def playable_category(db, make_question):
    """25 geçerli soruluk aktif kategori (bir oturum 20 soru çeker)."""
    category = Category.objects.create(slug="yazilim", name="Yazılım", color="#3B82F6")
    for index in range(25):
        make_question(category, text=f"Soru {index}?", correct=index % 4)
    return category


@pytest.fixture
def make_score(db):
    """Doğrudan skor tablosuna kayıt ekler (oyun oynatmadan)."""
    from django.utils import timezone

    from apps.leaderboard.models import ScoreEntry
    from apps.quiz.models import QuizSession

    def _make(category, name="Oyuncu", score=1000, ms=10_000, correct=10, created_at=None):
        session = QuizSession.objects.create(
            token_hash="x",
            category=category,
            status=QuizSession.Status.SUBMITTED,
            total_score=score,
            correct_count=correct,
            total_response_ms=ms,
        )
        return ScoreEntry.objects.create(
            session=session,
            category=category,
            player_name=name,
            score=score,
            correct_count=correct,
            total_response_ms=ms,
            created_at=created_at or timezone.now(),
        )

    return _make


@pytest.fixture
def make_question(db):
    def _make(category, text="Soru?", correct=0, **kwargs):
        question = Question.objects.create(category=category, text=text, **kwargs)
        for position in range(4):
            Choice.objects.create(
                question=question, text=f"Şık {position}", is_correct=position == correct
            )
        return question

    return _make
