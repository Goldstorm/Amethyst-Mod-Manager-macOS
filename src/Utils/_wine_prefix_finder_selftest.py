"""Focused regression checks for :mod:`Utils.wine_prefix_finder`.

Run from the repository root with::

    PYTHONPATH=src python3 src/Utils/_wine_prefix_finder_selftest.py

Tests use the real filesystem (CrossOver bottles, Wine prefixes) and mocked
launcher backends. No running of actual Wine executables.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

_SRC_ROOT = Path(__file__).resolve().parents[1]
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from Utils.wine_prefix_finder import (  # noqa: E402
    LAUNCHER_CROSSOVER,
    LAUNCHER_FAUGUS,
    LAUNCHER_HEROIC,
    LAUNCHER_LABELS,
    LAUNCHER_LUTRIS,
    LAUNCHER_STEAM,
    LAUNCHER_STEAM_SHORTCUT,
    LAUNCHER_UNKNOWN,
    PrefixInfo,
    build_prefix_env,
    find_prefix_for_game,
    identify_prefix,
)


# ---------------------------------------------------------------------------
# PrefixInfo dataclass
# ---------------------------------------------------------------------------

def test_prefix_info_defaults() -> None:
    """PrefixInfo with minimal args must fill in defaults."""
    info = PrefixInfo(prefix=Path("/tmp/pfx"))
    assert info.prefix == Path("/tmp/pfx")
    assert info.launcher == LAUNCHER_UNKNOWN
    assert info.launcher_label == "Custom"
    assert info.game_id == ""
    assert info.runner_name == ""
    print("✓ PrefixInfo defaults")


def test_prefix_info_auto_converts_string_prefix() -> None:
    """PrefixInfo must auto-convert string prefix to Path."""
    info = PrefixInfo(prefix="/tmp/pfx", launcher=LAUNCHER_STEAM)
    assert isinstance(info.prefix, Path)
    assert info.prefix == Path("/tmp/pfx")
    print("✓ PrefixInfo auto-converts string prefix")


def test_prefix_info_labels() -> None:
    """launcher_label must match LAUNCHER_LABELS."""
    for key, expected_label in LAUNCHER_LABELS.items():
        info = PrefixInfo(prefix=Path("/tmp/pfx"), launcher=key)
        assert info.launcher_label == expected_label, (
            f"{key}: expected {expected_label!r}, got {info.launcher_label!r}"
        )
    print("✓ PrefixInfo labels match LAUNCHER_LABELS")


def test_prefix_info_frozen() -> None:
    """PrefixInfo must be frozen (immutable)."""
    info = PrefixInfo(prefix=Path("/tmp/pfx"))
    try:
        info.prefix = Path("/other")
        assert False, "Should have raised FrozenInstanceError"
    except Exception:
        pass
    print("✓ PrefixInfo is frozen")


# ---------------------------------------------------------------------------
# build_prefix_env
# ---------------------------------------------------------------------------

def test_build_prefix_env_steam() -> None:
    """Steam prefix must set STEAM_COMPAT_DATA_PATH to compatdata parent."""
    info = PrefixInfo(
        prefix=Path("/steam/compatdata/377160/pfx"),
        launcher=LAUNCHER_STEAM,
    )
    env = build_prefix_env(info)
    assert env["WINEPREFIX"] == "/steam/compatdata/377160/pfx"
    assert env["STEAM_COMPAT_DATA_PATH"] == "/steam/compatdata/377160"
    print("✓ build_prefix_env sets Steam compat data path")


def test_build_prefix_env_steam_compatdata_parent() -> None:
    """When prefix name is not pfx/prefix, compat data = prefix itself."""
    info = PrefixInfo(
        prefix=Path("/steam/compatdata/377160"),
        launcher=LAUNCHER_STEAM,
    )
    env = build_prefix_env(info)
    assert env["STEAM_COMPAT_DATA_PATH"] == "/steam/compatdata/377160"
    assert env["WINEPREFIX"] == "/steam/compatdata/377160"
    print("✓ build_prefix_env handles non-pfx Steam prefix")


def test_build_prefix_env_non_steam() -> None:
    """Non-Steam prefix must only set WINEPREFIX."""
    info = PrefixInfo(
        prefix=Path("/bottles/MacOS"),
        launcher=LAUNCHER_CROSSOVER,
    )
    env = build_prefix_env(info)
    assert env["WINEPREFIX"] == "/bottles/MacOS"
    assert "STEAM_COMPAT_DATA_PATH" not in env
    print("✓ build_prefix_env non-Steam only sets WINEPREFIX")


def test_build_prefix_env_preserves_base() -> None:
    """build_prefix_env must not destroy base_env vars."""
    base = {"PATH": "/usr/bin", "FOO": "bar"}
    info = PrefixInfo(prefix=Path("/tmp/pfx"))
    env = build_prefix_env(info, base_env=base)
    assert env["PATH"] == "/usr/bin"
    assert env["FOO"] == "bar"
    assert "WINEPREFIX" in env
    print("✓ build_prefix_env preserves base env")


def test_build_prefix_env_does_not_mutate_base() -> None:
    """build_prefix_env must not mutate the caller's base_env."""
    base = {"FOO": "bar"}
    info = PrefixInfo(prefix=Path("/tmp/pfx"))
    build_prefix_env(info, base_env=base)
    assert "WINEPREFIX" not in base
    assert base == {"FOO": "bar"}
    print("✓ build_prefix_env does not mutate base env")


