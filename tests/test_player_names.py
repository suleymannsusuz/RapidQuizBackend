import pytest

from apps.leaderboard.profanity import contains_profanity
from apps.leaderboard.validators import InvalidPlayerName, validate_player_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Ayşe", "Ayşe"),
        ("Mert_34", "Mert_34"),
        ("Ömer Çağlar", "Ömer Çağlar"),
        ("İlker", "İlker"),
        ("Işık", "Işık"),
        ("ab", "ab"),
        ("a" * 20, "a" * 20),
        ("  Ali  ", "Ali"),
        ("Zeynep    Su", "Zeynep Su"),
        ("Ali Veli", "Ali Veli"),  # kesmeyen boşluk normal boşluğa çevrilir
    ],
)
def test_valid_names_are_accepted_and_normalized(raw, expected):
    assert validate_player_name(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "a",
        "a" * 21,
        "<script>alert(1)</script>",
        "Ali<b>",
        "Ali!",
        "ali@x.com",
        "Ali-Veli",
        "a\nb",
        "a\tb",
        "___",
        "  _ ",
        "Ali​",  # sıfır genişlikli boşluk
        "Ali😀",
        "Robert'); DROP TABLE--",
    ],
)
def test_invalid_names_are_rejected(raw):
    with pytest.raises(InvalidPlayerName):
        validate_player_name(raw)


def test_length_limit_applies_after_normalization():
    assert validate_player_name("  " + "a" * 20 + "  ") == "a" * 20
    with pytest.raises(InvalidPlayerName):
        validate_player_name("a" * 10 + "   " + "b" * 10)  # tek boşluğa inse de 21 karakter


@pytest.mark.parametrize(
    "name",
    [
        "amk",
        "AMK",
        "Amk123",
        "aaamk",
        "aq",
        "Siktir",
        "SİKTİR",
        "S1KT1R",
        "xxsiktirxx",
        "siiiiktir",
        "Orospu_cocugu",
        "ibne",
        "yarrak",
        "yarak",
        "FUCK",
        "fuuuuck",
        "F u c k",
        "fu_ck",
        "N1gg3r",
        "niggggger",
        "nigga",
        "Sh1t",
        "dick",
        "Cunt",
        "Big Asshole",
    ],
)
def test_profanity_is_detected(name):
    assert contains_profanity(name)
    with pytest.raises(InvalidPlayerName):
        validate_player_name(name)


@pytest.mark.parametrize(
    "name",
    [
        "Ayşe",
        "Mert34",
        "Ali10",
        "Scunthorpe",  # içinde "cunt" geçer
        "Niger",
        "Nigar",
        "Class",
        "Bass",
        "Assassin",
        "Analiz",
        "Kamkat",  # içinde "amk" geçer
        "Amina",
        "Sikke",
        "Slutsky",
        "Shiitake",
        "Cocktail",
        "Peacock",
        "Dickens",
        "Rapeseed",
        "Asena",
        "Aqua",
        "As",
        "Mustafa Kemal",
        "Hancock",
    ],
)
def test_innocent_names_are_not_flagged(name):
    assert not contains_profanity(name)
    assert validate_player_name(name)
