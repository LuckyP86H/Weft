import pytest

from weft.vault import PathEscapeError, Vault, VaultError


def test_iter_notes_skips_obsidian_dir_and_non_markdown(vault_dir):
    names = [p.name for p in Vault(vault_dir).iter_notes()]
    assert names == ["a.md", "b.md", "top.md"]


def test_info(vault_dir):
    info = Vault(vault_dir).info()
    assert info.note_count == 3
    assert info.is_obsidian_vault is True
    assert info.root == str(vault_dir.resolve())


def test_plain_folder_is_not_flagged_as_obsidian_vault(tmp_path):
    assert Vault(tmp_path).info().is_obsidian_vault is False


def test_missing_root_rejected(tmp_path):
    with pytest.raises(VaultError):
        Vault(tmp_path / "nope")


def test_resolve_stays_inside(vault_dir):
    v = Vault(vault_dir)
    assert v.resolve("inbox/a.md") == (vault_dir / "inbox" / "a.md").resolve()


@pytest.mark.parametrize("bad", ["../outside.md", "inbox/../../outside.md", "/etc/passwd"])
def test_resolve_rejects_escapes(vault_dir, bad):
    with pytest.raises(PathEscapeError):
        Vault(vault_dir).resolve(bad)


def test_resolve_rejects_symlink_escape(vault_dir, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (vault_dir / "link").symlink_to(outside)
    with pytest.raises(PathEscapeError):
        Vault(vault_dir).resolve("link/secret.md")
