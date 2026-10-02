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
- Games run via **Proton** (Linux) or **CrossOver / system Wine** (macOS)

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

## macOS Port (Phase 1 — Wizard Tool Launch via CrossOver/Wine)

Wizard tools (BethINI Pie, SSEEdit, BodySlide, …) now launch inside
CrossOver bottles or system Wine on macOS. The user picks a **CrossOver
bottle name** (or `System Wine`) on the wizard's "Choose Proton Version"
step; the rest of the flow is shared with Linux.

Architecture (`Utils/executables/launch.py`):
- `resolve_tool_prefix()` routes darwin to `_resolve_tool_prefix_macos()`,
  which returns `(wine_binary, prefix_root, env)` — **no Proton script**.
  `env` carries `WINEPREFIX` plus the `AMM_MACOS_WINE` marker
  (`MACOS_WINE_ENV`), which makes `run_tool_logged()` build
  `wine start.exe /wait /unix <exe>` instead of a Proton verb.
- **Raw wine, not the CrossOver wrapper**: the bottle-aware `wine` perl
  launcher (`Contents/SharedSupport/CrossOver/bin/wine`) manages bottles
  (update prompts, cxbottle.conf) and would trigger its update flow against
  foreign/foreign-version prefixes. Tool launches use the build's plain
  binary `lib/wine/x86_64-unix/wine`, where WINEPREFIX alone selects the
  prefix. `CX_ROOT` is set in env (CrossOver's `cxcompatdb.dll` otherwise
  logs `CX_ROOT not set` errors).
- **Prefix placement** mirrors Linux: isolated `prefix_<runner>/` next to
  the exe, shared `wine_prefixes/shared_<runner>/` in the app config dir,
  or the game prefix. macOS prefixes have `drive_c/` at the root (no
  `pfx/` subdir); `_tool_prefix_root()` normalises the various caller
  conventions. First use runs `wineboot --init` (synchronous), then seeds
  `ShowDotFiles` straight into `user.reg` and copies the bottle's font set
  into the fresh prefix (BethINI Pie hardcodes Segoe UI).
- **Build selection** (`Utils/crossover_finder.py`): a Mac can have several
  CrossOver builds (e.g. stable `CrossOver.app` + `CrossOver Preview
  [Ros].app`). `list_crossover_apps()` orders them official-first,
  newest-first; `app_for_bottle()` matches the bottle's `cxbottle.conf`
  `Timestamp` against each build's `CFBundleShortVersionString` so a bottle
  is driven by the build that created/updated it. `find_crossover_bottle_for_exe()`
  recovers the game's bottle (high-probability Steam/GOG roots first, then a
  bounded drive_c scan) when the saved prefix path is a Linux layout.
- **Registry**: `Utils/bethesda/registry.py` writes Bethesda `Installed Path`
  keys via plain `wine reg add` on macOS (SSE key name is
  `Bethesda Softworks\Skyrim Special Edition` — what BethINI Pie and
  xEdit/CK read; both 64-bit and Wow6432Node views are written).
- **Cleanup**: `shutdown_prefix_wineserver()` finds CrossOver's
  `bin/wineserver` via `find_wineserver_for_wine()` (raw wine lives in
  `lib/wine/x86_64-unix/` with the server in the build's `bin/`).

Notes:
- CrossOver 26.x bundle layout: `Contents/SharedSupport/CrossOver/{bin,lib}`;
  there is no `cxexec` in 26. Bottles may live anywhere (e.g. `~/Bottles/`)
  and appear as symlinks under `~/Library/Application Support/CrossOver/bottles/`.
- CrossOver bottles use their own Windows user (`crossover`), not
  `steamuser`: `link_mygames()` falls back to scanning the prefix's
  `drive_c/users/` when the standard `_MYGAMES_DOCS` path is missing.
- Selftests: `Utils/_crossover_finder_selftest.py`,
  `Utils/_wine_runner_selftest.py`, `Utils/_wine_prefix_finder_selftest.py`
  (run from `src/` as `-m Utils._<name>_selftest`; running the .py directly
  shadows the stdlib `collections` module with `Utils/collections`).

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
