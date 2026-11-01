"""JSON'dan kategori ve soru yükleme (load_questions komutunun mantığı)."""

import json
from dataclasses import dataclass
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import (
    CHOICE_TEXT_MAX,
    CHOICES_PER_QUESTION,
    QUESTION_TEXT_MAX,
    Category,
    Choice,
    Question,
    hex_color_validator,
)

EXPLANATION_MAX = 200


class QuestionDataError(Exception):
    """Soru ya da kategori dosyasında hatalı veri."""


@dataclass
class LoadResult:
    created: int = 0
    updated: int = 0


def _read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise QuestionDataError(f"{path}: dosya bulunamadı") from None
    except json.JSONDecodeError as exc:
        raise QuestionDataError(f"{path}: geçersiz JSON ({exc})") from None
    if not isinstance(data, list):
        raise QuestionDataError(f"{path}: kök değer bir liste olmalı")
    return data


def validate_question_item(item):
    """Tek bir soru kaydını doğrular, hata varsa mesajla QuestionDataError fırlatır."""
    if not isinstance(item, dict):
        raise QuestionDataError("kayıt bir nesne olmalı")

    text = item.get("text")
    if not isinstance(text, str) or not text.strip():
        raise QuestionDataError("'text' boş olamaz")
    if len(text) > QUESTION_TEXT_MAX:
        raise QuestionDataError(f"soru {len(text)} karakter, en fazla {QUESTION_TEXT_MAX} olabilir")

    difficulty = item.get("difficulty")
    if isinstance(difficulty, bool) or difficulty not in (1, 2, 3):
        raise QuestionDataError("'difficulty' 1, 2 veya 3 olmalı")

    explanation = item.get("explanation")
    if explanation is not None and (
        not isinstance(explanation, str) or len(explanation) > EXPLANATION_MAX
    ):
        raise QuestionDataError(
            f"'explanation' en fazla {EXPLANATION_MAX} karakterlik metin olmalı"
        )

    choices = item.get("choices")
    if not isinstance(choices, list) or len(choices) != CHOICES_PER_QUESTION:
        raise QuestionDataError(f"'choices' tam {CHOICES_PER_QUESTION} şık içermeli")
    for choice in choices:
        if not isinstance(choice, str) or not choice.strip():
            raise QuestionDataError("şıklar boş olamaz")
        if len(choice) > CHOICE_TEXT_MAX:
            raise QuestionDataError(
                f"şık '{choice}' {len(choice)} karakter, en fazla {CHOICE_TEXT_MAX} olabilir"
            )
    if len(set(choices)) != len(choices):
        raise QuestionDataError("şıklar birbirinden farklı olmalı")

    correct = item.get("correct")
    if isinstance(correct, bool) or not isinstance(correct, int) or not 0 <= correct < len(choices):
        raise QuestionDataError(
            f"'correct' 0 ile {len(choices) - 1} arasında bir şık sırası olmalı"
        )


def validate_questions_file(path):
    """Dosyadaki tüm soruları doğrular ve liste olarak döner (veritabanına dokunmaz)."""
    items = _read_json(path)
    seen = set()
    for index, item in enumerate(items, start=1):
        try:
            validate_question_item(item)
            if item["text"] in seen:
                raise QuestionDataError("aynı soru dosyada birden fazla kez geçiyor")
            seen.add(item["text"])
        except QuestionDataError as exc:
            raise QuestionDataError(f"{path} #{index}: {exc}") from None
    return items


def load_categories(path):
    items = _read_json(path)
    result = LoadResult()
    with transaction.atomic():
        for index, item in enumerate(items, start=1):
            try:
                slug = item["slug"]
                color = item["color"]
                hex_color_validator(color)
                defaults = {
                    "name": item["name"],
                    "description": item.get("description", ""),
                    "color": color,
                    "icon": item.get("icon", ""),
                    "sort_order": item.get("sort_order", index),
                    "is_active": item.get("is_active", True),
                }
            except (KeyError, TypeError, ValidationError) as exc:
                raise QuestionDataError(
                    f"{path} #{index}: kategori verisi hatalı ({exc})"
                ) from None
            _, created = Category.objects.update_or_create(slug=slug, defaults=defaults)
            result.created += created
            result.updated += not created
    return result


def load_questions_file(category, path):
    """Dosyadaki soruları kategoriye yükler; aynı metinli soru güncellenir (idempotent)."""
    items = validate_questions_file(path)
    result = LoadResult()
    with transaction.atomic():
        for item in items:
            question, created = Question.objects.update_or_create(
                category=category,
                text=item["text"],
                defaults={
                    "difficulty": item["difficulty"],
                    "explanation": item.get("explanation"),
                    "is_active": True,
                },
            )
            _sync_choices(question, item["choices"], item["correct"])
            result.created += created
            result.updated += not created
    return result


def _sync_choices(question, texts, correct_index):
    """Mevcut şıkları yerinde günceller; böylece geçmiş oturumlardaki şık kimlikleri korunur."""
    existing = list(question.choices.order_by("id"))
    question.choices.filter(is_correct=True).update(is_correct=False)
    for position, text in enumerate(texts):
        is_correct = position == correct_index
        if position < len(existing):
            choice = existing[position]
            choice.text = text
            choice.is_correct = is_correct
            choice.save(update_fields=["text", "is_correct"])
        else:
            Choice.objects.create(question=question, text=text, is_correct=is_correct)
    for extra in existing[len(texts) :]:
        extra.delete()