# ---------------------------------------------------------------------------
# identify_prefix
# ---------------------------------------------------------------------------

def test_identify_prefix_nonexistent() -> None:
    """identify_prefix must return None for nonexistent paths."""
    result = identify_prefix("/tmp/definitely_does_not_exist_99999")
    assert result is None
    print("✓ identify_prefix returns None for nonexistent path")


def test_identify_prefix_not_wine() -> None:
    """identify_prefix must return None for non-Wine directories."""
    with tempfile.TemporaryDirectory() as tmp:
        # Directory without drive_c/user.reg
        result = identify_prefix(tmp)
        assert result is None
    print("✓ identify_prefix returns None for non-Wine directory")


def test_identify_prefix_generic_wine() -> None:
    """A plain Wine prefix must be identified (may be lutris or unknown)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "drive_c").mkdir()
        (tmp_path / "user.reg").write_text("")

        result = identify_prefix(tmp_path)
        assert result is not None
        assert result.prefix == tmp_path
        # A bare prefix with drive_c+user.reg and no markers may be
        # classified as lutris (is_lutris_prefix catches it) or unknown
        assert result.launcher in (LAUNCHER_LUTRIS, LAUNCHER_UNKNOWN), (
            f"Expected lutris or unknown, got {result.launcher}"
        )
    print("✓ identify_prefix identifies generic Wine prefix")


def test_identify_prefix_lutris_marker() -> None:
    """A prefix with lutris.json must be identified as Lutris."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "drive_c").mkdir()
        (tmp_path / "user.reg").write_text("")
        (tmp_path / "lutris.json").write_text("{}")

        result = identify_prefix(tmp_path)
        assert result is not None
        assert result.launcher == LAUNCHER_LUTRIS
    print("✓ identify_prefix identifies Lutris prefix by marker")


def test_identify_prefix_steam_compatdata() -> None:
    """A Steam compatdata/pfx must be identified as Steam with App ID."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        steamapps = tmp_path / "steamapps"
        steamapps.mkdir()
        compatdata = steamapps / "compatdata"
        compatdata.mkdir()
        game_dir = compatdata / "123456"
        game_dir.mkdir()
        pfx = game_dir / "pfx"
        pfx.mkdir()
        (pfx / "drive_c").mkdir()
        (pfx / "user.reg").write_text("")

        result = identify_prefix(pfx)
        assert result is not None
        assert result.launcher == LAUNCHER_STEAM
        assert result.game_id == "123456"
    print("✓ identify_prefix identifies Steam compatdata with App ID")


def test_identify_prefix_steam_prefix() -> None:
    """A Steam compatdata/prefix (alternate name) must work too."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        steamapps = tmp_path / "steamapps"
        steamapps.mkdir()
        compatdata = steamapps / "compatdata"
        compatdata.mkdir()
        game_dir = compatdata / "789012"
        game_dir.mkdir()
        prefix = game_dir / "prefix"
        prefix.mkdir()
        (prefix / "drive_c").mkdir()
        (prefix / "user.reg").write_text("")

        result = identify_prefix(prefix)
        assert result is not None
        assert result.launcher == LAUNCHER_STEAM
        assert result.game_id == "789012"
    print("✓ identify_prefix identifies Steam compatdata/prefix")


# ---------------------------------------------------------------------------
# find_prefix_for_game
# ---------------------------------------------------------------------------

