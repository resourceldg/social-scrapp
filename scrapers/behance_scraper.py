"""
Behance scraper — creative portfolio platform (Adobe).

Value proposition for art/design niche
---------------------------------------
Behance is the world's largest creative portfolio network. It surfaces
architects, interior designers, artists, studios, and galleries that
publish project portfolios — highly qualified specifiers and buyers.

Search strategy
---------------
1. User search:  /search/users?search=<keyword>  (profiles, best for leads)
2. Project search: /search/projects?search=<keyword>  (extracts project authors)

Authentication
--------------
Behance requires an Adobe account to view follower counts and full profiles.
Credentials are read from BEHANCE_USERNAME / BEHANCE_PASSWORD env vars.
After first login the session cookies are saved to output/behance_session.json
and reused on every subsequent run (similar to the Instagram strategy).
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import quote

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import AppConfig
from models import Lead
from parsers.lead_parser import soup_from_html
from utils.classifiers import classify_lead, extract_interest_signals
from utils.helpers import (
    detect_location,
    extract_emails,
    extract_follower_count,
    extract_phones,
    extract_website,
    save_debug_html,
    scrape_with_retry,
    scroll_page,
)

logger = logging.getLogger(__name__)

_SESSION_COOKIE_FILE = Path("output/behance_session.json")

# Paths that are NOT user profiles on Behance
_SKIP_PATHS = (
    "/search/", "/jobs/", "/adobe/", "/tag/", "/field/",
    "/collection/", "/gallery/", "/moodboard/",
    "/login", "/signin", "/signup",
    "/about", "/blog", "/careers", "/help", "/press",
    "/payments", "/hire", "/joblist", "/freelancers",
    "/info/", "/api/", "/tools/", "/testimonials",
)

# Valid Behance username slug (alphanumeric / dash / underscore, 3–50 chars)
_HANDLE_RE = re.compile(r"^/([a-zA-Z0-9_-]{3,50})/?$")

# Signals that we hit a login wall
_LOGIN_SIGNALS = (
    "sign in",
    "sign up",
    "adobeid",
    "accounts.adobe.com",
    "ims-na1.adobelogin.com",
    "Log in to continue",
)

_MIN_LINKS_REAL_PAGE = 10

_BEHANCE_ORIGIN = "https://www.behance.net"


def _to_behance_path(href: str) -> str | None:
    """Normalise an href to a Behance path string, or return None if it's not a Behance profile link.

    Accepts both relative paths (/username) and absolute URLs
    (https://www.behance.net/username) as Behance's React app uses both.
    """
    if not href:
        return None
    if href.startswith(_BEHANCE_ORIGIN):
        href = href[len(_BEHANCE_ORIGIN):]
    if not href.startswith("/"):
        return None
    return href


def _is_profile_href(href: str) -> bool:
    path = _to_behance_path(href)
    if path is None:
        return False
    if any(path.startswith(skip) for skip in _SKIP_PATHS):
        return False
    return bool(_HANDLE_RE.match(path))


def _load_session_cookies(driver: WebDriver) -> bool:
    if not _SESSION_COOKIE_FILE.exists():
        return False
    try:
        cookies = json.loads(_SESSION_COOKIE_FILE.read_text())
        if not cookies:
            return False
        driver.get("https://www.behance.net/")
        time.sleep(1)
        for cookie in cookies:
            cookie.pop("sameSite", None)
            try:
                driver.add_cookie(cookie)
            except Exception:
                pass
        logger.info("Behance: loaded %d cookies from session file.", len(cookies))
        return True
    except Exception as exc:
        logger.debug("Behance: could not load session cookies: %s", exc)
        return False


def _save_session_cookies(driver: WebDriver) -> None:
    try:
        _SESSION_COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
        cookies = driver.get_cookies()
        _SESSION_COOKIE_FILE.write_text(json.dumps(cookies, indent=2))
        logger.info("Behance: session cookies saved (%d cookies).", len(cookies))
    except Exception as exc:
        logger.warning("Behance: could not save session cookies: %s", exc)


class BehanceScraper:
    platform = "behance"
    base_url = "https://www.behance.net"

    # ── Session management ────────────────────────────────────────────────────

    def _detect_login_wall(self, source: str) -> bool:
        lower = source[:6000].lower()
        return any(sig.lower() in lower for sig in _LOGIN_SIGNALS)

    def _is_logged_in(self, driver: WebDriver) -> bool:
        """Verify auth by hitting a page that only exists for logged-in users.

        /settings is a protected Behance route: unauthenticated requests redirect
        to the login/SSO page, so we can definitively detect auth status.
        """
        try:
            driver.get("https://www.behance.net/settings")
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(1.5)
            cur = driver.current_url
            src = driver.page_source

            # Redirected to Adobe/Behance login → not authenticated
            if (
                "accounts.adobe.com" in cur
                or "adobelogin.com" in cur
                or "auth/sso" in cur
                or "/login" in cur
            ):
                logger.info("Behance: session check → NOT logged in (redirected to %s).", cur)
                return False

            # Still on /settings (or /settings/...) → authenticated
            if "behance.net/settings" in cur:
                logger.info("Behance: session check → logged in (settings page loaded).")
                return True

            # Fallback: check for known authenticated-only JS tokens
            if any(s in src for s in (
                'data-testid="user-menu"', '"logged_in":true',
                'aria-label="Profile"', '"isLoggedIn":true',
            )):
                logger.info("Behance: session check → logged in (auth signal in source).")
                return True

            logger.info("Behance: session check → NOT logged in (no auth signal, url=%s).", cur)
            return False
        except Exception:
            return False

    def _try_login(self, driver: WebDriver, config: AppConfig) -> bool:
        """Automated Adobe SSO login — same direct-navigation pattern as Instagram.

        Skips the Sign-In button entirely: navigates straight to the Behance SSO
        endpoint which redirects to accounts.adobe.com, then fills email + password.
        """
        username = config.behance_username
        password = config.behance_password
        if not username or not password:
            logger.warning(
                "Behance: no credentials configured. "
                "Set BEHANCE_USERNAME and BEHANCE_PASSWORD in .env."
            )
            return False

        logger.info("Behance: attempting Adobe SSO login for '%s'.", username)
        try:
            # ── Step 1: navigate directly to the Behance SSO entry point ─────
            # This immediately redirects to accounts.adobe.com without needing
            # to find or click any Sign-In button on behance.net.
            driver.get(
                "https://www.behance.net/auth/sso/login"
                "?url=https%3A%2F%2Fwww.behance.net%2F"
            )

            # ── Step 2: wait for Adobe login page ────────────────────────────
            try:
                WebDriverWait(driver, 30).until(
                    lambda d: "accounts.adobe.com" in d.current_url
                    or "adobelogin.com" in d.current_url
                    or "auth.services.adobe.com" in d.current_url
                )
            except Exception:
                cur = driver.current_url
                logger.warning(
                    "Behance: Adobe login page did not load (stuck at %s).", cur
                )
                save_debug_html(driver, Path("debug_html"), "behance_no_adobe_redirect.html")
                return False

            logger.debug("Behance: reached Adobe login at %s", driver.current_url)
            time.sleep(2)  # let Adobe's React/Spectrum form fully render

            # ── Step 3: fill email ────────────────────────────────────────────
            email_field = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR,
                    "#EmailPage-EmailField, input[name='email'], "
                    "input[type='email'], input[name='username'], #username"
                ))
            )
            email_field.click()
            time.sleep(0.3)
            email_field.clear()
            email_field.send_keys(username)
            time.sleep(0.4)

            # ── Step 4: click Continue ────────────────────────────────────────
            # Try explicit Continue button; fall back to pressing Enter on the field
            try:
                continue_btn = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR,
                        "#EmailPage-ContinueButton, "
                        "button[data-id='EmailPage-ContinueButton'], "
                        "button[type='submit']"
                    ))
                )
                driver.execute_script("arguments[0].click();", continue_btn)
            except Exception:
                email_field.send_keys(Keys.RETURN)

            # ── Step 5: wait for password page & fill password ────────────────
            try:
                pass_field = WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR,
                        "#PasswordPage-PasswordField, "
                        "input[type='password'], input[name='password']"
                    ))
                )
            except Exception:
                cur = driver.current_url
                logger.warning(
                    "Behance: password field not found after Continue. URL: %s", cur
                )
                save_debug_html(driver, Path("debug_html"), "behance_no_password_field.html")
                return False

            pass_field.click()
            time.sleep(0.3)
            pass_field.clear()
            pass_field.send_keys(password)
            time.sleep(0.4)
            pass_field.send_keys(Keys.RETURN)

            # ── Step 6: wait for redirect back to behance.net ─────────────────
            # Adobe may show "Add backup email" / "Add phone" post-login screens
            # before the final redirect. Detect and dismiss them automatically.
            deadline = time.time() + 40
            while time.time() < deadline:
                cur = driver.current_url

                if "progressive-profile" in cur or "add-secondary-email" in cur:
                    logger.debug("Behance: Adobe post-login screen — clicking 'Not now'")
                    for sel in (
                        "button[data-id='notNowButton']",
                        "button.spectrum-Button--secondary",
                        "//button[normalize-space()='Not now']",
                    ):
                        try:
                            btn = (
                                driver.find_element(By.XPATH, sel)
                                if sel.startswith("//")
                                else driver.find_element(By.CSS_SELECTOR, sel)
                            )
                            driver.execute_script("arguments[0].click();", btn)
                            time.sleep(1.5)
                            break
                        except Exception:
                            continue

                if (
                    "behance.net" in cur
                    and "accounts.adobe.com" not in cur
                    and "adobelogin.com" not in cur
                    and "auth.services.adobe.com" not in cur
                ):
                    time.sleep(2)
                    logger.info("Behance: login successful — session at %s.", cur)
                    return True

                if any(x in cur for x in ("2factor", "two-step", "mfa")):
                    logger.warning(
                        "Behance: 2FA required at %s — run `python behance_login.py`.", cur
                    )
                    save_debug_html(driver, Path("debug_html"), "behance_login_failed.html")
                    return False

                time.sleep(1)

            cur = driver.current_url
            logger.warning("Behance: login redirect timed out at %s", cur)
            save_debug_html(driver, Path("debug_html"), "behance_login_failed.html")
            return False

        except Exception as exc:
            logger.warning("Behance: login attempt failed: %s", exc)
            save_debug_html(driver, Path("debug_html"), "behance_login_error.html")
            return False

    def _establish_session(self, driver: WebDriver, config: AppConfig) -> bool:
        """Chrome profile cookies → saved cookie file → programmatic login → warn."""
        # 1. Check if the cloned Chrome profile already has a valid Behance session
        #    (happens when the user is logged-in in their real Chrome browser)
        if self._is_logged_in(driver):
            logger.info("Behance: active session found in Chrome profile — no login needed.")
            _save_session_cookies(driver)
            return True

        # 2. Try restoring from our own saved cookie file
        if _load_session_cookies(driver):
            if self._is_logged_in(driver):
                logger.info("Behance: session restored from cookie file.")
                return True
            logger.info("Behance: saved cookies expired — will re-login.")
            try:
                _SESSION_COOKIE_FILE.unlink(missing_ok=True)
            except Exception:
                pass

        # 3. Fall back to programmatic login
        if self._try_login(driver, config):
            _save_session_cookies(driver)
            return True

        # Behance user-search pages are partially public — try without auth.
        logger.warning(
            "Behance: could not establish authenticated session.\n"
            "  Some profile data (followers, full bios) may be unavailable.\n"
            "  Set BEHANCE_USERNAME / BEHANCE_PASSWORD in .env for full access."
        )
        return False  # caller decides whether to continue

    # ── Public entry point ────────────────────────────────────────────────────

    def scrape(self, driver: WebDriver, config: AppConfig) -> list[Lead]:
        leads: list[Lead] = []

        # Behance search requires authentication — skip entirely if we can't log in.
        # Adobe SSO blocks headless Chrome; run `python behance_login.py` once to
        # save a real session that will be reused automatically for ~25 days.
        authenticated = self._establish_session(driver, config)
        if not authenticated:
            logger.warning(
                "Behance: skipping all searches — no authenticated session.\n"
                "  Run `python behance_login.py` once to bootstrap a session."
            )
            return []

        # Warm up the Behance SPA from the homepage so the React session state
        # initialises before we navigate directly to search URLs.
        try:
            driver.get("https://www.behance.net/")
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(2)
            logger.debug("Behance: homepage warm-up done.")
        except Exception:
            pass

        for keyword in config.behance_keywords:
            if len(leads) >= config.max_profiles_per_platform:
                break
            try:
                new_leads = scrape_with_retry(
                    lambda kw=keyword: self._scrape_keyword(driver, config, kw, leads),
                    max_retries=config.network_retries,
                    base_delay=5.0,
                    label=f"behance/{keyword}",
                )
                leads.extend(new_leads)
            except Exception as exc:
                logger.exception("Behance error for '%s': %s", keyword, exc)

        if leads:
            _save_session_cookies(driver)

        return leads[:config.max_profiles_per_platform]

    # ── Keyword scrape ────────────────────────────────────────────────────────

    def _scrape_keyword(
        self,
        driver: WebDriver,
        config: AppConfig,
        keyword: str,
        existing: list[Lead],
    ) -> list[Lead]:
        remaining = config.max_profiles_per_platform - len(existing)
        leads: list[Lead] = []

        # Strategy 1: user/profile search
        user_leads = self._search_users(driver, config, keyword, remaining)
        leads.extend(user_leads)
        remaining -= len(user_leads)

        # Strategy 2: project search → extract authors (if still need more)
        if remaining > 0 and len(leads) < 5:
            proj_leads = self._search_projects(driver, config, keyword, remaining)
            leads.extend(proj_leads)

        return leads

    # ── User / profile cards selector (Behance React SPA) ────────────────────
    # These selectors match elements that only appear when search results load.
    _USER_RESULT_SELECTORS = (
        "a[href^='/'][href*='/'][class*='UserCard']",
        "div[class*='UserCard'] a[href^='/']",
        "div[class*='user-card'] a[href^='/']",
        "ul[class*='search-results'] a[href^='/']",
        "section[class*='Search'] a[href^='/']",
    )
    _PROJECT_RESULT_SELECTORS = (
        "a[href^='/'][class*='ProjectCard']",
        "div[class*='ProjectCard'] a[href^='/']",
        "div[class*='project-card'] a[href^='/']",
        "ul[class*='ProjectsList'] a[href^='/']",
    )

    def _wait_for_spa_content(self, driver: WebDriver, selectors: tuple, timeout: int = 18) -> bool:
        """Wait up to `timeout` seconds for any of the SPA result selectors to appear."""
        import time as _time
        deadline = _time.time() + timeout
        while _time.time() < deadline:
            for sel in selectors:
                try:
                    if driver.find_elements(By.CSS_SELECTOR, sel):
                        return True
                except Exception:
                    pass
            _time.sleep(0.6)
        return False

    def _search_users(
        self,
        driver: WebDriver,
        config: AppConfig,
        keyword: str,
        limit: int,
    ) -> list[Lead]:
        url = f"{self.base_url}/search/users?search={quote(keyword)}&sort=appreciations"
        logger.info("Behance user search: keyword=%s", keyword)
        driver.get(url)
        WebDriverWait(driver, config.page_load_timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Log where we actually landed (detect silent redirects)
        cur = driver.current_url
        if "behance.net" not in cur or any(x in cur for x in ("/login", "/signin", "accounts.adobe.com")):
            logger.warning("Behance: redirected away from search to %s for '%s'", cur, keyword)
            save_debug_html(driver, config.debug_html_dir, f"behance_redirect_{quote(keyword)}.html", True)
            return []

        # Wait for React SPA to render user cards
        found = self._wait_for_spa_content(driver, self._USER_RESULT_SELECTORS, timeout=18)
        if not found:
            logger.debug("Behance: SPA user cards not detected for '%s' within timeout — parsing anyway", keyword)

        scroll_page(driver, scrolls=config.scrolls_override, min_delay=config.min_delay, max_delay=config.max_delay)
        save_debug_html(driver, config.debug_html_dir, f"behance_users_{quote(keyword)}.html", config.save_debug_html)

        return self._parse_user_cards(driver.page_source, keyword, limit)

    def _search_projects(
        self,
        driver: WebDriver,
        config: AppConfig,
        keyword: str,
        limit: int,
    ) -> list[Lead]:
        url = f"{self.base_url}/search/projects?search={quote(keyword)}&sort=appreciations"
        logger.info("Behance project search: keyword=%s", keyword)
        driver.get(url)
        WebDriverWait(driver, config.page_load_timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        cur = driver.current_url
        if "behance.net" not in cur or any(x in cur for x in ("/login", "/signin", "accounts.adobe.com")):
            logger.warning("Behance: redirected away from project search to %s for '%s'", cur, keyword)
            return []

        found = self._wait_for_spa_content(driver, self._PROJECT_RESULT_SELECTORS, timeout=18)
        if not found:
            logger.debug("Behance: SPA project cards not detected for '%s' within timeout — parsing anyway", keyword)

        scroll_page(driver, scrolls=config.scrolls_override, min_delay=config.min_delay, max_delay=config.max_delay)
        save_debug_html(driver, config.debug_html_dir, f"behance_proj_{quote(keyword)}.html", config.save_debug_html)

        return self._parse_project_authors(driver, config, keyword, limit)

    # ── HTML parsers ──────────────────────────────────────────────────────────

    def _parse_user_cards(self, html: str, keyword: str, limit: int) -> list[Lead]:
        soup = soup_from_html(html)
        seen: set[str] = set()
        leads: list[Lead] = []

        all_anchors = soup.select("a[href]")
        logger.debug(
            "Behance user search '%s': %d total anchors in page source.",
            keyword, len(all_anchors),
        )

        # Detect unauthenticated gate: real search results have many profile links;
        # if the page returned fewer than a threshold we are likely seeing only nav links.
        all_valid_hrefs = [
            a.get("href", "") for a in all_anchors
            if _is_profile_href(a.get("href", ""))
        ]
        if len(all_valid_hrefs) <= 3:
            # Log a sample of raw hrefs to help diagnose what the page returned
            sample = [a.get("href", "") for a in all_anchors[:20]]
            logger.warning(
                "Behance: only %d profile links found for '%s' — "
                "likely unauthenticated (login required for search results). "
                "Sample hrefs: %s",
                len(all_valid_hrefs), keyword, sample,
            )
            return []

        # Behance user cards: <a href="/username"> wrapping a user card
        for a in all_anchors:
            href = a.get("href", "")
            if not _is_profile_href(href):
                continue
            path = _to_behance_path(href)
            clean_href = path.rstrip("/")
            if clean_href in seen:
                continue
            seen.add(clean_href)

            profile_url = f"{self.base_url}{clean_href}"
            handle = clean_href.lstrip("/")

            # Grab the card container for text signals
            card = a.find_parent(["div", "li", "article"]) or a.parent
            card_text = card.get_text(" ", strip=True)[:1200] if card else handle

            leads.append(self._build_lead(keyword, handle, profile_url, card_text))
            if len(leads) >= limit:
                break

        logger.info("Behance: parsed %d user profiles for '%s'", len(leads), keyword)
        return leads

    def _parse_project_authors(
        self,
        driver: WebDriver,
        config: AppConfig,
        keyword: str,
        limit: int,
    ) -> list[Lead]:
        """Extract unique project authors from the project search grid."""
        soup = soup_from_html(driver.page_source)
        # Project cards link to /projectid/project-title — not user profiles.
        # Author links are usually nested inside each card as /username
        seen: set[str] = set()
        leads: list[Lead] = []

        all_anchors = soup.select("a[href]")
        logger.debug(
            "Behance project search '%s': %d total anchors in page source.",
            keyword, len(all_anchors),
        )

        all_valid = [
            a.get("href", "") for a in all_anchors
            if _is_profile_href(a.get("href", ""))
        ]
        if len(all_valid) <= 3:
            sample = [a.get("href", "") for a in all_anchors[:20]]
            logger.warning(
                "Behance: only %d author links found for '%s' — likely unauthenticated. "
                "Sample hrefs: %s",
                len(all_valid), keyword, sample,
            )
            return []

        # Try to find author handles embedded in project card markup
        for a in all_anchors:
            href = a.get("href", "")
            if not _is_profile_href(href):
                continue
            path = _to_behance_path(href)
            clean_href = path.rstrip("/")
            if clean_href in seen:
                continue
            seen.add(clean_href)

            profile_url = f"{self.base_url}{clean_href}"
            handle = clean_href.lstrip("/")
            card = a.find_parent(["div", "li", "article"]) or a.parent
            card_text = card.get_text(" ", strip=True)[:1200] if card else handle

            leads.append(self._build_lead(keyword, handle, profile_url, card_text))
            if len(leads) >= limit:
                break

        logger.info("Behance: parsed %d project authors for '%s'", len(leads), keyword)
        return leads

    # ── Lead construction ─────────────────────────────────────────────────────

    def _build_lead(self, keyword: str, handle: str, profile_url: str, text: str) -> Lead:
        city, country = detect_location(text)
        emails = extract_emails(text)
        phones = extract_phones(text)

        # Behance cards often show "X Followers" and "X Appreciations"
        followers = extract_follower_count(text)

        # Extract appreciations count as engagement hint
        appr_match = re.search(r"([\d,.]+[KkMm]?)\s*(?:appreciations?|apreciaciones?)", text, re.IGNORECASE)
        engagement = appr_match.group(0) if appr_match else ""

        # Extract occupation/specialty (Behance shows it below the name)
        occupation_match = re.search(
            r"\b(architect|interior designer|art director|creative director|"
            r"graphic designer|photographer|illustrator|animator|"
            r"diseñador|arquitecto|interiorista|curador|artista)\b",
            text,
            re.IGNORECASE,
        )
        occupation = occupation_match.group(0).title() if occupation_match else ""

        return Lead(
            source_platform=self.platform,
            search_term=keyword,
            name=handle,
            social_handle=handle,
            profile_url=profile_url,
            email=emails[0] if emails else "",
            phone=phones[0] if phones else "",
            website=extract_website(text),
            city=city,
            country=country,
            bio=(f"{occupation} — {text[:400]}" if occupation else text[:500]).strip(" —"),
            category=occupation or "creative_professional",
            lead_type=classify_lead(text),
            interest_signals=extract_interest_signals(text),
            followers=followers,
            engagement_hint=engagement,
            raw_data={
                "text_sample": text[:1200],
                "appreciations": engagement,
                "occupation": occupation,
            },
        )
