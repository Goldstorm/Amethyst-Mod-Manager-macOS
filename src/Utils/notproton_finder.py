"""
Utils/notproton_finder.py
Read-only discovery of NotProton compatibility tools and their runner copies.

NotProton (macOS Steam) brings the Linux Steam Play experience to the macOS
Steam client by force-enabling Steam Play over *patched copies of CrossOver*.
On disk it leaves a small, well-defined contract (all read-only for Amethyst):

- Compat tools:  <steam_root>/compatibilitytools.d/notproton-*/
  Each tool directory holds a Proton-verb-compatible ``run`` shell script,
  a ``build`` marker (e.g. ``27.0.0.41069-fex``), a ``flavor`` marker
  (``fex`` or ``rosetta``) and ``compatibilitytool.vdf`` (display name).
- Runner copies: <home>/Library/Application Support/notproton/runners/
  crossover-<build>/CrossOver/ with raw wine in
  lib/wine/{aarch64-unix,x86_64-unix}/ and the wineserver(s) in bin/.
- Game prefixes: <steam_root>/steamapps/compatdata/<appid>/pfx (the Linux
  Proton layout) plus a ``notproton-build`` record (line 1 = build id,
  line 2 = display name) written by the run script.
- Per-game mapping: patched Steam writes ``CompatToolMapping`` in
  config/config.vdf naming the tool directory - handled by
  Utils.launchers.steam, not this module.

The wine/wineserver selection below mirrors NotProton's own
dylib/feats/compat_run.sh exactly: fex tools use the arm64 loader
(aarch64-unix/wine.app + bin/wineserver-arm64); rosetta tools - or fex
tools whose arm64 loader/server is missing - fall back to
x86_64-unix/wine + bin/wineserver (or bin/wineserver-x86).

This module is strictly read-only, subprocess-free and cache-free (a
handful of small file reads per call) so it stays cheap enough for
GUI-thread use. Amethyst never writes to any NotProton-owned path.
"""

from __future__ import annotations

import os
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

from Utils.launchers.steam import _STEAM_CANDIDATES

# ---------------------------------------------------------------------------
# Module-level path roots (monkeypatch these in the selftest)
# ---------------------------------------------------------------------------

# Every Steam client root that may carry a compatibilitytools.d dir.
# Mirrors Utils.launchers.steam._STEAM_CANDIDATES (which already includes
# the macOS root on darwin).
_STEAM_ROOTS: list[Path] = list(_STEAM_CANDIDATES)

# NotProton keeps its patched CrossOver runner copies here.
_RUNNERS_ROOT = Path.home() / "Library" / "Application Support" / "notproton" / "runners"

_TOOL_NAME_PREFIX = "notproton"

_DISPLAY_NAME_RE = re.compile(r'"display_name"\s+"([^"]*)"')

# PE machine values (read from the prefix's ntdll.dll) -> NotProton flavor.
_MACHINE_FLAVOR = {0xAA64: "fex", 0x8664: "rosetta"}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NotProtonTool:
    """One installed NotProton compatibility tool.

    ``available`` is True iff the runner copy
    ``runners/crossover-<build>/CrossOver/lib/wine`` exists; the other
    path fields are still populated (pointing at the expected runner
    layout) so callers can report *which* directory is missing.
    """

    name: str               # tool directory name, e.g. "notproton-fex-41069"
    display: str            # "display_name" from compatibilitytool.vdf
    build: str              # contents of the ``build`` marker file
    flavor: str             # contents of the ``flavor`` marker ("fex"/"rosetta")
    tool_dir: Path          # .../compatibilitytools.d/<name>
    run_script: Path        # tool_dir / "run" (Proton-verb compatible)
    cx_root: Path           # .../notproton/runners/crossover-<build>/CrossOver
    wine_bin: Path          # raw wine executable for this tool's flavor
    wineserver: Path        # matching wineserver binary
    wine_unix_dir: Path     # .../lib/wine/{aarch64-unix,x86_64-unix}
    available: bool         # runner copy present and usable


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_macos() -> bool:
    return sys.platform == "darwin"


