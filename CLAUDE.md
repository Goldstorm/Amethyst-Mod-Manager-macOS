git# Amethyst Mod Manager — CLAUDE.md

Amethyst Mod Manager is a Python/PySide6 mod manager for Bethesda, Obsidian, and other games. Originally Linux-only, now being ported to macOS.

## Project Structure

- **`src/`** — Main source root (run from here so packages import cleanly)
  - `src/Utils/` — Core logic, now split into subpackages after the main refactor
     (`launchers/`, `wine/`, `environment/`, `executables/`, `bethesda/`,
     `deployment/`, `filegraph/`, `games/`, …). Top-level helpers include
     `config_paths.py`; macOS NotProton/CrossOver/system-Wine support
     lives in `notproton_finder.py`, `proton_compat.py`, `wine_runner.py`,
     `crossover_finder.py`, `wine_prefix_finder.py`.
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
- Games run via **Proton** (Linux) or **NotProton / CrossOver / system Wine** (macOS)

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
  `Utils/_wine_runner_selftest.py`, `Utils/_wine_prefix_finder_selftest.py`,
  `Utils/_notproton_finder_selftest.py`
  (run from `src/` as `-m Utils._<name>_selftest`; running the .py directly
  shadows the stdlib `collections` module with `Utils/collections`).

## macOS Port (Phase 2/3 — NotProton)

**NotProton** ports Proton to the macOS Steam client as **patched copies of
CrossOver** and force-enables Steam Play. Amethyst is a read-only consumer
of its on-disk contract — it never writes under
`~/Library/Application Support/notproton/`, `compatibilitytools.d/`, or
NotProton-managed prefix files (`notproton-*`, `.notproton-prefix.lock`):

| Piece | Location |
|---|---|
| Steam compat tools | `.../Steam/compatibilitytools.d/notproton-*/` — a Proton-verb-compatible **`run` shell script**, `build` (e.g. `27.0.0.41069-fex`) and `flavor` (`fex`/`rosetta`) markers, `compatibilitytool.vdf` (display name) |
| Runner copies | `.../notproton/runners/crossover-<build>/CrossOver/` — raw wine in `lib/wine/{aarch64-unix,x86_64-unix}/`, servers in `bin/` |
| Game prefixes | `.../steamapps/compatdata/<appid>/pfx` (Linux Proton layout) + a `notproton-build` record (line 1 = build id) |
| Per-game mapping | `CompatToolMapping` in `.../Steam/config/config.vdf` — the patched Steam writes the NotProton tool name, like Linux Proton mappings |

Key files:
- `Utils/notproton_finder.py` (new) — read-only discovery, stdlib-only, no
  subprocess. `NotProtonTool` dataclass; wine/wineserver resolution mirrors
  NotProton's `compat_run.sh` (fex → `aarch64-unix/wine.app/Contents/MacOS/wine`
  + `bin/wineserver-arm64`, with x86 fallbacks; rosetta →
  `x86_64-unix/wine` + `bin/wineserver`[-x86]). `list_notproton_tools()`
  (build desc, fex before rosetta), `find_notproton_tool()` (dir/display/
  flavor-suffixed display labels, case-insensitive), `tool_for_build()`,
  `build_record()` (reads `notproton-build`), `prefix_flavor()` (ntdll PE
  machine read), `runner_for_prefix()` (build record + ntdll disambiguation
  for builds shared by fex+rosetta tools), `notproton_tool_env()` (the
  `CX_ROOT`/`CX_HOME`/`WINEDLLPATH`/`WINESERVER` env the run script sets).
  Path roots are module-level constants so the selftest can monkeypatch
  them.
- `Utils/launchers/steam.py` — `_TOOL_SCRIPT_NAMES` gains `run` on darwin
  (Linux stays `("proton",)`); `list_installed_proton()` /
  `find_proton_for_game()` accept the run script; new
  `find_notproton_for_prefix()` resolves the tool that owns a prefix from
  `notproton-build` when no `CompatToolMapping`/`config_info` exists
  (always `None` off-darwin); `proton_run_command()` darwin branch invokes
  the run script **directly** (it is a shell script — verb passed through;
  the old `python3` wrapper would have failed); `find_any_installed_proton()`
  resolves NotProton display labels before directory-name matching.
- `Utils/executables/launch.py` — `_macos_wine_for_runner()` resolves
  NotProton labels to the tool's patched-CrossOver wine (missing runner
  copy refused, naming the `runners/crossover-<build>` dir);
  `_resolve_tool_prefix_macos()` uses the prefix's **own** runner in
  game-prefix mode when `notproton-build` is present, applies the
  tool's run-script env before `wineboot --init`, seeds fonts from the
  runner's `share/wine/fonts`, and waits briefly for the prefix's
  wineserver to flush `user.reg`; `run_tool_logged()` preserves
  `CX_HOME`/`WINEDLLPATH`/`WINESERVER`; `launch_via_steam()` leads the
  darwin candidates with `["open", url]` (LaunchServices);
  `launch_exe_via_proton()` falls back to `find_notproton_for_prefix()`
  for prefixes without a `CompatToolMapping`, refuses pre-launch when the
  mapped tool's runner copy is missing, and surfaces the tail of
  `compatdata/<id>/notproton-run.log` on non-zero exit;
  `get_game_prefix_env()` resolves the `notproton-build` record on darwin;
  `shutdown_prefix_wineserver()` resolves the runner's flavor-matched
  wineserver (the fex runner has no plain `bin/wineserver`).
- `Utils/wine_runner.py` — `NotProtonRunner` (label- or dir-name-
  qualified, else first available tool) driving a tool's wine with the
  run-script env; darwin auto-detect order notproton → crossover → system
  wine; `get_default_runner_type()` reports `notproton` first.
- `Utils/proton_compat.py` — darwin `find_prefix()` tries Steam's
  compatdata layout **first** (NotProton prefixes), bottles second;
  darwin `list_installed_proton()` lists NotProton run scripts before
  bottles / system wine.
- `wizards_qt/proton_step.py` — "Choose Wine Runner" lists NotProton tools
  first (display name + `(FEX)`/`(Rosetta)`), the no-runner message is
  NotProton-first, and the game-prefix checkbox help states the
  owning-runner rule.

Rules:
- **Never mix wine arch with prefix arch**: game-prefix mode always uses
  the prefix's own runner (the wizard dropdown selection is not used there,
  same rule as before).
- No NotProton installed → exactly the pre-Phase-2 behavior (bottles →
  system Wine, byte-identical messages). Tool present but its runner copy
  missing → listed but refused with the missing dir named (F7).
- Play (None) is the Linux Proton verb/env contract (`waitforexitandrun`,
  `STEAM_COMPAT_DATA_PATH`, …) executed by the `run` script, which
  seeds/updates the prefix from NotProton's template and launches via a
  loader `.app`; Play (auto) hands off via `steam://`.

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
