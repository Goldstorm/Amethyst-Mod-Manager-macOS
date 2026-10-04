# MERGE.md — Merging origin/main into the macOS fork

Read this before merging upstream (`origin/main`) into this branch, or before
resolving any merge conflict in this repository.

## The golden rule (owner's policy)

> **This is a fork of origin. The fork must adapt to the changes that are
> pushed to origin.**

Default conflict resolution: **take the upstream (`origin/main`) side.**
Fork-side changes only survive a conflict when they are the fork's own
platform work that upstream has no equivalent for (the macOS port, §"Keep").
When in doubt, upstream wins; re-deriving fork behavior on top of upstream's
new structure is always possible, but silently dropping an upstream feature
from the fork is not.

Practical consequence for a hunk:

| Hunk shape | Resolution |
|---|---|
| Ours empty, upstream added code | Take upstream |
| Ours is the old text, upstream changed the same line | Take upstream (unless the line is a macOS guard, §"Keep") |
| Ours added fork-only code, upstream untouched | Keep ours |
| Both changed the same logic (upstream evolved it further) | Take upstream; if ours contained fork-only additions, re-apply those additions on top of upstream's version |
| Binary/derived file | Regenerate from source (`.qm` from `.ts`, §"Gotchas") |

## Repository layout

- `origin` — upstream: `https://github.com/ChrisDKN/Amethyst-Mod-Manager.git` (Linux-first, Proton)
- `fork` — this project's remote: `git@github.com:Goldstorm/Amethyst-Mod-Manager-macOS.git`
- Work happens on `feature/2.5.3-mac` (tracks `fork/feature/2.5.3-mac`).

## Keep — fork-only work that must survive every merge

These are macOS-only. Upstream will never add them; losing them in a merge
breaks the macOS build. (All paths relative to `src/`.)

| Location | What to keep |
|---|---|
| `Utils/executables/launch.py` | `prepare_tool_prefix()` darwin branch → `_resolve_tool_prefix_macos()`; `_tool_prefix_root()` and its ~7 call sites (macOS prefixes have `drive_c/` at the root, no `pfx/`); `MACOS_WINE_ENV` handling in `run_tool_logged()` (`wine start.exe /wait /unix` instead of a Proton verb); `CX_ROOT` env passing to the winetricks-style runner; bottle font seeding; `shutdown_prefix_wineserver()` CrossOver layout |
| `Utils/crossover_finder.py` | Entire file — CrossOver app/bottle discovery, raw-wine (`lib/wine/x86_64-unix/wine`) vs wrapper wine, `app_for_bottle()` build matching |
| `Utils/wine_runner.py`, `Utils/wine_prefix_finder.py` | macOS runner/prefix support |
| `Utils/config_paths.py` | `import sys` + `_is_macos()` / `_macos_config_base()` (`~/Library/Application Support/AmethystModManager/`) |
| `Utils/environment/xdg.py` | `open` instead of `xdg-open`, macOS downloads dir |
| `Utils/launchers/steam.py` | macOS Steam path (`~/Library/Application Support/Steam/`) |
| `Utils/environment/sandbox.py` | `import sys` + darwin early-returns (`if sys.platform == "darwin": return None`) in `_flatpak_required_grant()` — no Flatpak on macOS; the macOS docstring note in `flatpak_blocked_path_hint()` |
| `Utils/flatpak/*` | No-op macOS guards |
| `Utils/ui/portal.py` | Skip portal/zenity on macOS, use Qt dialogs |
| `LOOT/rebuild_libloot.sh` | Platform-aware wheel pattern (`*macosx*.whl` vs `*linux*.whl`) |
| `Utils/bethesda/registry.py` | `wine reg add` path for macOS (SSE key = `Bethesda Softworks\Skyrim Special Edition`, both 64-bit and Wow6432Node views) |

Architecture notes for these live in `CLAUDE.md` (section "macOS Port").

## Overwrite — take upstream freely

- `src/version.py` (track upstream's version; the fork branch name may carry
  the fork version, but the file follows upstream)
- `Changelog.txt` (prepend upstream's new version blocks; the fork adds no
  entries for its own port work)
- `src/translations/amethyst_en.ts` / `.qm` (upstream strings win; fork-only
  strings that upstream removed or renamed — e.g. the old "LSFG-VK ..."
  branding replaced by "LSFG / MAKO" — are deleted, then the `.qm` is rebuilt,
  see Gotchas)
- All shared game logic, GUI features, wizards, Nexus/downloads plumbing,
  meson/flatpak packaging, docs.

## How to merge (proven procedure, used for the v2.5.3 merge)

1. **Never rebase.** The branch contains merge commits and is pushed to the
   fork; rebase would rewrite pushed history. Use `git merge origin/main`.
   ⚠️ `pull.rebase=true` is set in this repo's git config — a plain
   `git pull origin main` will try to rebase and choke. Always
   `git fetch origin main` + `git merge origin/main`.
2. **Backup first:** `git branch backup/pre-pull-<version> HEAD`.
3. **Preview conflicts read-only:**
   `git merge-tree --write-tree --name-only HEAD origin/main` lists exactly
   which files will conflict before anything is touched.
4. **Start:** `git merge origin/main --no-commit`; resolve per the table in
   §"The golden rule".
5. For each conflicted file, diff **both sides against the merge base**
   (`git diff <merge-base>..HEAD -- <file>` and
   `git diff <merge-base>..origin/main -- <file>`) to see what each side
   actually changed — a hunk where "ours" is empty means upstream alone
   touched that area and upstream wins without discussion.
