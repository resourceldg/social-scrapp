from __future__ import annotations

import dataclasses
import logging
import shutil
import time
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

# FB nav/auth links to exclude from results
_FB_SKIP_PATHS = (
    "/login", "/signup", "/help", "/privacy", "/terms", "/about",
    "/policies", "/recover", "/checkpoint", "/ajax", "/dialog",
    "/games", "/events", "/marketplace", "/watch",
    "/reel", "/reels", "/notifications", "/photo", "/photos",
    "/video", "/videos", "/stories", "/pages", "/hashtag",
    "/messages", "/permalink", "/play", "/mp", "/friends",
    "/bookmarks", "/groups", "/news", "/explore",
    "/ads", "/business", "/profile.php", "/gaming",
    "/instagram_direct",
)

# URL-based login indicators (checked against driver.current_url)
_FB_LOGIN_URL_SIGNALS = ("/login", "/checkpoint", "login_attempt", "reauth")


def _detect_facebook_login_wall(url: str, source: str) -> bool:
    """Return True if the page is a Facebook authentication wall."""
    # Fastest check: URL redirect
    if any(sig in url for sig in _FB_LOGIN_URL_SIGNALS):
        return True
    # Fallback: scan early HTML (FB embeds login strings in SSR JSON)
    lower = source[:12000].lower()
    return any(sig in lower for sig in (
        "log in to facebook",
        "log in or sign up",
        "you must log in",
        '"loginbutton"',
        "loginwith",
        '"login_form"',
    ))


def _is_facebook_logged_out(source: str) -> bool:
    """Return True if the page looks like the Facebook logged-out homepage/login form."""
    lower = source[:20000].lower()
    # These strings appear on the login form but NOT on the logged-in news feed
    logged_out_signals = (
        '"id":"email"',
        'name="email"',
        'id="email"',
        '"loginbutton"',
        '"login_form"',
        'action="/login/device-based',
        'value="log in"',
    )
    return any(sig in lower for sig in logged_out_signals)


def _normalize_fb_href(href: str, base_url: str) -> str:
    """Return a clean absolute Facebook URL for a real page/group, or '' to skip."""
    if not href:
        return ""
    # Make relative hrefs absolute
    if href.startswith("/"):
        href = base_url + href
    if "facebook.com" not in href:
        return ""
    try:
        p = urlparse(href)
        path = p.path.rstrip("/")
    except Exception:
        return ""
    # Skip l.facebook.com — external link redirect tracker (l.php?u=...)
    if p.netloc.startswith("l."):
        return ""
    if not path or path in ("/", ""):
        return ""
    if any(path.startswith(skip) for skip in _FB_SKIP_PATHS):
        return ""

    # Skip /search/* — these are search-tab filter links (Top, People, Videos…)
    if path.startswith("/search"):
        return ""

    # Extract the first path segment (the page/group slug)
    slug = path.lstrip("/").split("/")[0]

    # Skip Facebook tracking/obfuscated URLs (pfbid*, post share tokens)
    if slug.startswith("pfbid"):
        return ""
    # Skip single-character nav fragments (/t, /n, /l, etc.)
    if len(slug) < 2:
        return ""
    # Skip pure numeric slugs that look like post/group IDs (>10 digits)
    if slug.isdigit() and len(slug) > 10:
        return ""
    # Skip slugs that start with digits and end with dash (truncated post IDs)
    if slug[0].isdigit() and slug.endswith("-"):
        return ""
    # Strip tracking query params
    return f"{p.scheme}://{p.netloc}{path}"


