import json
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.loader import QuestionDataError, validate_question_item, validate_questions_file
from apps.catalog.models import Category, Choice, Question

DATA_DIR = Path(settings.BASE_DIR) / "data"
QUESTION_FILES = sorted((DATA_DIR / "questions").glob("*.json"))


def valid_item(**overrides):
    item = {
        "text": "HTTP 404 durum kodu neyi ifade eder?",
        "difficulty": 1,
        "choices": ["Kaynak bulunamadı", "Sunucu hatası", "Yetkisiz erişim", "Yönlendirme"],
        "correct": 0,
    }
    item.update(overrides)
    return item


def test_there_is_one_file_per_category():
    categories = {
        item["slug"] for item in json.loads((DATA_DIR / "categories.json").read_text("utf-8"))
    }
    assert {path.stem for path in QUESTION_FILES} == categories
    assert len(categories) == 5


@pytest.mark.parametrize("path", QUESTION_FILES, ids=lambda p: p.stem)
def test_shipped_question_files_are_valid(path):
    items = validate_questions_file(path)
    assert len(items) >= 25


@pytest.mark.parametrize(
    "overrides",
    [
        {"text": ""},
        {"text": "a" * 91},
        {"difficulty": 0},
        {"difficulty": 4},
        {"difficulty": True},
        {"choices": ["A", "B", "C"]},
        {"choices": ["A", "B", "C", "x" * 41]},
        {"choices": ["A", "A", "C", "D"]},
        {"choices": ["A", "B", "C", ""]},
        {"correct": 4},
        {"correct": -1},
        {"correct": "0"},
        {"explanation": "x" * 201},
    ],
)
def test_invalid_items_are_rejected(overrides):
    with pytest.raises(QuestionDataError):
        validate_question_item(valid_item(**overrides))


def test_valid_item_is_accepted():
    validate_question_item(valid_item())
    validate_question_item(valid_item(text="a" * 90, explanation="x" * 200))


@pytest.mark.django_db
def test_load_questions_command_populates_database():
    call_command("load_questions")

    assert Category.objects.count() == 5
    assert list(Category.objects.values_list("slug", flat=True)) == [
        "yazilim",
        "yapay-zeka",
        "bilgisayar-muhendisligi",
        "ulkeler",
        "fizik",
    ]
    total = sum(len(json.loads(p.read_text("utf-8"))) for p in QUESTION_FILES)
    assert Question.objects.count() == total
    for question in Question.objects.prefetch_related("choices"):
        choices = list(question.choices.all())
        assert len(choices) == 4
        assert sum(choice.is_correct for choice in choices) == 1


@pytest.mark.django_db
def test_load_questions_is_idempotent_and_keeps_choice_ids():
    call_command("load_questions")
    question_count = Question.objects.count()
    choice_ids = set(Choice.objects.values_list("id", flat=True))

    call_command("load_questions")

    assert Question.objects.count() == question_count
    assert set(Choice.objects.values_list("id", flat=True)) == choice_ids


@pytest.mark.django_db
def test_reload_updates_correct_choice_in_place(tmp_path):
    (tmp_path / "questions").mkdir()
    (tmp_path / "categories.json").write_text(
        json.dumps([{"slug": "yazilim", "name": "Yazılım", "color": "#3B82F6"}]), "utf-8"
    )
    path = tmp_path / "questions" / "yazilim.json"

    path.write_text(json.dumps([valid_item(correct=0)]), "utf-8")
    call_command("load_questions", data_dir=str(tmp_path))
    ids_before = list(Choice.objects.order_by("id").values_list("id", flat=True))

    path.write_text(json.dumps([valid_item(correct=2)]), "utf-8")
    call_command("load_questions", data_dir=str(tmp_path))

    assert list(Choice.objects.order_by("id").values_list("id", flat=True)) == ids_before
    assert Choice.objects.get(is_correct=True).text == "Yetkisiz erişim"


@pytest.mark.django_db
def test_invalid_file_aborts_and_names_the_item(tmp_path):
    (tmp_path / "questions").mkdir()
    (tmp_path / "categories.json").write_text(
        json.dumps([{"slug": "yazilim", "name": "Yazılım", "color": "#3B82F6"}]), "utf-8"
    )
    items = [valid_item(), valid_item(text="İkinci soru?", correct=9)]
    (tmp_path / "questions" / "yazilim.json").write_text(json.dumps(items), "utf-8")

    with pytest.raises(CommandError, match="#2"):
        call_command("load_questions", data_dir=str(tmp_path))

    assert Question.objects.count() == 0


@pytest.mark.django_db
def test_question_file_without_matching_category_fails(tmp_path):
    (tmp_path / "questions").mkdir()
    (tmp_path / "categories.json").write_text("[]", "utf-8")
    (tmp_path / "questions" / "bilinmeyen.json").write_text(json.dumps([valid_item()]), "utf-8")

    with pytest.raises(CommandError, match="bilinmeyen"):
        call_command("load_questions", data_dir=str(tmp_path))


def test_duplicate_text_in_one_file_is_rejected(tmp_path):
    path = tmp_path / "dup.json"
    path.write_text(json.dumps([valid_item(), valid_item()]), "utf-8")
    with pytest.raises(QuestionDataError, match="#2"):
        validate_questions_file(path)
