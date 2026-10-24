import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "source_encoding_preflight",
    Path(__file__).resolve().parents[3] / "scripts/check_utf8_sources.py",
)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


def test_utf8_preflight_accepts_unicode_sources_and_ignores_binary_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(CHECK, "ROOT", tmp_path)
    monkeypatch.setattr(CHECK, "FOLDERS", ("src",))
    (tmp_path / "src").mkdir()
    (tmp_path / "src/example.tsx").write_text('const title = "UAE · رقم";', encoding="utf-8")
    (tmp_path / "src/image.png").write_bytes(b"\x89PNG\xff")
    CHECK.ensure_utf8()


@pytest.mark.parametrize("suffix", [".tsx", ".py"])
def test_utf8_preflight_reports_a_legacy_character_without_rewriting_it(
    tmp_path, monkeypatch, suffix
):
    monkeypatch.setattr(CHECK, "ROOT", tmp_path)
    monkeypatch.setattr(CHECK, "FOLDERS", ("src",))
    (tmp_path / "src").mkdir()
    path = tmp_path / ("src/example" + suffix)
    content = b'title = "UAE \xb7 input"'
    path.write_bytes(content)
    with pytest.raises(ValueError, match="invalid UTF-8 at byte"):
        CHECK.ensure_utf8()
    assert path.read_bytes() == content
