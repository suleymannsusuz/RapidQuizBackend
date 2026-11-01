import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.catalog.models import Category, Choice, Question


@pytest.mark.django_db
def test_hex_color_is_validated():
    category = Category(slug="x", name="X", color="mavi")
    with pytest.raises(ValidationError) as exc:
        category.full_clean()
    assert "color" in exc.value.message_dict

    Category(slug="x", name="X", color="#14B8A6").full_clean()


def test_question_text_limit_is_90_characters(category):
    question = Question(category=category, text="a" * 91)
    with pytest.raises(ValidationError) as exc:
        question.full_clean()
    assert "text" in exc.value.message_dict

    Question(category=category, text="a" * 90).full_clean()


def test_choice_text_limit_is_40_characters(category, make_question):
    question = make_question(category)
    with pytest.raises(ValidationError) as exc:
        Choice(question=question, text="a" * 41).full_clean()
    assert "text" in exc.value.message_dict


@pytest.mark.parametrize("difficulty", [0, 4])
def test_difficulty_must_be_between_1_and_3(category, difficulty):
    with pytest.raises(ValidationError) as exc:
        Question(category=category, text="Soru?", difficulty=difficulty).full_clean()
    assert "difficulty" in exc.value.message_dict


def test_database_rejects_second_correct_choice(category, make_question):
    question = make_question(category, correct=0)
    with pytest.raises(IntegrityError), transaction.atomic():
        Choice.objects.create(question=question, text="İkinci doğru", is_correct=True)


def test_category_with_questions_cannot_be_deleted(category, make_question):
    from django.db.models import ProtectedError

    make_question(category)
    with pytest.raises(ProtectedError):
        category.delete()
