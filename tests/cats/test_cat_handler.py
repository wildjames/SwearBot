import json
import pytest
import types
from balaambot.cats.cat_handler import CatHandler, Cat
from balaambot.cats import cat_handler

@pytest.fixture
def patch_save_file(monkeypatch, tmp_path):
    # Patch SAVE_FILE to a temp file
    save_file = tmp_path / "cats.json"
    monkeypatch.setattr(cat_handler, "SAVE_FILE", save_file)
    return save_file

@pytest.fixture
def patch_logger(monkeypatch):
    dummy_logger = types.SimpleNamespace(
        info=lambda *a, **k: None,
        exception=lambda *a, **k: None,
    )
    monkeypatch.setattr(cat_handler, "logger", dummy_logger)
    return dummy_logger

def test_init_no_file(patch_save_file, patch_logger):
    handler = CatHandler()
    assert handler.cats == {}
    assert handler.get_num_cats() == 0

def test_init_with_valid_file(patch_save_file, patch_logger):
    cats_data = {"mittens": {"name": "Mittens"}}
    patch_save_file.write_text(json.dumps(cats_data))
    handler = CatHandler()
    assert "mittens" in handler.cats
    assert handler.cats["mittens"].name == "Mittens"

def test_init_with_invalid_json(patch_save_file, monkeypatch):
    patch_save_file.write_text("{not valid json")
    logged = {}
    def fake_exception(msg, *a, **k): logged["called"] = True
    monkeypatch.setattr(cat_handler, "logger", types.SimpleNamespace(
        info=lambda *a, **k: None,
        exception=fake_exception,
    ))
    handler = CatHandler()
    assert handler.cats == {}
    assert logged.get("called")

def test_add_cat_creates_and_persists(patch_save_file, patch_logger):
    handler = CatHandler()
    handler.add_cat("Whiskers")
    assert handler.get_cat("whiskers") == "Whiskers"
    # File should exist and contain the cat
    with patch_save_file.open() as f:
        data = json.load(f)
    assert "whiskers" in data
    assert data["whiskers"]["name"] == "Whiskers"

def test_add_cat_normalizes_id(patch_save_file, patch_logger):
    handler = CatHandler()
    handler.add_cat("  Fluffy  ")
    assert handler.get_cat("fluffy") == "  Fluffy  "
    assert handler.get_cat("  FLUFFY") == "  Fluffy  "
    assert handler.get_cat("FlUfFy") == "  Fluffy  "
    assert handler.get_cat("other") is None

def test_get_cat_names(patch_save_file, patch_logger):
    handler = CatHandler()
    handler.add_cat("A")
    handler.add_cat("B")
    names = handler.get_cat_names()
    assert "- A" in names
    assert "- B" in names
    assert names.count("- ") == 2

def test_get_num_cats(patch_save_file, patch_logger):
    handler = CatHandler()
    assert handler.get_num_cats() == 0
    handler.add_cat("X")
    handler.add_cat("Y")
    assert handler.get_num_cats() == 2

def test_save_creates_file_if_missing(patch_save_file, patch_logger):
    handler = CatHandler()
    handler.add_cat("Zed")
    assert patch_save_file.exists()
    with patch_save_file.open() as f:
        data = json.load(f)
    assert "zed" in data

def test_get_cat_id_normalization(patch_save_file, patch_logger):
    handler = CatHandler()
    assert handler._get_cat_id("  Foo  ") == "foo"
    assert handler._get_cat_id("BAR") == "bar"
