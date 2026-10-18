# Amethyst Mod Manager — macOS (from source)

Run the GUI mod manager natively on macOS. Mod install/deploy is native;
games and wizard tools (BethINI Pie, SSEEdit, …) run through a
compatibility runtime — **NotProton is recommended**, CrossOver bottles and
system Wine remain supported.

## 1. Runtime options

### NotProton (recommended)

[NotProton](https://github.com/NotProtonNot/NotProton) brings the Linux
Steam Play experience to the macOS Steam client: it force-enables Steam Play
and ports Proton over patched copies of CrossOver. With it, Amethyst works
like on Linux — Steam-managed prefixes, per-game tool selection, and Play
launching the game through the tool's `run` script.

Setup:

1. Use a Steam client build NotProton supports: **stable build
   `1791918634`** or **beta build `1791686101`** (Steam → Settings →
   Updates), with **CrossOver 26.3 or a supported CrossOver Preview build**
   installed (NotProton keeps its own patched runner copies per build).
2. Install NotProton:

   ```bash
   brew install --cask notprotonnot/notproton/notproton
   ```

   (or download `NotProton.app` from the
   [GitHub releases](https://github.com/NotProtonNot/NotProton/releases)).
3. In **Steam → Settings → Compatibility**, select a NotProton tool
   (fex or Rosetta flavour) for your game, then launch the game once so
   NotProton creates its prefix under
   `~/Library/Application Support/Steam/steamapps/compatdata/<appid>/pfx`.
4. In Amethyst, **Add Game** — the install and the NotProton prefix are
   auto-detected. Wizard tools list the NotProton tools on the
   "Choose Wine Runner" step; "Use game prefix" mode runs the tool inside
   the prefix with the tool that owns it. **Play** (launch mode *None*)
   starts the game through the tool's `run` script, and *Auto* hands off
   via `steam://` as usual.

### CrossOver bottles (legacy)

[CrossOver](https://www.codeweavers.com/) with your game installed in a
bottle. Wizard tools pick the bottle on the "Choose Wine Runner" step; the
game prefix is the bottle itself. This flow predates NotProton and is
unchanged.

### System Wine (legacy)

Wine via `brew install --cask wine-stable`, used when no bottle or
NotProton tool matches. The "System Wine" runner appears in the wizard
runner list when a wine binary is found.

## 2. Prerequisites (running from source)

```bash
xcode-select --install          # C toolchain (cc/clang)
brew install python@3.13 rust   # Python 3.13 + Cargo
```

## 3. Set up the Python environment

```bash
cd Amethyst-Mod-Manager
python3.13 -m venv .venv
.venv/bin/pip install -r src/requirements.txt   # PySide6 + vendored deps
```

## 4. Build the native extensions

Two extensions must sit in `src/` next to the packages. If the repo already
contains `src/loot.cpython-3XX-darwin.so` and `src/amethyst_filegraph.abi3.so`
matching your Python version, skip straight to running. Otherwise build them:

```bash
# libloot (sorting engine) — needs Cargo + C toolchain; pass a ref, e.g. v0.29.4
src/LOOT/rebuild_libloot.sh

# amethyst_filegraph (deployment catalog) — needs Cargo + C toolchain
native/amethyst_filegraph/build.sh
```

Both write their `.so` into `src/`.

## 5. Run

```bash
cd src
../.venv/bin/python3 run_qt.py        # or: ./run_qt.sh
```

## Notes

- Config & data live in `~/Library/Application Support/AmethystModManager/`;
  mod staging defaults to `~/Games/Amethyst/<Game>/` (set the per-user
  default on the onboarding page or in Settings).
- **NotProton**: Amethyst only *reads* NotProton state (tools under
  `compatibilitytools.d/notproton-*/`, runner copies under
  `~/Library/Application Support/notproton/runners/`, and the
  `notproton-build` record in each game's `compatdata/<appid>/`). If a
  NotProton tool's runner copy is missing (removed build, mid-update),
  wizard/Play refuse with the missing `runners/crossover-<build>` directory
  named — re-run NotProton.app to set the build up. If a game launch via a
  `run` script fails, the session log surfaces the tail of
  `compatdata/<appid>/notproton-run.log` (the script's own log).
- Wizard tools: "Use game prefix" runs the tool inside the game's prefix
  with the runner that owns it (the NotProton tool selected for the game,
  or the CrossOver bottle it is in); the runner picker does not apply in
  that mode. Isolated/shared prefixes are created with the selected
  runner's wine (`wineboot --init` on first use, fonts seeded from the
  runner).
- First launch of a game wizard with no runtime found: the
  "Choose Wine Runner" step points at NotProton first
  (`brew install --cask notprotonnot/notproton/notproton` + Steam →
  Settings → Compatibility), then CrossOver / system Wine.
