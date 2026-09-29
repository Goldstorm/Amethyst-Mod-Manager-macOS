git# Amethyst Mod Manager — CLAUDE.md

Amethyst Mod Manager is a Python/PySide6 mod manager for Bethesda, Obsidian, and other games. Originally Linux-only, now being ported to macOS.

## Project Structure

- **`src/`** — Main source root (run from here so packages import cleanly)
  - `src/Utils/` — Core logic, now split into subpackages after the main refactor
     (`launchers/`, `wine/`, `environment/`, `executables/`, `bethesda/`,
     `deployment/`, `filegraph/`, `games/`, …). Top-level helpers include
     `config_paths.py`; macOS CrossOver/system-Wine support lives in
     `proton_compat.py`, `wine_runner.py`, `crossover_finder.py`,
     `wine_prefix_finder.py`.
  - `src/Games/` — Game handlers (one per game/game family, auto-discovered)
  - `src/gui_qt/` — PySide6 Qt GUI (main window, modlist, plugins, dialogs)
  - `src/LOOT/` — LOOT sorting integration (calls libloot Python extension)
  - `src/Nexus/` — Nexus Mods API integration
  - `src/wizards_qt/` — Wizard tool dialogs (Pandora, DynDOLOD, etc.)
  - `src/wrappers/` — VRAMr/Bendr/ParallaxR wrapper tools
  - `src/run_qt.py` — GUI entry point
  - `src/cli.py` — CLI entry point
  - `src/app_bootstrap.py` — Startup hardening (path setup, stderr capture)
- **`flatpak/`** — Flatpak packaging manifest
- **`src/appimage/`** — AppImage build scripts

## Key Tech Stack

- **Python 3.13** with PySide6 (Qt 6)
- **libloot** — Core sorting engine via `maturin`-built Python extension (`loot.cpython-3XX-*.so`)
- **Meson** for build/packaging (AppImage, Flatpak)
- Games run via **Proton** (Linux), planned: **CrossOver/Wine** (macOS)

## Building & Running

### Run from source
```bash
cd src
../.venv/bin/python3 run_qt.py
```

### Rebuild libloot extension
```bash
./LOOT/rebuild_libloot.sh          # latest master
./LOOT/rebuild_libloot.sh v0.29.4  # specific tag
```
Produces `loot.cpython-3XX-*.so` in the project root. On macOS this produces `loot.cpython-313-darwin.so`.

## macOS Port (Phase 0 — Complete)

The following files were modified for macOS compatibility (paths reflect the
post-refactor `src/Utils/` subpackage layout):

| File | Change |
|------|--------|
| `Utils/config_paths.py` | macOS config in `~/Library/Application Support/AmethystModManager/` |
| `Utils/environment/xdg.py` | Use `open` instead of `xdg-open` on macOS; macOS downloads dir |
| `Utils/launchers/steam.py` | Added macOS Steam path (`~/Library/Application Support/Steam/`) |
| `Utils/environment/sandbox.py` | No-op on macOS (no Flatpak) |
| `Utils/flatpak/sandbox.py` | No-op on macOS |
| `Utils/flatpak/i386.py` | No-op on macOS |
| `Utils/ui/portal.py` | Skip portal/zenity on macOS, use Qt file dialog directly |
| `LOOT/rebuild_libloot.sh` | Platform-aware wheel pattern matching (`*macosx*.whl` vs `*linux*.whl`) |

## Game Handler Architecture

- `Games/base_game.py` — Abstract `BaseGame` class
- Each game/family in `Games/<name>/` with a `.py` file subclassing `BaseGame`
- Auto-discovered by `Utils/games/discovery.py`
- LOOT integration via `loot_sort_enabled`, `loot_game_type`, `loot_masterlist_repo` properties

## LOOT Integration

- `LOOT/loot_sorter.py` — Main sorting logic, calls `import loot` (native extension)
- `LOOT/eligibility.py` — ESL/medium-plugin eligibility checks
- Extension must match the Python version: `loot.cpython-313-darwin.so` on macOS

## Deployment

- Hardlink/symlink/copy modes (hardlink default, auto-fallback on EXDEV)
- Filegraph (`Utils/filegraph/`, the `amethyst_filegraph` Rust extension) tracks deployed files for clean restore
- Same-filesystem requirement for hardlinks (works on APFS)

## Config & Data Paths

- **macOS**: `~/Library/Application Support/AmethystModManager/`
- **Linux**: `$XDG_CONFIG_HOME/AmethystModManager/` (default `~/.config/AmethystModManager/`)
- Staging: `~/Games/Amethyst/<game>/`
- Downloads: `~/Downloads/`
