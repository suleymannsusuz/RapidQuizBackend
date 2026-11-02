"""Oyuncu adları için basit Türkçe + İngilizce küfür/hakaret filtresi.

Bilerek küçük tutulmuş bir listedir; yönetici panelinden uygunsuz skorlar silinebilir.
Eşleştirme "Scunthorpe sorunu"nu (masum sözcüklerin içinde geçen küfür parçaları) azaltmak
için ikiye ayrılır:

* `SUBSTRING_WORDS`: ayırt edici, uzun sözcükler; boşluk/_ atılmış metnin içinde aranır.
* `EXACT_WORDS`: kısa ya da masum sözcüklerin içinde geçebilen kelimeler; yalnızca
  boşluk/_ ile ayrılmış bir sözcüğün tamamı eşleşirse sayılır.

Metin eşleştirmeden önce Türkçe harfleri ASCII'ye indirir, sık görülen rakam ikamelerini
(1→i, 3→e, 4→a, 5→s, 7→t, 0→o) çözer ve art arda tekrarlanan harfleri (fuuuck) sadeleştirir.
"""

import re
import unicodedata

_ASCII_FOLD = str.maketrans(
    {"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u"}
)
_LEET = str.maketrans("013457", "oieast")

SUBSTRING_WORDS = {
    # Türkçe
    "orospu",
    "oruspu",
    "siktir",
    "sikerim",
    "sikeyim",
    "pezevenk",
    "kahpe",
    "gotveren",
    # İngilizce
    "fuck",
    "bitch",
    "asshole",
    "bastard",
    "pussy",
    "whore",
    "nigger",
    "faggot",
    "dickhead",
    "cocksucker",
}

EXACT_WORDS = {
    # Türkçe
    "amk",
    "aq",
    "sik",
    "sikik",
    "ibne",
    "yarak",
    "yarrak",
    "amcik",
    "gavat",
    "pust",
    # İngilizce
    "ass",
    "cunt",
    "slut",
    "nigga",
    "dick",
    "cock",
    "cum",
    "tits",
    "fag",
    "rape",
    "shit",
    "porn",
}


def _collapse(text):
    """Art arda tekrar eden harfleri teke indirir (siiiik -> sik)."""
    return re.sub(r"(.)\1+", r"\1", text)


def _squeeze(text):
    """3 ve üzeri tekrarı 2'ye indirir; çift harfli sözcükler (nigger) için."""
    return re.sub(r"(.)\1{2,}", r"\1\1", text)


def _fold(text):
    """NFKC, küçük harf ve Türkçe karakterleri ASCII'ye indirme (rakamlara dokunmaz)."""
    text = unicodedata.normalize("NFKC", text).replace("İ", "i").replace("I", "i").lower()
    return text.translate(_ASCII_FOLD)


def _matches(word, candidate_squeezed, candidate_collapsed):
    """Sözcük, adayın yazıldığı gibi ya da (çift harf içermiyorsa) tekrarsız hâliyle eşleşir."""
    if word == candidate_squeezed:
        return True
    return word == _collapse(word) and word == candidate_collapsed


def contains_profanity(name):
    """İsim küfür içeriyorsa True. Rakamlar hem harf yerine (s1ktir) hem de süs olarak
    (amk123) sayılabileceğinden iki varyant denenir."""
    folded = _fold(name)
    variants = (folded.translate(_LEET), re.sub(r"\d+", "", folded))
    return any(_check(variant) for variant in variants)


def _check(text):
    tokens = [token for token in re.split(r"[ _]+", text) if token]

    for token in tokens:
        squeezed, collapsed = _squeeze(token), _collapse(token)
        if any(_matches(word, squeezed, collapsed) for word in EXACT_WORDS):
            return True

    joined = "".join(tokens)
    squeezed, collapsed = _squeeze(joined), _collapse(joined)
    for word in SUBSTRING_WORDS:
        if word in squeezed or (word == _collapse(word) and word in collapsed):
            return True
    return False
