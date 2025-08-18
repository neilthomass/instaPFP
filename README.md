# Instagram PFP Tools

Minimal tooling to fetch a user's Instagram profile picture using a headless (mobile emulated) browser. You can:
- Run a local HTTP API to return the PFP as an image or JSON
- Use a Python script to download and save the PFP locally

## Requirements
- Python 3.8.1+
- Google Chrome installed and accessible
- `uv` package manager

## Install
```bash
uv sync
```

## Run the HTTP API
```bash
# Start the FastAPI server
uv run uvicorn api:app --reload

# Image response (proxied)
curl -LO http://127.0.0.1:8000/pfp/instagram

# Redirect to CDN URL
curl -I "http://127.0.0.1:8000/pfp/instagram?redirect=1"

# JSON metadata (URL only)
curl "http://127.0.0.1:8000/pfp/instagram?format=json"

# Use a specific emulated device
curl "http://127.0.0.1:8000/pfp/instagram?format=json&device=iPhone%2014%20Pro%20Max"
```

## Script Usage (download)
If you have `instapfp.py` locally (download helper):
```bash
uv run python instapfp.py USERNAME
```
Images will be saved under `downloads/USERNAME.ext`.

## How It Works
- Launches headless Chrome with mobile emulation (defaults to `iPhone 12 Pro`)
- Loads `https://www.instagram.com/{username}/`
- Extracts the best PFP URL from `srcset` or embedded JSON (HD variants)
- Optionally proxies image back through the API; otherwise you can redirect to the CDN URL

## Troubleshooting
- Chrome/driver issues on macOS:
  - Ensure Google Chrome is installed
  - Try re-running with a different headless flag (we already auto-retry)
  - If needed, set Chrome binary explicitly in code
- 404/Not Found:
  - Private or changed usernames may fail; verify the username is correct

## Notes
- This project is for educational use only. Respect Instagram's Terms of Service.