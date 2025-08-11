# download-pfp

Minimal tool to download an Instagram profile picture using Chrome mobile emulation, print its dimensions, and save it locally.

## Requirements
- Python 3.8.1+
- Google Chrome installed
- `uv` package manager

## Install and Run with uv

```bash
# Install dependencies
uv sync
uv run python main.py USERNAME

```

Images are saved into the `downloads/` directory with a user as filename.