"""Vault resolution: the --vault flag > env var > config file precedence."""

import json

import pytest

from weft.config import (
    ConfigError,
    resolve_vault,
    save_vault_path,
    user_config_path,
)


def test_cli_flag_wins_over_env_and_file(tmp_path):
    """The CLI flag beats the env var and the config file."""
    cli, env_dir, file_dir = (tmp_path / n for n in ("cli", "env", "file"))
    for d in (cli, env_dir, file_dir):
        d.mkdir()
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"vault_path": str(file_dir)}))

    got = resolve_vault(str(cli), {"WEFT_VAULT": str(env_dir)}, cfg)

    assert got.path == cli.resolve()
    assert got.source == "--vault flag"


def test_env_wins_over_file(tmp_path):
    """The env var beats the config file."""
    env_dir, file_dir = tmp_path / "env", tmp_path / "file"
    env_dir.mkdir()
    file_dir.mkdir()
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"vault_path": str(file_dir)}))

    got = resolve_vault(None, {"WEFT_VAULT": str(env_dir)}, cfg)

    assert got.path == env_dir.resolve()
    assert "WEFT_VAULT" in got.source


def test_falls_back_to_config_file(tmp_path):
    """The config file is used when nothing else is set."""
    vault = tmp_path / "v"
    vault.mkdir()
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"vault_path": str(vault)}))

    assert resolve_vault(None, {}, cfg).path == vault.resolve()


def test_nothing_configured_explains_how_to_fix(tmp_path):
    """No vault anywhere: the error explains how to fix it."""
    with pytest.raises(ConfigError, match="set-vault"):
        resolve_vault(None, {}, tmp_path / "missing.json")


def test_stale_path_after_moving_machines_is_a_clear_error(tmp_path):
    """A config path that no longer exists is a clear error, not a guess."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"vault_path": "/old/laptop/Vault"}))

    with pytest.raises(ConfigError, match="not a directory"):
        resolve_vault(None, {}, cfg)


def test_tilde_is_expanded(tmp_path, monkeypatch):
    """~/ paths are expanded before validation."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Vault").mkdir()

    got = resolve_vault("~/Vault", {}, tmp_path / "none.json")

    assert got.path == (tmp_path / "Vault").resolve()


def test_save_vault_path_round_trips_and_keeps_other_keys(tmp_path):
    """Saving the vault keeps other config keys and reads back."""
    vault = tmp_path / "v"
    vault.mkdir()
    cfg = tmp_path / "nested" / "config.json"
    cfg.parent.mkdir()
    cfg.write_text(json.dumps({"other": 1}))

    save_vault_path(cfg, vault)

    assert json.loads(cfg.read_text()) == {"other": 1, "vault_path": str(vault.resolve())}
    assert resolve_vault(None, {}, cfg).path == vault.resolve()


def test_save_refuses_nonexistent_vault(tmp_path):
    """Refuse to save a vault path that isn't a directory."""
    with pytest.raises(ConfigError):
        save_vault_path(tmp_path / "config.json", tmp_path / "nope")
    assert not (tmp_path / "config.json").exists()


def test_corrupt_config_file_is_reported(tmp_path):
    """A corrupt config file is reported, not silently ignored."""
    cfg = tmp_path / "config.json"
    cfg.write_text("{not json")
    with pytest.raises(ConfigError, match="not valid JSON"):
        resolve_vault(None, {}, cfg)


def test_user_config_path_override_and_xdg(tmp_path):
    """WEFT_CONFIG overrides; otherwise XDG_CONFIG_HOME is honored."""
    assert user_config_path({"WEFT_CONFIG": "~/x.json"}).name == "x.json"
    got = user_config_path({"XDG_CONFIG_HOME": str(tmp_path)})
    assert got == tmp_path / "weft" / "config.json"
