# Wizard macOS Compatibility Plan

## Goal

Make all wizard tool functionality work on macOS (CrossOver/Wine) alongside the existing Linux/Proton support.

---

## HANDOFF / Progress Log (updated 2026-08-30)

> Read this first. Phases 1–3 are committed. Phase 4 is **partly done and
> uncommitted** — the macOS resolver fallback is implemented but not tested or
> committed.

### What is committed (do not redo)

| Phase | Deliverable | State |
|---|---|---|
| 0 | Core compat (config paths, xdg, steam_finder macOS path, sandbox no-ops, libloot rebuild) | ✅ committed |
| 1 | `Utils/wine_runner.py` — `WineRunner` ABC + `ProtonRunner` / `CrossOverRunner` / `SystemWineRunner` / `LutrisRunner` / `HeroicRunner` + `get_runner()` / `get_default_runner_type()` + back-compat shims `wine_run_command` / `wine_reg_add`. Selftest `Utils/_wine_runner_selftest.py`. | ✅ committed |
| 2 | `Utils/crossover_finder.py` (bottle + wine-binary discovery), `Utils/wine_prefix_finder.py` (unified `find_prefix_for_game` / `identify_prefix` / `PrefixInfo`). Selftests present. | ✅ committed |
| 3 | `wizards_qt/wine_step.py` — `WineStepWidget` dual-mode UI (Proton on Linux, CrossOver bottle / system Wine on macOS). `proton_step.py` kept as fallback, **not** deleted. | ✅ committed |
| 4 (part 1) | `Utils/proton_compat.py` routed through `get_runner()`; the two cross-platform helpers `crossover_finder.find_wine_binary_for_name(name, prefer_plain_wine=…)` and `wine_prefix_finder.resolve_wine_runner_env(runner_name, prefix_path, base_env, prefer_plain_wine=…)` were added (commit "Orphaned File Commits"). | ✅ committed |

### What is UNCOMMITTED (the current work — verify before building on it)

The macOS **resolver fallback**: on `darwin`, the prefix-env resolvers that
previously returned `None` when no Proton could be found now fall back to a
CrossOver bottle / system-Wine prefix. Mirrors the existing
`proton_tools._resolve_lutris_wine_env` precedent. **Linux is a no-op** (the
fallback is guarded by `sys.platform == "darwin"`), so Linux behaviour is
unchanged. `git status` shows 4 modified files, ~129 insertions, all compile:

- **`Utils/proton_tools.py`** — new `_resolve_macos_wine_env(prefix_path,
   runner_name="", log_fn=_noop)`: no-op off darwin; on darwin calls
   `resolve_wine_runner_env(..., prefer_plain_wine=True)` so the result is a raw
   `wine`-named binary (never CrossOver's `cxexec`, which `proton_run_command`
   would mis-build as `python3 cxexec …`). Wired into `resolve_proton_env`.
- **`Utils/protontricks.py`** — `build_proton_env_for_game` calls
   `_resolve_macos_wine_env` after its Lutris fallback.
- **`Utils/exe_launch.py`** — macOS fallback in four spots: `get_tool_prefix_env`
   (isolated tool prefix, builds `prefix_<runner>` next to the exe),
   `get_game_prefix_env` (game prefix, 3-tuple), and `launch_exe_via_proton`
   (both its isolated-override hole and its game-prefix cascade hole — the latter
   routes through the existing `lutris_env_extra` "bare wine, no steam" env path).
- **`Utils/wine_prefix_finder.py`** — `resolve_wine_runner_env` gained a
   `prefer_plain_wine: bool = False` param, threaded into
   `find_wine_binary_for_name`.

**Why `prefer_plain_wine`:** `crossover_finder.find_crossover_wine_binary()`
prefers `cxexec`, but `proton_run_command` only takes its bare-wine branch for a
binary literally named `wine`/`wine64`. Every resolver returns its result into
the `proton_script` slot that feeds `proton_run_command`, so the fallback must
yield a `wine`-named binary, not `cxexec`.

### What is still TODO (in priority order)

