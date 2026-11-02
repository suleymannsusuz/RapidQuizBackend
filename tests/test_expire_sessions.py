import datetime
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.leaderboard.models import ScoreEntry
from apps.quiz.models import QuizSession, SessionQuestion

from .quiz_helpers import Game

pytestmark = pytest.mark.django_db


def make_session(category, status, age):
    session = QuizSession.objects.create(token_hash="x", category=category, status=status)
    QuizSession.objects.filter(pk=session.pk).update(started_at=timezone.now() - age)
    return session


def run(*args):
    out = StringIO()
    call_command("expire_sessions", *args, stdout=out)
    return out.getvalue()


def minutes(count):
    return datetime.timedelta(minutes=count)


def days(count):
    return datetime.timedelta(days=count)


def test_stale_active_sessions_are_marked_expired(category):
    stale = make_session(category, QuizSession.Status.ACTIVE, minutes(11))
    fresh = make_session(category, QuizSession.Status.ACTIVE, minutes(5))

    output = run()

    stale.refresh_from_db()
    fresh.refresh_from_db()
    assert stale.status == QuizSession.Status.EXPIRED
    assert fresh.status == QuizSession.Status.ACTIVE
    assert "1 oturum expired yapıldı" in output


def test_old_unsubmitted_sessions_are_deleted_with_their_questions(api_client, playable_category):
    Game(api_client)  # yarım bırakılmış
    Game(api_client).finish()  # bitmiş ama ismi hiç kaydedilmemiş
    QuizSession.objects.update(started_at=timezone.now() - days(8))

    output = run()

    assert QuizSession.objects.count() == 0
    assert SessionQuestion.objects.count() == 0
    assert "2 oturum silindi" in output


def test_sessions_younger_than_the_retention_period_are_kept(category):
    expired_recently = make_session(category, QuizSession.Status.EXPIRED, days(2))

    run()

    assert QuizSession.objects.filter(pk=expired_recently.pk).exists()


def test_custom_retention_days(category):
    session = make_session(category, QuizSession.Status.EXPIRED, days(2))

    run("--days", "1")

    assert not QuizSession.objects.filter(pk=session.pk).exists()


def test_sessions_with_a_saved_score_are_never_deleted(api_client, playable_category):
    game = Game(api_client)
    game.finish()
    game.submit_score("Kalıcı")
    QuizSession.objects.update(started_at=timezone.now() - days(365))

    run("--days", "0")

    assert QuizSession.objects.filter(pk=game.session_id).exists()
    assert ScoreEntry.objects.count() == 1


def test_dry_run_changes_nothing(category):
    stale = make_session(category, QuizSession.Status.ACTIVE, days(30))

    output = run("--dry-run")

    stale.refresh_from_db()
    assert stale.status == QuizSession.Status.ACTIVE
    assert "[deneme]" in output
    assert "1 oturum silinecek" in output
