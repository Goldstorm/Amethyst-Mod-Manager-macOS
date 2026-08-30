"""
Utils/crossover_finder.py
CrossOver bottle and wine binary discovery for macOS.

CrossOver (by CodeWeavers) stores its Wine bottles (prefixes) in several
possible locations depending on installation method (App Store vs DMG).
This module finds bottles and the CrossOver-bundled wine/cxexec binary.

Used by CrossOverRunner in wine_runner.py.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# CrossOver bottle locations (by installation method)
# ---------------------------------------------------------------------------

# App Store install (sandboxed)
_CX_APP_STORE_BOTTLES = Path.home() / "Library" / "Containers" / "com.codeweavers.CrossOver" / "Data" / "bottles"

# DMG / standard install
_CX_DMG_BOTTLES = Path.home() / "Library" / "Application Support" / "CrossOver" / "bottles"

# Older installs (pre-2020)
_CX_LEGACY_BOTTLES = Path.home() / "CrossOver" / "bottles"

_CX_BOTTLE_DIRS: list[Path] = [
    _CX_APP_STORE_BOTTLES,
    _CX_DMG_BOTTLES,
    _CX_LEGACY_BOTTLES,
]

# ---------------------------------------------------------------------------
# CrossOver wine binary locations
# ---------------------------------------------------------------------------

# cxexec is the recommended entry point — it sets up the environment
# correctly for the bottle. It lives inside the CrossOver.app bundle.
_CXEXEC_CANDIDATES: list[Path] = [
    Path("/Applications/CrossOver.app/Contents/Frameworks/CrossOver.app/Contents/MacOS/cxexec"),
    Path("/Applications/CrossOver.app/Contents/MacOS/cxexec"),
    Path("/Applications/CrossOver 24.app/Contents/Frameworks/CrossOver.app/Contents/MacOS/cxexec"),
    Path("/Applications/CrossOver 24.app/Contents/MacOS/cxexec"),
    Path("/Applications/CrossOver 23.app/Contents/Frameworks/CrossOver.app/Contents/MacOS/cxexec"),
    Path("/Applications/CrossOver 23.app/Contents/MacOS/cxexec"),
    Path("/Applications/CrossOver 22.app/Contents/Frameworks/CrossOver.app/Contents/MacOS/cxexec"),
    Path("/Applications/CrossOver 22.app/Contents/MacOS/cxexec"),
    Path("/Applications/CrossOver 21.app/Contents/Frameworks/CrossOver.app/Contents/MacOS/cxexec"),
    Path("/Applications/CrossOver 21.app/Contents/MacOS/cxexec"),
]

# Fallback: plain wine from CrossOver bundle
_CX_WINE_CANDIDATES: list[Path] = [
    Path("/Applications/CrossOver.app/Contents/SharedSupport/libexec/wine/mac/wine"),
    Path("/Applications/CrossOver.app/Contents/MacOS/wine"),
]


def _is_macos() -> bool:
    """Check if running on macOS."""
    return sys.platform == "darwin"


def list_crossover_bottles() -> list[Path]:
    """Return paths to all CrossOver bottles.

    Scans all known bottle directories and returns bottle paths sorted
    by name (case-insensitive). Each returned path is the bottle root
    (parent of drive_c), NOT the drive_c itself.

    Returns:
        List of bottle directory paths, sorted alphabetically.
        Empty list if no CrossOver bottles found.
    """
    if not _is_macos():
        return []

    bottles: list[Path] = []
    seen_names: set[str] = set()

    for bottle_dir in _CX_BOTTLE_DIRS:
        if not bottle_dir.is_dir():
            continue
        try:
            for entry in bottle_dir.iterdir():
                if not entry.is_dir():
                    continue
                # A valid bottle has a drive_c subdirectory
                drive_c = entry / "drive_c"
                if drive_c.is_dir():
                    name_lower = entry.name.lower()
                    if name_lower not in seen_names:
                        seen_names.add(name_lower)
                        bottles.append(entry)
        except OSError:
            continue

    bottles.sort(key=lambda p: p.name.lower())
    return bottles


def find_crossover_bottle(name: str) -> Path | None:
    """Try to find a CrossOver bottle by name (case-insensitive).

    Args:
        name: Bottle name to search for.

    Returns:
        Path to the bottle directory, or None if not found.
    """
    for bottle in list_crossover_bottles():
        if bottle.name.lower() == name.lower():
            return bottle
    return None


def find_crossover_wine_binary() -> Path | None:
    """Locate the CrossOver wine/cxexec binary.

    Prefers cxexec (which properly sets up the CrossOver environment)
    over the raw wine binary. Falls back to cxexec in PATH, then
    to the raw wine binary candidates.

    Returns:
        Path to cxexec or wine binary, or None if not found.
    """
    if not _is_macos():
        return None

    # 1. Try cxexec candidates (most reliable)
    for candidate in _CXEXEC_CANDIDATES:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    # 2. Try cxexec in PATH
    cxexec = shutil.which("cxexec")
    if cxexec:
        return Path(cxexec)

    # 3. Try raw wine from CrossOver bundle
    for candidate in _CX_WINE_CANDIDATES:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    # 4. Try to find any CrossOver.app and search inside it using known patterns
    applications = Path("/Applications")
    if applications.is_dir():
        try:
            for app in applications.iterdir():
                if not app.is_dir() or not app.name.startswith("CrossOver"):
                    continue

                # Search for cxexec using known patterns
                for pattern in _CXEXEC_PATTERNS:
                    candidate = app / pattern
                    if candidate.is_file() and os.access(candidate, os.X_OK):
                        return candidate

                # Search for wine using known patterns
                for pattern in _CX_WINE_PATTERNS:
                    candidate = app / pattern
                    if candidate.is_file() and os.access(candidate, os.X_OK):
                        return candidate

                # Deep search as last resort
                for root, dirs, files in os.walk(app):
                    depth = len(Path(root).relative_to(app).parts)
                    if depth > 7:
                        continue
                    if "cxexec" in files:
                        cxexec_path = Path(root) / "cxexec"
                        if os.access(cxexec_path, os.X_OK):
                            return cxexec_path
                    if "wine" in files:
                        wine_path = Path(root) / "wine"
                        if os.access(wine_path, os.X_OK):
                            return wine_path
        except OSError:
            pass

    return None


def crossover_installed() -> bool:
    """Check if CrossOver appears to be installed.

    Returns True if cxexec or a CrossOver wine binary is found,
    OR if any CrossOver bottles exist.
    """
    if not _is_macos():
        return False
    return (find_crossover_wine_binary() is not None
            or bool(list_crossover_bottles()))


def get_crossover_version() -> str | None:
    """Try to determine the installed CrossOver version.

    Returns a version string (e.g. "24.0") or None if undetectable.
    """
    if not _is_macos():
        return None

    # Try to read from the app bundle's Info.plist
    applications = Path("/Applications")
    if applications.is_dir():
        try:
            for app in applications.iterdir():
                if app.is_dir() and app.name.startswith("CrossOver"):
                    info_plist = app / "Contents" / "Info.plist"
                    if info_plist.is_file():
                        # Parse CFBundleShortVersionString from plist
                        try:
                            result = subprocess.run(
                                ["defaults", "read", str(info_plist), "CFBundleShortVersionString"],
                                capture_output=True, text=True, timeout=5
                            )
                            if result.returncode == 0:
                                return result.stdout.strip()
                        except Exception:
                            pass
                    # Fallback: extract version from app name
                    # e.g. "CrossOver 24.app" → "24"
                    name = app.name
                    if name.startswith("CrossOver "):
                        version_part = name[len("CrossOver "):-len(".app")] if name.endswith(".app") else name[len("CrossOver "):]
                        if version_part:
                            return version_part
        except OSError:
            pass

    return None


# CrossOver version-specific wine binary patterns (deep-search fallback).
# Defined at the bottom but referenced by find_crossover_wine_binary / the
_CX_WINE_PATTERNS = [
    "Contents/SharedSupport/CrossOver/CrossOver-Hosted Application/wine",
    "Contents/SharedSupport/libexec/wine/mac/wine",
    "Contents/MacOS/wine",
]

_CXEXEC_PATTERNS = [
    "Contents/Frameworks/CrossOver.app/Contents/MacOS/cxexec",
    "Contents/MacOS/cxexec",
]


def find_wine_binary_for_name(name: str, *, prefer_plain_wine: bool = False
                                ) -> "Path | None":
    """Map a :class:`WineStepWidget` runner *name* to a wine/cxexec binary.

    The macOS picker (``wizards_qt/wine_step.py``) offers one of two kinds of
    runner name:

      * a **CrossOver bottle name** (e.g. ``"Steam"``, ``"CrossOver 24"``) ->
        the CrossOver wine binary. The bottle itself is the prefix; the caller
        selects it via ``WINEPREFIX``.
      * the **``"System Wine"`` pseudo-name** (or ``""``) -> a Homebrew/PATH
        wine binary, resolved through
        :class:`Utils.wine_runner.SystemWineRunner`.

    ``prefer_plain_wine`` selects a generic ``wine`` binary over CrossOver's
    ``cxexec`` entry point. ``cxexec`` is bottle-specific (it configures a named
    bottle's environment), so isolated/shared *tool* prefixes -- which are plain
    Wine prefixes, not CrossOver bottles -- must use a plain ``wine``. A
    CrossOver bottle prefix itself is fine with ``cxexec``.

    Returns ``None`` off-darwin or when no binary can be resolved.
    """
    if not _is_macos():
        return None

    low = (name or "").strip().lower()

    # System Wine (Homebrew cask or a `wine` on PATH): reuse the abstraction's
    # own binary discovery so we never duplicate its candidate list here.
    if low in ("", "system wine", "wine", "wine-stable", "system"):
        from Utils.wine_runner import SystemWineRunner
        binary = SystemWineRunner().find_wine_binary()
        if binary is not None:
            return binary
        if not prefer_plain_wine:
            return find_crossover_wine_binary()
        return None

    if prefer_plain_wine:
        # Isolated/shared tool prefixes are plain Wine prefixes: prefer a raw
        # `wine` binary over the bottle-bound `cxexec` so the prefix is used as
        # a standalone WINEPREFIX.
        for candidate in _CX_WINE_CANDIDATES:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
        from Utils.wine_runner import SystemWineRunner
        binary = SystemWineRunner().find_wine_binary()
        if binary is not None:
            return binary

    # Named CrossOver bottle: any CrossOver wine binary is a valid runner; the
    # specific bottle is selected by the caller's WINEPREFIX.
    return find_crossover_wine_binary()