1. **Extend the selftests** (not yet done). Add cases to
   `Utils/_wine_prefix_finder_selftest.py`:
   - `resolve_wine_runner_env(name, prefix_path, prefer_plain_wine=True)` returns
     a `wine`-named binary when `find_wine_binary_for_name` yields one;
   - `_resolve_macos_wine_env` returns `(None, None)` when the platform is not
     darwin (mock `sys.platform`) and when no binary is found.
   - Run all three selftests (`_wine_runner_selftest.py`,
     `_crossover_finder_selftest.py`, `_wine_prefix_finder_selftest.py`) from
     `src/` — must stay green. They run without a real CrossOver install.
2. **macOS runtime verification** — the fallback is unverified end-to-end. With
   CrossOver or Homebrew wine installed: open a migrated wizard (Pandora / xEdit
   / DynDOLOD — the only 3 views on `WineStepWidget`), pick a bottle / "System
   Wine", run, and confirm the tool launches via a `wine` binary with
   `WINEPREFIX` set. Watch for: `resolve_compat_data(game_prefix)` must return the
   CrossOver bottle *root* (not its parent) for the game-prefix resolvers, or
   `WINEPREFIX` will point at the wrong prefix.
3. **Commit** the 4 files when 1–2 pass.
4. **Phase 5** — migrate the remaining ~45 wizard views off `proton_step.py`
   onto `wine_step.py` (only `pandora_view`, `dyndolod_view`, `xedit_view`
   done; they still say "ProtonStepWidget" in stale docstrings).
5. **Phase 6** — settings UI launcher-type picker (Steam Proton / CrossOver /
   Lutris / Heroic / System Wine) + default-prefix override. Not started.
6. **Known gap:** `list_installed_proton()` is not macOS-aware, but this does
   **not** block the fallback — `WineStepWidget` lists CrossOver bottles / system
   Wine directly (`wizards_qt/wine_step.py`), and the resolvers use
   `_resolve_macos_wine_env`. Only add macOS population to `list_installed_proton`
   if a Linux-only caller starts showing an empty picker.

### Quick reference for the next agent

- The **integration point** is `proton_run_command` (in
  `Utils/steam_finder.py`): it already runs a bare `wine` binary when the script
  is named `wine`/`wine64`. The macOS fallback plugs into that — do **not** add a
  `cxexec` branch there; yield a `wine` binary instead.
- All macOS fallbacks funnel through `_resolve_macos_wine_env`
  (`Utils/proton_tools.py`). Add new resolvers there too.
- Run from `src/` so imports resolve: `../.venv/bin/python3 …`.

---

## Current State

The wizard system has **44 Qt views** in `wizards_qt/`, but nearly all depend on **Proton-specific infrastructure**:

| Dependency | Used By |
|---|---|
| `proton_run_command()` | All wizards that run Windows `.exe` tools |
| `list_installed_proton()` | Proton version picker UI |
| `ProtonStepWidget` | Prefix/Proton selection step in wizards |
| `find_prefix()` | Steam prefix discovery |
| `protontricks.py` | Winetricks dependency installation |
| `proton_tools.py` | Wine tool execution, reg writes |

## Architecture: Wine Runner Abstraction

Create a platform-agnostic "Wine Runner" layer so wizards can run on macOS (CrossOver/Wine) or Linux (Proton) without conditionals scattered through every view.

---

## Phase 1: Create the Runner Abstraction  ✅ Done (committed)

**New file: `src/Utils/wine_runner.py`**

Define an interface that abstracts away Proton vs Wine/CrossOver:

```python
class WineRunner(ABC):
    """Platform-agnostic Wine/Proton runner."""

    @abstractmethod
    def run_in_prefix(self, prefix: Path, exe: Path, args: list[str], env: dict) -> list[str]:
        """Build command to run a Windows exe inside a prefix."""

    @abstractmethod
    def run_reg_add(self, prefix: Path, key: str, value: str, ...) -> list[str]:
        """Build wine reg add command."""

    @abstractmethod
    def find_wine_binary(self) -> Path | None:
        """Locate wine binary (Proton script, CrossOver, system wine)."""

    @abstractmethod
    def list_available_versions(self) -> list[str]:
        """Return human-readable names of available runners/versions."""

    @abstractmethod
    def install_dependency(self, prefix: Path, component: str, log_fn) -> bool:
        """Install a winetricks-style dependency into a prefix."""


def get_runner() -> WineRunner:
    """Returns the appropriate runner based on platform + config."""
```

### Implementations

