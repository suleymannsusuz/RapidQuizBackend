"""Oyun motoru: soru seçimi, süre kontrolü ve puanlama.

Bütün kurallar burada ve sunucu saatiyle işler; view'lar yalnızca isteği doğrular.
İstemciden gelen hiçbir süre ya da puan bilgisine güvenilmez.

Eşzamanlı isteklere (çift tıklama, aynı cevabın iki kez gönderilmesi) karşı her işlem,
oturum satırı `select_for_update` ile kilitlenerek tek bir transaction içinde yapılır.
Hata fırlatan yollar, kalıcı olması gereken durum değişikliklerini (ör. süre aşımı
kapatma) geri sarmamak için transaction bloğundan çıktıktan sonra hata fırlatır.
"""

import hashlib
import hmac
import random
import secrets
from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status

from apps.catalog.models import CHOICES_PER_QUESTION, Category, Choice, Question
from apps.core.exceptions import APIError

from .models import QuizSession, SessionQuestion

QUESTIONS_PER_SESSION = 20
TIME_LIMIT_MS = 5000
GRACE_MS = 700  # ağ toleransı: bu süre içinde gelen cevap kabul edilir, bonusu sıfırdır
SESSION_TTL = timedelta(minutes=10)
BASE_POINTS = 100
MAX_SPEED_BONUS = 50


# --- puanlama -----------------------------------------------------------------------------


def calculate_points(response_ms, is_correct):
    """Doğru cevap: 100 + round(50 × max(0, 5000 − t) / 5000); yarımlar yukarı yuvarlanır."""
    if not is_correct:
        return 0
    remaining = max(0, TIME_LIMIT_MS - response_ms)
    bonus = (2 * MAX_SPEED_BONUS * remaining + TIME_LIMIT_MS) // (2 * TIME_LIMIT_MS)
    return BASE_POINTS + bonus


# --- token ----------------------------------------------------------------------------------


def generate_token():
    return secrets.token_urlsafe(32)


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


# --- hatalar --------------------------------------------------------------------------------


def _invalid_token():
    return APIError(
        "invalid_token", "Oturum anahtarı eksik veya yanlış.", status.HTTP_401_UNAUTHORIZED
    )


def _expired():
    return APIError("session_expired", "Oturum süresi doldu.", status.HTTP_410_GONE)


def _mismatch(message="Bu soru, oturumun sıradaki sorusu değil."):
    return APIError("question_mismatch", message, status.HTTP_409_CONFLICT)


# --- oturum başlatma ------------------------------------------------------------------------


def _playable_question_ids(category):
    """Aktif ve geçerli (tam 4 şık, tam 1 doğru) soruların kimlikleri."""
    return list(
        Question.objects.filter(category=category, is_active=True)
        .annotate(
            choice_total=Count("choices"),
            correct_total=Count("choices", filter=Q(choices__is_correct=True)),
        )
        .filter(choice_total=CHOICES_PER_QUESTION, correct_total=1)
        .values_list("id", flat=True)
    )


def start_session(*, category_slug, platform, ip_hash):
    """Yeni oturum açar; (oturum, ham token) döner. Ham token yalnızca burada bilinir."""
    try:
        category = Category.objects.get(slug=category_slug, is_active=True)
    except Category.DoesNotExist:
        raise APIError("not_found", "Kategori bulunamadı.", status.HTTP_404_NOT_FOUND) from None

    question_ids = _playable_question_ids(category)
    if len(question_ids) < QUESTIONS_PER_SESSION:
        raise APIError(
            "category_unavailable",
            "Bu kategoride henüz yeterli soru yok.",
            status.HTTP_409_CONFLICT,
        )

    rng = random.SystemRandom()
    picked = rng.sample(question_ids, QUESTIONS_PER_SESSION)
    choice_ids = defaultdict(list)
    for question_id, choice_id in (
        Choice.objects.filter(question_id__in=picked)
        .order_by("id")
        .values_list("question_id", "id")
    ):
        choice_ids[question_id].append(choice_id)

    token = generate_token()
    with transaction.atomic():
        session = QuizSession.objects.create(
            token_hash=hash_token(token),
            category=category,
            platform=platform,
            ip_hash=ip_hash,
        )
        rows = []
        for position, question_id in enumerate(picked):
            order = list(choice_ids[question_id])
            rng.shuffle(order)
            rows.append(
                SessionQuestion(
                    session=session, question_id=question_id, position=position, choice_order=order
                )
            )
        SessionQuestion.objects.bulk_create(rows)
    return session, token


