import json

from tools.effect_sorter import words_store


def test_load_returns_empty_structure_for_broken_json(tmp_path, monkeypatch):
    words_json = tmp_path / "words.json"
    words_json.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(words_store.paths, "WORDS_JSON", words_json)

    assert words_store.load() == {"effect1": {}, "effect2": []}


def test_load_returns_empty_structure_for_non_dict_json(tmp_path, monkeypatch):
    words_json = tmp_path / "words.json"
    words_json.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    monkeypatch.setattr(words_store.paths, "WORDS_JSON", words_json)

    assert words_store.load() == {"effect1": {}, "effect2": []}


def test_load_normalizes_wrong_value_types(tmp_path, monkeypatch):
    words_json = tmp_path / "words.json"
    words_json.write_text(json.dumps({"effect1": [], "effect2": {}}), encoding="utf-8")
    monkeypatch.setattr(words_store.paths, "WORDS_JSON", words_json)

    assert words_store.load() == {"effect1": {}, "effect2": []}