6. When a fork-only helper and an upstream helper for the same job both exist
   (e.g. `_tool_prefix_root` vs upstream's
   `Utils/wine.prefix.normalize_prefix_path`), keep the fork's helper inside
   fork-owned code paths and let upstream's helper serve upstream's call
   sites — do not rewrite fork call sites to upstream's helper unless it is
   a strict superset of the fork one's behavior.
7. **Verify** (see below), then commit the merge with a message summarizing
   what was preserved vs integrated, and update the findings table in
   §"Merge history" of this file.

## Verification checklist

Run from `src/` with the venv interpreter
(`.venv/bin/python3`), **always as modules** (`-m Utils...._selftest`):

```
python3 -m compileall -q .            # whole tree must compile
python3 -m Utils._crossover_finder_selftest     # 23 tests, macOS
python3 -m Utils._wine_runner_selftest          # 29 tests, macOS
python3 -m Utils._wine_prefix_finder_selftest   # 26 tests, macOS
python3 -m Utils.bsa._selftest
python3 -m Utils.npc._selftest
python3 -m Utils.ba2._selftest
python3 -m Utils.profiles._selftest
python3 -m Utils.wabbajack._selftest
python3 -m Utils.processes._selftest
python3 -m Utils.environment._sandbox_selftest
python3 -m Games.BepInEx._bepinex_namespacing_selftest
python3 -m Utils.vfs._selftest                 # Linux-only (bubblewrap)
```

Plus an import smoke test of every conflicted module
(`python3 -c "import <module>"`), and a grep for stale references to
functions upstream renamed (in the v2.5.3 merge: `run_pack` was kept by
upstream while the fork's parallel refactor had split it into
`_stage_archives`/`_write_pack`/`_commit_pack` — the merge converged both).

**Known pre-existing failures on macOS** (identical before and after the
v2.5.3 merge — Linux-environment assumptions, NOT merge regressions; don't
"fix" them by touching shared code without owner approval):

- `Utils.processes._selftest` — assertion failure
- `Utils.environment._sandbox_selftest` — "genuinely ungranted path should
  still warn: /opt/SteamLibrary/game -> None" (the darwin guard in
  `sandbox.py` correctly suppresses Flatpak hints on macOS; the test expects
  Linux behavior)
- `Utils.wabbajack._selftest` — 1 failure + 2 errors (`Ba2ExtractError`,
  `FileExistsError` in temp dir)
- `Games.BepInEx._bepinex_namespacing_selftest` — "No pinned filegraph
  deployment plan is active" (needs a live deployment)
- `Utils.vfs._selftest` — requires bubblewrap (Linux); skip on macOS

## Gotchas

- **Selftests must be run as modules** from `src/`
  (`python3 -m Utils._<name>_selftest`). Running the `.py` file directly
  shadows the stdlib `collections` module with `Utils/collections`.
- **Translations:** `amethyst_en.ts` is text (mergeable), `amethyst_en.qm`
  is binary (not mergeable). Resolve the `.ts`, then rebuild:
  `lrelease src/translations/amethyst_en.ts -qm src/translations/amethyst_en.qm`
  (homebrew `lrelease` is fine). lrelease currently warns about a duplicate
  `MangoHud: {0}` message in the `LauncherSettingsOverlay` context — that is
  an upstream duplicate, harmless.
- **Upstream and the fork have converged on some features.** Download
  pause/resume (`Utils/downloads/control.py`, `Utils/downloads/resources.py`)
  and the pack/unpack split were developed on both sides; the files were
  byte-identical or converged cleanly. If a conflict looks like "same
  feature, two implementations", compare against the merge base before
  choosing — upstream's later version is usually the evolved one.
- **`launch.py` is the highest-risk file** (tool-launch routing). After any
  merge, re-read the `prepare_tool_prefix` darwin branch and confirm
  `run_tool_logged` still builds `wine start.exe /wait /unix` for
  `MACOS_WINE_ENV`.
- **Wizard run-loop:** upstream v2.5.3 refactored wizard workers from Qt
  signals (`safe_emit`/`*_sig`) to an event queue
  (`queue.SimpleQueue` + `_run_events` + `_drain_run_events` + `_run_timer`).
  The queue architecture is upstream's to own; fork wizard changes should be
  written against it.
- macOS CrossOver specifics (raw wine vs wrapper, `CX_ROOT`, bottles as
  symlinks, `crossover` Windows user not `steamuser`, 26.x bundle layout)
  are documented in `CLAUDE.md` — keep it updated when port work changes.

## Merge history

| Date | Upstream range | Conflicts | Outcome |
|---|---|---|---|
| 2026-10-03 | `7c04b7ca4` (v2.5.2-era) → `91520a18a` (v2.5.3), 158 commits | 27 files, all content | Commit `a9e532b2c`. Kept: all §"Keep" items. Took upstream: version 2.5.3 + changelog; mako `wrap_command` + LSFG/MAKO env forwarding (`launch.py`); version_change/rollback (`mods/install.py`, `nexus_meta.py`); batch BSA pack/unpack + packing-state tracking (`bsa/pack.py`, `gui_qt/app.py`, `bsa_pack_overlay.py`); resume-aware downloads + mirror retry (`nexus_download.py`, downloads UI, `notification_center.py` `StatusProgressStack`); wizard event-queue refactor (`pgpatcher_view.py`, `script_extender_view.py` + `strip_top_dir`); multi-select missing-reqs/Nexus; rule-matching semantics fix (`deployment/custom_rules.py`, `shared.py` docstring, `routing_rules_overlay.py`); upstream `filegraph/adapter.py` timestamp sanitisation on top of the fork's `ctime_ns`/archive-scan fields. `.qm` rebuilt (5862 messages). |
