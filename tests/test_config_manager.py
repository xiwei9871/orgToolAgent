"""Tests for configuration loading and runtime path management."""

from __future__ import annotations

import json
from pathlib import Path

from config.manager import ConfigManager
from config.schema import AppConfig
from utils.paths import RuntimePaths


def test_runtime_paths_use_appdata_root(tmp_path: Path, monkeypatch) -> None:
    """Runtime paths should be created under the APPDATA root."""
    monkeypatch.setenv("APPDATA", str(tmp_path))

    paths = RuntimePaths.from_env("DesktopSmartOrganizer")

    assert paths.root == tmp_path / "DesktopSmartOrganizer"
    assert paths.config_file == paths.root / "config.json"
    assert paths.logs_dir.is_dir()
    assert paths.tasks_dir.is_dir()
    assert paths.automation_dir.is_dir()
    assert paths.automation_state_file == paths.automation_dir / "mail_job_state.json"
    assert paths.mail_inbox_dir.is_dir()


def test_config_manager_returns_defaults_when_file_missing(
    tmp_path: Path, monkeypatch
) -> None:
    """Missing config files should load default settings."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    manager = ConfigManager.for_app("DesktopSmartOrganizer")

    config = manager.load()

    assert isinstance(config, AppConfig)
    assert config.automation.mailbox_address == "chenduanxiwei@163.com"
    assert config.automation.imap_folder == "INBOX"
    assert config.automation.attachment_extensions == [".pdf"]


def test_config_manager_saves_and_reloads_changes(tmp_path: Path, monkeypatch) -> None:
    """Saved configuration should round-trip through JSON."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    manager = ConfigManager.for_app("DesktopSmartOrganizer")

    config = manager.load()
    config.general.archive_root_name = "鎴戠殑妗岄潰褰掓。"
    config.general.desktop_path = "D:/妗岄潰"
    config.invoice.hash_algorithm = "md5"

    manager.save(config)
    reloaded = manager.load()

    assert reloaded.general.archive_root_name == "鎴戠殑妗岄潰褰掓。"
    assert reloaded.general.desktop_path == "D:/妗岄潰"
    assert reloaded.invoice.hash_algorithm == "md5"

    saved_data = json.loads(manager.paths.config_file.read_text(encoding="utf-8"))
    assert saved_data["general"]["archive_root_name"] == "鎴戠殑妗岄潰褰掓。"
    assert saved_data["general"]["desktop_path"] == "D:/妗岄潰"
    assert saved_data["invoice"]["hash_algorithm"] == "md5"


def test_runtime_paths_fall_back_when_primary_root_is_not_writable(
    tmp_path: Path, monkeypatch
) -> None:
    """Runtime paths should fall back to the workspace runtime root if APPDATA is not writable."""
    blocked_root = tmp_path / "blocked-appdata"
    monkeypatch.setenv("APPDATA", str(blocked_root))
    monkeypatch.chdir(tmp_path)

    original_ensure_dirs = RuntimePaths.ensure_dirs

    def fake_ensure_dirs(self: RuntimePaths) -> None:
        if self.root == blocked_root / "DesktopSmartOrganizer":
            raise PermissionError("blocked")
        original_ensure_dirs(self)

    monkeypatch.setattr(RuntimePaths, "ensure_dirs", fake_ensure_dirs)

    paths = RuntimePaths.from_env("DesktopSmartOrganizer")

    assert paths.root == tmp_path / ".runtime" / "DesktopSmartOrganizer"
