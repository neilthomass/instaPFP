#!/usr/bin/env python3
import json
import logging
import re
from html import unescape
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse, RedirectResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("pfp_api")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Instagram PFP API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


def _extract_largest_from_srcset(srcset_value: str) -> Optional[str]:
    if not srcset_value:
        return None
    candidates = []
    for part in srcset_value.split(','):
        part = part.strip()
        m = re.match(r"(\S+)\s+(\d+)w", part)
        if m:
            url, width = m.groups()
            try:
                candidates.append((int(width), url))
            except ValueError:
                continue
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _extract_hd_from_html(html: str) -> Optional[str]:
    html = unescape(html)
    m = re.search(r'"profile_pic_url_hd"\s*:\s*"(https:[^"\\]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r'"hd_profile_pic_versions"\s*:\s*(\[[^\]]+\])', html)
    if m:
        try:
            versions = json.loads(m.group(1))
            if isinstance(versions, list) and versions:
                versions.sort(key=lambda v: v.get("width", 0), reverse=True)
                return versions[0].get("url")
        except Exception:
            pass
    m = re.search(r'"hd_profile_pic_url_info"\s*:\s*\{([^}]+)\}', html)
    if m:
        frag = m.group(0)
        m2 = re.search(r'"url"\s*:\s*"(https:[^"\\]+)"', frag)
        if m2:
            return m2.group(1)
    return None



@app.get("/image")
async def proxy_image(u: str = Query(..., alias="u")):
    """Proxy an arbitrary image URL (validated to be https) to the client.
    Avoids CORS/referrer/hotlink issues on the frontend.
    """
    if not u.lower().startswith("https://"):
        raise HTTPException(status_code=400, detail="Only https URLs allowed")
    r = requests.get(u, stream=True, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to fetch image")
    ct = r.headers.get("content-type", "image/jpeg")
    return StreamingResponse(r.iter_content(chunk_size=8192), media_type=ct)


def fetch_pfp(username: str) -> str:
    """Fetch the best profile picture URL for a username."""
    username = username.lstrip('@')

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9",
    }

    profile_url = f"https://www.instagram.com/{username}/"
    r = requests.get(profile_url, headers=headers, timeout=30)
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Username not found")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to fetch profile page")

    html = r.text
    if re.search(r"Sorry, this page isn(?:'|’)?t available\\.", html, re.I):
        raise HTTPException(status_code=404, detail="Username not found")

    # Attempt to extract from img tag with profile alt text
    img_tag_match = re.search(
        r'<img[^>]+alt="[^"]*profile picture[^"]*"[^>]*>',
        html,
        re.IGNORECASE,
    )
    best_url = None
    if img_tag_match:
        tag = img_tag_match.group(0)
        srcset_match = re.search(r'srcset="([^"]+)"', tag)
        src_match = re.search(r'src="([^"]+)"', tag)
        srcset = srcset_match.group(1) if srcset_match else ""
        src = src_match.group(1) if src_match else ""
        best_url = _extract_largest_from_srcset(srcset) or src

    if not best_url:
        best_url = _extract_hd_from_html(html)

    if not best_url:
        # Fallback to Open Graph image
        og_match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
        if og_match:
            best_url = og_match.group(1)

    if not best_url:
        raise HTTPException(status_code=404, detail="Image not found")

    return best_url


@app.get("/pfp/{username}")
async def get_pfp(
    username: str,
    format: str = Query("image", pattern="^(image|json)$"),
    redirect: bool = Query(False),
):
    url = fetch_pfp(username)

    if format == "json":
        return JSONResponse({"url": url})

    if redirect:
        return RedirectResponse(url)

    r = requests.get(url, stream=True, timeout=30)
    if r.status_code != 200:
        raise HTTPException(status_code=404, detail="Image not found")
    content_type = r.headers.get("content-type", "image/jpeg")
    return StreamingResponse(r.iter_content(chunk_size=8192), media_type=content_type)


@app.get("/", response_class=HTMLResponse)
async def ui():
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />

  <style>
    :root { color-scheme: light dark; }
    html, body { height: 100%; }
    body {
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
      margin: 0;
      background-color: #0b0c10; /* fallback */
      background-position: center center;
      background-repeat: no-repeat;
      background-size: cover; /* stretch to fill window */
    }
    .wrap { min-height: 100dvh; display: grid; place-items: center; padding: 2rem; }
    .card { width: 100%; max-width: 720px; padding: 1.25rem; border: 1px solid #2b2b2f; border-radius: 1rem; background: #0f1115; box-shadow: 0 10px 30px rgba(0,0,0,0.3); }
    h1 { font-size: 1.35rem; margin: 0 0 1rem; color: #e5e7eb; }
    label { display: block; font-size: 0.9rem; color: #9ca3af; margin-bottom: 0.25rem; }
    input, button { font-size: 1rem; }
    input[type=text] { width: 100%; padding: 0.7rem 0.85rem; border: 1px solid #2b2b2f; border-radius: 0.6rem; color: #e5e7eb; background: #0b0c10; }
    input[type=text]::placeholder { color: #6b7280; }
    .row { display: flex; gap: 0.75rem; align-items: end; margin-top: 0.9rem; }
    .row > div { flex: 1; }
    button { padding: 0.7rem 1rem; background: linear-gradient(135deg,#6d28d9,#2563eb); color: white; border: 0; border-radius: 0.6rem; cursor: pointer; }
    button[disabled] { opacity: 0.6; cursor: progress; }
    .error { color: #fca5a5; margin-top: 0.6rem; min-height: 1.25rem; }
  </style>
  <script>
    async function onSubmit(e) {
      e.preventDefault();
      const username = document.getElementById('username').value.trim().replace(/^@/, '');
      const errorEl = document.getElementById('error');
      const btn = document.getElementById('btn');
      errorEl.textContent = '';
      // clear previous background if any
      document.body.style.backgroundImage = '';
      if (!username) { errorEl.textContent = 'Please enter a username.'; return; }
      btn.disabled = true; btn.textContent = 'Loading…';
      if (window.__busy) { return; }
      window.__busy = true;
      try {
        const res = await fetch(`/pfp/${encodeURIComponent(username)}`);
        if (!res.ok) {
          if (res.status === 404) {
            throw new Error('Instagram account does not exist');
          }
          throw new Error(`Error ${res.status}`);
        }
        // The response is the image bytes; convert to a blob and use as page background
        const blob = await res.blob();
        const objectUrl = URL.createObjectURL(blob);
        document.body.style.backgroundImage = `url(${objectUrl})`;
        // Revoke later to avoid leaks
        setTimeout(() => URL.revokeObjectURL(objectUrl), 30000);
  
      } catch (err) {
        errorEl.textContent = 'Instagram account does not exist';
      } finally {
        window.__busy = false;
        btn.disabled = false; btn.textContent = 'Fetch PFP';
      }
    }
    window.addEventListener('DOMContentLoaded', () => {
      document.getElementById('form').addEventListener('submit', onSubmit);
      document.getElementById('username').addEventListener('keyup', (e) => { if (e.key === 'Enter') { onSubmit(e); }});
    });
  </script>
  </head>
<body>
  <div class="wrap"><div class="card">
    <h1></h1>
    <form id="form">
      <label for="username">Instagram Username</label>
      <input id="username" type="text" placeholder="e.g. zuck" autocomplete="off" />
      <div class="row">
        <div style="flex:0 0 auto;">
          <button id="btn" type="submit">Fetch PFP</button>
        </div>
      </div>
      <div id="error" class="error"></div>
    </form>
  </div></div>
</body>
</html>
"""
