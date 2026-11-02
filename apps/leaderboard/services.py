"""Skor kaydı ve sıralama.

Skor yalnızca bitmiş (`finished`) bir oturumdan, bir kez ve sunucunun hesapladığı puanla
yazılır; istemci yalnızca ismi gönderir.
"""

import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status

from apps.catalog.models import Category
from apps.core.exceptions import APIError
from apps.quiz import services as quiz_services
from apps.quiz.models import QuizSession

from .models import ScoreEntry

logger = logging.getLogger(__name__)

LEADERBOARD_SIZE = 10

# Eşitlik bozma: 1) yüksek puan 2) düşük toplam süre 3) erken bitiren (4: tekrarlanabilirlik).
ORDERING = ("-score", "total_response_ms", "created_at", "id")


def _row(rank, entry):
    return {
        "rank": rank,
        "player_name": entry.player_name,
        "score": entry.score,
        "correct_count": entry.correct_count,
        "created_at": entry.created_at,
    }


def top_entries(category):
    entries = ScoreEntry.objects.filter(category=category).order_by(*ORDERING)[:LEADERBOARD_SIZE]
    return [_row(rank, entry) for rank, entry in enumerate(entries, start=1)]


def rank_of(entry):
    """Aynı kategoride bu kayıttan önce gelen kayıt sayısı + 1."""
    ahead = ScoreEntry.objects.filter(category_id=entry.category_id).filter(
        Q(score__gt=entry.score)
        | Q(score=entry.score, total_response_ms__lt=entry.total_response_ms)
        | Q(
            score=entry.score,
            total_response_ms=entry.total_response_ms,
            created_at__lt=entry.created_at,
        )
        | Q(
            score=entry.score,
            total_response_ms=entry.total_response_ms,
            created_at=entry.created_at,
            id__lt=entry.id,
        )
    )
    return ahead.count() + 1


def is_implausibly_fast(session):
    """Soru başına ortalama cevap süresi, insanın okuyup şık seçebileceğinin altındaysa True.

    Skor şişirme (soru bankasını toplayan bot) önlemidir. `total_response_ms` sunucu
    saatiyle ölçülür (soru sunulduktan cevabın ulaşmasına kadar, ağ gecikmesi dahil) ve
    süre aşımı sorular tam süre (5000 ms) sayılır. Eşik `SCORE_MIN_AVG_RESPONSE_MS`
    ayarıyla değişir; 0 önlemi kapatır.
    """
    minimum = settings.SCORE_MIN_AVG_RESPONSE_MS
    return session.total_response_ms < minimum * quiz_services.QUESTIONS_PER_SESSION


def submit_score(session_id, token, player_name):
    """Biten oturumun puanını isimle kaydeder; sıralamayı ve ilk 10'u döner."""
    quiz_services.expire_if_stale(session_id)
    problem = entry = None
    with transaction.atomic():
        session = quiz_services.lock_session(session_id, token)
        # Son soru terk edilmişse süresi dolduğunda oturum burada bitmiş sayılır.
        quiz_services.settle_stale_question(session, timezone.now())

        if session.status == QuizSession.Status.SUBMITTED:
            problem = APIError(
                "score_already_submitted",
                "Bu oturumun skoru zaten kaydedildi.",
                status.HTTP_409_CONFLICT,
            )
        elif session.status != QuizSession.Status.FINISHED:
            problem = APIError(
                "session_not_finished", "Quiz henüz bitmedi.", status.HTTP_409_CONFLICT
            )
        elif is_implausibly_fast(session):
            logger.warning(
                "Şüpheli skor reddedildi: oturum=%s ortalama=%d ms/soru ip_hash=%s",
                session.id,
                session.total_response_ms // quiz_services.QUESTIONS_PER_SESSION,
                session.ip_hash[:12],
            )
            problem = APIError(
                "score_rejected",
                "Cevapların insan için fazla hızlıydı, skor kaydedilemedi.",
                422,
            )
        else:
            entry = ScoreEntry.objects.create(
                session=session,
                category_id=session.category_id,
                player_name=player_name,
                score=session.total_score,
                correct_count=session.correct_count,
                total_response_ms=session.total_response_ms,
                created_at=session.finished_at,
            )
            session.status = QuizSession.Status.SUBMITTED
            session.save(update_fields=["status"])

    # Hata, transaction dışında fırlatılır: yukarıdaki süre aşımı kapatma geri sarılmasın.
    if problem:
        raise problem

    rank = rank_of(entry)
    return {
        "rank": rank,
        "in_top_10": rank <= LEADERBOARD_SIZE,
        "score": entry.score,
        "leaderboard": top_entries(entry.category_id),
    }


def get_leaderboard(category_slug):
    try:
        category = Category.objects.get(slug=category_slug, is_active=True)
    except Category.DoesNotExist:
        raise APIError("not_found", "Kategori bulunamadı.", status.HTTP_404_NOT_FOUND) from None
    return {
        "category": {"slug": category.slug, "name": category.name},
        "leaderboard": top_entries(category),
    }
