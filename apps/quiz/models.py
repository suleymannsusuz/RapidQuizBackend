import uuid

from django.db import models
from django.db.models import Q


class QuizSession(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Devam ediyor"
        FINISHED = "finished", "Bitti"
        SUBMITTED = "submitted", "Skor kaydedildi"
        EXPIRED = "expired", "Süresi doldu"

    class Platform(models.TextChoices):
        WEB = "web", "Web"
        IOS = "ios", "iOS"
        ANDROID = "android", "Android"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token_hash = models.CharField("token özeti", max_length=64)
    category = models.ForeignKey(
        "catalog.Category", on_delete=models.PROTECT, related_name="sessions"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    current_index = models.PositiveSmallIntegerField(default=0)
    total_score = models.PositiveIntegerField(default=0)
    correct_count = models.PositiveSmallIntegerField(default=0)
    total_response_ms = models.PositiveIntegerField(default=0)
    platform = models.CharField(max_length=10, choices=Platform.choices, default=Platform.WEB)
    ip_hash = models.CharField(max_length=64, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "quiz_sessions"
        verbose_name = "quiz oturumu"
        verbose_name_plural = "quiz oturumları"
        indexes = [models.Index(fields=["status", "started_at"], name="session_status_started")]

    def __str__(self):
        return f"{self.id} ({self.status})"


class SessionQuestion(models.Model):
    session = models.ForeignKey(
        QuizSession, on_delete=models.CASCADE, related_name="session_questions"
    )
    question = models.ForeignKey("catalog.Question", on_delete=models.PROTECT, related_name="+")
    position = models.PositiveSmallIntegerField()
    # Bu oturumdaki şık sırası: şık kimliklerinin listesi. Doküman smallint[] öngörüyordu;
    # JSONField PostgreSQL'de jsonb olur ve SQLite ile de çalışır.
    choice_order = models.JSONField()
    served_at = models.DateTimeField(null=True, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    selected_choice = models.ForeignKey(
        "catalog.Choice", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    is_correct = models.BooleanField(default=False)
    response_ms = models.PositiveIntegerField(default=0)
    points = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "session_questions"
        ordering = ["session_id", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "position"], name="sessionq_unique_position"
            ),
            models.UniqueConstraint(
                fields=["session", "question"], name="sessionq_unique_question"
            ),
            # Soru başına en yüksek puan: 100 + 50 hız bonusu.
            models.CheckConstraint(condition=Q(points__lte=150), name="sessionq_points_max_150"),
        ]

    def __str__(self):
        return f"{self.session_id} #{self.position}"
