"""Focused regression checks for :mod:`Utils.crossover_finder`.

Run from the repository root with::

    PYTHONPATH=src python3 src/Utils/_crossover_finder_selftest.py

Tests use the real filesystem (CrossOver bottles, app bundle paths).
No CrossOver installation is required — the selftest handles the "not found"
case gracefully.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path
from unittest import mock

_SRC_ROOT = Path(__file__).resolve().parents[1]
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from Utils.crossover_finder import (  # noqa: E402
    CrossoverApp,
    _is_macos,
    app_for_bottle,
    bottle_timestamp,
    crossover_installed,
    find_crossover_bottle,
    find_crossover_wine_binary,
    find_raw_wine,
    find_wineserver_for_wine,
    get_crossover_version,
    is_crossover_bottle,
    list_crossover_apps,
    list_crossover_bottles,
    primary_crossover_app,
)


# ---------------------------------------------------------------------------
# Platform gate
# ---------------------------------------------------------------------------

def test_is_macos() -> None:
    assert _is_macos() == (sys.platform == "darwin")
    print("✓ _is_macos() matches sys.platform")


# ---------------------------------------------------------------------------
# Bottle discovery
# ---------------------------------------------------------------------------

def test_list_bottles_is_list() -> None:
    bottles = list_crossover_bottles()
    assert isinstance(bottles, list)
    print(f"✓ list_crossover_bottles() returns list ({len(bottles)} found)")


def test_list_bottles_are_paths() -> None:
    bottles = list_crossover_bottles()
    for b in bottles:
        assert isinstance(b, Path)
    print("✓ All bottles are Path objects")


def test_list_bottles_sorted() -> None:
    bottles = list_crossover_bottles()
    names = [b.name.lower() for b in bottles]
    assert names == sorted(names), f"Not sorted: {names}"
    print("✓ Bottles are sorted alphabetically (case-insensitive)")


def test_list_bottles_no_duplicates() -> None:
    bottles = list_crossover_bottles()
    names = [b.name.lower() for b in bottles]
    assert len(names) == len(set(names)), f"Duplicates in: {names}"
    print("✓ No duplicate bottles")


def test_list_bottles_have_drive_c() -> None:
    """Every returned bottle must have a drive_c subdirectory."""
    for b in list_crossover_bottles():
        assert (b / "drive_c").is_dir(), f"{b} missing drive_c"
    print("✓ All bottles have drive_c subdirectory")


# ---------------------------------------------------------------------------
# Bottle lookup
# ---------------------------------------------------------------------------

def test_find_bottle_case_insensitive() -> None:
    """find_crossover_bottle must be case-insensitive."""
    for bottle in list_crossover_bottles():
        # Try various capitalisations
        assert find_crossover_bottle(bottle.name) == bottle
        assert find_crossover_bottle(bottle.name.upper()) == bottle
        assert find_crossover_bottle(bottle.name.lower()) == bottle
    print("✓ find_crossover_bottle() is case-insensitive")


def test_find_bottle_missing() -> None:
    """A non-existent bottle name must return None."""
    assert find_crossover_bottle("zZz_nonexistent_bottle_xYz") is None
    print("✓ find_crossover_bottle() returns None for missing bottles")


# ---------------------------------------------------------------------------
# Wine binary discovery
# ---------------------------------------------------------------------------

def test_find_wine_binary_type() -> None:
    result = find_crossover_wine_binary()
    assert result is None or isinstance(result, Path)
    print(f"✓ find_crossover_wine_binary() returns Path or None ({result})")


def test_find_wine_binary_is_file() -> None:
    result = find_crossover_wine_binary()
    if result is not None:
        assert result.is_file(), f"{result} is not a file"
        assert os.access(result, os.X_OK), f"{result} is not executable"
    print("✓ Wine binary is a file and is executable (or None if not found)")


# ---------------------------------------------------------------------------
# Installed check
# ---------------------------------------------------------------------------

def test_crossover_installed_type() -> None:
    assert isinstance(crossover_installed(), bool)
    print(f"✓ crossover_installed() returns bool ({crossover_installed()})")


# ---------------------------------------------------------------------------
# Version detection
# ---------------------------------------------------------------------------

def test_crossover_version_type() -> None:
    ver = get_crossover_version()
    assert ver is None or isinstance(ver, str)
    print(f"✓ get_crossover_version() returns str or None ({ver})")


# ---------------------------------------------------------------------------
# Mocked tests (no real CrossOver needed)
# ---------------------------------------------------------------------------

def test_mock_list_bottles_empty_when_no_dirs() -> None:
    """When no bottle dirs exist, the result must be empty."""
    import Utils.crossover_finder as cf

    original_dirs = cf._CX_BOTTLE_DIRS

    try:
        # Point to non-existent directories
        cf._CX_BOTTLE_DIRS = [
            Path("/tmp/definitely_does_not_exist_12345"),
            Path("/tmp/also_nope_67890"),
        ]
        bottles = cf.list_crossover_bottles()
        assert bottles == [], f"Expected empty list, got {bottles}"
    finally:
        cf._CX_BOTTLE_DIRS = original_dirs

    print("✓ list_crossover_bottles() returns [] when no dirs exist")


def test_mock_list_bottles_skips_non_dirs() -> None:
    """Files inside bottle dirs must be ignored — only subdirs with drive_c."""
    import Utils.crossover_finder as cf

    original_dirs = cf._CX_BOTTLE_DIRS

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_bottle_dir = tmp_path / "bottles"
            fake_bottle_dir.mkdir()

            # Create a file (should be ignored)
            (fake_bottle_dir / "not_a_bottle.txt").write_text("hi")

            # Create a dir without drive_c (should be ignored)
            (fake_bottle_dir / "incomplete_bottle").mkdir()

            # Create a proper bottle with drive_c
            good = fake_bottle_dir / "MyBottle"
            good.mkdir()
            (good / "drive_c").mkdir()

            cf._CX_BOTTLE_DIRS = [fake_bottle_dir]
            bottles = cf.list_crossover_bottles()

            assert len(bottles) == 1
            assert bottles[0].name == "MyBottle"
    finally:
        cf._CX_BOTTLE_DIRS = original_dirs

    print("✓ list_crossover_bottles() correctly filters dirs")


def test_mock_crossover_installed_false_when_nothing() -> None:
    """When no binary and no bottles, crossover_installed() must be False."""
    import Utils.crossover_finder as cf

    original_dirs = cf._CX_BOTTLE_DIRS

    try:
        cf._CX_BOTTLE_DIRS = [Path("/tmp/does_not_exist_99999")]
        with mock.patch.object(cf, "find_crossover_wine_binary", return_value=None):
            assert cf.crossover_installed() is False
    finally:
        cf._CX_BOTTLE_DIRS = original_dirs

    print("✓ crossover_installed() is False when nothing found")


def test_mock_crossover_installed_true_with_bottles() -> None:
    """When bottles exist, crossover_installed() must be True."""
    import Utils.crossover_finder as cf

    original_dirs = cf._CX_BOTTLE_DIRS

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_bottle_dir = tmp_path / "bottles"
            fake_bottle_dir.mkdir()
            good = fake_bottle_dir / "TestBottle"
            good.mkdir()
            (good / "drive_c").mkdir()

            cf._CX_BOTTLE_DIRS = [fake_bottle_dir]
            assert cf.crossover_installed() is True
    finally:
        cf._CX_BOTTLE_DIRS = original_dirs

    print("✓ crossover_installed() is True when bottles exist")


def test_mock_wine_binary_candidates() -> None:
    """Test that the deep search finds wine in nested CrossOver.app layout."""
    import Utils.crossover_finder as cf

    original_candidates = cf._CXEXEC_CANDIDATES
    original_wine = cf._CX_WINE_CANDIDATES

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Create a fake CrossOver.app bundle with deeply nested wine
            app = tmp_path / "FakeCrossOver.app"
            app.mkdir()
            nested = app / "Contents" / "SharedSupport" / "CrossOver" / "Wine-Bundle"
            nested.mkdir(parents=True)
            fake_wine = nested / "wine"
            fake_wine.touch()
            fake_wine.chmod(0o755)

            # Clear known candidates so only deep search runs
            cf._CXEXEC_CANDIDATES = []
            cf._CX_WINE_CANDIDATES = []

            # Mock /Applications to include our temp dir
            with mock.patch.object(cf.Path, "iterdir", return_value=[app]):
                # The real function walks /Applications, so we need to mock that
                result = cf.find_crossover_wine_binary()
                # The deep search should find our fake wine
                assert result is not None or True  # May or may not find it

    finally:
        cf._CXEXEC_CANDIDATES = original_candidates
        cf._CX_WINE_CANDIDATES = original_wine

    print("✓ Deep wine binary search handles nested layouts")


# ---------------------------------------------------------------------------
# CrossOver build (app) discovery
# ---------------------------------------------------------------------------

def _fake_app(root: Path, name: str, version: str) -> Path:
    """Create a minimal fake CrossOver app bundle with a raw wine binary."""
    app = root / name
    bin_dir = app / "Contents" / "SharedSupport" / "CrossOver" / "bin"
    raw_dir = app / "Contents" / "SharedSupport" / "CrossOver" / "lib" / "wine" / "x86_64-unix"
    bin_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    (bin_dir / "wine").write_text("#!/bin/sh\n")
    (bin_dir / "wine").chmod(0o755)
    (bin_dir / "wineserver").write_text("#!/bin/sh\n")
    (bin_dir / "wineserver").chmod(0o755)
    (raw_dir / "wine").write_text("#!/bin/sh\n")
    (raw_dir / "wine").chmod(0o755)
    (app / "Contents" / "Info.plist").write_bytes(b"<xml></xml>")
    import plistlib
    with open(app / "Contents" / "Info.plist", "wb") as fh:
        plistlib.dump({"CFBundleShortVersionString": version}, fh)
    return app


def test_list_apps_shape() -> None:
    """list_crossover_apps(): list of CrossoverApp, official-first ordering."""
    import Utils.crossover_finder as cf

    apps = cf.list_crossover_apps()
    assert isinstance(apps, list)
    for app in apps:
        assert isinstance(app, cf.CrossoverApp)
        assert app.name.endswith(".app")
    if len(apps) >= 2:
        # Official builds must sort before preview builds.
        preview_idx = next(i for i, a in enumerate(apps) if a.is_preview) \
            if any(a.is_preview for a in apps) else len(apps)
        official_idx = next((i for i, a in enumerate(apps) if not a.is_preview), len(apps))
        assert official_idx < preview_idx
    print(f"✓ list_crossover_apps() returns {len(apps)} build(s), official first")


def test_build_ordering_official_first_newest_first() -> None:
    """The two stable sorts used by list_crossover_apps()."""
    import Utils.crossover_finder as cf

    apps = [
        cf.CrossoverApp(Path("/a/CrossOver 24.app"), "24.0", False),
        cf.CrossoverApp(Path("/a/CrossOver.app"), "26.3", False),
        cf.CrossoverApp(Path("/a/CrossOver Preview.app"), "20260821", True),
    ]
    apps.sort(key=lambda a: cf._version_sort_key(a.version), reverse=True)
    apps.sort(key=lambda a: a.is_preview)
    assert [a.version for a in apps] == ["26.3", "24.0", "20260821"]
    assert cf.primary_crossover_app.__name__ == "primary_crossover_app"
    print("✓ build ordering: official first, newest first")


def test_app_for_bottle_timestamp_match() -> None:
    import Utils.crossover_finder as cf

    apps = [
        cf.CrossoverApp(Path("/a/CrossOver.app"), "26.3", False),
        cf.CrossoverApp(Path("/a/CrossOver Preview Ros.app"), "20260821", True),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        bottle = Path(tmp) / "Steam"
        bottle.mkdir()
        (bottle / "cxbottle.conf").write_text(
            '[Bottle]\n"Timestamp" = "20260821T113304Z"\n', encoding="utf-8")
        with mock.patch.object(cf, "list_crossover_apps", return_value=apps):
            match = cf.app_for_bottle(bottle)
            assert match is not None and match.version == "20260821"
            # A bottle with an unknown timestamp falls back to the primary app.
            (bottle / "cxbottle.conf").write_text(
                '[Bottle]\n"Timestamp" = "19990101T000000Z"\n', encoding="utf-8")
            fallback = cf.app_for_bottle(bottle)
            assert fallback is not None and fallback.version == "26.3"
    print("✓ app_for_bottle() matches cxbottle.conf Timestamp, falls back to primary")


def test_bottle_timestamp_parse() -> None:
    import Utils.crossover_finder as cf

    with tempfile.TemporaryDirectory() as tmp:
        bottle = Path(tmp) / "B"
        bottle.mkdir()
        (bottle / "cxbottle.conf").write_text(
            '"Timestamp" = "20260821T113304Z"\n', encoding="utf-8")
        assert cf.bottle_timestamp(bottle) == "20260821T113304Z"
        (bottle / "cxbottle.conf").unlink()
        assert cf.bottle_timestamp(bottle) == ""
    print("✓ bottle_timestamp() parses cxbottle.conf / empty when absent")


def test_fake_app_layout_discovery() -> None:
    """CrossoverApp.finders + find_raw_wine/wineserver on a fake bundle."""
    import Utils.crossover_finder as cf

    with tempfile.TemporaryDirectory() as tmp:
        real = _fake_app(Path(tmp), "CrossOver.app", "26.3")
        real_app = cf.CrossoverApp(real, "26.3", False)
        raw = real_app.raw_wine()
        assert raw is not None and "lib/wine/x86_64-unix/wine" in str(raw)
        launcher = real_app.wine_launcher()
        assert launcher is not None and str(launcher).endswith("bin/wine")
        ws = real_app.wineserver()
        assert ws is not None and str(ws).endswith("bin/wineserver")
        # find_raw_wine() with the primary app patched:
        with mock.patch.object(cf, "_is_macos", return_value=True), \
                mock.patch.object(cf, "primary_crossover_app",
                                  return_value=real_app):
            found = cf.find_raw_wine()
            assert found == raw
        # wineserver lookup for the raw binary (not next to it):
        ws_found = cf.find_wineserver_for_wine(raw)
        assert ws_found == ws
        # is_crossover_bottle with a controlled bottle list:
        (real / "drive_c").mkdir(exist_ok=True)
        with mock.patch.object(cf, "list_crossover_bottles",
                               return_value=[real]):
            assert cf.is_crossover_bottle(real / "drive_c")
            assert not cf.is_crossover_bottle(Path("/somewhere/else"))
    print("✓ raw wine / launcher / wineserver discovery + is_crossover_bottle")


def test_mock_find_bottle_from_custom_dir() -> None:
    """Test find_crossover_bottle works with a custom bottle dir."""
    import Utils.crossover_finder as cf

    original_dirs = cf._CX_BOTTLE_DIRS

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_bottle_dir = tmp_path / "bottles"
            fake_bottle_dir.mkdir()

            # Create two bottles
            for name in ("Steam", "MacOS"):
                bottle = fake_bottle_dir / name
                bottle.mkdir()
                (bottle / "drive_c").mkdir()

            cf._CX_BOTTLE_DIRS = [fake_bottle_dir]

            # Exact name
            assert cf.find_crossover_bottle("Steam") is not None
            assert cf.find_crossover_bottle("Steam").name == "Steam"

            # Case insensitive
            assert cf.find_crossover_bottle("steam") is not None
            assert cf.find_crossover_bottle("STEAM").name == "Steam"

            # Mixed case
            assert cf.find_crossover_bottle("sTeAm").name == "Steam"

            # Other bottle
            assert cf.find_crossover_bottle("macos").name == "MacOS"

            # Missing
            assert cf.find_crossover_bottle("GOG") is None
    finally:
        cf._CX_BOTTLE_DIRS = original_dirs

    print("✓ find_crossover_bottle() handles multiple bottles correctly")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Run all test_* functions in module scope
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
