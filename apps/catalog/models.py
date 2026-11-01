from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

# 5 saniyede okunabilir uzunluk sınırları (bkz. proje dokümanı, bölüm 4)
QUESTION_TEXT_MAX = 90
CHOICE_TEXT_MAX = 40
CHOICES_PER_QUESTION = 4

hex_color_validator = RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Renk #RRGGBB biçiminde olmalı.")


class Category(models.Model):
    slug = models.SlugField("kısa ad", max_length=50, unique=True)
    name = models.CharField("ad", max_length=60)
    description = models.CharField("açıklama", max_length=200, blank=True)
    color = models.CharField("renk", max_length=7, validators=[hex_color_validator])
    icon = models.CharField("ikon", max_length=40, blank=True)
    sort_order = models.PositiveSmallIntegerField("sıra", default=0)
    is_active = models.BooleanField("aktif", default=True)

    class Meta:
        db_table = "categories"
        ordering = ["sort_order", "id"]
        verbose_name = "kategori"
        verbose_name_plural = "kategoriler"

    def __str__(self):
        return self.name


class Question(models.Model):
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="questions", verbose_name="kategori"
    )
    text = models.CharField("soru", max_length=QUESTION_TEXT_MAX)
    difficulty = models.PositiveSmallIntegerField(
        "zorluk",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(3)],
        help_text="1 = kolay, 3 = zor",
    )
    explanation = models.CharField("açıklama", max_length=200, null=True, blank=True)
    is_active = models.BooleanField("aktif", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "questions"
        ordering = ["category_id", "id"]
        verbose_name = "soru"
        verbose_name_plural = "sorular"
        constraints = [
            models.CheckConstraint(
                condition=Q(difficulty__gte=1, difficulty__lte=3), name="question_difficulty_1_3"
            ),
        ]

    def __str__(self):
        return self.text


class Choice(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="choices", verbose_name="soru"
    )
    text = models.CharField("şık", max_length=CHOICE_TEXT_MAX)
    is_correct = models.BooleanField("doğru şık", default=False)

    class Meta:
        db_table = "choices"
        ordering = ["id"]
        verbose_name = "şık"
        verbose_name_plural = "şıklar"
        constraints = [
            # Soru başına en fazla bir doğru şık; "tam bir" kuralını admin ve
            # load_questions ayrıca doğrular (4 şık + 1 doğru).
            models.UniqueConstraint(
                fields=["question"],
                condition=Q(is_correct=True),
                name="choice_one_correct_per_question",
            ),
        ]

    def __str__(self):
        return self.text
