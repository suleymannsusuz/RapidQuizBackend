from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.loader import QuestionDataError, load_categories, load_questions_file
from apps.catalog.models import Category


class Command(BaseCommand):
    help = (
        "data/categories.json ve data/questions/<kategori-slug>.json dosyalarını yükler. "
        "Tekrar çalıştırmak güvenlidir: aynı metinli sorular güncellenir."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-dir",
            default=str(Path(settings.BASE_DIR) / "data"),
            help="categories.json ve questions/ klasörünü içeren dizin (varsayılan: data/)",
        )

    def handle(self, *args, data_dir, **options):
        data_dir = Path(data_dir)
        try:
            result = load_categories(data_dir / "categories.json")
            self.stdout.write(f"Kategoriler: {result.created} yeni, {result.updated} güncellendi")

            files = sorted((data_dir / "questions").glob("*.json"))
            if not files:
                raise CommandError(f"{data_dir / 'questions'} altında soru dosyası yok")
            for path in files:
                try:
                    category = Category.objects.get(slug=path.stem)
                except Category.DoesNotExist:
                    raise CommandError(
                        f"{path.name}: '{path.stem}' slug'lı kategori categories.json'da yok"
                    ) from None
                result = load_questions_file(category, path)
                self.stdout.write(
                    f"{category.name}: {result.created} yeni, {result.updated} güncellendi"
                )
        except QuestionDataError as exc:
            raise CommandError(str(exc)) from None
