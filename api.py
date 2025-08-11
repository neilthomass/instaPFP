#!/usr/bin/env python3
import io
import re
import json
import time
import logging
from html import unescape
from typing import Optional, Tuple
from urllib.parse import urlparse

import requests
from PIL import Image
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse, RedirectResponse, JSONResponse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException

logger = logging.getLogger("pfp_api")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Instagram PFP API", version="0.1.0")


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


def _extract_hd_from_page_json(driver: webdriver.Chrome) -> Optional[str]:
    try:
        html = driver.page_source
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
    except Exception:
        return None
    return None


def _get_image_dimensions_from_url(url: str) -> Optional[Tuple[int, int]]:
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        with Image.open(io.BytesIO(resp.content)) as img:
            return img.size
    except Exception:
        return None


def fetch_pfp(username: str, device_name: str = "iPhone 12 Pro") -> Tuple[str, Optional[Tuple[int, int]]]:
    """Fetch the best profile picture URL and its dimensions for a username."""
    username = username.lstrip('@')

    chrome_options = Options()
    chrome_options.add_experimental_option("mobileEmulation", {"deviceName": device_name})
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--remote-debugging-port=0")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--no-default-browser-check")

    # Prefer Selenium Manager to locate matching Chrome/Driver
    try:
        driver = webdriver.Chrome(options=chrome_options)
    except WebDriverException:
        # Retry once with legacy headless flag for older chromes
        chrome_options.arguments = [arg for arg in chrome_options.arguments if not arg.startswith("--headless")]
        chrome_options.add_argument("--headless")
        driver = webdriver.Chrome(options=chrome_options)
    try:
        profile_url = f"https://www.instagram.com/{username}/"
        driver.get(profile_url)
        time.sleep(2)

        # 404 template check
        html = driver.page_source
        if re.search(r"Sorry, this page isn(?:'|’)t available\\.", html, re.I):
            raise HTTPException(status_code=404, detail="Username not found")

        wait = WebDriverWait(driver, 12)
        img_el = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "img[alt*='profile picture'], img[alt*='profile photo']"))
        )

        src = img_el.get_attribute("src") or ""
        srcset = img_el.get_attribute("srcset") or ""
        best_url = _extract_largest_from_srcset(srcset) or src
        if not best_url:
            best_url = _extract_hd_from_page_json(driver)
        if not best_url:
            raise HTTPException(status_code=502, detail="Could not locate profile image URL")

        dims = _get_image_dimensions_from_url(best_url)
        return best_url, dims
    finally:
        try:
            driver.quit()
        except Exception:
            pass


@app.get("/pfp/{username}")
async def get_pfp(
    username: str,
    format: str = Query("image", pattern="^(image|json)$"),
    redirect: bool = Query(False),
    device: str = Query("iPhone 12 Pro"),
):
    url, dims = fetch_pfp(username, device_name=device)

    if format == "json":
        return JSONResponse({
            "username": username,
            "url": url,
            "width": dims[0] if dims else None,
            "height": dims[1] if dims else None,
        })

    if redirect:
        return RedirectResponse(url)

    # Proxy the image through this API
    r = requests.get(url, stream=True, timeout=30)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to fetch image")
    content_type = r.headers.get("content-type", "image/jpeg")
    return StreamingResponse(r.iter_content(chunk_size=8192), media_type=content_type)