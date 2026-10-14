"""End to end: launch `weft serve` as a real subprocess and speak MCP over stdio.

This is the same path Claude Code / Claude Desktop use, so it proves the
vault location is picked up from each configuration channel.
"""

import sys

from mcp import Client, StdioServerParameters

from weft.cli import main


def _params(*extra_args, env=None):
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "weft", "serve", *extra_args],
        env=env,
    )


async def _vault_root(params):
    async with Client(params) as client:
        result = await client.call_tool("weft_vault_info", {})
    return result.structured_content["root"]


async def test_serve_with_vault_flag(vault_dir):
    """The --vault flag reaches the server over real stdio."""
    assert await _vault_root(_params("--vault", str(vault_dir))) == str(vault_dir.resolve())


async def test_serve_with_env_var(vault_dir, tmp_path):
    """The WEFT_VAULT env var reaches the server over real stdio."""
    # NOTE: env replaces (not extends) the subprocess environment;
    # sys.executable must stay absolute or the child won't start.
    env = {"WEFT_VAULT": str(vault_dir), "WEFT_CONFIG": str(tmp_path / "none.json")}
    assert await _vault_root(_params(env=env)) == str(vault_dir.resolve())


def test_config_set_vault_then_show(vault_dir, tmp_path, monkeypatch, capsys):
    """set-vault persists the path, and show reads it back."""
    monkeypatch.setenv("WEFT_CONFIG", str(tmp_path / "cfg.json"))
    monkeypatch.delenv("WEFT_VAULT", raising=False)

    assert main(["config", "set-vault", str(vault_dir)]) == 0
    assert main(["config", "show"]) == 0

    assert str(vault_dir.resolve()) in capsys.readouterr().out


def test_serve_without_config_fails_fast_with_help(tmp_path, monkeypatch, capsys):
    """No vault configured: fail fast with a helpful message."""
    monkeypatch.setenv("WEFT_CONFIG", str(tmp_path / "none.json"))
    monkeypatch.delenv("WEFT_VAULT", raising=False)

    assert main(["serve"]) == 1
    assert "No vault configured" in capsys.readouterr().err