def _read_marker(path: Path) -> str:
    """Read a single-line marker file (``build``/``flavor``), '' when unreadable."""
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _display_name(tool_dir: Path) -> str | None:
    """Extract the ``display_name`` from the tool's compatibilitytool.vdf."""
    try:
        text = (tool_dir / "compatibilitytool.vdf").read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = _DISPLAY_NAME_RE.search(text)
    return m.group(1) if m else None


def _is_executable(path: Path) -> bool:
    try:
        return path.is_file() and os.access(path, os.X_OK)
    except OSError:
        return False


def _resolve_wine(cx_root: Path, flavor: str) -> tuple[Path, Path, Path]:
    """Pick (wine_unix_dir, wine_bin, wineserver) for a tool's runner copy.

    Mirrors compat_run.sh: default to the arm64 loader, and fall back to
    the x86_64 wine + (Rosetta) server when the flavor is rosetta or the
    arm64 loader/server is missing or not executable.
    """
    wine_unix = cx_root / "lib" / "wine" / "aarch64-unix"
    wine_bin = wine_unix / "wine.app" / "Contents" / "MacOS" / "wine"
    wineserver = cx_root / "bin" / "wineserver-arm64"
    if flavor == "rosetta" or not _is_executable(wine_bin) or not _is_executable(wineserver):
        wine_unix = cx_root / "lib" / "wine" / "x86_64-unix"
        wine_bin = wine_unix / "wine"
        wineserver = cx_root / "bin" / "wineserver"
        if not _is_executable(wineserver):
            wineserver = cx_root / "bin" / "wineserver-x86"
    return wine_unix, wine_bin, wineserver


def _build_sort_key(build: str) -> list[int]:
    """Numeric version parts of a build id ("27.0.0.41069-fex" -> [27,0,0,41069])."""
    version = build.split("-", 1)[0]
    parts: list[int] = []
    for piece in version.split("."):
        num = 0
        for ch in piece:
            if not ch.isdigit():
                break
            num = num * 10 + int(ch)
        parts.append(num)
    return parts


