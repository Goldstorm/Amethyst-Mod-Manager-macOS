"""
Utils/proton_compat.py
Platform-agnostic wrappers for Proton-specific utility functions.

On Linux:  Routes through Steam Proton (identical to existing behavior).
On macOS: Routes through CrossOver / system Wine via WineRunner.

This module re-exports the old function names so existing callers don't need
changing. It is the Phase 4 migration bridge described in WIZ_PLAN.md.

All functions here are thin wrappers around :mod:`Utils.wine_runner`.
"""

from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from collections.abc import Sequence


# ---------------------------------------------------------------------------
# proton_run_command replacement
# ---------------------------------------------------------------------------

def proton_run_command(
    proton_script: Path,
    *args: str,
    env: dict | None = None,
    host_cwd: str | Path | None = None,
) -> list[str]:
    """Build command to run a Windows exe through Wine/Proton.

    On Linux:  Uses Steam Proton (via wine_runner.ProtonRunner).
    On macOS: Uses CrossOver or system Wine (via wine_runner.CrossOverRunner
              or SystemWineRunner).

    Backwards-compatible replacement for
    ``steam_finder.proton_run_command``. The *proton_script* parameter is
    ignored on macOS (the runner discovers its own binary).
    """
    if sys.platform != "darwin":
        # Linux: delegate to existing implementation
        from Utils.launchers.steam import proton_run_command as _original
        return _original(proton_script, *args, env=env, host_cwd=host_cwd)

    # macOS: route through WineRunner
    from Utils.wine_runner import get_runner

    runner = get_runner()
    # Extract prefix from env
    prefix_str = env.get("WINEPREFIX", "") if env else ""
    prefix = Path(prefix_str) if prefix_str else None

    if prefix is None or not prefix.is_dir():
        # No prefix — try to find one from STEAM_COMPAT_DATA_PATH
        compat_data = env.get("STEAM_COMPAT_DATA_PATH", "") if env else ""
        if compat_data:
            cd = Path(compat_data)
            pfx = cd / "pfx" if (cd / "pfx").is_dir() else cd
            if pfx.is_dir():
                prefix = pfx

    if prefix is None:
        return []

    # Strip Proton verbs — CrossOver/system wine doesn't use them
    clean_args = [
        a for a in args
        if a not in ("run", "runinprefix", "waitforexitandrun")
    ]

    return runner.run_in_prefix(
        prefix=prefix,
        exe=Path(proton_script) if proton_script else Path("/dev/null"),
        args=clean_args,
        env=env,
        host_cwd=host_cwd,
    )


# ---------------------------------------------------------------------------
# list_installed_proton replacement
# ---------------------------------------------------------------------------

def list_installed_proton() -> list[Path]:
    """Return available Wine/Proton runners.

    On Linux:  Steam Proton scripts (compatibilitytools.d + steamapps/common).
    On macOS: CrossOver bottle paths (one per bottle).

    Backwards-compatible: returns list of Path objects. Callers that extract
    ``path.parent.name`` for display will get bottle names on macOS.
    """
    if sys.platform != "darwin":
        from Utils.launchers.steam import list_installed_proton as _original
        return _original()

    # macOS: return CrossOver bottles as "runner paths"
    from Utils.crossover_finder import list_crossover_bottles
    bottles = list_crossover_bottles()

    # Also check for system wine
    from Utils.wine_runner import SystemWineRunner
    sys_wine = SystemWineRunner().find_wine_binary()
    if sys_wine:
        bottles.append(sys_wine.parent)

    # Deduplicate
    seen: set[Path] = set()
    result: list[Path] = []
    for b in bottles:
        try:
            resolved = b.resolve()
        except Exception:
            resolved = b
        if resolved not in seen:
            seen.add(resolved)
            result.append(b)
    return result


# ---------------------------------------------------------------------------
# find_prefix replacement
# ---------------------------------------------------------------------------

def find_prefix(
    steam_id: str,
    game_path: Path | str | None = None,
) -> Path | None:
    """Find the Wine prefix for a game.

    On Linux:  Steam compatdata prefix.
    On macOS: CrossOver bottle matching the game.

    Backwards-compatible replacement for ``steam_finder.find_prefix``.
    """
    if sys.platform != "darwin":
        from Utils.launchers.steam import find_prefix as _original
        return _original(steam_id, game_path)

    # macOS: try to find a CrossOver bottle
    from Utils.crossover_finder import find_crossover_bottle, list_crossover_bottles

    # Try to find by app ID (some games use Steam ID as bottle name)
    if steam_id:
        bottle = find_crossover_bottle(steam_id)
        if bottle:
            return bottle

    # Try all bottles
    bottles = list_crossover_bottles()
    return bottles[0] if bottles else None


# ---------------------------------------------------------------------------
# list_installed_proton_names (convenience)
# ---------------------------------------------------------------------------

