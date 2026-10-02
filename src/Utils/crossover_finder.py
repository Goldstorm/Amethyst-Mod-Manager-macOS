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
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
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

    # 0. Installed CrossOver builds (deterministic order: official first,
    #    newest first) - covers the current and 26.x bundle layouts.
    for app in list_crossover_apps():
        for finder in (app.wine_launcher, app.raw_wine):
            found = finder()
            if found is not None:
                return found

    # 1. Try cxexec candidates (most reliable on pre-26 builds)
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


# ---------------------------------------------------------------------------
# CrossOver build (app bundle) discovery
#
# A Mac can have several CrossOver builds installed at once (e.g. the stable
# "CrossOver.app" plus a "CrossOver Preview [Ros].app"). Each build is a self
# contained app bundle with its own wine under
# Contents/SharedSupport/CrossOver/{bin,lib}. Bottles record which build last
# touched them in cxbottle.conf ("Timestamp"), so a bottle should be driven
# by the build that created/updated it whenever that build is still installed.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CrossoverApp:
    """One installed CrossOver build (an .app bundle)."""

    path: Path          # e.g. /Applications/CrossOver.app
    version: str        # CFBundleShortVersionString ("26.3", "20260821", ...)
    is_preview: bool    # True for "CrossOver Preview" builds

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def shared_support(self) -> Path:
        return self.path / "Contents" / "SharedSupport" / "CrossOver"

    @property
    def bin_dir(self) -> Path:
        return self.shared_support / "bin"

    def wine_launcher(self) -> Path | None:
        """The CrossOver ``wine`` entry point (perl wrapper, bottle-aware)."""
        cand = self.bin_dir / "wine"
        return cand if (cand.is_file() and os.access(cand, os.X_OK)) else None

    def raw_wine(self) -> Path | None:
        """The underlying wine binary (plain Wine: WINEPREFIX selects prefix).

        Unlike the bottle-aware wrapper this runs any prefix - including
        Amethyst's isolated/shared tool prefixes, which are not bottles.
        """
        cand = self.shared_support / "lib" / "wine" / "x86_64-unix" / "wine"
        return cand if (cand.is_file() and os.access(cand, os.X_OK)) else None

    def wineserver(self) -> Path | None:
        cand = self.bin_dir / "wineserver"
        return cand if (cand.is_file() and os.access(cand, os.X_OK)) else None


def _app_bundle_version(app: Path) -> str:
    """CFBundleShortVersionString from the bundle's Info.plist ('' if absent)."""
    plist = app / "Contents" / "Info.plist"
    if not plist.is_file():
        return ""
    try:
        import plistlib
        with open(plist, "rb") as fh:
            data = plistlib.load(fh)
        return str(data.get("CFBundleShortVersionString") or "")
    except Exception:
        return ""


def _version_sort_key(version: str) -> tuple:
    nums = re.findall(r"\d+", version or "")
    return tuple(int(n) for n in nums[:3]) if nums else (0,)


def list_crossover_apps() -> list[CrossoverApp]:
    """All installed CrossOver builds, official builds first, newest first.

    Scans /Applications (and ~/Applications). Returns [] off-darwin or when
    no CrossOver build is installed.
    """
    if not _is_macos():
        return []
    apps: list[CrossoverApp] = []
    seen: set[str] = set()
    for app_dir in (Path("/Applications"), Path.home() / "Applications"):
        if not app_dir.is_dir():
            continue
        try:
            entries = list(app_dir.iterdir())
        except OSError:
            continue
        for app in entries:
            if not (app.name.startswith("CrossOver")
                    and app.name.endswith(".app")):
                continue
            try:
                if not app.is_dir():
                    continue
                key = str(app.resolve())
            except OSError:
                continue
            if key in seen:
                continue
            seen.add(key)
            apps.append(CrossoverApp(
                path=app,
                version=_app_bundle_version(app),
                is_preview="preview" in app.name.lower(),
            ))
    # Newest build first (stable), then official before preview builds.
    apps.sort(key=lambda a: _version_sort_key(a.version), reverse=True)
    apps.sort(key=lambda a: a.is_preview)
    return apps


def primary_crossover_app() -> CrossoverApp | None:
    """The build to use by default (official build, newest version)."""
    apps = list_crossover_apps()
    return apps[0] if apps else None


