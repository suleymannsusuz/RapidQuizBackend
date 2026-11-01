# Rapid Quiz — Backend

Rapid Quiz için Django + Django REST Framework API'si. Tasarım ve kurallar: [`docs/rapid-quiz-proje-dokumani.md`](docs/rapid-quiz-proje-dokumani.md). Geliştirici/Claude Code notları: [`CLAUDE.md`](CLAUDE.md).

## Yerel kurulum (Docker)

```bash
cp .env.example .env
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py load_questions
docker compose exec web python manage.py createsuperuser
```

- API: http://localhost:8000/api/v1/ · Swagger: http://localhost:8000/api/v1/docs/ · Admin: http://localhost:8000/admin/

## Docker'sız çalıştırma

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements-dev.txt
# PostgreSQL yoksa geçici olarak SQLite (Aşama 2'den sonra PostgreSQL gerekir):
set DATABASE_URL=sqlite:///db.sqlite3
python manage.py migrate && python manage.py load_questions
python manage.py runserver
```

## Test ve kod kalitesi

```bash
pytest
ruff check . && ruff format --check .
```

## Soru ekleme

Admin panelinden ya da `data/questions/<kategori-slug>.json` dosyasına ekleyip `python manage.py load_questions` ile. Biçim:

```json
{ "text": "HTTP 404 durum kodu neyi ifade eder?", "difficulty": 1,
  "choices": ["Sunucu hatası", "Kaynak bulunamadı", "Yetkisiz erişim", "Yönlendirme"], "correct": 1 }
```

Sınırlar: soru en fazla 90, şık en fazla 40 karakter; tam 4 şık, tam 1 doğru. Komut tekrar çalıştırılabilir: aynı metinli sorular güncellenir.