def list_installed_proton_names() -> list[str]:
    """Return human-readable names of available runners.

    On Linux:  Proton version names (e.g. "GE-Proton10-28").
    On macOS: Bottle names (e.g. "Steam", "MacOS") or "System Wine".
    """
    runners = list_installed_proton()
    names = []
    for r in runners:
        name = r.parent.name if r.name != "wine" else "System Wine"
        if name not in names:
            names.append(name)
    return names


# ---------------------------------------------------------------------------
# winetricks-style dependency installation
# ---------------------------------------------------------------------------

def install_winetricks_verb(
    prefix: Path,
    component: str,
    log_fn: Callable[[str], None] | None = None,
) -> bool:
    """Install a winetricks verb into a Wine prefix.

    On Linux:  Uses protontricks/winetricks.
    On macOS: Uses CrossOver's bundled winetricks or system winetricks.
    """
    log = log_fn or (lambda _m: None)

    if sys.platform != "darwin":
        from Utils.wine.protontricks import install_winetricks_verb as _original
        return _original(prefix, component, log_fn=log)

    # macOS: use WineRunner
    from Utils.wine_runner import get_runner
    runner = get_runner()
    return runner.install_dependency(prefix, component, log_fn=log)


def install_d3dcompiler_47(
    prefix: Path,
    log_fn: Callable[[str], None] | None = None,
) -> bool:
    """Install d3dcompiler_47 into a Wine prefix."""
    log = log_fn or (lambda _m: None)

    if sys.platform != "darwin":
        from Utils.wine.protontricks import install_d3dcompiler_47 as _original
        return _original(prefix, log_fn=log)

    from Utils.wine_runner import get_runner
    from Utils.wine.protontricks import D3D_DEP_KEY
    runner = get_runner()
    return runner.install_dependency(prefix, D3D_DEP_KEY, log_fn=log)


def install_vcredist(
    prefix: Path,
    log_fn: Callable[[str], None] | None = None,
) -> bool:
    """Install Visual C++ redistributable into a Wine prefix."""
    log = log_fn or (lambda _m: None)

    if sys.platform != "darwin":
        from Utils.wine.protontricks import install_vcredist as _original
        return _original(prefix, log_fn=log)

    from Utils.wine_runner import get_runner
    from Utils.wine.protontricks import VCREDIST_DEP_KEY
    runner = get_runner()
    return runner.install_dependency(prefix, VCREDIST_DEP_KEY, log_fn=log)


# ---------------------------------------------------------------------------
# Wine registry operations
# ---------------------------------------------------------------------------

def wine_reg_add(
    prefix: Path,
    key: str,
    value: str,
    value_name: str = "",
    value_type: str = "REG_SZ",
    env: dict | None = None,
) -> list[str]:
    """Build command for `wine reg add` inside a Wine prefix.

    Platform-agnostic: uses the appropriate runner.
    """
    from Utils.wine_runner import get_runner
    runner = get_runner()
    return runner.run_reg_add(prefix, key, value, value_name, value_type, env)


# ---------------------------------------------------------------------------
# Prefix health / dependency checking
# ---------------------------------------------------------------------------

def is_dep_installed(prefix: Path, key: str) -> bool:
    """Check if a dependency is installed in a prefix.

    Works on both Linux and macOS.
    """
    from Utils.wine.protontricks import is_dep_installed as _original
    return _original(prefix, key)


# ---------------------------------------------------------------------------
# Wine tool launchers (winecfg, regedit, etc.)
# ---------------------------------------------------------------------------

def launch_wine_tool(
    tool: str,
    prefix: Path,
    env: dict | None = None,
) -> bool:
    """Launch a Wine tool (winecfg, regedit, etc.) in a prefix.

    Platform-agnostic: uses the appropriate runner.
    """
    from Utils.wine_runner import get_runner
    runner = get_runner()

    wine_bin = runner.find_wine_binary()
    if wine_bin is None:
        return False

    tool_env = env.copy() if env else {}
    tool_env["WINEPREFIX"] = str(prefix)

    cmd = [str(wine_bin), tool]
    try:
        subprocess.Popen(
            cmd,
            env=tool_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Environment resolution helpers
# ---------------------------------------------------------------------------

def resolve_proton_env_for_game(game) -> tuple[Path | None, dict]:
    """Resolve Proton script + env for a game.

    On Linux:  Uses Steam Proton.
    On macOS: Returns (None, {}) — CrossOver doesn't need a proton script.

    Backwards-compatible return: (proton_script, env) where proton_script
    is None on macOS.
    """
    if sys.platform != "darwin":
        from Utils.wine.protontricks import build_proton_env_for_game
        return build_proton_env_for_game(game)

    # macOS: return CrossOver env
    prefix = game.get_prefix_path() if hasattr(game, "get_prefix_path") else None
    if prefix:
        env = {"WINEPREFIX": str(prefix)}
        return (None, env)
    return (None, {})
