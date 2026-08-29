"""Focused regression checks for :mod:`Utils.wine_runner`.

Run from the repository root with::

    PYTHONPATH=src python3 src/Utils/_wine_runner_selftest.py

Tests verify command generation, runner selection, and interface contracts.
No running of actual Wine executables — command lists are validated as strings.
"""

from __future__ import annotations

import sys
import tempfile
from abc import ABC
from pathlib import Path
from typing import Sequence
from unittest import mock

_SRC_ROOT = Path(__file__).resolve().parents[1]
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from Utils.wine_runner import (  # noqa: E402
    CrossOverRunner,
    HeroicRunner,
    LutrisRunner,
    ProtonRunner,
    SystemWineRunner,
    WineRunner,
    get_default_runner_type,
    get_runner,
    wine_reg_add,
    wine_run_command,
)


# ---------------------------------------------------------------------------
# Abstract base class contract
# ---------------------------------------------------------------------------

def test_wine_runner_is_abstract() -> None:
    """WineRunner must not be instantiable directly."""
    assert issubclass(WineRunner, ABC)
    # Attempting to instantiate should raise TypeError
    try:
        WineRunner()
        assert False, "Should have raised TypeError"
    except TypeError:
        pass
    print("✓ WineRunner is abstract and uninstantiable")


def test_all_runners_are_subclasses() -> None:
    """All concrete runners must subclass WineRunner."""
    for cls in (ProtonRunner, CrossOverRunner, SystemWineRunner,
                LutrisRunner, HeroicRunner):
        assert issubclass(cls, WineRunner), f"{cls.__name__} not subclass"
    print("✓ All concrete runners subclass WineRunner")


def test_all_runners_are_instantiable() -> None:
    """All concrete runners must be instantiable."""
    runners = [
        ProtonRunner(),
        CrossOverRunner(),
        SystemWineRunner(),
        LutrisRunner(),
        HeroicRunner(),
    ]
    for r in runners:
        assert isinstance(r, WineRunner)
    print("✓ All concrete runners are instantiable")


# ---------------------------------------------------------------------------
# CrossOverRunner command generation
# ---------------------------------------------------------------------------

def test_crossover_run_in_prefix_command() -> None:
    """run_in_prefix must produce a valid wine command."""
    runner = CrossOverRunner()

    with mock.patch.object(runner, "find_wine_binary", return_value=Path("/fake/wine")):
        cmd = runner.run_in_prefix(
            prefix=Path("/prefix/pfx"),
            exe=Path("/game/tool.exe"),
            args=["--verbose", "--output=/tmp/out"],
        )

        assert isinstance(cmd, list)
        assert cmd[0] == "/fake/wine"
        assert "start" in cmd
        assert "/unix" in cmd
        assert "/game/tool.exe" in cmd
        assert "--verbose" in cmd
        assert "--output=/tmp/out" in cmd
    print("✓ CrossOverRunner.run_in_prefix() generates correct command")


def test_crossover_run_in_prefix_no_wine() -> None:
    """run_in_prefix must return empty list when wine binary is missing."""
    runner = CrossOverRunner()

    with mock.patch.object(runner, "find_wine_binary", return_value=None):
        cmd = runner.run_in_prefix(
            prefix=Path("/prefix/pfx"),
            exe=Path("/game/tool.exe"),
        )
        assert cmd == []
    print("✓ CrossOverRunner.run_in_prefix() returns [] when no wine")


def test_crossover_run_reg_add_command() -> None:
    """run_reg_add must produce a valid reg add command."""
    runner = CrossOverRunner()

    with mock.patch.object(runner, "find_wine_binary", return_value=Path("/fake/wine")):
        cmd = runner.run_reg_add(
            prefix=Path("/prefix/pfx"),
            key=r"HKLM\Software\MyApp",
            value="test_value",
            value_name="MyKey",
            value_type="REG_SZ",
        )

        assert isinstance(cmd, list)
        assert cmd[0] == "/fake/wine"
        assert "reg" in cmd
        assert "add" in cmd
        assert r"HKLM\Software\MyApp" in cmd
        assert "/v" in cmd
        assert "MyKey" in cmd
        assert "/t" in cmd
        assert "REG_SZ" in cmd
        assert "/d" in cmd
        assert "test_value" in cmd
        assert "/f" in cmd
    print("✓ CrossOverRunner.run_reg_add() generates correct command")