def bottle_timestamp(bottle: Path) -> str:
    """CrossOver build timestamp recorded in the bottle's cxbottle.conf.

    E.g. ``20260821T113304Z`` - the build date of the CrossOver version that
    last created or updated the bottle. '' when unreadable/absent.
    """
    conf = Path(bottle) / "cxbottle.conf"
    try:
        text = conf.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    m = re.search(r'"?Timestamp"?\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else ""


def app_for_bottle(bottle: Path) -> CrossoverApp | None:
    """The installed build that last created/updated *bottle*.

    Matches the bottle's recorded build timestamp against the installed
    builds' version strings. Falls back to the primary (official, newest)
    build when the owning build was removed, and None when no build is
    installed at all.
    """
    apps = list_crossover_apps()
    if not apps:
        return None
    ts = bottle_timestamp(bottle)
    if ts:
        for app in apps:
            if app.version and ts.startswith(app.version):
                return app
        for app in apps:
            if app.version and app.version in ts:
                return app
    return apps[0]


def find_raw_wine(app: CrossoverApp | None = None) -> Path | None:
    """A plain (non-bottle) wine binary for *app*, or the primary build.

    Plain wine honours WINEPREFIX for any prefix - bottles and the isolated/
    shared tool prefixes - without CrossOver's bottle-management wrapper
    (no update prompts, no cxbottle.conf assumptions).
    """
    if not _is_macos():
        return None
    app = app or primary_crossover_app()
    if app is not None and app.raw_wine() is not None:
        return app.raw_wine()
    if app is not None and app.wine_launcher() is not None:
        return app.wine_launcher()
    # Legacy layouts / very old builds: fall back to the classic search.
    return find_crossover_wine_binary()


def crossover_root_for_wine(wine_bin: Path) -> Path | None:
    """The CrossOver SharedSupport/CrossOver root a wine binary belongs to.

    Plain wine loaded from a CrossOver build still pulls in the build's
    cxcompatdb.dll, which logs errors unless CX_ROOT points at the build.
    Returns None for wine outside a CrossOver bundle (e.g. Homebrew).
    """
    marker = "/Contents/SharedSupport/CrossOver/"
    s = str(wine_bin)
    if marker not in s:
        return None
    bundle = s.split(marker, 1)[0]
    root = Path(bundle) / "Contents" / "SharedSupport" / "CrossOver"
    return root if root.is_dir() else None


def find_wineserver_for_wine(wine_bin: Path) -> Path | None:
    """Locate the wineserver matching a wine binary.

    Plain wine ships wineserver next to wine; CrossOver's raw wine lives in
    lib/wine/x86_64-unix/ with its wineserver in the build's bin/ folder.
    """
    p = Path(wine_bin)
    cand = p.parent / "wineserver"
    if cand.is_file():
        return cand
    marker = "/Contents/SharedSupport/CrossOver/"
    s = str(p)
    if marker in s:
        bundle = s.split(marker, 1)[0]
        cand = (Path(bundle) / "Contents" / "SharedSupport"
                / "CrossOver" / "bin" / "wineserver")
        if cand.is_file():
            return cand
    return None


def is_crossover_bottle(path: Path) -> bool:
    """True when *path* is (inside) one of the discovered CrossOver bottles."""
    if not _is_macos() or not Path(path).is_dir():
        return False
    p = Path(path)
    try:
        p = p.resolve()
    except OSError:
        pass
    for bottle in list_crossover_bottles():
        try:
            b = bottle.resolve()
        except OSError:
            continue
        if p == b or b in p.parents:
            return True
    return False


def find_crossover_bottle_for_exe(
        exe_name: str,
        *,
        max_visits: int = 15000,
        max_depth: int = 9,
) -> "tuple[Path, Path] | None":
    """Find a CrossOver bottle that contains *exe_name*; (bottle, exe path).

    Used to recover the game's bottle when the saved prefix path is missing
    or points at a Linux layout. Checks the high-probability Steam/GOG install
    locations first (O(#games) dir listings) and only falls back to a bounded
    depth-first scan of drive_c, so it stays fast enough for a UI thread.
    """
    if not _is_macos() or not exe_name:
        return None
    target = exe_name.lower()
    for bottle in list_crossover_bottles():
        drive_c = bottle / "drive_c"
        if not drive_c.is_dir():
            continue
        # 1. Likely install roots: Steam / GOG / raw Program Files dirs.
        candidates: list[Path] = []
        for progfiles in ("Program Files (x86)", "Program Files"):
            pf = drive_c / progfiles
            if not pf.is_dir():
                continue
            for store in ("Steam/steamapps/common", "GOG Games"):
                root = pf / store
                if root.is_dir():
                    try:
                        for entry in root.iterdir():
                            if entry.is_dir():
                                candidates.append(entry / exe_name)
                    except OSError:
                        pass
            # A game installed straight into Program Files: <dir>/<exe>
            try:
                for entry in pf.iterdir():
                    if entry.is_dir() and entry.name.lower() not in ("steam", "gog games"):
                        candidates.append(entry / exe_name)
            except OSError:
                pass
        for cand in candidates:
            if cand.is_file() and cand.name.lower() == target:
                return bottle, cand
        # 2. Bounded scan of the whole drive_c.
        hit = _bounded_find_file(drive_c, target,
                                 max_visits=max_visits, max_depth=max_depth)
        if hit is not None:
            return bottle, hit
    return None


def _bounded_find_file(root: Path, name_lower: str, *,
                       max_visits: int, max_depth: int) -> Path | None:
    """Depth-first case-insensitive file search with a visit budget."""
    import os as _os
    stack: list[tuple[Path, int]] = [(root, 0)]
    visited = 0
    while stack:
        d, depth = stack.pop()
        if depth > max_depth:
            continue
        try:
            entries = list(_os.scandir(d))
        except OSError:
            continue
        for entry in entries:
            visited += 1
            if visited > max_visits:
                return None
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append((Path(entry.path), depth + 1))
                elif entry.is_file(follow_symlinks=True) \
                        and entry.name.lower() == name_lower:
                    return Path(entry.path)
            except OSError:
                continue
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
