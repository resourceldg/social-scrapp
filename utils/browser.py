from __future__ import annotations

import logging

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from config import AppConfig

logger = logging.getLogger(__name__)


def build_driver(config: AppConfig) -> webdriver.Chrome:
    options = Options()
    if config.headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")

    if config.user_data_dir:
        options.add_argument(f"--user-data-dir={config.user_data_dir}")
    if config.chrome_profile_path:
        options.add_argument(f"--profile-directory={config.chrome_profile_path}")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.set_page_load_timeout(45)
    logger.info("Chrome driver started. Verify that your session is already logged-in.")
    return driver
