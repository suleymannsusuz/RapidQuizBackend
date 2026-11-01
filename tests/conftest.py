import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Category, Choice, Question


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def category(db):
    return Category.objects.create(slug="yazilim", name="Yazılım", color="#3B82F6", sort_order=1)


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
