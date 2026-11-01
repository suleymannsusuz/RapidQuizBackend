FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# Önce bağımlılıklar: kod değişince bu katman önbellekten gelir
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Admin'in statik dosyaları imaja gömülür, whitenoise sunar
RUN SECRET_KEY=build-only DJANGO_SETTINGS_MODULE=config.settings.prod \
    python manage.py collectstatic --noinput

RUN useradd --create-home appuser
USER appuser

EXPOSE 8080
CMD gunicorn config.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --timeout 30 --access-logfile -
