from pathlib import Path

import environ
from corsheaders.defaults import default_headers

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
if (BASE_DIR / ".env").exists():
    environ.Env.read_env(BASE_DIR / ".env")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "apps.core",
    "apps.catalog",
    "apps.quiz",
    "apps.leaderboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "tr"
TIME_ZONE = "Europe/Istanbul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Skor şişirmeye karşı: soru başına ortalama cevap süresi bunun altındaysa skor kaydedilmez
# (ms). Gerçek bir oyuncu soruyu okuyup şık seçerken ağ gecikmesi dahil bundan çok daha uzun
# sürer. 0 önlemi kapatır. Bütün ortamlarda aynıdır (üretimde farklı davranış olmasın).
SCORE_MIN_AVG_RESPONSE_MS = env.int("SCORE_MIN_AVG_RESPONSE_MS", default=500)

# Admin varsayılan /admin/ dışında bir yola alınabilir (prodüksiyonda önerilir).
ADMIN_URL = env("ADMIN_URL", default="admin/")

# API çerezsiz ve başlık tabanlıdır: oturum/CSRF doğrulaması yok, yalnızca JSON.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    # IP başına sınırlar (bkz. apps/quiz/throttles.py). Sayaçlar yerel bellekte tutulur:
    # her gunicorn işçisi kendi sayacını sayar, yani gerçek sınır işçi sayısı kadar esner.
    "DEFAULT_THROTTLE_RATES": {
        "session_start": "10/min",
        "answer": "120/min",
        "question": "240/min",
        "score": "20/hour",
        "leaderboard": "120/min",
    },
    # Önündeki güvenilir vekil sayısı; 0 ise yalnızca REMOTE_ADDR kullanılır. X-Forwarded-For
    # istemci tarafından sahtelenebilir, bu yüzden sayı gerçek altyapıya göre ayarlanmalı.
    "NUM_PROXIES": env.int("NUM_PROXIES", default=0),
}

# Web istemcisinin özel oturum başlığını gönderebilmesi için (CORS ön kontrolü).
CORS_ALLOW_HEADERS = (*default_headers, "x-session-token")

SPECTACULAR_SETTINGS = {
    "TITLE": "Rapid Quiz API",
    "DESCRIPTION": "Rapid Quiz web ve mobil istemcilerinin ortak REST API'si.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}
