"""
Extract Instagram cookies from your running Chrome browser.

No manual login needed — reads directly from Chrome's cookie database.
Chrome does NOT need to be closed.

Usage:
    python extract_chrome_cookies.py

Saves cookies to output/instagram_session.json in the same format
used by the scraper (Selenium driver.get_cookies() format).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import browser_cookie3

SESSION_FILE = Path("output/instagram_session.json")
INSTAGRAM_DOMAIN = ".instagram.com"

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def _cookie_to_dict(c) -> dict:
    """Convert http.cookiejar.Cookie → Selenium-style dict."""
    return {
        "name": c.name,
        "value": c.value,
        "domain": c.domain,
        "path": c.path,
        "secure": bool(c.secure),
        "httpOnly": False,  # not exposed by cookiejar
        "expiry": int(c.expires) if c.expires else None,
    }


def main() -> None:
    logger.info("Reading Instagram cookies from Chrome...")

    try:
        jar = browser_cookie3.chrome(domain_name="instagram.com")
    except Exception as exc:
        logger.error("Could not read Chrome cookies: %s", exc)
        logger.error("Make sure Chrome is open and you are logged into Instagram.")
        sys.exit(1)

    cookies = [_cookie_to_dict(c) for c in jar]

    if not cookies:
        logger.error("No Instagram cookies found in Chrome.")
        logger.error("Make sure you are logged into Instagram in Chrome.")
        sys.exit(1)

    # Check for session cookie (key indicator of a valid login)
    has_session = any(c["name"] == "sessionid" for c in cookies)
    if not has_session:
        logger.warning("'sessionid' cookie not found — you may not be logged in on Chrome.")

    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(cookies, indent=2))

    logger.info("SUCCESS — %d cookies saved to %s", len(cookies), SESSION_FILE)
    if has_session:
        logger.info("Session cookie found. The scraper will use this session automatically.")
    else:
        logger.info("Warning: no sessionid found. Open Instagram in Chrome and log in first.")


if __name__ == "__main__":
    main()
