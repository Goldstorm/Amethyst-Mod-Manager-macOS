# Wizard macOS Compatibility Plan

## Goal

Make all wizard tool functionality work on macOS (CrossOver/Wine) alongside the existing Linux/Proton support.

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

## Phase 1: Create the Runner Abstraction

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

## Phase 2: Prefix Discovery for macOS

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

## Phase 3: Replace ProtonStepWidget with Platform-Agnostic Version

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

## Phase 4: Update Core Utility Functions

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

## Phase 5: Update Individual Wizard Views

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

## Phase 6: Settings & UI Configuration

Add to settings/preferences:

- **Launcher type selector**: Steam Proton / CrossOver / Lutris / Heroic / System Wine
- **Default Wine prefix path**: Manual override per-game or global
- **CrossOver bottle selection**: Per-game bottle picker

---

## Suggested Implementation Order

| Week | Phase | Deliverable |
|---|---|---|
| 1 | Phase 1 | `wine_runner.py` + `crossover_finder.py` |
| 2 | Phase 3 | `WineStepWidget` replacing `ProtonStepWidget` |
| 3 | Phase 4 | Wrap `proton_run_command` and friends through abstraction |
| 4 | Phase 5 (P1) | Update download-only wizards (already mostly compatible) |
| 5 | Phase 5 (P2) | Update Windows-tool wizards |
| 6 | Phase 6 | Settings integration + testing |

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
