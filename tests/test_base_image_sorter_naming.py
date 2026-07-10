from pathlib import Path

import pytest

from tools.base_image_sorter import naming


def test_validate_accepts_valid_tokens():
    naming.validate("Forest_of_Seclusion", "day")


@pytest.mark.parametrize(
    "args",
    [
        ("", "day"),
        ("Forest", ""),
        ("Forest", "dawn"),
        ("Forest Name", "day"),
        ("リンチ農場", "day"),
        ("Forest!", "day"),
    ],
)
def test_validate_rejects_invalid_tokens(args):
    with pytest.raises(naming.ValidationError):
        naming.validate(*args)


def test_next_sequence_returns_one_when_no_matching_files(tmp_path: Path):
    (tmp_path / "Other_day_001.png").write_bytes(b"")
    assert naming.next_sequence(tmp_path, "Forest", "day") == 1


def test_next_sequence_continues_after_existing_files(tmp_path: Path):
    (tmp_path / "Forest_day_001.png").write_bytes(b"")
    (tmp_path / "Forest_day_009.png").write_bytes(b"")
    (tmp_path / "Forest_night_999.png").write_bytes(b"")
    assert naming.next_sequence(tmp_path, "Forest", "day") == 10


def test_next_sequence_rolls_over_after_999(tmp_path: Path):
    (tmp_path / "Forest_day_999.png").write_bytes(b"")
    assert naming.next_sequence(tmp_path, "Forest", "day") == 1000


def test_format_sequence_and_build_filename():
    assert naming.format_sequence(7) == "007"
    assert naming.format_sequence(1000) == "1000"
    assert naming.build_filename("Forest", "day", 7) == "Forest_day_007.png"
