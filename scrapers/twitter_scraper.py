from __future__ import annotations

import logging
import re
from urllib.parse import quote

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

# Paths on x.com that are NOT user profiles
_X_SKIP_PATHS = ("/search", "/explore", "/notifications", "/messages", "/home",
                 "/settings", "/i/", "/login", "/hashtag/")
# Known non-user handles (legal/help pages that appear in search results)
_X_GARBAGE_HANDLES = frozenset({
    "tos", "privacy", "about", "help", "rules", "safety", "accessibility",
    "jobs", "ads", "business", "developers", "status", "blog",
})
# Valid X/Twitter handles
_X_HANDLE_RE = re.compile(r"^https?://(?:x|twitter)\.com/([a-zA-Z0-9_]{1,50})/?$")


def _is_profile_url(url: str) -> bool:
    if not url or ("x.com" not in url and "twitter.com" not in url):
        return False
    if "/status/" in url or "/photo/" in url:
        return False
    if any(f"/{skip.strip('/')}" in url for skip in _X_SKIP_PATHS):
        return False
    m = _X_HANDLE_RE.match(url.split("?")[0])
    if not m:
        return False
    return m.group(1).lower() not in _X_GARBAGE_HANDLES


class TwitterScraper:
    platform = "twitter"
    base_url = "https://x.com"

    def scrape(self, driver: WebDriver, config: AppConfig) -> list[Lead]:
        leads: list[Lead] = []
        for keyword in config.twitter_keywords:
            try:
                new_leads = scrape_with_retry(
                    lambda kw=keyword: self._scrape_keyword(driver, config, kw, leads),
                    max_retries=config.network_retries,
                    base_delay=5.0,
                    label=f"twitter/{keyword}",
                )
                leads.extend(new_leads)
                if len(leads) >= config.max_profiles_per_platform:
                    return leads[:config.max_profiles_per_platform]
            except Exception as exc:
                logger.exception("Twitter/X error for %s: %s", keyword, exc)
        return leads

    def _scrape_keyword(self, driver: WebDriver, config: AppConfig, keyword: str, existing: list[Lead]) -> list[Lead]:
        url = f"{self.base_url}/search?q={quote(keyword)}&src=typed_query&f=user"
        logger.info("Twitter/X keyword=%s", keyword)
        driver.get(url)
        WebDriverWait(driver, config.page_load_timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        scroll_page(driver, scrolls=config.scrolls_override, min_delay=config.min_delay, max_delay=config.max_delay)
        save_debug_html(driver, config.debug_html_dir, f"twitter_{quote(keyword)}.html", config.save_debug_html)

        soup = soup_from_html(driver.page_source)
        seen: set[str] = set()
        new_leads: list[Lead] = []
        remaining = config.max_profiles_per_platform - len(existing)

        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if href.startswith("/"):
                href = f"{self.base_url}{href}"
            if not _is_profile_url(href):
                continue
            clean_href = href.split("?")[0].rstrip("/")
            if clean_href in seen:
                continue
            seen.add(clean_href)

            card = a.find_parent("article") or a.find_parent(["li", "div"]) or a.parent
            card_text = card.get_text(" ", strip=True)[:1000] if card else ""

            new_leads.append(self._lead_from_candidate(keyword, clean_href, card_text))
            if len(new_leads) >= remaining:
                break

        return new_leads

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
            lead_type=classify_lead(text),
            followers=extract_follower_count(text),
            engagement_hint="inferred from search result snippet",
            interest_signals=extract_interest_signals(text),
            raw_data={"text_sample": text[:1000]},
        )
