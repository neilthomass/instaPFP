#!/usr/bin/env python3
import json
import logging
import re
from html import unescape
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mobile_pfp")


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


def download_pfp(username: str, device_name: str = "iPhone 12 Pro") -> Optional[str]:
    """Download the highest quality Instagram profile picture for a username."""
    username = username.lstrip('@')

    chrome_options = Options()
    mobile_emulation = {"deviceName": device_name}
    chrome_options.add_experimental_option("mobileEmulation", mobile_emulation)
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        profile_url = f"https://www.instagram.com/{username}/"
        driver.get(profile_url)

        nav_html = driver.page_source
        if re.search(r"Sorry, this page isn(?:'|’)t available\\.", nav_html, re.I):
            logger.error(f"Username not found: @{username}")
            return None

        wait = WebDriverWait(driver, 0.1)
        try:
            img_el = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "img[alt*='profile picture'], img[alt*='profile photo']"))
            )
        except TimeoutException:
            logger.error("Timed out waiting for profile image; profile may not exist or is not accessible")
            return None

        src = img_el.get_attribute("src") or ""
        srcset = img_el.get_attribute("srcset") or ""
        best_url = _extract_largest_from_srcset(srcset) or src

        if not best_url:
            best_url = _extract_hd_from_page_json(driver)

        if not best_url:
            logger.error("Could not find profile image URL")
            return None

        downloads_dir = Path("downloads")
        downloads_dir.mkdir(exist_ok=True)

        parsed = urlparse(best_url)
        ext = 'jpg'
        if '.' in parsed.path:
            tail = parsed.path.rsplit('/', 1)[-1]
            if '.' in tail:
                ext = tail.split('.')[-1].split('?')[0].lower()
                if ext not in {"jpg", "jpeg", "png", "webp"}:
                    ext = "jpg"

        filepath = downloads_dir / f"{username}.{ext}"

        with requests.get(best_url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        print(f"Downloaded to: {filepath}")
        return str(filepath)

    except Exception as e:
        logger.error(f"Failed to retrieve or download PFP: {e}")
        return None
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def cli() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Download Instagram PFP via mobile emulation")
    parser.add_argument("username", help="Instagram username (without @)")
    parser.add_argument("--device", default="iPhone 12 Pro", help="Chrome mobile emulation device name")
    args = parser.parse_args()
    download_pfp(args.username, device_name=args.device)


if __name__ == "__main__":
    cli()
