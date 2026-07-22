from pathlib import Path
import sys

from app_paths import APP_DIR_NAME, writable_data_dir


def test_source_mode_uses_project_directory(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert writable_data_dir() == Path(__file__).resolve().parent


def test_frozen_windows_uses_local_app_data_and_migrates_legacy_files(
    monkeypatch,
    tmp_path,
):
    local_app_data = tmp_path / "LocalAppData"
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    (legacy_dir / "data.json").write_text('{"schema_version": 3}', encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", str(legacy_dir / "WIT-Combat-Manager.exe"))
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    result = writable_data_dir()

    assert result == local_app_data / APP_DIR_NAME
    assert (result / "data.json").read_text(encoding="utf-8") == '{"schema_version": 3}'

    (result / "data.json").write_text("new", encoding="utf-8")
    assert writable_data_dir().joinpath("data.json").read_text(encoding="utf-8") == "new"
