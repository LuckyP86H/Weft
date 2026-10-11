import json

from weft.discovery import detect_vaults, obsidian_registry_path


def test_lists_existing_vaults_only(tmp_path):
    real = tmp_path / "Real"
    real.mkdir()
    registry = tmp_path / "obsidian.json"
    registry.write_text(json.dumps({"vaults": {
        "a": {"path": str(real), "ts": 1},
        "b": {"path": str(tmp_path / "Gone"), "ts": 2},
    }}))

    assert detect_vaults(registry) == [real]


def test_missing_or_odd_registry_gives_empty_list(tmp_path):
    assert detect_vaults(tmp_path / "nope.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2]")
    assert detect_vaults(bad) == []
    bad.write_text("not json")
    assert detect_vaults(bad) == []


def test_registry_path_uses_injected_home(tmp_path):
    fake_home = tmp_path / "home"
    got = obsidian_registry_path(env={}, home=fake_home)
    assert str(got).startswith(str(fake_home))
    assert got.name == "obsidian.json"
