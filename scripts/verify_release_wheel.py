from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Install an Alterios MCP wheel into a clean venv and run release smoke.")
    parser.add_argument("wheel")
    args = parser.parse_args()
    wheel = Path(args.wheel).resolve()
    if not wheel.is_file():
        parser.error(f"wheel was not found: {wheel}")

    with tempfile.TemporaryDirectory(prefix="alterios-mcp-release-") as temp_dir:
        venv_dir = Path(temp_dir) / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
        scripts_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
        python = scripts_dir / ("python.exe" if os.name == "nt" else "python")
        doctor = scripts_dir / ("alterios-doctor.exe" if os.name == "nt" else "alterios-doctor")
        release_smoke = scripts_dir / ("alterios-release-smoke.exe" if os.name == "nt" else "alterios-release-smoke")

        subprocess.run([str(python), "-m", "pip", "install", str(wheel)], check=True)
        subprocess.run([str(doctor), "--skip-startup-benchmark", "--json"], check=True)
        subprocess.run([str(release_smoke), "--skip-startup-benchmark", "--json"], check=True)

    print(f"Release wheel verified in a clean virtual environment: {wheel.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
