"""Focused regression checks for :mod:`Utils.notproton_finder`.

Run as a module from the repository's ``src/`` directory::

    cd src && ../.venv/bin/python3 -m Utils._notproton_finder_selftest

(run as a module, not by script path - a ``Utils/collections`` file shadows
the stdlib module of the same name when run directly).

The tests build a synthetic NotProton fixture tree (four tools mirroring a
real install, runner copies with the per-flavor wine layout, and prefixes
with ``notproton-build`` records + synthesized ntdll machine bytes) and
monkeypatch the module's path roots onto it, so they pass on macOS and
Linux alike without any NotProton installation.
"""

from __future__ import annotations

import struct
import sys
import tempfile
from pathlib import Path
from unittest import mock

_SRC_ROOT = Path(__file__).resolve().parents[1]
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from Utils import notproton_finder as npf  # noqa: E402

# ---------------------------------------------------------------------------
# Fixture construction
# ---------------------------------------------------------------------------

# (tool dir name, build, flavor, display name) - mirrors a real machine with
# NotProton 1.1.7. The 41069-fex build is deliberately shared by a fex and a
# rosetta tool (the build/flavor disambiguation case).
_FIXTURE_TOOLS = [
    ("notproton-26.3", "26.3.0.39832", "rosetta", "CrossOver 26.3"),
    ("notproton-fex-41069", "27.0.0.41069-fex", "fex",
     "CrossOver 2026 10 06-ARM64 - FEX"),
    ("notproton-fex-rosetta-41069", "27.0.0.41069-fex", "rosetta",
     "CrossOver 2026 10 06-ARM64 - Rosetta"),
    ("notproton-preview-41069", "27.0.0.41069", "rosetta",
     "CrossOver 2026 10 06-X86 - Rosetta"),
]


def _write(path: Path, text: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def _make_tool(tool_root: Path, name: str, build: str, flavor: str,
               display: str) -> Path:
    tool_dir = tool_root / name
    _write(tool_dir / "run", "#!/bin/sh\nexit 0\n", executable=True)
    _write(tool_dir / "build", build + "\n")
    _write(tool_dir / "flavor", flavor + "\n")
    _write(tool_dir / "compatibilitytool.vdf",
           f'\"compatibilitytools\" {{\n  \"notproton\" {{\n'
           f'    "{name}" {{\n      "display_name" "{display}"\n'
           f'    }}\n  }}\n}}\n')
    return tool_dir


def _make_runner(runners_root: Path, build: str, *, with_arm64: bool = True,
                 with_plain_server: bool = True) -> None:
    """A CrossOver runner copy with the per-flavor wine/server layout."""
    cx = runners_root / f"crossover-{build}" / "CrossOver"
    wine_unix_dirs = ["x86_64-unix", "x86_64-windows"]
    if with_arm64:
        wine_unix_dirs.append("aarch64-unix")
    for d in wine_unix_dirs:
        _write(cx / "lib" / "wine" / d / ".keep", "")
    _write(cx / "lib" / "wine" / "x86_64-unix" / "wine", "#!/bin/sh\n",
           executable=True)
    if with_arm64:
        _write(cx / "lib" / "wine" / "aarch64-unix" / "wine.app"
               / "Contents" / "MacOS" / "wine", "#!/bin/sh\n", executable=True)
    if with_plain_server:
        _write(cx / "bin" / "wineserver", "#!/bin/sh\n", executable=True)
    _write(cx / "bin" / "wineserver-x86", "#!/bin/sh\n", executable=True)
    _write(cx / "bin" / "wineserver-arm64", "#!/bin/sh\n", executable=True)


def _write_fake_ntdll(path: Path, machine: int) -> None:
    """Synthesize an ntdll.dll whose PE export dir reports *machine*."""
    export_off = 128
    buf = bytearray(256)
    struct.pack_into("<I", buf, 60, export_off)
    buf[export_off:export_off + 4] = b"PE\x00\x00"
    struct.pack_into("<H", buf, export_off + 4, machine)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(buf))


