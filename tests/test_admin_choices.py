import pytest
from django.forms.models import inlineformset_factory

from apps.catalog.admin import ChoiceInline, ChoiceInlineFormSet
from apps.catalog.models import Choice, Question

FormSet = inlineformset_factory(
    Question,
    Choice,
    formset=ChoiceInlineFormSet,
    fields=["text", "is_correct"],
    extra=ChoiceInline.extra,
    min_num=ChoiceInline.min_num,
    max_num=ChoiceInline.max_num,
    validate_min=ChoiceInline.validate_min,
)


def build_data(texts, correct):
    data = {
        "choices-TOTAL_FORMS": str(len(texts)),
        "choices-INITIAL_FORMS": "0",
        "choices-MIN_NUM_FORMS": "4",
        "choices-MAX_NUM_FORMS": "4",
    }
    for index, text in enumerate(texts):
        data[f"choices-{index}-text"] = text
        if index in correct:
            data[f"choices-{index}-is_correct"] = "on"
    return data


@pytest.fixture
def question(category):
    return Question.objects.create(category=category, text="Soru?")


def test_four_choices_with_one_correct_is_valid(question):
    formset = FormSet(build_data(["A", "B", "C", "D"], correct={2}), instance=question)
    assert formset.is_valid(), formset.errors


def test_no_correct_choice_is_rejected(question):
    formset = FormSet(build_data(["A", "B", "C", "D"], correct=set()), instance=question)
    assert not formset.is_valid()
    assert "Tam olarak bir şık" in formset.non_form_errors()[0]


def test_two_correct_choices_are_rejected(question):
    formset = FormSet(build_data(["A", "B", "C", "D"], correct={0, 1}), instance=question)
    assert not formset.is_valid()
    assert "Tam olarak bir şık" in formset.non_form_errors()[0]


def test_fewer_than_four_choices_are_rejected(question):
    formset = FormSet(build_data(["A", "B", "C"], correct={0}), instance=question)
    assert not formset.is_valid()


def test_too_long_choice_is_rejected(question):
    formset = FormSet(build_data(["A", "B", "C", "x" * 41], correct={0}), instance=question)
    assert not formset.is_valid()
