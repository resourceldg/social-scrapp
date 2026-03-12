from __future__ import annotations

import logging
from urllib.parse import quote

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import AppConfig
from models import Lead
from parsers.lead_parser import soup_from_html
from utils.classifiers import classify_lead, extract_interest_signals
from utils.helpers import clean_text, detect_location, extract_emails, extract_phones, extract_website, random_delay, save_debug_html

logger = logging.getLogger(__name__)

INSTAGRAM_SELECTORS = {
    "profile_links": ["a[href^='/']"],
}


class InstagramScraper:
    platform = "instagram"
    base_url = "https://www.instagram.com"

    def scrape(self, driver: WebDriver, config: AppConfig) -> list[Lead]:
        leads: list[Lead] = []
        for keyword in config.instagram_keywords:
            try:
                url = f"{self.base_url}/explore/tags/{quote(keyword.lstrip('#'))}/"
                logger.info("Instagram keyword=%s", keyword)
                driver.get(url)
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                random_delay(config.min_delay, config.max_delay)
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.4);")
                random_delay(config.min_delay, config.max_delay)
                save_debug_html(driver, config.debug_html_dir, f"instagram_{quote(keyword)}.html", config.save_debug_html)

                soup = soup_from_html(driver.page_source)
                profile_links = []
                for sel in INSTAGRAM_SELECTORS["profile_links"]:
                    profile_links.extend([a.get("href", "") for a in soup.select(sel)])

                seen = set()
                for href in profile_links:
                    if not href.startswith("/") or "/p/" in href or href.count("/") > 2:
                        continue
                    if href in seen:
                        continue
                    seen.add(href)
                    profile_url = f"{self.base_url}{href}"
                    leads.append(self._profile_to_lead(keyword, href.strip("/"), profile_url, soup.get_text(" ", strip=True)))
                    if len(leads) >= config.max_profiles_per_platform:
                        return leads
            except Exception as exc:
                logger.exception("Instagram error for %s: %s", keyword, exc)
        return leads

    def _profile_to_lead(self, keyword: str, handle: str, profile_url: str, text: str) -> Lead:
        city, country = detect_location(text)
        emails = extract_emails(text)
        phones = extract_phones(text)
        website = extract_website(text)
        signals = extract_interest_signals(text)
        return Lead(
            source_platform=self.platform,
            search_term=keyword,
            name=handle,
            social_handle=handle,
            profile_url=profile_url,
            email=emails[0] if emails else "",
            phone=phones[0] if phones else "",
            website=website,
            city=city,
            country=country,
            bio=clean_text([text[:500]]),
            lead_type=classify_lead(text),
            interest_signals=signals,
            raw_data={"text_sample": text[:1000]},
        )