class _Fixture:
    """Synthetic Steam root + runners root + game prefixes."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.steam_root = tmp / "steam"
        self.tool_root = self.steam_root / "compatibilitytools.d"
        self.runners_root = tmp / "notproton" / "runners"

        for name, build, flavor, display in _FIXTURE_TOOLS:
            _make_tool(self.tool_root, name, build, flavor, display)

        # Non-qualifying entries: a notproton dir missing its build marker,
        # and a plain Proton tool (wrong name prefix).
        _make_tool(self.tool_root, "notproton-broken", "9.9.9.9", "rosetta",
                   "Broken")
        (self.tool_root / "notproton-broken" / "build").unlink()
        _make_tool(self.tool_root, "proton-10", "10.0.1", "rosetta",
                   "Proton 10.0")

        # Runner copies: all builds except 27.0.0.41069 (its tool must come
        # back available=False).
        _make_runner(self.runners_root, "26.3.0.39832")
        _make_runner(self.runners_root, "27.0.0.41069-fex")

        # Game prefixes with notproton-build records + ntdll machine bytes.
        self.pfx_rosetta = self.steam_root / "steamapps" / "compatdata" / "489830"
        self.pfx_fex = self.steam_root / "steamapps" / "compatdata" / "123456"
        _write(self.pfx_rosetta / "notproton-build",
               "27.0.0.41069-fex\nCrossOver 2026 10 06-ARM64 - Rosetta\n")
        _write(self.pfx_fex / "notproton-build",
               "27.0.0.41069-fex\nCrossOver 2026 10 06-ARM64 - FEX\n")
        _write_fake_ntdll(
            self.pfx_rosetta / "pfx" / "drive_c" / "windows" / "system32"
            / "ntdll.dll", 0x8664)
        _write_fake_ntdll(
            self.pfx_fex / "pfx" / "drive_c" / "windows" / "system32"
            / "ntdll.dll", 0xAA64)

    def patch(self):
        return mock.patch.multiple(
            npf, _STEAM_ROOTS=[self.steam_root], _RUNNERS_ROOT=self.runners_root)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _run_all() -> None:
    with tempfile.TemporaryDirectory(prefix="amm-notproton-selftest-") as td:
        fx = _Fixture(Path(td))
        with fx.patch():
            _test_listing_and_exclusions(fx)
            _test_listing_order(fx)
            _test_wine_selection(fx)
            _test_tool_env(fx)
            _test_missing_runner_copy(fx)
            _test_find_by_label(fx)
            _test_tool_for_build(fx)
            _test_build_record(fx)
            _test_prefix_flavor(fx)
            _test_runner_for_prefix(fx)
            _test_fallback_chain(Path(td) / "alt")
            _test_not_installed_empty_roots(fx)


def _test_listing_and_exclusions(fx: _Fixture) -> None:
    tools = npf.list_notproton_tools()
    names = [t.name for t in tools]
    assert sorted(names) == sorted(t[0] for t in _FIXTURE_TOOLS), \
        f"unexpected tools: {names}"
    assert "notproton-broken" not in names
    assert "proton-10" not in names
    assert npf.notproton_installed() is True
    for tool in tools:
        assert isinstance(tool.tool_dir, Path)
        assert tool.run_script == tool.tool_dir / "run"
        assert tool.run_script.is_file()
        assert tool.display
    print("✓ list_notproton_tools() finds the 4 fixture tools, skips junk")


def _test_listing_order(fx: _Fixture) -> None:
    names = [t.name for t in npf.list_notproton_tools()]
    # Build version descending; 27.0.0.41069-fex and 27.0.0.41069 parse to
    # the same numeric version, so their relative order is the stable
    # flavor order (fex before rosetta).
    assert names == [
        "notproton-fex-41069",
        "notproton-fex-rosetta-41069",
        "notproton-preview-41069",
        "notproton-26.3",
    ], f"bad order: {names}"
    print("✓ Listing is sorted build-desc, fex before rosetta")


def _test_wine_selection(fx: _Fixture) -> None:
    tools = {t.name: t for t in npf.list_notproton_tools()}

    fex = tools["notproton-fex-41069"]
    assert fex.available is True
    assert fex.wine_unix_dir.name == "aarch64-unix"
    assert fex.wine_bin == (fex.wine_unix_dir / "wine.app" / "Contents"
                            / "MacOS" / "wine")
    assert fex.wine_bin.is_file()
    assert fex.wineserver == fex.cx_root / "bin" / "wineserver-arm64"
    assert fex.wineserver.is_file()

    rosetta = tools["notproton-26.3"]
    assert rosetta.available is True
    assert rosetta.wine_unix_dir.name == "x86_64-unix"
    assert rosetta.wine_bin == rosetta.wine_unix_dir / "wine"
    assert rosetta.wine_bin.is_file()
    assert rosetta.wineserver == rosetta.cx_root / "bin" / "wineserver"
    assert rosetta.wineserver.is_file()
    print("✓ wine/wineserver resolution mirrors compat_run.sh per flavor")


def _test_tool_env(fx: _Fixture) -> None:
    tools = {t.name: t for t in npf.list_notproton_tools()}

    rosetta = tools["notproton-26.3"]
    env = npf.notproton_tool_env(rosetta)
    assert set(env) == {"CX_ROOT", "CX_HOME", "WINEDLLPATH", "WINESERVER"}
    assert env["CX_ROOT"] == str(rosetta.cx_root)
    assert env["CX_HOME"] == str(npf._CX_HOME)
    expected_dllpath = (f"{rosetta.cx_root / 'lib' / 'wine' / 'x86_64-windows'}"
                        f":{rosetta.wine_unix_dir}")
    assert env["WINEDLLPATH"] == expected_dllpath, env["WINEDLLPATH"]
    assert env["WINESERVER"] == str(rosetta.wineserver)

    fex = tools["notproton-fex-41069"]
    fenv = npf.notproton_tool_env(fex)
    # fex: WINEDLLPATH ends with the aarch64 loader dir, not x86_64-unix.
    assert fenv["WINEDLLPATH"].endswith(f":{fex.wine_unix_dir}")
    assert fex.wine_unix_dir.name == "aarch64-unix"
    print("✓ notproton_tool_env() mirrors compat_run.sh per flavor")


def _test_missing_runner_copy(fx: _Fixture) -> None:
    tools = {t.name: t for t in npf.list_notproton_tools()}
    preview = tools["notproton-preview-41069"]
    assert preview.available is False
    assert not preview.cx_root.is_dir()
    # Paths still describe the expected (missing) runner layout.
    assert preview.cx_root == (fx.runners_root / "crossover-27.0.0.41069"
                               / "CrossOver")
    assert preview.wine_unix_dir.name == "x86_64-unix"
    print("✓ Tool with missing runner copy is listed but available=False")


def _test_find_by_label(fx: _Fixture) -> None:
    assert npf.find_notproton_tool("notproton-26.3").name == "notproton-26.3"
    # Display name, case-insensitive.
    assert npf.find_notproton_tool("CROSSOVER 26.3").name == "notproton-26.3"
    # Flavor-suffixed display (the label the UI persists).
    assert (npf.find_notproton_tool(
        "CrossOver 2026 10 06-ARM64 - Rosetta (Rosetta)")
        .name == "notproton-fex-rosetta-41069")
    assert (npf.find_notproton_tool(
        "crossover 2026 10 06-arm64 - fex (fex)")
        .name == "notproton-fex-41069")
    assert npf.find_notproton_tool("no such tool") is None
    assert npf.find_notproton_tool("") is None
    print("✓ find_notproton_tool() matches dir/display/suffixed labels")


def _test_tool_for_build(fx: _Fixture) -> None:
    assert (npf.tool_for_build("26.3.0.39832").name
            == "notproton-26.3")
    # Shared build disambiguated by flavor.
    assert (npf.tool_for_build("27.0.0.41069-fex", "fex").name
            == "notproton-fex-41069")
    assert (npf.tool_for_build("27.0.0.41069-fex", "rosetta").name
            == "notproton-fex-rosetta-41069")
    # Without a flavor, list order wins (fex first).
    assert (npf.tool_for_build("27.0.0.41069-fex").name
            == "notproton-fex-41069")
    assert npf.tool_for_build("27.0.0.41069").name == "notproton-preview-41069"
    assert npf.tool_for_build("9.9.9.9") is None
    assert npf.tool_for_build("") is None
    print("✓ tool_for_build() resolves build ids incl. shared builds")


def _test_build_record(fx: _Fixture) -> None:
    record = npf.build_record(fx.pfx_rosetta)
    assert record == ("27.0.0.41069-fex",
                      "CrossOver 2026 10 06-ARM64 - Rosetta"), record
    missing = fx.tmp / "nowhere"
    assert npf.build_record(missing) is None
    empty = fx.tmp / "empty"
    (empty / "notproton-build").parent.mkdir(parents=True, exist_ok=True)
    (empty / "notproton-build").write_text("", encoding="utf-8")
    assert npf.build_record(empty) is None
    print("✓ build_record() reads notproton-build, None when absent/empty")


def _test_prefix_flavor(fx: _Fixture) -> None:
    rosetta_pfx = fx.pfx_rosetta / "pfx"
    fex_pfx = fx.pfx_fex / "pfx"
    assert npf.prefix_flavor(rosetta_pfx) == "rosetta"
    assert npf.prefix_flavor(fex_pfx) == "fex"
    assert npf.prefix_flavor(fx.pfx_rosetta / "nope") is None
    assert npf.prefix_flavor(None) is None
    # Corrupt signature.
    bad = fx.tmp / "bad" / "pfx"
    _write_fake_ntdll(bad / "drive_c" / "windows" / "system32" / "ntdll.dll",
                      0x8664)
    with open(bad / "drive_c" / "windows" / "system32" / "ntdll.dll",
              "r+b") as f:
        f.seek(128)
        f.write(b"XXXX")
    assert npf.prefix_flavor(bad) is None
    # Unknown (32-bit) machine.
    old = fx.tmp / "old" / "pfx"
    _write_fake_ntdll(old / "drive_c" / "windows" / "system32" / "ntdll.dll",
                      0x14C)
    assert npf.prefix_flavor(old) is None
    print("✓ prefix_flavor() reads the ntdll PE machine")


def _test_runner_for_prefix(fx: _Fixture) -> None:
    # Shared build, machine bytes disambiguate.
    assert (npf.runner_for_prefix(fx.pfx_rosetta, fx.pfx_rosetta / "pfx")
            .name == "notproton-fex-rosetta-41069")
    assert (npf.runner_for_prefix(fx.pfx_fex, fx.pfx_fex / "pfx")
            .name == "notproton-fex-41069")
    # Machine unreadable -> prefer an available tool (fex first).
    assert (npf.runner_for_prefix(fx.pfx_rosetta, fx.pfx_rosetta / "ghost")
            .name == "notproton-fex-41069")
    # Uninstalled build / no record.
    orphan = fx.tmp / "orphan"
    (orphan / "notproton-build").parent.mkdir(parents=True, exist_ok=True)
    (orphan / "notproton-build").write_text("9.9.9.1\nGhost\n",
                                            encoding="utf-8")
    assert npf.runner_for_prefix(orphan, orphan / "pfx") is None
    bare = fx.tmp / "bare"
    bare.mkdir(parents=True, exist_ok=True)
    assert npf.runner_for_prefix(bare, bare / "pfx") is None
    print("✓ runner_for_prefix() disambiguates shared builds via ntdll")


def _test_fallback_chain(alt_root: Path) -> None:
    """fex flavor whose arm64 loader is missing falls back to x86 wine."""
    tool_root = alt_root / "steam" / "compatibilitytools.d"
    runners_root = alt_root / "notproton" / "runners"
    _make_tool(tool_root, "notproton-fex-test", "9.8.7.1-fex", "fex",
               "Test FEX")
    _make_runner(runners_root, "9.8.7.1-fex", with_arm64=False,
                 with_plain_server=False)

    with mock.patch.multiple(npf, _STEAM_ROOTS=[alt_root / "steam"],
                             _RUNNERS_ROOT=runners_root):
        tools = npf.list_notproton_tools()
        assert len(tools) == 1
        tool = tools[0]
        assert tool.available is True
        assert tool.wine_unix_dir.name == "x86_64-unix"
        assert tool.wine_bin == tool.wine_unix_dir / "wine"
        # No bin/wineserver -> falls back to bin/wineserver-x86.
        assert tool.wineserver == tool.cx_root / "bin" / "wineserver-x86"
    print("✓ fex tool with missing arm64 loader falls back to x86 wine")


def _test_not_installed_empty_roots(fx: _Fixture) -> None:
    with mock.patch.object(npf, "_STEAM_ROOTS", []):
        assert npf.list_notproton_tools() == []
        assert npf.notproton_installed() is False
    print("✓ No Steam roots -> no tools, notproton_installed() is False")


if __name__ == "__main__":
    _run_all()
    print("\nAll notproton_finder selftests passed ✓")
