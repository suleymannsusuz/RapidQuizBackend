from django.db import models
from django.utils import timezone


class ScoreEntry(models.Model):
    # Bir oturum tek skor yazar. PROTECT: oturumlar temizlenirken skor tablosu silinmesin.
    session = models.OneToOneField(
        "quiz.QuizSession", on_delete=models.PROTECT, related_name="score_entry"
    )
    category = models.ForeignKey(
        "catalog.Category", on_delete=models.PROTECT, related_name="score_entries"
    )
    player_name = models.CharField("oyuncu", max_length=20)
    score = models.PositiveIntegerField("puan")
    correct_count = models.PositiveSmallIntegerField("doğru sayısı")
    total_response_ms = models.PositiveIntegerField("toplam süre (ms)")
    # Oynanış bitiş zamanı: eşitlikte "daha erken bitiren" önce gelir. İsim sonradan
    # girilse bile sıralama bundan etkilenmesin diye otomatik değil, bilerek elle verilir.
    created_at = models.DateTimeField("oynanma zamanı", default=timezone.now)

    class Meta:
        db_table = "score_entries"
        verbose_name = "skor"
        verbose_name_plural = "skorlar"
        indexes = [
            # İlk 10 sorgusu ve sıra hesabı için (bkz. proje dokümanı, bölüm 6).
            models.Index(
                fields=["category", "-score", "total_response_ms", "created_at"],
                name="score_leaderboard_idx",
            ),
        ]

    def __str__(self):
        return f"{self.player_name}: {self.score}"