# --- ortak yardımcılar ----------------------------------------------------------------------


def _expire_if_stale(session_id):
    """10 dakikayı geçen aktif oturumu 'expired' yapar (ayrı, kısa bir güncelleme)."""
    QuizSession.objects.filter(
        pk=session_id,
        status=QuizSession.Status.ACTIVE,
        started_at__lt=timezone.now() - SESSION_TTL,
    ).update(status=QuizSession.Status.EXPIRED)


def _lock_session(session_id, token):
    """Oturumu kilitleyerek getirir, token'ı doğrular. atomic blok içinde çağrılmalı."""
    try:
        session = QuizSession.objects.select_for_update().get(pk=session_id)
    except QuizSession.DoesNotExist:
        raise APIError("not_found", "Oturum bulunamadı.", status.HTTP_404_NOT_FOUND) from None
    if not token or not hmac.compare_digest(session.token_hash, hash_token(token)):
        raise _invalid_token()
    if session.status == QuizSession.Status.EXPIRED:
        raise _expired()
    return session


def _elapsed_ms(served_at, now):
    return (now - served_at) // timedelta(milliseconds=1)


def _current_row(session):
    return SessionQuestion.objects.select_related("question").get(
        session=session, position=session.current_index
    )


def _close_question(session, row, now, *, selected_choice_id, is_correct, points, response_ms):
    """Soruyu kapatır, oturum toplamlarını günceller ve sıradaki soruya geçer."""
    row.answered_at = now
    row.selected_choice_id = selected_choice_id
    row.is_correct = is_correct
    row.points = points
    row.response_ms = response_ms
    row.save(
        update_fields=["answered_at", "selected_choice", "is_correct", "points", "response_ms"]
    )

    session.total_score += points
    session.correct_count += int(is_correct)
    session.total_response_ms += response_ms
    session.current_index += 1
    fields = ["total_score", "correct_count", "total_response_ms", "current_index"]
    if session.current_index >= QUESTIONS_PER_SESSION:
        session.status = QuizSession.Status.FINISHED
        session.finished_at = now
        fields += ["status", "finished_at"]
    session.save(update_fields=fields)


def _close_as_timeout(session, row, now):
    # Süre aşımı her zaman tam süre olarak sayılır; böylece soru atlayarak toplam süre
    # (eşitlik bozmada kullanılır) kısaltılamaz.
    _close_question(
        session,
        row,
        now,
        selected_choice_id=None,
        is_correct=False,
        points=0,
        response_ms=TIME_LIMIT_MS,
    )


def _settle_stale_question(session, now):
    """Sunulmuş ama süresi (5000 + 700 ms) geçmiş mevcut soruyu süre aşımı olarak kapatır."""
    if session.status != QuizSession.Status.ACTIVE:
        return
    row = _current_row(session)
    if row.served_at is not None and _elapsed_ms(row.served_at, now) > TIME_LIMIT_MS + GRACE_MS:
        _close_as_timeout(session, row, now)


# --- soru sunma -----------------------------------------------------------------------------


