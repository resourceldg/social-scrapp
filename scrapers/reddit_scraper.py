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
from utils.helpers import detect_location, extract_emails, extract_phones, extract_website, save_debug_html, scrape_with_retry, scroll_page

logger = logging.getLogger(__name__)


class RedditScraper:
    platform = "reddit"
    base_url = "https://www.reddit.com"

    def scrape(self, driver: WebDriver, config: AppConfig) -> list[Lead]:
        leads: list[Lead] = []
        for keyword in config.reddit_keywords:
            try:
                new_leads = scrape_with_retry(
                    lambda kw=keyword: self._scrape_keyword(driver, config, kw, leads),
                    max_retries=config.network_retries,
                    base_delay=5.0,
                    label=f"reddit/{keyword}",
                )
                leads.extend(new_leads)
                if len(leads) >= config.max_profiles_per_platform:
                    return leads[:config.max_profiles_per_platform]
            except Exception as exc:
                logger.exception("Reddit error for %s: %s", keyword, exc)
        return leads

    def _scrape_keyword(self, driver: WebDriver, config: AppConfig, keyword: str, existing: list[Lead]) -> list[Lead]:
        url = f"{self.base_url}/search/?q={quote(keyword)}&type=sr,user"
        logger.info("Reddit keyword=%s", keyword)
        driver.get(url)
        WebDriverWait(driver, config.page_load_timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        scroll_page(driver, scrolls=config.scrolls_override, min_delay=config.min_delay, max_delay=config.max_delay)
        save_debug_html(driver, config.debug_html_dir, f"reddit_{quote(keyword)}.html", config.save_debug_html)

        soup = soup_from_html(driver.page_source)
        seen: set[str] = set()
        new_leads: list[Lead] = []
        remaining = config.max_profiles_per_platform - len(existing)

        # Prefer /r/ communities first, then /user/ profiles
        for a in soup.select("a[href^='/r/'], a[href^='/user/']"):
            href = a.get("href", "").rstrip("/")
            parts = href.split("/")
            if len(parts) < 3:
                continue
            canonical = "/" + "/".join(parts[1:3])
            full_url = f"{self.base_url}{canonical}"
            if full_url in seen:
                continue
            seen.add(full_url)

            card = a.find_parent(["div", "li", "article"]) or a.parent
            card_text = card.get_text(" ", strip=True)[:1000] if card else ""

            new_leads.append(self._lead_from_candidate(keyword, full_url, card_text))
            if len(new_leads) >= remaining:
                break

        return new_leads

    def _lead_from_candidate(self, keyword: str, url: str, text: str) -> Lead:
        city, country = detect_location(text)
        emails = extract_emails(text)
        phones = extract_phones(text)
        handle = url.rstrip("/").split("/")[-1]
        is_user = "/user/" in url
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
            category="reddit_user" if is_user else "subreddit",
            lead_type=classify_lead(text),
            interest_signals=extract_interest_signals(text),
            raw_data={"text_sample": text[:1000]},
        )
