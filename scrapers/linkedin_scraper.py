from __future__ import annotations

import logging
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

# Strings present in LinkedIn's login/authwall pages
_LI_LOGIN_SIGNALS = (
    "authwall",
    "join now",
    "join linkedin",
    "sign in to linkedin",
    "be part of the community",
    "/login?",
    "linkedin.com/login",
)


def _detect_linkedin_login_wall(source: str) -> bool:
    """Return True if the page is a LinkedIn authentication wall."""
    lower = source[:8000].lower()
    return any(sig in lower for sig in _LI_LOGIN_SIGNALS)


def _normalize_li_url(href: str) -> str:
    """Strip LinkedIn tracking query params from profile URLs."""
    try:
        p = urlparse(href)
        return f"{p.scheme}://{p.netloc}{p.path.rstrip('/')}"
    except Exception:
        return href


class LinkedInScraper:
    platform = "linkedin"
    base_url = "https://www.linkedin.com"

    def scrape(self, driver: WebDriver, config: AppConfig) -> list[Lead]:
        leads: list[Lead] = []
        for keyword in config.linkedin_keywords:
            try:
                new_leads = scrape_with_retry(
                    lambda kw=keyword: self._scrape_keyword(driver, config, kw, leads),
                    max_retries=config.network_retries,
                    base_delay=5.0,
                    label=f"linkedin/{keyword}",
                )
                leads.extend(new_leads)
                if len(leads) >= config.max_profiles_per_platform:
                    return leads[:config.max_profiles_per_platform]
            except Exception as exc:
                logger.exception("LinkedIn error for %s: %s", keyword, exc)
        return leads

    def _scrape_keyword(self, driver: WebDriver, config: AppConfig, keyword: str, existing: list[Lead]) -> list[Lead]:
        url = f"{self.base_url}/search/results/all/?keywords={quote(keyword)}"
        logger.info("LinkedIn keyword=%s", keyword)
        driver.get(url)
        WebDriverWait(driver, config.page_load_timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Check redirect URL — LinkedIn sends unauthenticated users to /authwall
        current_url = driver.current_url
        if any(sig in current_url for sig in ("/authwall", "/login", "/uas/login", "/checkpoint")):
            logger.warning(
                "LinkedIn: redirected to auth page (%s) for keyword '%s' — session expired or not logged in",
                current_url, keyword,
            )
            save_debug_html(driver, config.debug_html_dir, f"linkedin_authwall_{quote(keyword)}.html", True)
            return []

        # Wait for React to render result cards (up to 12s)
        try:
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/in/'], a[href*='/company/']"))
            )
        except Exception:
            logger.debug("LinkedIn: no profile links appeared for '%s' within timeout — page may be empty or blocked", keyword)

        scroll_page(driver, scrolls=config.scrolls_override, min_delay=config.min_delay, max_delay=config.max_delay)
        save_debug_html(driver, config.debug_html_dir, f"linkedin_{quote(keyword)}.html", config.save_debug_html)

        if _detect_linkedin_login_wall(driver.page_source):
            logger.warning(
                "LinkedIn: login wall detected for keyword '%s' — configure a "
                "Chrome profile with an active LinkedIn session (USER_DATA_DIR / "
                "CHROME_PROFILE_PATH in settings)",
                keyword,
            )
            return []

        soup = soup_from_html(driver.page_source)
        seen: set[str] = set()
        new_leads: list[Lead] = []
        remaining = config.max_profiles_per_platform - len(existing)

        links = soup.select("a[href*='/in/'], a[href*='/company/']")
        if not links:
            logger.warning(
                "LinkedIn: 0 profile links found for '%s' (url=%s) — session may be expired or DOM changed",
                keyword, current_url,
            )

        for a in links:
            href = a.get("href", "")
            if "/in/" not in href and "/company/" not in href:
                continue
            clean_href = _normalize_li_url(href)
            if clean_href in seen:
                continue
            seen.add(clean_href)

            card = a.find_parent("li") or a.find_parent("div") or a.parent
            card_text = card.get_text(" ", strip=True)[:1000] if card else ""

            new_leads.append(self._lead_from_candidate(keyword, clean_href, card_text))
            if len(new_leads) >= remaining:
                break

        return new_leads

    def _lead_from_candidate(self, keyword: str, profile_url: str, text: str) -> Lead:
        from urllib.parse import unquote as _unquote
        city, country = detect_location(text)
        emails = extract_emails(text)
        phones = extract_phones(text)
        # Extract the real handle: segment right after /in/ or /company/,
        # ignoring trailing language codes ("en", "es"…) or page suffixes ("posts", "about"…).
        _LINKEDIN_SUFFIXES = {
            "en", "es", "fr", "de", "it", "pt", "nl", "ar", "zh", "ja", "ko", "ru",
            "posts", "about", "recent-activity", "detail", "overlay",
        }
        # URL-decode the profile_url before processing (handles tomás-... encoded as tom%C3%A1s-...)
        profile_url = _unquote(profile_url)
        _parts = [p for p in profile_url.split("/") if p]
        slug = ""
        for _marker in ("in", "company"):
            if _marker in _parts:
                _idx = _parts.index(_marker)
                for _seg in _parts[_idx + 1:]:
                    if _seg.lower() not in _LINKEDIN_SUFFIXES:
                        slug = _seg
                        break
                if slug:
                    break
        if not slug:
            slug = _parts[-1] if _parts else ""

        # Skip entries where slug is still a garbage suffix, or looks like an
        # event/exhibition page title (e.g. "volarte-la-inédita-exhibición-pasajera")
        if slug.lower() in _LINKEDIN_SUFFIXES or len(slug) < 2 \
                or len(slug) > 50 or slug.count("-") > 4:
            logger.debug("LinkedIn: skipping garbage slug '%s' from %s", slug, profile_url)
            slug = ""

        # Normalize profile_url to the canonical /in/<handle> or /company/<handle> form
        _base_url = profile_url
        if slug:
            _slug_pos = profile_url.find(f"/{slug}")
            if _slug_pos != -1:
                _base_url = profile_url[:_slug_pos + len(slug) + 1].rstrip("/")

        category = "linkedin_company" if "/company/" in profile_url else "linkedin_person"
        return Lead(
            source_platform=self.platform,
            search_term=keyword,
            name=slug,
            social_handle=slug,
            profile_url=_base_url,
            email=emails[0] if emails else "",
            phone=phones[0] if phones else "",
            website=extract_website(text),
            city=city,
            country=country,
            bio=text[:500],
            category=category,
            lead_type=classify_lead(text),
            interest_signals=extract_interest_signals(text),
            followers=extract_follower_count(text),
            raw_data={"text_sample": text[:1000]},
        )
