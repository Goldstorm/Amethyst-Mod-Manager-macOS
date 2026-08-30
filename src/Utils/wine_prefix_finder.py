"""
Utils/wine_prefix_finder.py
Unified Wine/Proton prefix discovery across all launchers.

Provides a single entry point to find the Wine prefix for a game regardless
of which launcher installed it (Steam, Lutris, Heroic, Faugus, CrossOver,
non-Steam shortcuts) and a reverse lookup to identify which launcher manages
a given prefix path.

Used by get_runner().run_in_prefix(), wizard prefix selection, and tool launch
where the prefix must be resolved without knowing the launcher ahead of time.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

# ---------------------------------------------------------------------------
# Prefix info — returned by all discovery functions
# ---------------------------------------------------------------------------

# Launcher identity strings
LAUNCHER_STEAM = "steam"
LAUNCHER_LUTRIS = "lutris"
LAUNCHER_HEROIC = "heroic"
LAUNCHER_FAUGUS = "faugus"
LAUNCHER_CROSSOVER = "crossover"
LAUNCHER_STEAM_SHORTCUT = "steam_shortcut"
LAUNCHER_UNKNOWN = "unknown"

LAUNCHER_LABELS: dict[str, str] = {
    LAUNCHER_STEAM: "Steam",
    LAUNCHER_LUTRIS: "Lutris",
    LAUNCHER_HEROIC: "Heroic",
    LAUNCHER_FAUGUS: "Faugus",
    LAUNCHER_CROSSOVER: "CrossOver",
    LAUNCHER_STEAM_SHORTCUT: "Steam (Non-Steam Shortcut)",
    LAUNCHER_UNKNOWN: "Custom",
}


@dataclass(frozen=True)
class PrefixInfo:
    """Resolved Wine prefix with launcher metadata.

    Attributes:
        prefix:         The prefix path (drive_c/ root, NOT compatdata parent).
        launcher:       Launcher identity string (e.g. "steam", "lutris").
        launcher_label: Human-readable label.
        game_id:        Store/app identifier (Steam App ID, Heroic appName, etc.)
                        Empty string if unknown.
        runner_name:    Proton/Wine runner name (e.g. "GE-Proton10-28").
                        Empty string if unknown.
    """
    prefix: Path
    launcher: str = LAUNCHER_UNKNOWN
    launcher_label: str = ""
    game_id: str = ""
    runner_name: str = ""

    def __post_init__(self) -> None:
        # Ensure prefix is always a Path
        if not isinstance(self.prefix, Path):
            object.__setattr__(self, "prefix", Path(self.prefix))
        if not self.launcher_label:
            object.__setattr__(self, "launcher_label",
                               LAUNCHER_LABELS.get(self.launcher, self.launcher))


# ---------------------------------------------------------------------------
# Core: find prefix for a game by various search criteria
# ---------------------------------------------------------------------------

def find_prefix_for_game(
    *,
    steam_id: str = "",
    alt_steam_ids: list[str] | None = None,
    app_names: list[str] | None = None,
    exe_name: str = "",
    exe_name_alts: list[str] | None = None,
    game_path: Path | str | None = None,
    launcher_hint: str | None = None,
) -> PrefixInfo | None:
    """Find the Wine prefix for a game across all launcher backends.

    Search order (modified by *launcher_hint* when set):
      1. Steam (compatdata) — if steam_id provided
      2. Lutris — if exe_name matches a Lutris game
      3. Heroic — if app_names provided
      4. Faugus — if exe_name matches a Faugus game
      5. Steam non-Steam shortcuts — if exe_name matches
      6. CrossOver — scan all bottles for a matching game exe

    Args:
        steam_id:         Steam App ID (e.g. "377160").
        alt_steam_ids:    Alternate Steam IDs to try.
        app_names:        Heroic/Epic/GOG app names.
        exe_name:         Windows exe name (e.g. "Fallout4.exe").
        exe_name_alts:    Alternate exe names.
        game_path:        Game install directory (helps Steam find the right
                          library).
        launcher_hint:    Prefer a specific launcher (short-circuits search).

    Returns:
        PrefixInfo if found, None otherwise.
    """
    if launcher_hint:
        # Short-circuit: only check the hinted launcher
        result = _find_prefix_single_launcher(
            launcher=launcher_hint,
            steam_id=steam_id,
            app_names=app_names,
            exe_name=exe_name,
            exe_name_alts=exe_name_alts,
            game_path=game_path,
        )
        if result:
            return result
        # If hinted launcher fails, fall through to full search
        # (the hint is a preference, not a hard constraint)

    all_exe_names = [exe_name, *(exe_name_alts or [])]

    # 1. Steam
    steam_candidates = [steam_id, *(alt_steam_ids or [])]
    for sid in steam_candidates:
        if not sid:
            continue
        info = _find_steam_prefix(sid, game_path)
        if info:
            return info

    # 2. Lutris
    if all_exe_names:
        info = _find_lutris_prefix(all_exe_names)
        if info:
            return info

    # 3. Heroic
    if app_names:
        info = _find_heroic_prefix(app_names)
        if info:
            return info

    # 4. Faugus
    if all_exe_names:
        info = _find_faugus_prefix(all_exe_names)
        if info:
            return info

    # 5. Steam non-Steam shortcuts
    if all_exe_names:
        info = _find_shortcut_prefix(all_exe_names)
        if info:
            return info

    # 6. CrossOver (macOS only)
    if sys.platform == "darwin":
        info = _find_crossover_prefix(exe_name, app_names)
        if info:
            return info

    return None


def _find_prefix_single_launcher(
    *,
    launcher: str,
    steam_id: str = "",
    app_names: list[str] | None = None,
    exe_name: str = "",
    exe_name_alts: list[str] | None = None,
    game_path: Path | str | None = None,
) -> PrefixInfo | None:
    """Find prefix using a single launcher backend."""
    all_exe_names = [exe_name, *(exe_name_alts or [])]

    if launcher == LAUNCHER_STEAM:
        if steam_id:
            return _find_steam_prefix(steam_id, game_path)
        # Try alt IDs
        for sid in (app_names or []):
            info = _find_steam_prefix(sid, game_path)
            if info:
                return info

    elif launcher == LAUNCHER_LUTRIS:
        if all_exe_names:
            return _find_lutris_prefix(all_exe_names)

    elif launcher == LAUNCHER_HEROIC:
        if app_names:
            return _find_heroic_prefix(app_names)

    elif launcher == LAUNCHER_FAUGUS:
        if all_exe_names:
            return _find_faugus_prefix(all_exe_names)

    elif launcher == LAUNCHER_CROSSOVER:
        if sys.platform == "darwin":
            return _find_crossover_prefix(exe_name, app_names)

    elif launcher == LAUNCHER_STEAM_SHORTCUT:
        if all_exe_names:
            return _find_shortcut_prefix(all_exe_names)

    return None


# ---------------------------------------------------------------------------
# Per-launcher discovery
# ---------------------------------------------------------------------------

def _find_steam_prefix(
    steam_id: str,
    game_path: Path | str | None = None,
) -> PrefixInfo | None:
    """Find prefix via Steam compatdata."""
    try:
        from Utils.steam_finder import (
            find_prefix as _find_steam_prefix,
            find_proton_for_game,
        )
        prefix = _find_steam_prefix(steam_id, game_path)
        if prefix is None:
            return None

        # Resolve runner name
        runner_name = ""
        try:
            proton_script = find_proton_for_game(steam_id)
            if proton_script:
                runner_name = proton_script.parent.name
        except Exception:
            pass

        return PrefixInfo(
            prefix=Path(prefix),
            launcher=LAUNCHER_STEAM,
            launcher_label="Steam",
            game_id=steam_id,
            runner_name=runner_name,
        )
    except Exception:
        return None


def _find_lutris_prefix(exe_names: list[str]) -> PrefixInfo | None:
    """Find prefix via Lutris game matching."""
    try:
        from Utils.lutris_finder import find_lutris_game_info_by_exe

        for exe in exe_names:
            if not exe:
                continue
            info = find_lutris_game_info_by_exe(exe)
            if info is not None and info[1] is not None:
                prefix = Path(info[1])
                # info[0] = wine binary, info[1] = prefix, info[2] = slug
                runner_name = info[2] if len(info) > 2 and info[2] else ""

                return PrefixInfo(
                    prefix=prefix,
                    launcher=LAUNCHER_LUTRIS,
                    launcher_label="Lutris",
                    game_id=runner_name,
                    runner_name=runner_name,
                )
    except Exception:
        pass
    return None


def _find_heroic_prefix(app_names: list[str]) -> PrefixInfo | None:
    """Find prefix via Heroic Games Launcher."""
    try:
        from Utils.heroic_finder import (
            find_heroic_prefix,
            find_heroic_proton_for_prefix,
        )
        prefix = find_heroic_prefix(app_names)
        if prefix is None:
            return None

        runner_name = ""
        try:
            proton_script = find_heroic_proton_for_prefix(prefix)
            if proton_script:
                runner_name = proton_script.parent.name
        except Exception:
            pass

        return PrefixInfo(
            prefix=Path(prefix),
            launcher=LAUNCHER_HEROIC,
            launcher_label="Heroic",
            game_id=app_names[0] if app_names else "",
            runner_name=runner_name,
        )
    except Exception:
        return None


def _find_faugus_prefix(exe_names: list[str]) -> PrefixInfo | None:
    """Find prefix via Faugus Launcher."""
    try:
        from Utils.faugus_finder import find_faugus_game_info_by_exe

        for exe in exe_names:
            if not exe:
                continue
            info = find_faugus_game_info_by_exe(exe)
            if info is not None and info[1] is not None:
                prefix = Path(info[1])
                runner_name = info[2] if len(info) > 2 and info[2] else ""

                return PrefixInfo(
                    prefix=prefix,
                    launcher=LAUNCHER_FAUGUS,
                    launcher_label="Faugus",
                    game_id=runner_name,
                    runner_name=runner_name,
                )
    except Exception:
        pass
    return None


def _find_shortcut_prefix(exe_names: list[str]) -> PrefixInfo | None:
    """Find prefix via Steam non-Steam shortcuts."""
    try:
        from Utils.steam_shortcuts import find_shortcut_game_info_by_exe

        for exe in exe_names:
            if not exe:
                continue
            info = find_shortcut_game_info_by_exe(exe)
            if info is not None and info[1] is not None:
                prefix = Path(info[1])
                runner_name = info[2] if len(info) > 2 and info[2] else ""

                return PrefixInfo(
                    prefix=prefix,
                    launcher=LAUNCHER_STEAM_SHORTCUT,
                    launcher_label="Steam (Non-Steam Shortcut)",
                    game_id=runner_name,
                    runner_name=runner_name,
                )
    except Exception:
        pass
    return None


def _find_crossover_prefix(
    exe_name: str = "",
    app_names: list[str] | None = None,
) -> PrefixInfo | None:
    """Find prefix via CrossOver bottles (macOS).

    Scans all CrossOver bottles looking for the target exe or a game
    matching the app names.
    """
    if sys.platform != "darwin":
        return None

    try:
        from Utils.crossover_finder import list_crossover_bottles
        bottles = list_crossover_bottles()
    except Exception:
        return None

    for bottle in bottles:
        drive_c = bottle / "drive_c"
        if not drive_c.is_dir():
            continue

        # Check for the exe in Program Files, Programs, Program Files (x86)
        for subdir in (
            "Program Files",
            "Program Files (x86)",
            "Program Files (x86)",
            "Games",
        ):
            search_root = drive_c / subdir
            if not search_root.is_dir():
                continue
            if exe_name:
                found = _search_for_exe(search_root, exe_name)
                if found:
                    return PrefixInfo(
                        prefix=bottle,
                        launcher=LAUNCHER_CROSSOVER,
                        launcher_label="CrossOver",
                        game_id=bottle.name,
                        runner_name="",
                    )

        # Also check the bottle name against app names
        if app_names:
            bottle_lower = bottle.name.lower()
            for name in app_names:
                if name.lower() in bottle_lower or bottle_lower in name.lower():
                    return PrefixInfo(
                        prefix=bottle,
                        launcher=LAUNCHER_CROSSOVER,
                        launcher_label="CrossOver",
                        game_id=bottle.name,
                        runner_name="",
                    )

    return None


def _search_for_exe(root: Path, exe_name: str, max_depth: int = 5) -> Path | None:
    """Search for a Windows exe inside a Wine prefix drive_c subtree."""
    try:
        for level in range(max_depth + 1):
            for candidate in root.rglob(f"*{exe_name}"):
                if level > max_depth:
                    break
                if (candidate.is_file()
                        and candidate.name.lower() == exe_name.lower()):
                    return candidate
    except OSError:
        pass
    # Fast path: direct check
    direct = root / exe_name
    if direct.is_file():
        return direct
    # One-level deep in common locations
    for subdir in root.iterdir():
        if subdir.is_dir():
            candidate = subdir / exe_name
            if candidate.is_file():
                return candidate
    return None


# ---------------------------------------------------------------------------
# Reverse lookup: identify what manages a given prefix path
# ---------------------------------------------------------------------------

def identify_prefix(prefix_path: str | Path) -> PrefixInfo | None:
    """Determine which launcher manages a given prefix path.

    Returns PrefixInfo with launcher identification, or None if the path
    doesn't look like a Wine prefix.
    """
    p = Path(prefix_path)
    if not p.is_dir():
        return None

    # Check if it's a Wine prefix at all
    if not _looks_like_wine_prefix(p):
        return None

    # Steam compatdata pattern: .../steamapps/compatdata/<id>/pfx
    if _is_steam_compatdata_prefix(p):
        steam_id = _extract_steam_id(p)
        return PrefixInfo(
            prefix=p,
            launcher=LAUNCHER_STEAM,
            launcher_label="Steam",
            game_id=steam_id,
        )

    # Lutris: lutris.json marker
    if (p / "lutris.json").is_file():
        return PrefixInfo(
            prefix=p,
            launcher=LAUNCHER_LUTRIS,
            launcher_label="Lutris",
        )

    # CrossOver bottle (macOS)
    if sys.platform == "darwin" and _is_crossover_bottle(p):
        return PrefixInfo(
            prefix=p,
            launcher=LAUNCHER_CROSSOVER,
            launcher_label="CrossOver",
            game_id=p.name,
        )

    # Heroic: check if path is under a known Heroic prefix dir
    try:
        from Utils.heroic_finder import find_heroic_prefix
        # Heroic prefixes are usually under ~/Games/Heroic/Prefixes/
        # or a custom defaultWinePrefix
    except Exception:
        pass

    # Faugus
    try:
        from Utils.faugus_finder import is_faugus_prefix
        if is_faugus_prefix(p):
            return PrefixInfo(
                prefix=p,
                launcher=LAUNCHER_FAUGUS,
                launcher_label="Faugus",
            )
    except Exception:
        pass

    # Lutris fallback (no lutris.json but proper prefix layout)
    try:
        from Utils.lutris_finder import is_lutris_prefix
        if is_lutris_prefix(p):
            return PrefixInfo(
                prefix=p,
                launcher=LAUNCHER_LUTRIS,
                launcher_label="Lutris",
            )
    except Exception:
        pass

    # Generic Wine prefix
    return PrefixInfo(
        prefix=p,
        launcher=LAUNCHER_UNKNOWN,
        launcher_label="Custom",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _looks_like_wine_prefix(p: Path) -> bool:
    """Check if a directory looks like a Wine prefix."""
    return (p / "drive_c").is_dir() and (p / "user.reg").is_file()


def _is_steam_compatdata_prefix(p: Path) -> bool:
    """Check if p is inside a Steam compatdata directory."""
    # Pattern: .../steamapps/compatdata/<id>/pfx
    #   p = .../steamapps/compatdata/<id>/pfx
    #   p.parent = .../steamapps/compatdata/<id>
    #   p.parent.parent = .../steamapps/compatdata
    #   p.parent.parent.parent = .../steamapps
    if p.name not in ("pfx", "prefix"):
        return False
    parent = p.parent
    grandparent = parent.parent
    if grandparent.name != "compatdata":
        return False
    # The steamapps dir is the parent of compatdata
    steamapps = grandparent.parent
    return steamapps.name == "steamapps"


def _extract_steam_id(p: Path) -> str:
    """Extract Steam App ID from a compatdata path."""
    parent = p.parent
    if p.name in ("pfx", "prefix"):
        return parent.name
    return ""


def _is_crossover_bottle(p: Path) -> bool:
    """Check if a path is inside a CrossOver bottles directory."""
    if sys.platform != "darwin":
        return False
    try:
        from Utils.crossover_finder import list_crossover_bottles
        bottles = list_crossover_bottles()
        return p in bottles or any(
            p == b or b in p.parents or b == p.parent
            for b in bottles
        )
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Wizard helper: find or create an isolated prefix for a tool
# ---------------------------------------------------------------------------

def find_tool_prefix(
    *,
    game,
    tool_exe_name: str,
    prefix_mode: str,
    runner_name: str,
) -> Path | None:
    """Find the prefix for a wizard tool based on the selected prefix mode.

    Mirrors the logic in Utils.exe_launch but returns Path | None without
    mutating anything. Used by WineStepWidget to show prefix status.

    Args:
        game:           BaseGame instance.
        tool_exe_name:  Exe name (e.g. "BethINI.exe").
        prefix_mode:    One of "isolated", "shared", "game".
        runner_name:    Runner name (e.g. "GE-Proton10-28").

    Returns:
        Prefix path or None (for "game" mode the game's own prefix is used).
    """
    if prefix_mode == "game":
        pfx = (game.get_prefix_path()
               if hasattr(game, "get_prefix_path") else None)
        return Path(pfx) if pfx else None

    try:
        from Utils.exe_launch import (
            PREFIX_MODE_SHARED, PREFIX_MODE_ISOLATED,
            shared_prefix_dir,
        )
    except Exception:
        return None

    if prefix_mode == PREFIX_MODE_SHARED:
        return shared_prefix_dir(runner_name)

    # Isolated: prefix_<runner_name>/ next to the tool exe
    try:
        from Utils.xedit_tools import tool_exe_path
        exe = tool_exe_path(game, tool_exe_name, "")
        return exe.parent / f"prefix_{runner_name}"
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Cross-platform prefix environment builder
# ---------------------------------------------------------------------------

def build_prefix_env(
    prefix_info: PrefixInfo,
    base_env: dict | None = None,
) -> dict:
    """Build a WINEPREFIX / STEAM_COMPAT_DATA_PATH environment for a prefix.

    Args:
        prefix_info:  PrefixInfo from find_prefix_for_game() or identify_prefix().
        base_env:     Base environment dict to copy from.

    Returns:
        Environment dict with prefix vars set.
    """
    env = base_env.copy() if base_env else {}
    prefix = prefix_info.prefix

    if prefix_info.launcher == LAUNCHER_STEAM:
         # Steam compatdata: STEAM_COMPAT_DATA_PATH is the compatdata/<id>/ dir
        compat_data = prefix.parent if prefix.name in ("pfx", "prefix") else prefix
        env["STEAM_COMPAT_DATA_PATH"] = str(compat_data)
        env["WINEPREFIX"] = str(prefix)
    else:
         # Non-Steam: WINEPREFIX is the prefix root
        env["WINEPREFIX"] = str(prefix)

    return env


# ---------------------------------------------------------------------------
# Runner name → wine binary + prefix env (cross-platform, macOS-aware)
# ---------------------------------------------------------------------------

def resolve_wine_runner_env(
    runner_name: str,
    *,
    prefix_path: "Path | None" = None,
    base_env: "dict | None" = None,
) -> "tuple[Path, dict] | tuple[None, None]":
    """Resolve a *runner name* to ``(wine_binary, env)`` for any platform.

    This is the macOS entry point that the Linux-only resolvers in
    :mod:`Utils.exe_launch` / :mod:`Utils.protontricks` fall back to when
    ``find_steam_root_for_proton_script`` returns ``None``. On Linux it is not
    used (those resolvers already handle Proton directly), so this never
    changes Linux behaviour.

    *runner_name* is whatever :class:`WineStepWidget` hands the caller — a
    CrossOver bottle name, ``"System Wine"``, or ``""``. *prefix_path* is the
    prefix to run in (a CrossOver bottle root, an isolated/shared tool prefix,
    or the game's own prefix); when given it goes into ``env['WINEPREFIX']``.

    Returns ``(wine_binary, env)`` on success or ``(None, None)`` when no
    wine binary can be found (i.e. neither CrossOver nor system Wine is
    installed).
    """
    from Utils.crossover_finder import find_wine_binary_for_name

    runner = find_wine_binary_for_name(runner_name)
    if runner is None:
        return None, None

    env = {}
    if prefix_path is not None:
        env["WINEPREFIX"] = str(prefix_path)
    if base_env:
        # Let the caller's explicit env win over the runner's own, but always
        # keep WINEPREFIX (the prefix is the whole point).
        merged = dict(base_env)
        merged.setdefault("WINEPREFIX", env.get("WINEPREFIX", ""))
        env = merged
    return runner, env