def _iter_tool_dirs() -> list[Path]:
    """Every NotProton tool directory across the known Steam roots.

    A directory qualifies iff its name starts with ``notproton`` and it
    contains both a ``run`` file and a ``build`` file. Deduplicated by
    resolved path (symlinked Steam roots must not double-list a tool).
    """
    dirs: list[Path] = []
    seen: set[Path] = set()
    for steam_root in _STEAM_ROOTS:
        ctd = steam_root / "compatibilitytools.d"
        if not ctd.is_dir():
            continue
        try:
            entries = sorted(ctd.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir() or not entry.name.startswith(_TOOL_NAME_PREFIX):
                continue
            if not (entry / "run").is_file() or not (entry / "build").is_file():
                continue
            try:
                resolved = entry.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            dirs.append(entry)
    return dirs


def _tool_from_dir(tool_dir: Path) -> NotProtonTool:
    build = _read_marker(tool_dir / "build")
    flavor = _read_marker(tool_dir / "flavor")
    display = _display_name(tool_dir) or tool_dir.name
    cx_root = _RUNNERS_ROOT / f"crossover-{build}" / "CrossOver"
    wine_unix, wine_bin, wineserver = _resolve_wine(cx_root, flavor)
    return NotProtonTool(
        name=tool_dir.name,
        display=display,
        build=build,
        flavor=flavor,
        tool_dir=tool_dir,
        run_script=tool_dir / "run",
        cx_root=cx_root,
        wine_bin=wine_bin,
        wineserver=wineserver,
        wine_unix_dir=wine_unix,
        available=(cx_root / "lib" / "wine").is_dir(),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_notproton_tools() -> list[NotProtonTool]:
    """All installed NotProton tools, newest build first.

    Sorted by build version descending, then ``fex`` before ``rosetta``
    within the same build (deterministic for UI lists and pickers).
    """
    tools = [_tool_from_dir(d) for d in _iter_tool_dirs()]
    tools.sort(key=lambda t: t.flavor)                       # fex < rosetta
    tools.sort(key=lambda t: _build_sort_key(t.build), reverse=True)
    return tools


def notproton_installed() -> bool:
    """True when at least one NotProton tool is installed."""
    return bool(list_notproton_tools())


def find_notproton_tool(name: str) -> NotProtonTool | None:
    """Find a tool by directory name, display name, or flavor-suffixed display.

    Case-insensitive. Accepts the labels the UI persists for selected
    runners (e.g. "CrossOver 26.3", "CrossOver 26.3 (Rosetta)") as well as
    raw tool directory names.
    """
    if not name:
        return None
    target = name.strip().casefold()
    for tool in list_notproton_tools():
        candidates = {
            tool.name.casefold(),
            tool.display.casefold(),
            f"{tool.display} (FEX)".casefold(),
            f"{tool.display} (Rosetta)".casefold(),
        }
        if target in candidates:
            return tool
    return None


def tool_for_build(build: str, flavor: str | None = None) -> NotProtonTool | None:
    """Find a tool by its build id (and flavor, when given).

    A build can be shared by a fex and a rosetta tool (e.g. the 41069-fex
    build); pass *flavor* to disambiguate. Without it, the first match in
    list order wins (fex before rosetta).
    """
    if not build:
        return None
    for tool in list_notproton_tools():
        if tool.build != build:
            continue
        if flavor is None or tool.flavor == flavor:
            return tool
    return None


def build_record(compat_data: Path) -> "tuple[str, str] | None":
    """Read NotProton's ``notproton-build`` record for a compatdata dir.

    Returns ``(build, display)`` - line 1 is the build id, line 2 the tool
    display name - or None when the record is absent or unreadable.
    """
    try:
        lines = (Path(compat_data) / "notproton-build").read_text(
            encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if not lines or not lines[0].strip():
        return None
    build = lines[0].strip()
    display = lines[1].strip() if len(lines) > 1 else ""
    return build, display


def prefix_flavor(prefix: Path | str | None) -> str | None:
    """Detect a prefix's flavor from its ntdll PE machine (like compat_run.sh).

    Reads drive_c/windows/system32/ntdll.dll: u32 at offset 60 is the export
    directory RVA, which must point at a "PE\\0\\0" signature; the u16 after
    the signature is the machine (0xAA64 = aarch64/fex, 0x8664 = x86_64/
    rosetta). Returns "fex"/"rosetta", or None when unreadable/unknown.
    """
    if prefix is None:
        return None
    dll = Path(prefix) / "drive_c" / "windows" / "system32" / "ntdll.dll"
    try:
        with open(dll, "rb") as f:
            head = f.read(64)
            if len(head) < 64:
                return None
            export_off = struct.unpack_from("<I", head, 60)[0]
            if export_off < 64 or export_off > 1 << 24:
                return None
            f.seek(export_off)
            sig = f.read(4)
            if sig != b"PE\x00\x00":
                return None
            machine = struct.unpack("<H", f.read(2))[0]
    except (OSError, struct.error):
        return None
    return _MACHINE_FLAVOR.get(machine)


def runner_for_prefix(compat_data: Path, prefix: Path | str | None = None) -> NotProtonTool | None:
    """Resolve the NotProton tool that owns a game's prefix.

    Reads the ``notproton-build`` record and matches installed tools by
    build; when a build is shared by fex and rosetta tools the prefix's
    ntdll machine (``prefix_flavor``) disambiguates. When the machine is
    unreadable, prefers an available tool (fex first, list order). Returns
    None when the record is missing, no tool matches, or none is available.
    """
    record = build_record(compat_data)
    if record is None:
        return None
    build, _display = record
    tools = [t for t in list_notproton_tools() if t.build == build]
    if not tools:
        return None
    if len(tools) == 1:
        return tools[0]
    flavor = prefix_flavor(prefix)
    if flavor is not None:
        for tool in tools:
            if tool.flavor == flavor and tool.available:
                return tool
    for tool in tools:
        if tool.available:
            return tool
    return None
