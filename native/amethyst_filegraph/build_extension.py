#!/usr/bin/env python3
"""Build the locked abi3 extension into the application's src directory."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys


def main() -> int:
    if len(sys.argv) != 1:
        raise SystemExit("usage: build_extension.py")
    crate = Path(__file__).resolve().parent
    repository = crate.parents[1]
    manifest_path = crate / "Cargo.toml"
    output_path = repository / "src" / "amethyst_filegraph.abi3.so"
    target = crate / "target"
    environment = os.environ.copy()
    environment["CARGO_TARGET_DIR"] = str(target)
    subprocess.run(
        ["cargo", "build", "--manifest-path", str(manifest_path),
         "--release", "--locked"],
        check=True,
        env=environment,
        cwd=str(crate),
    )
    # cargo names the cdylib by platform: .dylib on macOS, .so elsewhere. The
    # Python loader expects a fixed name (amethyst_filegraph.abi3.so), so copy
    # whichever artifact this host produced onto that name.
    candidates = [target / "release" / "libamethyst_filegraph.dylib",
                  target / "release" / "libamethyst_filegraph.so"]
    source = next((path for path in candidates if path.is_file()), None)
    if source is None:
        missing = target / "release"
        raise SystemExit(f"cargo did not produce a release artifact under {missing}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output_path)
    print(f"Installed {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
