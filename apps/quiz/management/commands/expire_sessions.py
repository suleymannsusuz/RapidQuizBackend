from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.quiz.models import QuizSession
from apps.quiz.services import SESSION_TTL

BATCH_SIZE = 1000


class Command(BaseCommand):
    help = (
        "Süresi geçen aktif oturumları 'expired' yapar ve eski, skoru kaydedilmemiş "
        "oturumları (soruları ve ip_hash dahil) siler. Skoru kaydedilmiş oturumlara dokunmaz. "
        "Oturumlar istek sırasında zaten süresi dolmuş sayıldığından bu komut yalnızca "
        "temizlik içindir ve elle çalıştırılır."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Bu günden eski, skorsuz oturumlar silinir (varsayılan: 7)",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Ne yapılacağını gösterir, değişiklik yapmaz"
        )

    def handle(self, *args, days, dry_run, **options):
        now = timezone.now()
        stale_active = Q(status=QuizSession.Status.ACTIVE, started_at__lt=now - SESSION_TTL)
        to_expire = QuizSession.objects.filter(stale_active)
        purgeable = (
            QuizSession.objects.filter(started_at__lt=now - timedelta(days=days))
            .filter(
                Q(status__in=[QuizSession.Status.EXPIRED, QuizSession.Status.FINISHED])
                | stale_active
            )
            .filter(score_entry__isnull=True)
        )

        if dry_run:
            self.stdout.write(
                f"[deneme] {to_expire.count()} oturum expired yapılacak, "
                f"{purgeable.count()} oturum silinecek"
            )
            return

        expired = to_expire.update(status=QuizSession.Status.EXPIRED)
        deleted = 0
        while True:
            ids = list(purgeable.values_list("pk", flat=True)[:BATCH_SIZE])
            if not ids:
                break
            QuizSession.objects.filter(pk__in=ids).delete()
            deleted += len(ids)
        self.stdout.write(f"{expired} oturum expired yapıldı, {deleted} oturum silindi")