def serve_question(session_id, token):
    """Sıradaki soruyu verir. İlk istekte süre başlar; tekrarda kalan süre döner."""
    _expire_if_stale(session_id)
    payload = None
    with transaction.atomic():
        session = _lock_session(session_id, token)
        now = timezone.now()
        _settle_stale_question(session, now)

        if session.status == QuizSession.Status.ACTIVE:
            row = _current_row(session)
            if row.served_at is None:
                row.served_at = now
                row.save(update_fields=["served_at"])
            elapsed = _elapsed_ms(row.served_at, now)

            texts = dict(Choice.objects.filter(question=row.question).values_list("id", "text"))
            # Oyun sürerken yönetici bir şıkkı değiştirmiş olabilir: kayıtlı sıra güncel
            # şıklarla süzülür, yeni eklenenler sona konur.
            ordered = [cid for cid in row.choice_order if cid in texts]
            ordered += [cid for cid in texts if cid not in row.choice_order]
            payload = {
                "position": row.position,
                "total_questions": QUESTIONS_PER_SESSION,
                # Doğru şık bilgisi bilerek yok; yalnızca kimlik ve metin.
                "question": {"id": row.question_id, "text": row.question.text},
                "choices": [{"id": cid, "text": texts[cid]} for cid in ordered],
                "time_limit_ms": TIME_LIMIT_MS,
                "remaining_ms": max(0, TIME_LIMIT_MS - elapsed),
                "current_score": session.total_score,
            }

    if payload is None:
        raise APIError("session_finished", "Quiz zaten bitti.", status.HTTP_409_CONFLICT)
    return payload


# --- cevap işleme ---------------------------------------------------------------------------


def submit_answer(session_id, token, question_id, choice_id):
    """Cevabı sunucu saatine göre değerlendirir; `choice_id=None` süre aşımı demektir."""
    _expire_if_stale(session_id)
    with transaction.atomic():
        session = _lock_session(session_id, token)
        now = timezone.now()

        try:
            row = SessionQuestion.objects.get(session=session, question_id=question_id)
        except SessionQuestion.DoesNotExist:
            raise _mismatch() from None
        if row.answered_at is not None:
            raise APIError(
                "already_answered", "Bu soru zaten cevaplanmış.", status.HTTP_409_CONFLICT
            )
        if row.position != session.current_index:
            raise _mismatch()
        if row.served_at is None:
            raise _mismatch("Bu soru henüz sunulmadı.")

        # Şıklar ve doğruluk bilgisi cevap anında güncel veritabanından okunur.
        correctness = dict(
            Choice.objects.filter(question_id=question_id).values_list("id", "is_correct")
        )
        correct_choice_id = next((cid for cid, ok in correctness.items() if ok), None)

        elapsed = _elapsed_ms(row.served_at, now)
        timed_out = choice_id is None or elapsed > TIME_LIMIT_MS + GRACE_MS
        if not timed_out and choice_id not in correctness:
            raise APIError(
                "validation_error",
                "Eksik veya geçersiz alan.",
                status.HTTP_400_BAD_REQUEST,
                {"choice_id": ["Bu şık sorunun şıkları arasında değil."]},
            )
        if timed_out:
            _close_as_timeout(session, row, now)
            points = 0
            is_correct = False
        else:
            is_correct = choice_id == correct_choice_id
            response_ms = min(elapsed, TIME_LIMIT_MS)
            points = calculate_points(response_ms, is_correct)
            _close_question(
                session,
                row,
                now,
                selected_choice_id=choice_id,
                is_correct=is_correct,
                points=points,
                response_ms=response_ms,
            )

        return {
            "is_correct": is_correct,
            "correct_choice_id": correct_choice_id,
            "points": points,
            "total_score": session.total_score,
            "timed_out": timed_out,
            "is_last": row.position == QUESTIONS_PER_SESSION - 1,
        }


# --- sonuç ----------------------------------------------------------------------------------


def get_result(session_id, token):
    """Biten oturumun puan özetini verir."""
    _expire_if_stale(session_id)
    payload = None
    with transaction.atomic():
        session = _lock_session(session_id, token)
        _settle_stale_question(session, timezone.now())
        if session.status != QuizSession.Status.ACTIVE:
            category = session.category
            payload = {
                "status": session.status,
                "category": {"slug": category.slug, "name": category.name},
                "total_questions": QUESTIONS_PER_SESSION,
                "total_score": session.total_score,
                "correct_count": session.correct_count,
                "total_response_ms": session.total_response_ms,
            }

    if payload is None:
        raise APIError("session_not_finished", "Quiz henüz bitmedi.", status.HTTP_409_CONFLICT)
    return payload
