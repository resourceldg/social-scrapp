"""
One-time Instagram session bootstrapper.

Run this script ONCE with a visible Chrome window to log in manually.
The session cookies are saved to output/instagram_session.json and reused
automatically by the scraper on every subsequent run — no manual login needed.

Usage:
    python instagram_login.py

The script will:
  1. Open a visible Chrome window (not headless)
  2. Navigate to Instagram login
  3. Wait up to 3 minutes for you to log in manually
  4. Save the session cookies
  5. Close the browser

After this, `python main.py` will use the saved session automatically.
Cookies typically last 25–30 days. Re-run this script when they expire.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from config import load_config

SESSION_FILE = Path("output/instagram_session.json")
WAIT_MINUTES = 3

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    config = load_config()

    logger.info("=" * 60)
    logger.info("Instagram session bootstrapper")
    logger.info("=" * 60)
    logger.info("A Chrome window will open. Log in to Instagram manually.")
    logger.info("You have %d minutes. The window will close automatically.", WAIT_MINUTES)
    logger.info("")

    options = Options()
    # NOT headless — needed to pass Instagram's detection + allow manual interaction
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=es-AR,es,en-US,en")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,900")
    options.add_argument("--password-store=gnome-libsecret")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"},
    )

    try:
        driver.get("https://www.instagram.com/accounts/login/")
        logger.info("Browser opened. Please log in to Instagram now...")

        deadline = time.time() + WAIT_MINUTES * 60
        logged_in = False

        while time.time() < deadline:
            url = driver.current_url
            if "/accounts/login" not in url and "/login" not in url:
                # Navigated away from login page — check if we're really in
                time.sleep(2)
                driver.get("https://www.instagram.com/accounts/edit/")
                time.sleep(3)
                if "/accounts/login" not in driver.current_url:
                    logged_in = True
                    break
            time.sleep(3)

        if not logged_in:
            logger.error("Timed out — you did not complete login within %d minutes.", WAIT_MINUTES)
            sys.exit(1)

        # Save cookies
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        cookies = driver.get_cookies()
        SESSION_FILE.write_text(json.dumps(cookies, indent=2))
        logger.info("")
        logger.info("SUCCESS — %d cookies saved to %s", len(cookies), SESSION_FILE)
        logger.info("The scraper will use this session automatically.")
        logger.info("Re-run this script in ~25 days when cookies expire.")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
