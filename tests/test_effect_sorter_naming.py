from pathlib import Path

import pytest

from tools.effect_sorter import naming


def test_validate_accepts_valid_tokens():
    naming.validate("WS", "back", "lotus_glow", "spark-01")


@pytest.mark.parametrize(
    "args",
    [
        ("", "back", "lotus", "glow"),
        ("WS", "", "lotus", "glow"),
        ("WS", "back", "", "glow"),
        ("WS", "back", "lotus", ""),
        ("WS", "side", "lotus", "glow"),
        ("W S", "back", "lotus", "glow"),
        ("ウォリ", "back", "lotus", "glow"),
        ("WS!", "back", "lotus", "glow"),
    ],
)
def test_validate_rejects_invalid_tokens(args):
    with pytest.raises(naming.ValidationError):
        naming.validate(*args)


def test_next_sequence_returns_one_when_no_matching_files(tmp_path: Path):
    (tmp_path / "other__back__lotus__glow__001.png").write_bytes(b"")
    assert naming.next_sequence(tmp_path, "WS", "back", "lotus", "glow") == 1


def test_next_sequence_continues_after_existing_files(tmp_path: Path):
    (tmp_path / "WS__back__lotus__glow__001.png").write_bytes(b"")
    (tmp_path / "WS__back__lotus__glow__009.png").write_bytes(b"")
    (tmp_path / "WS__front__lotus__glow__999.png").write_bytes(b"")
    assert naming.next_sequence(tmp_path, "WS", "back", "lotus", "glow") == 10


def test_next_sequence_rolls_over_after_999(tmp_path: Path):
    (tmp_path / "WS__back__lotus__glow__999.png").write_bytes(b"")
    assert naming.next_sequence(tmp_path, "WS", "back", "lotus", "glow") == 1000


def test_format_sequence_and_build_filename():
    assert naming.format_sequence(7) == "007"
    assert naming.format_sequence(1000) == "1000"
    assert naming.build_filename("WS", "back", "lotus", "glow", 7) == "WS__back__lotus__glow__007.png"
