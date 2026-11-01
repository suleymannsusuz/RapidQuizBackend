from .base import *  # noqa: F403
from .base import MIDDLEWARE, env

DEBUG = True
# Geliştirmede statik dosyaları runserver sunar; staticfiles/ klasörü gerekmez.
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]
SECRET_KEY = env("SECRET_KEY", default="dev-only-insecure-key")
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://rapidquiz:rapidquiz@localhost:5432/rapidquiz",
    )
}

# Vite geliştirme sunucusu
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:5173", "http://127.0.0.1:5173"],
)
