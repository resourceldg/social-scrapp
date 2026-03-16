from __future__ import annotations

import logging
import random
import shutil
import tempfile
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from config import AppConfig

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# Injected on every new document to remove bot fingerprints
_CDP_STEALTH = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['es-AR', 'es', 'en-US', 'en']});
window.chrome = {runtime: {}};
"""

# Tracker/analytics domains to block (saves bandwidth + hides automation signals)
_BLOCKED_URLS = [
    "google-analytics.com/*",
    "googletagmanager.com/*",
    "*.doubleclick.net/*",
    "connect.facebook.net/*/fbevents.js",
    "static.ads-twitter.com/*",
    "analytics.pinterest.com/*",
    "*.hotjar.com/*",
    "*.segment.io/*",
    "*.segment.com/*",
]

# Blocked font/media URL patterns (cannot block images via CDP — use prefs instead)
_BLOCKED_ASSET_URLS = [
    "*.woff", "*.woff2", "*.ttf", "*.eot", "*.otf",
    "*.mp4", "*.webm", "*.ogg", "*.mp3", "*.wav", "*.flac",
]

# Session files to copy from the real Chrome profile.
# Copying only these avoids conflicts with Chrome's singleton lock
# (which prevents Selenium from opening the same profile directory while
# Chrome is running).
_SESSION_FILES = [
    "Cookies",
    "Login Data",
    "Login Data For Account",
    "Web Data",
    "Preferences",
    "Secure Preferences",
]
_SESSION_DIRS = ["Network"]


def _clone_profile(src_user_data: str, src_profile: str) -> tuple[str, str]:
    """Copy session files from a live Chrome profile into a fresh temp directory.

    Returns (temp_user_data_dir, profile_dir_name) — caller is responsible for
    cleaning up the temp dir after the driver session ends.

    This allows Selenium to inherit a logged-in Chrome session without opening
    the same user-data-dir that the running Chrome instance already holds locked.
    """
    src_profile_dir = Path(src_user_data) / src_profile
    tmp_root = Path(tempfile.mkdtemp(prefix="scrapper_chrome_"))
    tmp_profile_dir = tmp_root / src_profile
    tmp_profile_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for fname in _SESSION_FILES:
        src = src_profile_dir / fname
        if src.exists():
            try:
                shutil.copy2(src, tmp_profile_dir / fname)
                copied += 1
            except OSError:
                pass  # file may be locked; skip non-critical files

    for dname in _SESSION_DIRS:
        src = src_profile_dir / dname
        if src.is_dir():
            try:
                shutil.copytree(src, tmp_profile_dir / dname)
                copied += 1
            except OSError:
                pass

    # Copy Local State from user data root (needed for account info)
    local_state = Path(src_user_data) / "Local State"
    if local_state.exists():
        try:
            shutil.copy2(local_state, tmp_root / "Local State")
        except OSError:
            pass

    logger.info(
        "Profile cloned: %s/%s → %s (%d items copied)",
        src_user_data, src_profile, tmp_root, copied,
    )
    return str(tmp_root), src_profile


def build_driver(config: AppConfig) -> tuple[webdriver.Chrome, str | None]:
    """Build and return (driver, tmp_dir).

    tmp_dir is the path of the cloned profile temp directory that must be
    deleted after the driver quits, or None if no profile cloning was done.
    """
    options = Options()

    if config.headless:
        options.add_argument("--headless=new")

    # ── Bandwidth savings (slow-connection mode) ──────────────────────────────
    prefs: dict = {
        "profile.default_content_setting_values.notifications": 2,
    }
    if config.block_images:
        # Chrome-level image blocking: no image bytes ever downloaded
        prefs["profile.managed_default_content_settings.images"] = 2
        # Disable media autoplay
        prefs["profile.default_content_setting_values.media_stream_mic"] = 2
        prefs["profile.default_content_setting_values.media_stream_camera"] = 2
    options.add_experimental_option("prefs", prefs)

    # Anti-detection
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f"--user-agent={random.choice(_USER_AGENTS)}")
    options.add_argument("--lang=es-AR,es,en-US,en")

    # Use gnome-libsecret so Selenium can decrypt v11 cookies from the cloned profile
    options.add_argument("--password-store=gnome-libsecret")

    # Stability
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--window-size=1440,900")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")

    # Slow-connection helpers
    options.add_argument("--enable-features=NetworkService")
    options.add_argument("--disk-cache-size=104857600")   # 100 MB disk cache

    tmp_dir: str | None = None

    if config.user_data_dir and config.chrome_profile_path:
        # Clone the live profile so we don't conflict with a running Chrome instance
        tmp_user_data, profile_name = _clone_profile(
            config.user_data_dir, config.chrome_profile_path
        )
        tmp_dir = tmp_user_data
        options.add_argument(f"--user-data-dir={tmp_user_data}")
        options.add_argument(f"--profile-directory={profile_name}")
    elif config.user_data_dir:
        options.add_argument(f"--user-data-dir={config.user_data_dir}")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.set_page_load_timeout(config.page_load_timeout)

    # Remove navigator.webdriver and other automation fingerprints via CDP
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": _CDP_STEALTH})

    # Block trackers + heavy asset types via CDP Network interception
    blocked = _BLOCKED_URLS + (_BLOCKED_ASSET_URLS if config.block_images else [])
    if blocked:
        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": blocked})

    logger.info(
        "Chrome driver started (timeout=%ds, block_images=%s, profile_cloned=%s).",
        config.page_load_timeout,
        config.block_images,
        tmp_dir is not None,
    )
    return driver, tmp_dir
