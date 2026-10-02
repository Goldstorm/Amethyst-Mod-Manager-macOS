# Amethyst Mod Manager — macOS (from source)

Run the GUI mod manager natively on macOS. Mod install/deploy is native;
games and wizard tools (BethINI Pie, SSEEdit, …) run inside a **CrossOver**
bottle or system Wine via the Wizard menu.

## 1. Prerequisites

```bash
xcode-select --install          # C toolchain (cc/clang)
brew install python@3.13 rust   # Python 3.13 + Cargo
```

For launching games/tools you also need [CrossOver](https://www.codeweavers.com/)
with your game installed in a bottle (or Wine via `brew install --cask
wine-stable` for the "System Wine" runner).

## 2. Set up the Python environment

```bash
cd Amethyst-Mod-Manager
python3.13 -m venv .venv
.venv/bin/pip install -r src/requirements.txt   # PySide6 + vendored deps
```

## 3. Build the native extensions

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

## 4. Run

```bash
cd src
../.venv/bin/python3 run_qt.py        # or: ./run_qt.sh
```

## Notes

- Config & data live in `~/Library/Application Support/AmethystModManager/`;
  staging defaults to `~/Documents/My Games/Mods/Stage/<Game>/`.
- First launch of a game wizard: pick your CrossOver **bottle** on the
  "Choose Proton Version" step — isolated tool prefixes are created next to
  the tool exe automatically (registry key, My Games link and fonts included).