| Class | Platform | Binary | Notes |
|---|---|---|---|
| `ProtonRunner` | Linux | `Proton/proton` script | Wraps existing `proton_run_command` logic |
| `CrossOverRunner` | macOS | `cxexec` or `WINEPREFIX=... wine` | Uses CrossOver bottles |
| `LutrisRunner` | Linux | Lutris wine runner | Partially exists in `lutris_finder.py` |
| `HeroicRunner` | Linux/macOS | Heroic's wine | Partially exists in `heroic_finder.py` |
| `SystemWineRunner` | macOS/Linux | `/usr/bin/wine` or `brew --prefix wine` | Fallback for system Wine |

---

## Phase 2: Prefix Discovery for macOS  ✅ Done (committed)

**New file: `src/Utils/crossover_finder.py`**

CrossOver stores bottles at:
- `~/Library/Containers/com.codeweavers.CrossOver/Data/bottles/` (App Store)
- `~/Library/Application Support/CrossOver/bottles/` (DMG install)
- `~/CrossOver/bottles/` (older installs)

```python
def list_crossover_bottles() -> list[Path]:
    """Return paths to all CrossOver bottles."""

def find_crossover_bottle(name: str) -> Path | None:
    """Try to find a bottle by name (case-insensitive)."""

def find_crossover_wine_binary() -> Path | None:
    """Locate the CrossOver wine/cxexec binary."""
```

**Also create: `src/Utils/wine_prefix_finder.py`** — unified prefix discovery

```python
def find_wine_prefix(game_path: Path, launcher: str, ...) -> Path | None:
    """Find the Wine/Proton prefix for a game by launcher type."""
    match launcher:
        case "steam": return find_steam_prefix(...)
        case "crossover": return find_crossover_prefix(...)
        case "lutris": return find_lutris_prefix(...)
        case "heroic": return find_heroic_prefix(...)
```

---

## Phase 3: Replace ProtonStepWidget with Platform-Agnostic Version  ⚠️ Widget done; 3 of ~48 views migrated

**Modify/Rename: `wizards_qt/proton_step.py` -> `wizards_qt/wine_step.py`**

The current `ProtonStepWidget` lets users pick Proton version + prefix mode. On macOS, this should:

1. **On Linux**: Show Proton versions (current behavior)
2. **On macOS**: Show:
   - CrossOver bottle selector
   - System Wine binary picker
   - Manual prefix path entry

```python
class WineStepWidget(QWidget):
    """Choose Wine/Proton runner + prefix placement for a wizard tool."""

    def _build_ui(self):
        if sys.platform == "darwin":
            self._build_crossover_ui()  # bottle picker
        else:
            self._build_proton_ui()     # current behavior
```

All existing wizard views that embed `ProtonStepWidget` get updated to import `WineStepWidget` instead.

---

## Phase 4: Update Core Utility Functions  ⚠️ In progress — part 1 + macOS resolver fallback UNCOMMITTED (see HANDOFF)

**Strategy: Don't delete existing functions — wrap them through the abstraction.**

| Current Function | New Behavior |
|---|---|
| `steam_finder.proton_run_command()` | Route through `WineRunner.run_in_prefix()` |
| `steam_finder.list_installed_proton()` | On macOS: return CrossOver bottles or system Wine |
| `protontricks.install_component()` | On macOS: use `winetricks` via Wine/CrossOver |
| `proton_tools.*` functions | Route through runner abstraction |

```python
# In steam_finder.py:
def proton_run_command(*args, **kwargs):
    """Backwards compat: routes to appropriate WineRunner."""
    runner = get_runner()
    return runner.run_in_prefix(*args, **kwargs)
```

---

## Phase 5: Update Individual Wizard Views  ❌ ~3 of 48 views done (pandora / dyndolod / xedit)

### Priority 1 — Already macOS-Compatible (no Proton dependency)

These just download files and extract — minimal changes needed:

- `script_extender_view.py` — SKSE, F4SE, NVSE, FOSE, SFSE, etc.
- `reshade_view.py` — ReShade installer
- `esm_fixes_view.py` — ESM fixes downloader/extractor
- `bsa_decompressor_view.py` — BSA decompressor
- `fnv_4gb_view.py` — 4GB patcher
- `fallout_downgrade_view.py` — FO3 downgrader
- `fallout_4_downgrader_view.py` — FO4 downgrader
- `modio_settings_view.py` — API key entry
- `bg3_import_view.py` — Mod.io import
- `curated_profile_view.py` — Amethyst manifest import

