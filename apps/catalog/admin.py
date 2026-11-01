from django import forms
from django.contrib import admin
from django.forms.models import BaseInlineFormSet

from .models import CHOICES_PER_QUESTION, Category, Choice, Question


class ChoiceInlineFormSet(BaseInlineFormSet):
    """Her soruda tam 4 şık ve tam 1 doğru şık olmalı."""

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        kept = [
            form.cleaned_data
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]
        if len(kept) != CHOICES_PER_QUESTION:
            raise forms.ValidationError(f"Her sorunun tam {CHOICES_PER_QUESTION} şıkkı olmalı.")
        if sum(1 for data in kept if data.get("is_correct")) != 1:
            raise forms.ValidationError("Tam olarak bir şık doğru olarak işaretlenmeli.")


class ChoiceInline(admin.TabularInline):
    model = Choice
    formset = ChoiceInlineFormSet
    extra = CHOICES_PER_QUESTION
    min_num = CHOICES_PER_QUESTION
    max_num = CHOICES_PER_QUESTION
    validate_min = True


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "color", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "category", "difficulty", "is_active")
    list_filter = ("category", "difficulty", "is_active")
    search_fields = ("text",)
    inlines = [ChoiceInline]
