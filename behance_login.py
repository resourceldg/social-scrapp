"""
Behance session bootstrapper — fully automated via visible Chrome.

Adobe SSO blocks headless Chrome but allows visible browser windows.
This script opens a visible Chrome window, fills email + password automatically
using credentials from .env, and saves the resulting session cookies so that
`python main.py` can use them without any manual interaction.

Usage:
    python behance_login.py

Re-run every ~25 days when cookies expire (the scraper will warn you).
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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from config import load_config

SESSION_FILE = Path("output/behance_session.json")
SSO_URL = (
    "https://www.behance.net/auth/sso/login"
    "?url=https%3A%2F%2Fwww.behance.net%2F"
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def _build_driver() -> webdriver.Chrome:
    options = Options()
    # NOT headless — Adobe SSO detects and blocks headless Chrome.
    # A visible window passes Adobe's bot checks.
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=es-AR,es,en-US,en")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,900")
    options.add_argument("--password-store=gnome-libsecret")
    # Block heavy assets to speed up login
    options.add_argument("--blink-settings=imagesEnabled=false")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"},
    )
    return driver


def _automate_login(driver: webdriver.Chrome, username: str, password: str) -> bool:
    """Fill Adobe SSO form automatically in a visible Chrome window."""
    logger.info("Navigating to Behance SSO…")
    driver.get(SSO_URL)

    # ── Wait for Adobe login page ─────────────────────────────────────────────
    logger.info("Waiting for Adobe login page…")
    try:
        WebDriverWait(driver, 30).until(
            lambda d: "accounts.adobe.com" in d.current_url
            or "adobelogin.com" in d.current_url
            or "auth.services.adobe.com" in d.current_url
        )
    except Exception:
        logger.error(
            "Adobe login page did not load (stuck at %s).", driver.current_url
        )
        return False

    logger.info("Adobe login page loaded at %s", driver.current_url)
    time.sleep(2)  # let Spectrum/React form fully render

    # ── Fill email ────────────────────────────────────────────────────────────
    logger.info("Filling email…")
    try:
        email_field = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR,
                "#EmailPage-EmailField, input[name='email'], "
                "input[type='email'], input[name='username'], #username"
            ))
        )
        email_field.click()
        time.sleep(0.4)
        email_field.clear()
        email_field.send_keys(username)
        time.sleep(0.4)
    except Exception as exc:
        logger.error("Email field not found: %s", exc)
        return False

    # ── Click Continue ────────────────────────────────────────────────────────
    logger.info("Clicking Continue…")
    try:
        btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR,
                "#EmailPage-ContinueButton, "
                "button[data-id='EmailPage-ContinueButton'], "
                "button[type='submit']"
            ))
        )
        driver.execute_script("arguments[0].click();", btn)
    except Exception:
        email_field.send_keys(Keys.RETURN)

    # ── Fill password ─────────────────────────────────────────────────────────
    logger.info("Waiting for password field…")
    try:
        pass_field = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR,
                "#PasswordPage-PasswordField, "
                "input[type='password'], input[name='password']"
            ))
        )
        pass_field.click()
        time.sleep(0.4)
        pass_field.clear()
        pass_field.send_keys(password)
        time.sleep(0.4)
        logger.info("Submitting password…")
        pass_field.send_keys(Keys.RETURN)
    except Exception as exc:
        logger.error("Password field not found: %s", exc)
        return False

    # ── Wait for redirect back to behance.net (dismiss post-login modals) ───────
    logger.info("Waiting for redirect back to Behance…")
    deadline = time.time() + 40
    while time.time() < deadline:
        cur = driver.current_url

        # Adobe shows post-login "progressive profile" screens (add secondary email,
        # phone, etc.) before redirecting. Detect and dismiss them automatically.
        if "progressive-profile" in cur or "add-secondary-email" in cur or "add-phone" in cur:
            logger.info("Adobe post-login screen detected — clicking 'Not now'…")
            for sel in (
                "button[data-id='notNowButton']",
                "button.spectrum-Button--secondary",
                "button[aria-label='Not now']",
                "//button[normalize-space()='Not now']",
            ):
                try:
                    if sel.startswith("//"):
                        btn = driver.find_element(By.XPATH, sel)
                    else:
                        btn = driver.find_element(By.CSS_SELECTOR, sel)
                    driver.execute_script("arguments[0].click();", btn)
                    logger.info("Clicked 'Not now' via '%s'", sel)
                    time.sleep(1.5)
                    break
                except Exception:
                    continue

        # Success: landed on behance.net outside of Adobe auth
        if (
            "behance.net" in cur
            and "accounts.adobe.com" not in cur
            and "adobelogin.com" not in cur
            and "auth.services.adobe.com" not in cur
        ):
            time.sleep(2)
            logger.info("Automated login succeeded — now at %s", cur)
            return True

        if any(x in cur for x in ("2factor", "two-step", "mfa")):
            logger.warning("2FA required at %s — fall back to manual completion.", cur)
            return False

        time.sleep(1)

    logger.error("Login redirect timed out at %s", driver.current_url)
    return False


def _wait_manual_completion(driver: webdriver.Chrome, wait_minutes: int = 3) -> bool:
    """Fallback: wait for the user to complete login manually (e.g. 2FA)."""
    logger.info(
        "Waiting up to %d minutes for you to complete login manually…", wait_minutes
    )
    deadline = time.time() + wait_minutes * 60
    while time.time() < deadline:
        cur = driver.current_url
        if (
            "behance.net" in cur
            and "accounts.adobe.com" not in cur
            and "adobelogin.com" not in cur
            and "/auth/sso" not in cur
        ):
            time.sleep(2)
            src = driver.page_source
            if "sign in" not in src[:4000].lower():
                return True
        time.sleep(2)
    return False


def main() -> None:
    config = load_config()
    username = config.behance_username
    password = config.behance_password

    if not username or not password:
        logger.error(
            "No credentials found. Set BEHANCE_USERNAME and BEHANCE_PASSWORD in .env"
        )
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Behance automated session bootstrapper")
    logger.info("Account: %s", username)
    logger.info("=" * 60)
    logger.info(
        "A Chrome window will open and fill your credentials automatically.\n"
        "If Adobe requires 2FA or CAPTCHA, complete it manually in the window."
    )

    driver = _build_driver()
    try:
        logged_in = _automate_login(driver, username, password)

        if not logged_in:
            # Automated fill failed or 2FA needed — give user a chance to finish manually
            logged_in = _wait_manual_completion(driver, wait_minutes=3)

        if not logged_in:
            logger.error("Login was not completed. Exiting.")
            sys.exit(1)

        # Save cookies
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        cookies = driver.get_cookies()
        SESSION_FILE.write_text(json.dumps(cookies, indent=2))
        logger.info("")
        logger.info("SUCCESS — %d cookies saved to %s", len(cookies), SESSION_FILE)
        logger.info("`python main.py` will use this session automatically (~25 days).")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