def test_crossover_run_reg_add_default_value() -> None:
    """run_reg_add with empty value_name must omit /v."""
    runner = CrossOverRunner()

    with mock.patch.object(runner, "find_wine_binary", return_value=Path("/fake/wine")):
        cmd = runner.run_reg_add(
            prefix=Path("/prefix/pfx"),
            key=r"HKLM\Software\MyApp",
            value="default_val",
            value_name="",
        )
        assert "/v" not in cmd
    print("✓ CrossOverRunner.run_reg_add() omits /v for default value")


def test_crossover_list_versions() -> None:
    """list_available_versions must return bottle names."""
    runner = CrossOverRunner()

    with mock.patch(
        "Utils.crossover_finder.list_crossover_bottles",
        return_value=[Path("/bottles/Steam"), Path("/bottles/MacOS")],
    ):
        versions = runner.list_available_versions()
        assert "Steam" in versions
        assert "MacOS" in versions
    print("✓ CrossOverRunner.list_available_versions() returns bottle names")


# ---------------------------------------------------------------------------
# SystemWineRunner command generation
# ---------------------------------------------------------------------------

def test_system_wine_run_in_prefix_command() -> None:
    """run_in_prefix must produce a valid wine command."""
    runner = SystemWineRunner()

    with mock.patch.object(runner, "find_wine_binary", return_value=Path("/usr/bin/wine")):
        cmd = runner.run_in_prefix(
            prefix=Path("/home/user/.wine"),
            exe=Path("/opt/game/tool.exe"),
            args=["--flag"],
        )

        assert isinstance(cmd, list)
        assert cmd[0] == "/usr/bin/wine"
        assert "start" in cmd
        assert "/unix" in cmd
        assert "/opt/game/tool.exe" in cmd
        assert "--flag" in cmd
    print("✓ SystemWineRunner.run_in_prefix() generates correct command")


def test_system_wine_reg_add_command() -> None:
    """run_reg_add must produce a valid wine reg add command."""
    runner = SystemWineRunner()

    with mock.patch.object(runner, "find_wine_binary", return_value=Path("/usr/bin/wine")):
        cmd = runner.run_reg_add(
            prefix=Path("/home/user/.wine"),
            key=r"HKCU\Software\MyApp",
            value="1",
            value_name="Enabled",
            value_type="REG_DWORD",
        )

        assert cmd[0] == "/usr/bin/wine"
        assert "reg" in cmd
        assert "add" in cmd
        assert "REG_DWORD" in cmd
    print("✓ SystemWineRunner.run_reg_add() generates correct command")


# ---------------------------------------------------------------------------
# LutrisRunner command generation
# ---------------------------------------------------------------------------

def test_lutris_run_in_prefix_command() -> None:
    """run_in_prefix must produce a valid wine command."""
    runner = LutrisRunner()

    with mock.patch.object(runner, "find_wine_binary", return_value=Path("/home/user/.local/share/lutris/wine-8.0/bin/wine")):
        cmd = runner.run_in_prefix(
            prefix=Path("/home/user/Games/prefix"),
            exe=Path("/home/user/Games/tool.exe"),
        )

        assert isinstance(cmd, list)
        assert str(cmd[0]).endswith("/wine")
        assert "start" in cmd
        assert "/home/user/Games/tool.exe" in cmd
    print("✓ LutrisRunner.run_in_prefix() generates correct command")


# ---------------------------------------------------------------------------
# HeroicRunner command generation
# ---------------------------------------------------------------------------

def test_heroic_run_in_prefix_command() -> None:
    """run_in_prefix must route through proton_run_command."""
    runner = HeroicRunner()

    fake_script = Path("/opt/heroic/proton/GE-Proton9-27/proton")

    with mock.patch.object(runner, "find_wine_binary", return_value=fake_script):
        with mock.patch(
            "Utils.steam_finder.proton_run_command",
            return_value=["python3", str(fake_script), "runinprefix", "/game.exe"],
        ):
            cmd = runner.run_in_prefix(
                prefix=Path("/home/user/Games/prefix"),
                exe=Path("/home/user/Games/tool.exe"),
            )

            assert isinstance(cmd, list)
            assert "runinprefix" in cmd
    print("✓ HeroicRunner.run_in_prefix() routes through proton_run_command")


# ---------------------------------------------------------------------------
# Factory: get_runner()
# ---------------------------------------------------------------------------

def test_get_runner_default_returns_winerunner() -> None:
    """get_runner() with no args must return a WineRunner."""
    runner = get_runner()
    assert isinstance(runner, WineRunner)
    print(f"✓ get_runner() returns WineRunner ({runner.__class__.__name__})")


