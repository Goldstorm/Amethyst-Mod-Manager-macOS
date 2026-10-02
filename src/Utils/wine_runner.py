"""
Utils/wine_runner.py
Platform-agnostic Wine/Proton runner abstraction.

Provides a unified interface for running Windows executables, installing
dependencies, and managing Wine prefixes — regardless of whether the
underlying runtime is Steam Proton (Linux), CrossOver (macOS), Lutris Wine,
Heroic's Wine, or system Wine.

This module is the cornerstone of the macOS port (Phase 1 of WIZ_PLAN.md).
Wizard views and tool launchers import through `get_runner()` and never
need to know which backend is active.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from collections.abc import Sequence

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
LogFn = Callable[[str], None]


# ---------------------------------------------------------------------------
# Abstract base — the contract all runners implement
# ---------------------------------------------------------------------------
class WineRunner(ABC):
    """Platform-agnostic Wine/Proton runner."""

    @abstractmethod
    def run_in_prefix(
        self,
        prefix: Path,
        exe: Path,
        args: Sequence[str] = (),
        env: dict | None = None,
        *,
        host_cwd: str | Path | None = None,
        verb: str = "runinprefix",
    ) -> list[str]:
        """Build command to run a Windows exe inside a prefix.

        Args:
            prefix:     Wine/Proton prefix directory.
            exe:        Windows executable to run.
            args:       Extra arguments after the exe.
            env:        Environment dict (mutated by some runners).
            host_cwd:   Host working directory for the process.
            verb:       Proton verb (run, runinprefix, waitforexitandrun).
                        Ignored by non-Proton runners.
        """
        ...

    @abstractmethod
    def run_reg_add(
        self,
        prefix: Path,
        key: str,
        value: str,
        value_name: str = "",
        value_type: str = "REG_SZ",
        env: dict | None = None,
    ) -> list[str]:
        """Build command for `wine reg add` inside a prefix.

        Args:
            prefix:      Wine/Proton prefix directory.
            key:         Registry key path (e.g. HKLM\\Software\\MyApp).
            value:       Data to write.
            value_name:  Value name (empty for default value).
            value_type:  REG_SZ, REG_DWORD, REG_EXPAND_SZ, etc.
            env:         Environment dict.
        """
        ...

    @abstractmethod
    def find_wine_binary(self) -> Path | None:
        """Locate the wine/proton binary for this runner."""
        ...

    @abstractmethod
    def list_available_versions(self) -> list[str]:
        """Return human-readable names of available runner versions."""
        ...

    @abstractmethod
    def install_dependency(
        self,
        prefix: Path,
        component: str,
        log_fn: LogFn,
        env: dict | None = None,
    ) -> bool:
        """Install a winetricks-style dependency into a prefix.

        Args:
            prefix:    Target Wine prefix.
            component: Dependency identifier (e.g. "d3dcompiler_47", "vcredist_x64").
            log_fn:    Logging callback.
            env:       Environment dict.
        Returns:
            True if installation succeeded or was already present.
        """
        ...

    # -----------------------------------------------------------------------
    # Concrete helpers (have defaults but subclasses may override)
    # -----------------------------------------------------------------------

    def run_wine_tool(
        self,
        prefix: Path,
        tool: str,
        env: dict | None = None,
    ) -> list[str]:
        """Build command to launch a Wine tool (winecfg, regedit, etc.).

        Default implementation uses `wine <tool>` directly.
        """
        wine_bin = self.find_wine_binary()
        if wine_bin is None:
            return []
        cmd_env = env.copy() if env else {}
        cmd_env["WINEPREFIX"] = str(prefix)
        return [str(wine_bin), tool]


# ---------------------------------------------------------------------------
# ProtonRunner — wraps existing Steam Proton / umu-run plumbing
# ---------------------------------------------------------------------------
class ProtonRunner(WineRunner):
    """Runner that uses Steam Proton (Linux).

    Delegates to the existing ``steam_finder.proton_run_command()`` and
    ``list_installed_proton()`` infrastructure. On Steam-less systems,
    automatically routes through umu-run when available.
    """

    def run_in_prefix(
        self,
        prefix: Path,
        exe: Path,
        args: Sequence[str] = (),
        env: dict | None = None,
        *,
        host_cwd: str | Path | None = None,
        verb: str = "runinprefix",
    ) -> list[str]:
        from Utils.launchers.steam import proton_run_command, find_any_installed_proton

        proton_script = find_any_installed_proton()
        if proton_script is None:
            return []

        run_env = env.copy() if env else {}
        # Map prefix → STEAM_COMPAT_DATA_PATH for Proton
        run_env["STEAM_COMPAT_DATA_PATH"] = str(prefix.parent if prefix.name == "pfx" else prefix)
        run_env["WINEPREFIX"] = str(prefix)

        return proton_run_command(
            proton_script,
            verb,
            str(exe),
            *map(str, args),
            env=run_env,
            host_cwd=host_cwd,
        )

    def run_reg_add(
        self,
        prefix: Path,
        key: str,
        value: str,
        value_name: str = "",
        value_type: str = "REG_SZ",
        env: dict | None = None,
    ) -> list[str]:
        from Utils.launchers.steam import proton_run_command, find_any_installed_proton

        proton_script = find_any_installed_proton()
        if proton_script is None:
            return []

        run_env = env.copy() if env else {}
        run_env["STEAM_COMPAT_DATA_PATH"] = str(prefix.parent if prefix.name == "pfx" else prefix)
        run_env["WINEPREFIX"] = str(prefix)

        cmd_args = ["runinprefix", "reg", "add", key]
        if value_name:
            cmd_args.extend(["/v", value_name])
        cmd_args.extend(["/t", value_type, "/d", value, "/f"])

        return proton_run_command(proton_script, *cmd_args, env=run_env)

    def find_wine_binary(self) -> Path | None:
        from Utils.launchers.steam import find_any_installed_proton
        return find_any_installed_proton()

    def list_available_versions(self) -> list[str]:
        from Utils.launchers.steam import list_installed_proton
        return [s.parent.name for s in list_installed_proton()]

    def install_dependency(
        self,
        prefix: Path,
        component: str,
        log_fn: LogFn,
        env: dict | None = None,
    ) -> bool:
        """Install a dependency using protontricks infrastructure."""
        from Utils.wine.protontricks import is_dep_installed, install_winetricks_verb
        from Utils.wine.protontricks import D3D_DEP_KEY, VCREDIST_DEP_KEY
        from Utils.wine.protontricks import install_d3dcompiler_47, install_vcredist

        if is_dep_installed(prefix, component):
            return True

        if component == D3D_DEP_KEY:
            return install_d3dcompiler_47(prefix, log_fn=log_fn)
        elif component == VCREDIST_DEP_KEY:
            return install_vcredist(prefix, log_fn=log_fn)
        else:
            # Generic winetricks verb
            return install_winetricks_verb(prefix, component, log_fn=log_fn)


# ---------------------------------------------------------------------------
# CrossOverRunner — macOS CrossOver bottles
# ---------------------------------------------------------------------------
class CrossOverRunner(WineRunner):
    """Runner that uses CrossOver bottles (macOS).

    Uses `cxexec` or the CrossOver-bundled `wine` binary with WINEPREFIX
    pointing to a CrossOver bottle's `drive_c` parent.
    """

    def __init__(self, bottle_path: Path | None = None):
        """
        Args:
            bottle_path: Specific bottle to use. If None, the runner
                         discovers bottles at runtime via crossover_finder.
        """
        self._bottle_path = bottle_path

    def _find_bottle(self) -> Path | None:
        if self._bottle_path and self._bottle_path.is_dir():
            return self._bottle_path
        from Utils.crossover_finder import find_crossover_bottle, list_crossover_bottles
        # Try to find a default bottle
        bottles = list_crossover_bottles()
        return bottles[0] if bottles else None

    def run_in_prefix(
        self,
        prefix: Path,
        exe: Path,
        args: Sequence[str] = (),
        env: dict | None = None,
        *,
        host_cwd: str | Path | None = None,
        verb: str = "runinprefix",
    ) -> list[str]:
        wine_bin = self.find_wine_binary()
        if wine_bin is None:
            return []

        run_env = env.copy() if env else {}
        run_env["WINEPREFIX"] = str(prefix)

        # `start.exe /wait /unix` blocks until the tool exits (winetricks'
        # form); the raw wine binary honours WINEPREFIX for both bottles and
        # plain tool prefixes without the bottle-management wrapper.
        cmd = [str(wine_bin), "start.exe", "/wait", "/unix", str(exe)]
        if args:
            cmd.extend(map(str, args))

        # CrossOver uses DISPLAY from the environment; no special wrapping needed
        return cmd

    def run_reg_add(
        self,
        prefix: Path,
        key: str,
        value: str,
        value_name: str = "",
        value_type: str = "REG_SZ",
        env: dict | None = None,
    ) -> list[str]:
        wine_bin = self.find_wine_binary()
        if wine_bin is None:
            return []

        run_env = env.copy() if env else {}
        run_env["WINEPREFIX"] = str(prefix)

        cmd = [str(wine_bin), "reg", "add", key]
        if value_name:
            cmd.extend(["/v", value_name])
        cmd.extend(["/t", value_type, "/d", value, "/f"])
        return cmd

    def find_wine_binary(self) -> Path | None:
        """Prefer the raw wine binary: plain Wine semantics (WINEPREFIX selects
        the prefix) for both bottles and Amethyst's plain tool prefixes."""
        from Utils.crossover_finder import (
            find_crossover_wine_binary, find_raw_wine,
        )
        return find_raw_wine() or find_crossover_wine_binary()

    def list_available_versions(self) -> list[str]:
        from Utils.crossover_finder import list_crossover_bottles
        bottles = list_crossover_bottles()
        return [b.name for b in bottles]

    def install_dependency(
        self,
        prefix: Path,
        component: str,
        log_fn: LogFn,
        env: dict | None = None,
    ) -> bool:
        """Install a dependency using winetricks inside the CrossOver prefix."""
        wine_bin = self.find_wine_binary()
        if wine_bin is None:
            log_fn("CrossOver: wine binary not found")
            return False

        run_env = env.copy() if env else {}
        run_env["WINEPREFIX"] = str(prefix)

        # CrossOver bundles winetricks; try it first
        cx_winetricks = self._find_crossover_winetricks()
        if cx_winetricks:
            cmd = [str(cx_winetricks), "--unattended", component]
        else:
            # Fall back to system winetricks via CrossOver's wine
            wt = shutil.which("winetricks")
            if not wt:
                log_fn(f"CrossOver: no winetricks found for component '{component}'")
                return False
            cmd = [wt, "--unattended", component]

        try:
            result = subprocess.run(
                cmd,
                env=run_env,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                log_fn(f"CrossOver: installed {component}")
                return True
            else:
                log_fn(f"CrossOver: winetricks failed for {component}: {result.stderr[:200]}")
                return False
        except subprocess.TimeoutExpired:
            log_fn(f"CrossOver: winetricks timed out for {component}")
            return False
        except Exception as e:
            log_fn(f"CrossOver: error installing {component}: {e}")
            return False

    def _find_crossover_winetricks(self) -> Path | None:
        """Locate CrossOver's bundled winetricks."""
        bottle = self._find_bottle()
        if bottle:
            bundled = bottle / "drive_c" / "Program Files" / "Winetricks" / "winetricks"
            if bundled.is_file():
                return bundled
        # CrossOver app bundle location
        for candidate in [
            Path("/Applications/CrossOver.app/Contents/Resources/cxOffice/tools/winetricks"),
            Path("/Applications/CrossOver.app/Contents/SharedSupport/libexec/winetricks"),
        ]:
            if candidate.is_file():
                return candidate
        return None


# ---------------------------------------------------------------------------
# SystemWineRunner — plain `wine` from PATH or Homebrew
# ---------------------------------------------------------------------------
class SystemWineRunner(WineRunner):
    """Runner that uses system Wine (macOS or Linux).

    Falls back to this when no Proton or CrossOver is available.
    Wine must be in PATH (e.g. Homebrew's `brew install --cask wine-stable`).
    """

    def run_in_prefix(
        self,
        prefix: Path,
        exe: Path,
        args: Sequence[str] = (),
        env: dict | None = None,
        *,
        host_cwd: str | Path | None = None,
        verb: str = "runinprefix",
    ) -> list[str]:
        wine_bin = self.find_wine_binary()
        if wine_bin is None:
            return []

        run_env = env.copy() if env else {}
        run_env["WINEPREFIX"] = str(prefix)

        cmd = [str(wine_bin), "start", "/unix", str(exe)]
        if args:
            cmd.extend(map(str, args))
        return cmd

    def run_reg_add(
        self,
        prefix: Path,
        key: str,
        value: str,
        value_name: str = "",
        value_type: str = "REG_SZ",
        env: dict | None = None,
    ) -> list[str]:
        wine_bin = self.find_wine_binary()
        if wine_bin is None:
            return []

        run_env = env.copy() if env else {}
        run_env["WINEPREFIX"] = str(prefix)

        cmd = [str(wine_bin), "reg", "add", key]
        if value_name:
            cmd.extend(["/v", value_name])
        cmd.extend(["/t", value_type, "/d", value, "/f"])
        return cmd

    def find_wine_binary(self) -> Path | None:
        wine = shutil.which("wine")
        if wine:
            return Path(wine)
        # Homebrew on macOS
        if sys.platform == "darwin":
            brew_prefix = shutil.which("brew")
            if brew_prefix:
                try:
                    result = subprocess.run(
                        ["brew", "--prefix", "wine-stable"],
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0:
                        candidate = Path(result.stdout.strip()) / "bin" / "wine"
                        if candidate.is_file():
                            return candidate
                except Exception:
                    pass
                # Also try wine (non-stable)
                result = subprocess.run(
                    ["brew", "--prefix", "wine"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    candidate = Path(result.stdout.strip()) / "bin" / "wine"
                    if candidate.is_file():
                        return candidate
        return None

    def list_available_versions(self) -> list[str]:
        wine_bin = self.find_wine_binary()
        if wine_bin is None:
            return []
        try:
            result = subprocess.run(
                [str(wine_bin), "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                return [f"System Wine {version}"]
        except Exception:
            pass
        return ["System Wine"]

    def install_dependency(
        self,
        prefix: Path,
        component: str,
        log_fn: LogFn,
        env: dict | None = None,
    ) -> bool:
        """Install a dependency using winetricks."""
        wt = shutil.which("winetricks")
        if not wt:
            log_fn(f"System Wine: winetricks not found in PATH for component '{component}'")
            return False

        run_env = env.copy() if env else {}
        run_env["WINEPREFIX"] = str(prefix)

        cmd = [wt, "--unattended", component]
        try:
            result = subprocess.run(
                cmd,
                env=run_env,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                log_fn(f"System Wine: installed {component}")
                return True
            else:
                log_fn(f"System Wine: winetricks failed for {component}: {result.stderr[:200]}")
                return False
        except subprocess.TimeoutExpired:
            log_fn(f"System Wine: winetricks timed out for {component}")
            return False
        except Exception as e:
            log_fn(f"System Wine: error installing {component}: {e}")
            return False


# ---------------------------------------------------------------------------
# LutrisRunner — Lutris Wine runner (Linux)
# ---------------------------------------------------------------------------
class LutrisRunner(WineRunner):
    """Runner that uses Lutris-managed Wine builds."""

    def __init__(self, wine_version: str = "", prefix_path: Path | None = None):
        self._wine_version = wine_version
        self._prefix_path = prefix_path

    def run_in_prefix(
        self,
        prefix: Path,
        exe: Path,
        args: Sequence[str] = (),
        env: dict | None = None,
        *,
        host_cwd: str | Path | None = None,
        verb: str = "runinprefix",
    ) -> list[str]:
        wine_bin = self.find_wine_binary()
        if wine_bin is None:
            return []

        run_env = env.copy() if env else {}
        run_env["WINEPREFIX"] = str(prefix)

        cmd = [str(wine_bin), "start", "/unix", str(exe)]
        if args:
            cmd.extend(map(str, args))
        return cmd

    def run_reg_add(
        self,
        prefix: Path,
        key: str,
        value: str,
        value_name: str = "",
        value_type: str = "REG_SZ",
        env: dict | None = None,
    ) -> list[str]:
        wine_bin = self.find_wine_binary()
        if wine_bin is None:
            return []

        run_env = env.copy() if env else {}
        run_env["WINEPREFIX"] = str(prefix)

        cmd = [str(wine_bin), "reg", "add", key]
        if value_name:
            cmd.extend(["/v", value_name])
        cmd.extend(["/t", value_type, "/d", value, "/f"])
        return cmd

    def find_wine_binary(self) -> Path | None:
        from Utils.launchers.lutris import find_lutris_wine_for_prefix
        prefix = self._prefix_path
        if prefix:
            return find_lutris_wine_for_prefix(prefix)
        # Try to find any lutris wine
        from Utils.launchers.lutris import find_lutris_roots
        for root in find_lutris_roots():
            wine_dir = root.data_dir / "wine"
            if wine_dir.is_dir():
                for ver_dir in sorted(wine_dir.iterdir(), reverse=True):
                    if ver_dir.is_dir():
                        for exe_name in ("wine", "wine64"):
                            candidate = ver_dir / "bin" / exe_name
                            if candidate.is_file():
                                return candidate
        return None

    def list_available_versions(self) -> list[str]:
        from Utils.launchers.lutris import find_lutris_roots
        versions: list[str] = []
        for root in find_lutris_roots():
            wine_dir = root.data_dir / "wine"
            if wine_dir.is_dir():
                for ver_dir in sorted(wine_dir.iterdir(), reverse=True):
                    if ver_dir.is_dir():
                        versions.append(ver_dir.name)
        return versions

    def install_dependency(
        self,
        prefix: Path,
        component: str,
        log_fn: LogFn,
        env: dict | None = None,
    ) -> bool:
        """Install a dependency using winetricks via Lutris Wine."""
        wine_bin = self.find_wine_binary()
        if wine_bin is None:
            log_fn("Lutris: wine binary not found")
            return False

        wt = shutil.which("winetricks")
        if not wt:
            log_fn(f"Lutris: winetricks not found in PATH for component '{component}'")
            return False

        run_env = env.copy() if env else {}
        run_env["WINEPREFIX"] = str(prefix)
        # Use the Lutris wine binary for winetricks
        run_env["WINE"] = str(wine_bin)

        cmd = [wt, "--unattended", component]
        try:
            result = subprocess.run(
                cmd,
                env=run_env,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                log_fn(f"Lutris: installed {component}")
                return True
            else:
                log_fn(f"Lutris: winetricks failed for {component}: {result.stderr[:200]}")
                return False
        except subprocess.TimeoutExpired:
            log_fn(f"Lutris: winetricks timed out for {component}")
            return False
        except Exception as e:
            log_fn(f"Lutris: error installing {component}: {e}")
            return False


# ---------------------------------------------------------------------------
# HeroicRunner — Heroic Games Launcher Wine (Linux/macOS)
# ---------------------------------------------------------------------------
class HeroicRunner(WineRunner):
    """Runner that uses Heroic Games Launcher's Wine builds."""

    def __init__(self, prefix_path: Path | None = None):
        self._prefix_path = prefix_path

    def run_in_prefix(
        self,
        prefix: Path,
        exe: Path,
        args: Sequence[str] = (),
        env: dict | None = None,
        *,
        host_cwd: str | Path | None = None,
        verb: str = "runinprefix",
    ) -> list[str]:
        proton_script = self.find_wine_binary()
        if proton_script is None:
            return []

        run_env = env.copy() if env else {}
        run_env["WINEPREFIX"] = str(prefix)

        # Heroic uses Proton scripts, so go through proton_run_command
        from Utils.launchers.steam import proton_run_command
        return proton_run_command(
            proton_script,
            "runinprefix",
            str(exe),
            *map(str, args),
            env=run_env,
            host_cwd=host_cwd,
        )

    def run_reg_add(
        self,
        prefix: Path,
        key: str,
        value: str,
        value_name: str = "",
        value_type: str = "REG_SZ",
        env: dict | None = None,
    ) -> list[str]:
        proton_script = self.find_wine_binary()
        if proton_script is None:
            return []

        run_env = env.copy() if env else {}
        run_env["WINEPREFIX"] = str(prefix)

        from Utils.launchers.steam import proton_run_command
        cmd_args = ["runinprefix", "reg", "add", key]
        if value_name:
            cmd_args.extend(["/v", value_name])
        cmd_args.extend(["/t", value_type, "/d", value, "/f"])
        return proton_run_command(proton_script, *cmd_args, env=run_env)

    def find_wine_binary(self) -> Path | None:
        from Utils.launchers.heroic import find_heroic_proton_for_prefix
        prefix = self._prefix_path
        if prefix:
            return find_heroic_proton_for_prefix(prefix)
        from Utils.launchers.heroic import list_heroic_proton_scripts
        scripts = list_heroic_proton_scripts()
        return scripts[0] if scripts else None

    def list_available_versions(self) -> list[str]:
        from Utils.launchers.heroic import list_heroic_proton_scripts
        return [s.parent.name for s in list_heroic_proton_scripts()]

    def install_dependency(
        self,
        prefix: Path,
        component: str,
        log_fn: LogFn,
        env: dict | None = None,
    ) -> bool:
        """Install a dependency using winetricks via Heroic's Wine."""
        from Utils.wine.protontricks import is_dep_installed, install_winetricks_verb
        from Utils.wine.protontricks import D3D_DEP_KEY, VCREDIST_DEP_KEY
        from Utils.wine.protontricks import install_d3dcompiler_47, install_vcredist

        if is_dep_installed(prefix, component):
            return True

        if component == D3D_DEP_KEY:
            return install_d3dcompiler_47(prefix, log_fn=log_fn)
        elif component == VCREDIST_DEP_KEY:
            return install_vcredist(prefix, log_fn=log_fn)
        else:
            return install_winetricks_verb(prefix, component, log_fn=log_fn)


# ---------------------------------------------------------------------------
# Factory — pick the right runner for this platform
# ---------------------------------------------------------------------------

def get_runner(launcher_type: str | None = None) -> WineRunner:
    """Returns the appropriate WineRunner based on platform + config.

    Args:
        launcher_type: Optional explicit launcher type override.
            One of: "proton", "crossover", "system_wine", "lutris", "heroic".
            If None, auto-detects based on platform and available tools.
    """
    if launcher_type == "crossover":
        return CrossOverRunner()
    elif launcher_type == "system_wine":
        return SystemWineRunner()
    elif launcher_type == "lutris":
        return LutrisRunner()
    elif launcher_type == "heroic":
        return HeroicRunner()

    # Auto-detect
    if sys.platform == "darwin":
        # macOS: try CrossOver first, then system Wine
        from Utils.crossover_finder import list_crossover_bottles
        if list_crossover_bottles():
            return CrossOverRunner()
        return SystemWineRunner()
    else:
        # Linux: try Proton first, then Lutris, then Heroic, then system Wine
        from Utils.launchers.steam import steam_client_installed, list_installed_proton
        if list_installed_proton():
            return ProtonRunner()
        # Check Lutris
        try:
            from Utils.launchers.lutris import find_lutris_roots
            if find_lutris_roots():
                return LutrisRunner()
        except Exception:
            pass
        # Check Heroic
        try:
            from Utils.launchers.heroic import list_heroic_proton_scripts
            if list_heroic_proton_scripts():
                return HeroicRunner()
        except Exception:
            pass
        # Fallback to system Wine
        return SystemWineRunner()


def get_default_runner_type() -> str:
    """Return the default launcher type string for this platform."""
    if sys.platform == "darwin":
        from Utils.crossover_finder import list_crossover_bottles
        if list_crossover_bottles():
            return "crossover"
        return "system_wine"
    else:
        from Utils.launchers.steam import list_installed_proton
        if list_installed_proton():
            return "proton"
        try:
            from Utils.launchers.lutris import find_lutris_roots
            if find_lutris_roots():
                return "lutris"
        except Exception:
            pass
        try:
            from Utils.launchers.heroic import list_heroic_proton_scripts
            if list_heroic_proton_scripts():
                return "heroic"
        except Exception:
            pass
        return "system_wine"


# ---------------------------------------------------------------------------
# Backwards-compat shims (Phase 4 migration helpers)
#
# These thin wrappers route old-style calls through the WineRunner abstraction.
# They will be removed once all callers are migrated in Phase 4/5.
# ---------------------------------------------------------------------------

def wine_run_command(
    prefix: Path,
    exe: Path,
    args: Sequence[str] = (),
    env: dict | None = None,
    *,
    launcher_type: str | None = None,
    host_cwd: str | Path | None = None,
) -> list[str]:
    """Build command to run a Windows exe inside a Wine/Proton prefix.

    Backwards-compatible wrapper that auto-selects the appropriate runner.

    Args:
        prefix:       Wine/Proton prefix directory.
        exe:          Windows executable to run.
        args:         Extra arguments.
        env:          Environment dict.
        launcher_type: Override launcher type ("proton", "crossover", etc.).
        host_cwd:     Host working directory.
    """
    runner = get_runner(launcher_type)
    return runner.run_in_prefix(prefix, exe, args, env, host_cwd=host_cwd)


def wine_reg_add(
    prefix: Path,
    key: str,
    value: str,
    value_name: str = "",
    value_type: str = "REG_SZ",
    env: dict | None = None,
    launcher_type: str | None = None,
) -> list[str]:
    """Build `wine reg add` command through the appropriate runner.

    Backwards-compatible wrapper.
    """
    runner = get_runner(launcher_type)
    return runner.run_reg_add(prefix, key, value, value_name, value_type, env)
