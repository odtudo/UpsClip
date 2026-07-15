#!/usr/bin/env python3
import shutil
import subprocess
import sys

DEPENDENCIES = {
    "python3": ["python3", "--version"],
    "node": ["node", "--version"],
    "npm": ["npm", "--version"],
    "ffmpeg": ["ffmpeg", "-version"],
    "ffprobe": ["ffprobe", "-version"],
    "yt-dlp": ["yt-dlp", "--version"],
}


def main() -> int:
    missing: list[str] = []
    for name, command in DEPENDENCIES.items():
        executable = shutil.which(command[0])
        if not executable:
            print(f"MISSING  {name}")
            missing.append(name)
            continue
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        first_line = (result.stdout or result.stderr).splitlines()[0]
        print(f"OK       {name}: {first_line}")
    if missing:
        print(f"\nInstall missing dependencies: {', '.join(missing)}", file=sys.stderr)
        return 1
    print("\nAll native runtime dependencies are available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
