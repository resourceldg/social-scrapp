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
from utils.helpers import detect_location, extract_emails, extract_phones, extract_website, random_delay, save_debug_html

logger = logging.getLogger(__name__)

PINTEREST_SELECTORS = {
    "result_links": ["a[href*='/']"],
}


class PinterestScraper:
    platform = "pinterest"
    base_url = "https://www.pinterest.com"

    def scrape(self, driver: WebDriver, config: AppConfig) -> list[Lead]:
        leads: list[Lead] = []
        for keyword in config.pinterest_keywords:
            try:
                url = f"{self.base_url}/search/users/?q={quote(keyword)}"
                logger.info("Pinterest keyword=%s", keyword)
                driver.get(url)
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                random_delay(config.min_delay, config.max_delay)
                save_debug_html(driver, config.debug_html_dir, f"pinterest_{quote(keyword)}.html", config.save_debug_html)

                soup = soup_from_html(driver.page_source)
                text = soup.get_text(" ", strip=True)
                links = []
                for selector in PINTEREST_SELECTORS["result_links"]:
                    links.extend([a.get("href", "") for a in soup.select(selector)])

                for href in links[: config.max_results_per_query]:
                    if href.startswith("/"):
                        href = f"{self.base_url}{href}"
                    if "pinterest.com" not in href:
                        continue
                    leads.append(self._lead_from_candidate(keyword, href, text))
                    if len(leads) >= config.max_profiles_per_platform:
                        return leads
            except Exception as exc:
                logger.exception("Pinterest error for %s: %s", keyword, exc)
        return leads

    def _lead_from_candidate(self, keyword: str, url: str, text: str) -> Lead:
        city, country = detect_location(text)
        emails = extract_emails(text)
        phones = extract_phones(text)
        handle = url.rstrip("/").split("/")[-1]
        return Lead(
            source_platform=self.platform,
            search_term=keyword,
            name=handle,
            social_handle=handle,
            profile_url=url,
            email=emails[0] if emails else "",
            phone=phones[0] if phones else "",
            website=extract_website(text),
            city=city,
            country=country,
            bio=text[:500],
            category="profile_or_board",
            lead_type=classify_lead(text),
            interest_signals=extract_interest_signals(text),
            raw_data={"text_sample": text[:1000]},
        )
