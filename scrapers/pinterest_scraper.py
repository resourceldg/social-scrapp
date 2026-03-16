from __future__ import annotations

import logging
import re
from urllib.parse import quote, urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import AppConfig
from models import Lead
from parsers.lead_parser import soup_from_html
from utils.classifiers import classify_lead, extract_interest_signals
from utils.helpers import detect_location, extract_emails, extract_follower_count, extract_phones, extract_website, save_debug_html, scrape_with_retry, scroll_page

logger = logging.getLogger(__name__)

# Pinterest user profile paths are /username/ (one segment, no /pin/ /board/ etc.)
_PIN_SKIP_PATHS = ("/pin/", "/search/", "/explore/", "/ideas/", "/today/", "/login/")
_PIN_HANDLE_RE = re.compile(r"^/([a-zA-Z0-9_.-]{3,50})/?$")


def _is_user_href(href: str) -> bool:
    if not href or not href.startswith("/"):
        return False
    if any(href.startswith(skip) for skip in _PIN_SKIP_PATHS):
        return False
    return bool(_PIN_HANDLE_RE.match(href))


class PinterestScraper:
    platform = "pinterest"
    base_url = "https://www.pinterest.com"

    def scrape(self, driver: WebDriver, config: AppConfig) -> list[Lead]:
        leads: list[Lead] = []
        for keyword in config.pinterest_keywords:
            try:
                new_leads = scrape_with_retry(
                    lambda kw=keyword: self._scrape_keyword(driver, config, kw, leads),
                    max_retries=config.network_retries,
                    base_delay=5.0,
                    label=f"pinterest/{keyword}",
                )
                leads.extend(new_leads)
                if len(leads) >= config.max_profiles_per_platform:
                    return leads[:config.max_profiles_per_platform]
            except Exception as exc:
                logger.exception("Pinterest error for %s: %s", keyword, exc)
        return leads

    def _scrape_keyword(self, driver: WebDriver, config: AppConfig, keyword: str, existing: list[Lead]) -> list[Lead]:
        url = f"{self.base_url}/search/users/?q={quote(keyword)}"
        logger.info("Pinterest keyword=%s", keyword)
        driver.get(url)
        WebDriverWait(driver, config.page_load_timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        scroll_page(driver, scrolls=config.scrolls_override, min_delay=config.min_delay, max_delay=config.max_delay)
        save_debug_html(driver, config.debug_html_dir, f"pinterest_{quote(keyword)}.html", config.save_debug_html)

        soup = soup_from_html(driver.page_source)
        seen: set[str] = set()
        new_leads: list[Lead] = []
        remaining = config.max_profiles_per_platform - len(existing)

        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not _is_user_href(href):
                continue
            clean_href = href.rstrip("/")
            if clean_href in seen:
                continue
            seen.add(clean_href)

            profile_url = f"{self.base_url}{clean_href}"
            card = a.find_parent(["div", "li", "article"]) or a.parent
            card_text = card.get_text(" ", strip=True)[:1000] if card else ""

            new_leads.append(self._lead_from_candidate(keyword, profile_url, card_text))
            if len(new_leads) >= remaining:
                break

        return new_leads

    def _lead_from_candidate(self, keyword: str, url: str, text: str) -> Lead:
        city, country = detect_location(text)
        emails = extract_emails(text)
        phones = extract_phones(text)
        handle = urlparse(url).path.rstrip("/").split("/")[-1]
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
            followers=extract_follower_count(text),
            raw_data={"text_sample": text[:1000]},
        )