class FacebookScraper:
    platform = "facebook"
    base_url = "https://www.facebook.com"
    _session_warmed: bool = False  # warm up once per driver instance

    def scrape(self, driver: WebDriver, config: AppConfig) -> list[Lead]:
        """Headless-first strategy:
        1. Try with the provided (headless) driver.
        2. If the first search page is bot-blocked (<500 bytes) fall back to a
           dedicated non-headless driver built and cleaned up entirely here.
        """
        if not self._warm_up(driver, config):
            logger.info("Facebook: headless warm-up failed — trying visible fallback")
            return self._run_with_visible(config)

        leads: list[Lead] = []
        for keyword in config.facebook_keywords:
            try:
                result = scrape_with_retry(
                    lambda kw=keyword: self._try_keyword(driver, config, kw, leads),
                    max_retries=config.network_retries,
                    base_delay=5.0,
                    label=f"facebook/{keyword}",
                )
                if result is None:
                    # Bot-detected on first keyword → switch to visible driver
                    logger.info(
                        "Facebook: bot-blocked on '%s' — switching to visible driver", keyword
                    )
                    return self._run_with_visible(config)
                leads.extend(result)
                if len(leads) >= config.max_profiles_per_platform:
                    return leads[:config.max_profiles_per_platform]
            except Exception as exc:
                logger.exception("Facebook error for %s: %s", keyword, exc)
        return leads

    def _run_with_visible(self, config: AppConfig) -> list[Lead]:
        """Build a non-headless driver, run the full Facebook scrape, clean up."""
        from utils.browser import build_driver
        visible_config = dataclasses.replace(config, headless=False)
        fb_driver, fb_tmp = build_driver(visible_config)
        logger.info("Facebook: visible driver started")
        try:
            if not self._warm_up(fb_driver, visible_config):
                logger.warning("Facebook: visible warm-up also failed — giving up")
                return []
            leads: list[Lead] = []
            for keyword in config.facebook_keywords:
                try:
                    result = scrape_with_retry(
                        lambda kw=keyword: self._try_keyword(fb_driver, config, kw, leads),
                        max_retries=config.network_retries,
                        base_delay=5.0,
                        label=f"facebook/{keyword}",
                    )
                    if result is None:
                        logger.warning("Facebook: bot-blocked even with visible driver for '%s'", keyword)
                        continue
                    leads.extend(result)
                    if len(leads) >= config.max_profiles_per_platform:
                        return leads[:config.max_profiles_per_platform]
                except Exception as exc:
                    logger.exception("Facebook visible error for %s: %s", keyword, exc)
            return leads
        finally:
            try:
                fb_driver.quit()
            except Exception:
                pass
            if fb_tmp:
                shutil.rmtree(fb_tmp, ignore_errors=True)
            logger.info("Facebook: visible driver cleaned up")

    def _warm_up(self, driver: WebDriver, config: AppConfig) -> bool:
        """Load facebook.com; auto-login with credentials if needed.

        Returns True if a valid session is active after warm-up, False otherwise.
        """
        logger.info("Facebook: warm-up — loading homepage")
        driver.get(self.base_url)
        WebDriverWait(driver, config.page_load_timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(3)

        src = driver.page_source
        cur = driver.current_url
        logger.info("Facebook warm-up: url=%s  src_len=%d", cur, len(src))

        if len(src) < 500:
            logger.warning("Facebook: homepage returned minimal content — bot detection active")
            save_debug_html(driver, config.debug_html_dir, "facebook_warmup_empty.html", True)
            return False

        # Not logged in — try credentials if available
        if _detect_facebook_login_wall(cur, src) or _is_facebook_logged_out(src):
            if not config.facebook_username or not config.facebook_password:
                logger.warning(
                    "Facebook: not logged in and no credentials configured. "
                    "Set FACEBOOK_USERNAME and FACEBOOK_PASSWORD in .env"
                )
                save_debug_html(driver, config.debug_html_dir, "facebook_warmup_login.html", True)
                return False
            logger.info("Facebook: not logged in — attempting auto-login with credentials")
            return self._login(driver, config)

        save_debug_html(driver, config.debug_html_dir, "facebook_warmup_ok.html", True)
        logger.info("Facebook: session active — proceeding with search")
        return True

    def _login(self, driver: WebDriver, config: AppConfig) -> bool:
        """Log into Facebook using username/password credentials."""
        from selenium.webdriver.common.keys import Keys

        login_url = f"{self.base_url}/login/"
        logger.info("Facebook: navigating to login page")
        driver.get(login_url)
        WebDriverWait(driver, config.page_load_timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(2)

        try:
            email_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "email"))
            )
            email_field.clear()
            email_field.send_keys(config.facebook_username)
            time.sleep(0.5)

            pass_field = driver.find_element(By.ID, "pass")
            pass_field.clear()
            pass_field.send_keys(config.facebook_password)
            time.sleep(0.5)

            pass_field.send_keys(Keys.RETURN)
            logger.info("Facebook: credentials submitted — waiting for redirect")
        except Exception as exc:
            logger.warning("Facebook: could not fill login form: %s", exc)
            save_debug_html(driver, config.debug_html_dir, "facebook_login_failed.html", True)
            return False

        # Wait for redirect away from /login/
        try:
            WebDriverWait(driver, 20).until(
                lambda d: "/login" not in d.current_url
            )
        except Exception:
            pass  # may time out on checkpoint/2FA

        time.sleep(3)
        cur = driver.current_url
        src = driver.page_source
        logger.info("Facebook: post-login url=%s  src_len=%d", cur, len(src))

        if "/login" in cur or "/checkpoint" in cur:
            logger.warning(
                "Facebook: login failed or requires 2FA/checkpoint (url=%s). "
                "Log into Facebook manually in Chrome, then re-run.",
                cur,
            )
            save_debug_html(driver, config.debug_html_dir, "facebook_login_failed.html", True)
            return False

        logger.info("Facebook: login successful")
        return True

    def _try_keyword(self, driver: WebDriver, config: AppConfig, keyword: str, existing: list[Lead]) -> list[Lead] | None:
        """Scrape one keyword. Returns None if bot-detected (caller should switch driver)."""
        # /search/pages/ is deprecated — use top-level search which includes pages
        url = f"{self.base_url}/search/top/?q={quote(keyword)}"
        logger.info("Facebook keyword=%s  url=%s", keyword, url)
        driver.get(url)
        WebDriverWait(driver, config.page_load_timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        # Wait for React to hydrate search results (Facebook is a SPA)
        time.sleep(3)

        current_url = driver.current_url
        logger.info("Facebook landed on: %s", current_url)

        # Detect blank/Not Found page — bot block returns 48-byte skeleton
        page_src = driver.page_source
        if len(page_src) < 500:
            logger.warning("Facebook: page source too short (%d bytes) for '%s' — bot block", len(page_src), keyword)
            save_debug_html(driver, config.debug_html_dir, f"facebook_empty_{quote(keyword)}.html", True)
            return None  # signal: switch to visible driver

        if _detect_facebook_login_wall(current_url, page_src):
            logger.warning(
                "Facebook: login wall detected for keyword '%s' (landed on %s) — "
                "configure a Chrome profile with an active Facebook session "
                "(USER_DATA_DIR / CHROME_PROFILE_PATH in settings)",
                keyword, current_url,
            )
            save_debug_html(driver, config.debug_html_dir, f"facebook_login_wall_{quote(keyword)}.html", True)
            return []

        scroll_page(driver, scrolls=config.scrolls_override, min_delay=config.min_delay, max_delay=config.max_delay)
        # Always save debug HTML for Facebook (helps diagnose render issues)
        save_debug_html(driver, config.debug_html_dir, f"facebook_{quote(keyword)}.html", True)

        soup = soup_from_html(driver.page_source)  # re-read after scroll
        all_anchors = soup.select("a[href]")
        logger.info("Facebook keyword=%s → total <a href> tags: %d", keyword, len(all_anchors))

        seen: set[str] = set()
        new_leads: list[Lead] = []
        remaining = config.max_profiles_per_platform - len(existing)

        # Log a sample of hrefs to diagnose filtering
        _sample_hrefs = [a.get("href", "") for a in all_anchors[:20]]
        logger.debug("Facebook href sample: %s", _sample_hrefs)

        # Select both absolute (href*=facebook.com) and relative (href^=/) links
        for a in all_anchors:
            href = a.get("href", "")
            clean_href = _normalize_fb_href(href, self.base_url)
            if not clean_href or clean_href in seen:
                continue
            seen.add(clean_href)

            card = a.find_parent(["div", "li", "article"]) or a.parent
            card_text = card.get_text(" ", strip=True)[:1000] if card else ""

            new_leads.append(self._lead_from_candidate(keyword, clean_href, card_text))
            if len(new_leads) >= remaining:
                break

        logger.info("Facebook keyword=%s → %d leads found", keyword, len(new_leads))
        return new_leads

    def _lead_from_candidate(self, keyword: str, url: str, text: str) -> Lead:
        city, country = detect_location(text)
        emails = extract_emails(text)
        phones = extract_phones(text)
        path = urlparse(url).path.rstrip("/")
        name = path.split("/")[-1]
        category = "facebook_group" if "/groups/" in path else "facebook_page"
        return Lead(
            source_platform=self.platform,
            search_term=keyword,
            name=name,
            social_handle=name,
            profile_url=url,
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
