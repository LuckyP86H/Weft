"""Shared fixtures for the Weft test suite."""

import pytest


@pytest.fixture
def vault_dir(tmp_path):
    """A small fake Obsidian vault."""
    root = tmp_path / "MyVault"
    (root / ".obsidian").mkdir(parents=True)
    (root / ".obsidian" / "plugin-note.md").write_text("not a user note")
    (root / "inbox").mkdir()
    (root / "inbox" / "a.md").write_text("# a")
    (root / "notes").mkdir()
    (root / "notes" / "b.md").write_text("# b")
    (root / "top.md").write_text("# top")
    (root / "readme.txt").write_text("ignored")
    return root