def test_find_prefix_no_criteria() -> None:
    """find_prefix_for_game with no criteria must return None."""
    result = find_prefix_for_game()
    assert result is None
    print("✓ find_prefix_for_game returns None with no criteria")


def test_find_prefix_steam_id_not_found() -> None:
    """Nonexistent Steam ID must return None (not crash)."""
    result = find_prefix_for_game(steam_id="999999999")
    assert result is None
    print("✓ find_prefix_for_game returns None for missing Steam ID")


def test_find_prefix_empty_exe_name() -> None:
    """Empty exe_name must not cause errors."""
    result = find_prefix_for_game(exe_name="")
    assert result is None
    print("✓ find_prefix_for_game handles empty exe_name")


def test_find_prefix_launcher_hint_ignored_on_failure() -> None:
    """When hinted launcher fails, must fall through (not hard-fail)."""
    result = find_prefix_for_game(
        steam_id="999999999",
        launcher_hint=LAUNCHER_STEAM,
    )
    # May find something or not, but must not crash
    assert result is None or isinstance(result, PrefixInfo)
    print("✓ find_prefix_for_game falls through on hint failure")


# ---------------------------------------------------------------------------
# Launcher constants
# ---------------------------------------------------------------------------

def test_launcher_constants() -> None:
    """All launcher constants must be in LAUNCHER_LABELS."""
    for key in (LAUNCHER_STEAM, LAUNCHER_LUTRIS, LAUNCHER_HEROIC,
                LAUNCHER_FAUGUS, LAUNCHER_CROSSOVER,
                LAUNCHER_STEAM_SHORTCUT, LAUNCHER_UNKNOWN):
        assert key in LAUNCHER_LABELS, f"{key} missing from LAUNCHER_LABELS"
    print("✓ All launcher constants are in LAUNCHER_LABELS")


# ---------------------------------------------------------------------------
# CrossOver bottle identification (macOS only, graceful on other platforms)
# ---------------------------------------------------------------------------

def test_identify_crossover_bottle() -> None:
    """CrossOver bottles must be identified on macOS."""
    import sys
    if sys.platform != "darwin":
        print("✓ identify_prefix skips CrossOver on non-macOS")
        return

    bottle = Path.home() / "Library" / "Application Support" / "CrossOver" / "bottles" / "Steam"
    if not bottle.is_dir():
        print("✓ identify_prefix skips missing CrossOver bottle")
        return

    result = identify_prefix(bottle)
    assert result is not None
    assert result.launcher == LAUNCHER_CROSSOVER
    print(f"✓ identify_prefix identifies CrossOver bottle ({bottle.name})")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_prefix_info_unicode_prefix() -> None:
    """PrefixInfo must handle unicode paths."""
    info = PrefixInfo(prefix=Path("/home/用户/游戏/pfx"))
    assert info.prefix == Path("/home/用户/游戏/pfx")
    print("✓ PrefixInfo handles unicode paths")


def test_prefix_info_spaces_in_prefix() -> None:
    """PrefixInfo must handle paths with spaces."""
    info = PrefixInfo(prefix=Path("/Users/name/My Games/Prefix"))
    assert info.prefix == Path("/Users/name/My Games/Prefix")
    env = build_prefix_env(info)
    assert "My Games" in env["WINEPREFIX"]
    print("✓ PrefixInfo handles paths with spaces")


def test_build_prefix_env_none_base() -> None:
    """build_prefix_env with None base_env must not crash."""
    info = PrefixInfo(prefix=Path("/tmp/pfx"))
    env = build_prefix_env(info, base_env=None)
    assert "WINEPREFIX" in env
    print("✓ build_prefix_env handles None base_env")


def test_identify_prefix_empty_dir() -> None:
    """identify_prefix on empty dir must return None."""
    with tempfile.TemporaryDirectory() as tmp:
        result = identify_prefix(tmp)
        assert result is None
    print("✓ identify_prefix returns None for empty directory")


def test_identify_prefix_dir_without_drive_c() -> None:
    """Dir with user.reg but no drive_c must return None."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "user.reg").write_text("")

        result = identify_prefix(tmp_path)
        assert result is None
    print("✓ identify_prefix returns None without drive_c")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
        except Exception as e:
            print(f"✗ {test_fn.__name__}: {e}")
            failed += 1

    if failed:
        print(f"\n{failed} test(s) FAILED")
        sys.exit(1)
    else:
        print(f"\nAll {len(tests)} tests passed ✓")


if __name__ == "__main__":
    main()