def test_get_runner_explicit_crossover() -> None:
    """get_runner('crossover') must return CrossOverRunner."""
    runner = get_runner("crossover")
    assert isinstance(runner, CrossOverRunner)
    print("✓ get_runner('crossover') returns CrossOverRunner")


def test_get_runner_explicit_system_wine() -> None:
    """get_runner('system_wine') must return SystemWineRunner."""
    runner = get_runner("system_wine")
    assert isinstance(runner, SystemWineRunner)
    print("✓ get_runner('system_wine') returns SystemWineRunner")


def test_get_runner_explicit_lutris() -> None:
    """get_runner('lutris') must return LutrisRunner."""
    runner = get_runner("lutris")
    assert isinstance(runner, LutrisRunner)
    print("✓ get_runner('lutris') returns LutrisRunner")


def test_get_runner_explicit_heroic() -> None:
    """get_runner('heroic') must return HeroicRunner."""
    runner = get_runner("heroic")
    assert isinstance(runner, HeroicRunner)
    print("✓ get_runner('heroic') returns HeroicRunner")


# ---------------------------------------------------------------------------
# Factory: get_default_runner_type()
# ---------------------------------------------------------------------------

def test_get_default_runner_type_is_string() -> None:
    """get_default_runner_type() must return a string."""
    t = get_default_runner_type()
    assert isinstance(t, str)
    assert t in ("proton", "crossover", "system_wine", "lutris", "heroic")
    print(f"✓ get_default_runner_type() returns valid string: '{t}'")


# ---------------------------------------------------------------------------
# Backwards-compat shims
# ---------------------------------------------------------------------------

def test_wine_run_command_shim() -> None:
    """wine_run_command() must delegate to the correct runner."""
    with mock.patch(
        "Utils.wine_runner.get_runner",
        return_value=SystemWineRunner(),
    ) as mock_get:
        runner = mock_get.return_value
        expected_cmd = ["/usr/bin/wine", "start", "/unix", "/game.exe", "--flag"]
        runner.run_in_prefix = mock.Mock(return_value=expected_cmd)

        cmd = wine_run_command(
            prefix=Path("/prefix"),
            exe=Path("/game.exe"),
            args=["--flag"],
        )

        assert cmd == expected_cmd
        runner.run_in_prefix.assert_called_once()
    print("✓ wine_run_command() delegates to get_runner().run_in_prefix()")


def test_wine_reg_add_shim() -> None:
    """wine_reg_add() must delegate to the correct runner."""
    with mock.patch(
        "Utils.wine_runner.get_runner",
        return_value=CrossOverRunner(),
    ) as mock_get:
        runner = mock_get.return_value
        expected_cmd = ["wine", "reg", "add", "HKLM\\Soft", "/v", "K", "/t", "REG_SZ", "/d", "V", "/f"]
        runner.run_reg_add = mock.Mock(return_value=expected_cmd)

        cmd = wine_reg_add(
            prefix=Path("/prefix"),
            key="HKLM\\Soft",
            value="V",
            value_name="K",
            value_type="REG_SZ",
        )

        assert cmd == expected_cmd
        runner.run_reg_add.assert_called_once()
    print("✓ wine_reg_add() delegates to get_runner().run_reg_add()")


# ---------------------------------------------------------------------------
# Environment handling
# ---------------------------------------------------------------------------

def test_env_is_not_mutated_by_runner() -> None:
    """run_in_prefix must not mutate the caller's env dict."""
    runner = CrossOverRunner()
    original_env = {"PATH": "/usr/bin", "FOO": "bar"}

    with mock.patch.object(runner, "find_wine_binary", return_value=Path("/fake/wine")):
        env_copy = original_env.copy()
        runner.run_in_prefix(
            prefix=Path("/prefix"),
            exe=Path("/game.exe"),
            env=env_copy,
        )
        # env_copy should have WINEPREFIX added, but original must be untouched
        assert original_env.get("WINEPREFIX") is None
        assert "FOO" in original_env
    print("✓ run_in_prefix does not mutate caller's env dict")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_args() -> None:
    """run_in_prefix with no extra args must still produce valid command."""
    runner = CrossOverRunner()

    with mock.patch.object(runner, "find_wine_binary", return_value=Path("/fake/wine")):
        cmd = runner.run_in_prefix(
            prefix=Path("/prefix"),
            exe=Path("/game.exe"),
            args=[],
        )
        assert "/fake/wine" in cmd[0]
        assert "/game.exe" in cmd
    print("✓ run_in_prefix handles empty args")


