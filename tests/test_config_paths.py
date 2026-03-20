from pathlib import Path

from nanobot.config.loader import get_config_path
from nanobot.config.paths import (
    get_bridge_install_dir,
    get_cli_history_path,
    get_cron_dir,
    get_data_dir,
    get_legacy_sessions_dir,
    get_logs_dir,
    get_media_dir,
    get_runtime_subdir,
    get_workspace_path,
)
from nanobot.config.schema import Config


def test_runtime_dirs_follow_config_path(monkeypatch, tmp_path: Path) -> None:
    config_file = tmp_path / "instance-a" / "config.json"
    monkeypatch.setattr("nanobot.config.paths.get_config_path", lambda: config_file)

    assert get_data_dir() == config_file.parent
    assert get_runtime_subdir("cron") == config_file.parent / "cron"
    assert get_cron_dir() == config_file.parent / "cron"
    assert get_logs_dir() == config_file.parent / "logs"


def test_media_dir_supports_channel_namespace(monkeypatch, tmp_path: Path) -> None:
    config_file = tmp_path / "instance-b" / "config.json"
    monkeypatch.setattr("nanobot.config.paths.get_config_path", lambda: config_file)

    assert get_media_dir() == config_file.parent / "media"
    assert get_media_dir("telegram") == config_file.parent / "media" / "telegram"


def test_shared_and_legacy_paths_default_to_global_instance(monkeypatch) -> None:
    monkeypatch.delenv("NANOBOT_HOME", raising=False)
    monkeypatch.delenv("NANOBOT_CONFIG", raising=False)
    monkeypatch.setattr("nanobot.config.loader._current_config_path", None)

    assert get_cli_history_path() == Path.home() / ".nanobot" / "history" / "cli_history"
    assert get_bridge_install_dir() == Path.home() / ".nanobot" / "bridge"
    assert get_legacy_sessions_dir() == Path.home() / ".nanobot" / "sessions"


def test_workspace_path_is_explicitly_resolved(monkeypatch) -> None:
    monkeypatch.delenv("NANOBOT_HOME", raising=False)
    monkeypatch.delenv("NANOBOT_CONFIG", raising=False)
    monkeypatch.setattr("nanobot.config.loader._current_config_path", None)

    assert get_workspace_path() == Path.home() / ".nanobot" / "workspace"
    assert get_workspace_path("~/custom-workspace") == Path.home() / "custom-workspace"


def test_instance_paths_follow_nanobot_home_env(monkeypatch, tmp_path: Path) -> None:
    home_dir = tmp_path / "project-instance"
    monkeypatch.delenv("NANOBOT_CONFIG", raising=False)
    monkeypatch.setenv("NANOBOT_HOME", str(home_dir))
    monkeypatch.setattr("nanobot.config.loader._current_config_path", None)

    assert get_config_path() == home_dir / "config.json"
    assert get_cli_history_path() == home_dir / "history" / "cli_history"
    assert get_bridge_install_dir() == home_dir / "bridge"
    assert get_legacy_sessions_dir() == home_dir / "sessions"
    assert get_workspace_path() == home_dir / "workspace"
    assert Config().workspace_path == home_dir / "workspace"


def test_config_path_prefers_nanobot_config_env(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "dev.json"
    monkeypatch.delenv("NANOBOT_HOME", raising=False)
    monkeypatch.setenv("NANOBOT_CONFIG", str(config_path))
    monkeypatch.setattr("nanobot.config.loader._current_config_path", None)

    assert get_config_path() == config_path
    assert get_workspace_path() == config_path.parent / "workspace"
    assert get_cli_history_path() == config_path.parent / "history" / "cli_history"
    assert get_bridge_install_dir() == config_path.parent / "bridge"
    assert get_legacy_sessions_dir() == config_path.parent / "sessions"
    assert Config().workspace_path == config_path.parent / "workspace"
