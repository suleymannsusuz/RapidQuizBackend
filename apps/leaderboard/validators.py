import re
import unicodedata

from .profanity import contains_profanity

NAME_MIN = 2
NAME_MAX = 20

# Harf, rakam, boşluk ve alt çizgi; HTML/özel karakter ve görünmez karakterler girmez.
_ALLOWED = re.compile(r"^[\w ]+$")


class InvalidPlayerName(ValueError):
    """İsim kurallara uymuyor; mesaj doğrudan kullanıcıya gösterilebilir."""


def normalize_player_name(raw):
    name = unicodedata.normalize("NFKC", raw).strip()
    return re.sub(" {2,}", " ", name)


def validate_player_name(raw):
    """Adı normalleştirip doğrular; geçerliyse temizlenmiş adı döner."""
    name = normalize_player_name(raw)
    if not NAME_MIN <= len(name) <= NAME_MAX:
        raise InvalidPlayerName(f"İsim {NAME_MIN}–{NAME_MAX} karakter olmalı.")
    if not _ALLOWED.match(name):
        raise InvalidPlayerName("İsimde yalnızca harf, rakam, boşluk ve _ kullanılabilir.")
    if not any(char.isalnum() for char in name):
        raise InvalidPlayerName("İsim en az bir harf ya da rakam içermeli.")
    if contains_profanity(name):
        raise InvalidPlayerName("Bu isim kullanılamaz.")
    return name
