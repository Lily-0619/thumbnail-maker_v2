from core.text_renderer import detect_language_category


def test_detect_language_category_current_behavior():
    assert detect_language_category("ひらがな") == "ja"
    assert detect_language_category("カタカナ") == "ja"
    assert detect_language_category("한글") == "ko"
    assert detect_language_category("кириллица") == "ru"
    assert detect_language_category("漢字") == "zh"
    assert detect_language_category("abc123") == "en"
    assert detect_language_category("かな漢字") == "ja"