def test_path_with_spaces() -> None:
    """Paths with spaces must be handled correctly (as Path objects)."""
    runner = CrossOverRunner()

    with mock.patch.object(runner, "find_wine_binary", return_value=Path("/fake/wine")):
        cmd = runner.run_in_prefix(
            prefix=Path("/Users/name/Games/My Game/prefix"),
            exe=Path("/Users/name/Games/My Game/Tool.exe"),
        )
        # Path objects are converted to strings preserving spaces
        assert any("My Game" in c for c in cmd)
    print("✓ run_in_prefix handles paths with spaces")


def test_unicode_paths() -> None:
    """Paths with unicode characters must survive round-trip."""
    runner = CrossOverRunner()

    with mock.patch.object(runner, "find_wine_binary", return_value=Path("/fake/wine")):
        cmd = runner.run_in_prefix(
            prefix=Path("/home/user/游戏/prefix"),
            exe=Path("/home/user/游戏/工具.exe"),
        )
        assert any("游戏" in c for c in cmd)
    print("✓ run_in_prefix handles unicode paths")


# ---------------------------------------------------------------------------
# CrossOverRunner bottle selection
# ---------------------------------------------------------------------------

def test_crossover_bottle_path_init() -> None:
    """CrossOverRunner should accept an explicit bottle path."""
    bottle = Path("/custom/bottles/MyBottle")
    runner = CrossOverRunner(bottle_path=bottle)
    assert runner._bottle_path == bottle
    print("✓ CrossOverRunner accepts explicit bottle_path")


def test_crossover_find_bottle_prefers_explicit() -> None:
    """_find_bottle must prefer the explicit bottle over auto-discovery."""
    with tempfile.TemporaryDirectory() as tmp:
        bottle = Path(tmp) / "MyBottle"
        bottle.mkdir()
        runner = CrossOverRunner(bottle_path=bottle)
        found = runner._find_bottle()
        assert found == bottle
    print("✓ CrossOverRunner._find_bottle() prefers explicit bottle")


def test_crossover_find_bottle_fallback() -> None:
    """_find_bottle must fall back to auto-discovery when explicit is missing."""
    bottle = Path("/nonexistent/bottle_99999")
    runner = CrossOverRunner(bottle_path=bottle)

    with mock.patch(
        "Utils.crossover_finder.list_crossover_bottles",
        return_value=[Path("/auto/bottles/Steam")],
    ):
        found = runner._find_bottle()
        assert found == Path("/auto/bottles/Steam")
    print("✓ CrossOverRunner._find_bottle() falls back to auto-discovery")


# ---------------------------------------------------------------------------
# ProtonRunner (Linux — test structure, not actual execution)
# ---------------------------------------------------------------------------

def test_proton_run_in_prefix_uses_proton_run_command() -> None:
    """ProtonRunner.run_in_prefix must call proton_run_command."""
    runner = ProtonRunner()
    fake_script = Path("/steam/compatibilitytools.d/Proton/proton")

    with mock.patch(
        "Utils.steam_finder.find_any_installed_proton",
        return_value=fake_script,
    ), mock.patch(
        "Utils.steam_finder.proton_run_command",
        return_value=["python3", str(fake_script), "runinprefix", "/game.exe"],
    ) as mock_proton:
        cmd = runner.run_in_prefix(
            prefix=Path("/steam/compatdata/123/pfx"),
            exe=Path("/game.exe"),
        )

        mock_proton.assert_called_once()
        # Verify STEAM_COMPAT_DATA_PATH was passed
        call_kwargs = mock_proton.call_args
        env = call_kwargs.kwargs.get("env", call_kwargs[1].get("env", {}))
        assert "STEAM_COMPAT_DATA_PATH" in env
    print("✓ ProtonRunner.run_in_prefix() calls proton_run_command with compat data path")


def test_proton_run_in_prefix_no_proton() -> None:
    """ProtonRunner must return [] when no Proton is installed."""
    runner = ProtonRunner()

    with mock.patch(
        "Utils.steam_finder.find_any_installed_proton",
        return_value=None,
    ):
        cmd = runner.run_in_prefix(
            prefix=Path("/prefix"),
            exe=Path("/game.exe"),
        )
        assert cmd == []
    print("✓ ProtonRunner.run_in_prefix() returns [] when no Proton")


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