### Priority 2 — Run Windows Tools (need WineStepWidget integration)

These run `.exe` files through Wine/Proton — need the abstraction:

- `bethini_view.py` — BethINI.exe
- `creationkit_view.py` — Creation Kit
- `wrye_bash_view.py` — Wrye Bash
- `xedit_view.py` — SSEEdit, FO4Edit, etc.
- `pgpatcher_view.py` — PG Patcher
- `pandora_view.py` — Pandora DK
- `dyndolod_view.py` — DynDOLOD, TexGen, xLODGen
- `eslifier_view.py` — ESLifier
- `bodyslide_view.py` / `bodyslide_linux_view.py` — BodySlide/Outfit Studio
- `texture_tool_view.py` — VRAMr, BENDr, ParallaxR
- `skygen_view.py` / `plugin_audit_view.py` — SkyGen tools
- `synthesis_view.py` — Synthesis
- `ttw_view.py` — Tales of Two Wastelands
- `pandora_view.py` — Pandora DK
- `dtkit_patch_view.py` — DTKit patcher

### Priority 3 — macOS-Incompatible (need investigation/cross-compilation)

These depend on Linux-specific features or native binaries:

- `re_pak_restore_view.py` — RE pak restore
- `me3_install_view.py` — ME3Tweaks
- `regulation_merge_view.py` — Regulation merge
- `srml_view.py` / `mscloader_view.py` — Specialized tools

---

## Phase 6: Settings & UI Configuration  ❌ Not started

Add to settings/preferences:

- **Launcher type selector**: Steam Proton / CrossOver / Lutris / Heroic / System Wine
- **Default Wine prefix path**: Manual override per-game or global
- **CrossOver bottle selection**: Per-game bottle picker

---

## Phase Status (as of 2026-08-30 — see HANDOFF above for detail)

| Phase | Deliverable | State |
|---|---|---|
| 0 | Core compat | ✅ Committed |
| 1 | `wine_runner.py` + `crossover_finder.py` discovery | ✅ Committed |
| 2 | `crossover_finder.py` + `wine_prefix_finder.py` | ✅ Committed |
| 3 | `WineStepWidget` (dual-mode) | ✅ Widget committed; ⚠️ 3/48 views migrated |
| 4 part 1 | `proton_compat.py` routed through `get_runner()` | ✅ Committed |
| 4 part 2 | **macOS resolver fallback** (`_resolve_macos_wine_env` + wiring) | ⚠️ **Done, UNCOMMITTED, unverified** |
| 5 | Migrate remaining ~45 wizard views to `WineStepWidget` | ❌ Not started |
| 6 | Settings launcher-type picker + prefix override | ❌ Not started |

---

## Quick Win Checklist: Immediate macOS-Compatible Wizards

These need **zero Proton interaction** and work on macOS with minimal changes:

- [ ] `modio_settings_view.py` — API key entry only
- [ ] `curated_profile_view.py` — manifest download + install
- [ ] `bg3_import_view.py` — mod import wizard
- [ ] `smapi_view.py` — download + extract (no Wine exe running)

These need Wine exe execution but **same abstraction pattern**:

- [ ] `script_extender_view.py` — download + extract to game root
- [ ] `reshade_view.py` — download + extract + registry writes
- [ ] `esm_fixes_view.py` / `bsa_decompressor_view.py` — download + extract + run small .exe

---

## Files Modified by This Plan

**New files:**
- `src/Utils/wine_runner.py` — Abstract runner interface + factory
- `src/Utils/crossover_finder.py` — CrossOver bottle discovery
- `src/Utils/wine_prefix_finder.py` — Unified prefix discovery

**Modified files:**
- `src/Utils/steam_finder.py` — Wrap `proton_run_command`, `list_installed_proton`
- `src/Utils/protontricks.py` — Route through WineRunner
- `src/Utils/proton_tools.py` — Route through WineRunner
- `src/wizards_qt/proton_step.py` — Rename to `wine_step.py`, dual-mode UI
- `src/wizards_qt/*.py` — 44 wizard views (various priority levels)
- `src/gui_qt/` — Settings UI for launcher type selection
