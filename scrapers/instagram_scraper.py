"""
Instagram scraper with route evaluation and adaptive strategy.

Route priority:
  1. Clean sanitized hashtag URL (most stable public route)
  2. Raw-encoded fallback hashtag URL
  3. Skip gracefully if all candidates are penalized

All attempted routes are recorded in RouteEvaluator for learning.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import quote

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import AppConfig
from core.route_evaluator import RouteEvaluator, RouteCandidate
from models import Lead
from parsers.lead_parser import soup_from_html
from utils.classifiers import classify_lead, extract_interest_signals
from utils.helpers import (
    clean_text,
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

# Paths that are NOT user profiles on Instagram
_SKIP_PATH_PREFIXES = (
    "/p/", "/reel/", "/reels/", "/stories/", "/tv/",
    "/explore/", "/accounts/", "/direct/", "/ar/",
    "/login/", "/challenge/",
)
# Valid Instagram handles: 1–30 alphanumeric / dot / underscore
_HANDLE_RE = re.compile(r"^/([a-zA-Z0-9._]{1,30})/?$")

# If these strings appear in page source, the route hit a wall
_BLOCK_SIGNALS = (
    "Log in to Instagram",
    "instagramlogin",
    "checkpoint_required",
    "challenge_required",
    "action_blocked",
    "Please wait a few minutes before you try again",
)
# Marker present in the empty React shell served when not logged in
_LITE_REDIRECT = "/web/lite/"
# Min <a href> tags expected on a real hashtag listing page
_MIN_LINKS_REAL_PAGE = 15

# Where we persist Instagram cookies between runs (avoids GNOME keyring issues)
_SESSION_COOKIE_FILE = Path("output/instagram_session.json")
# Cookies are valid for this many days before forcing re-login
_SESSION_MAX_AGE_DAYS = 25


def _load_session_cookies(driver: WebDriver) -> bool:
    """Inject saved cookies into the driver. Returns True if file existed and was loaded."""
    if not _SESSION_COOKIE_FILE.exists():
        return False
    try:
        cookies = json.loads(_SESSION_COOKIE_FILE.read_text())
        if not cookies:
            return False
        # Must navigate to the domain before injecting cookies
        driver.get("https://www.instagram.com/")
        time.sleep(1)
        for cookie in cookies:
            # Remove fields Chrome rejects on injection
            cookie.pop("sameSite", None)
            try:
                driver.add_cookie(cookie)
            except Exception:
                pass
        logger.info("Instagram: loaded %d cookies from session file.", len(cookies))
        return True
    except Exception as exc:
        logger.debug("Instagram: could not load session cookies: %s", exc)
        return False


def _save_session_cookies(driver: WebDriver) -> None:
    """Persist current browser cookies to disk for future runs."""
    try:
        _SESSION_COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
        cookies = driver.get_cookies()
        _SESSION_COOKIE_FILE.write_text(json.dumps(cookies, indent=2))
        logger.info("Instagram: session cookies saved (%d cookies).", len(cookies))
    except Exception as exc:
        logger.warning("Instagram: could not save session cookies: %s", exc)


class InstagramScraper:
    platform = "instagram"
    base_url = "https://www.instagram.com"

    def __init__(self, route_evaluator: RouteEvaluator | None = None) -> None:
        self._route_eval = route_evaluator

    def _is_profile_href(self, href: str) -> bool:
        if not href or not href.startswith("/"):
            return False
        if any(href.startswith(skip) for skip in _SKIP_PATH_PREFIXES):
            return False
        return bool(_HANDLE_RE.match(href))

    def _detect_block(self, source: str) -> bool:
        lower = source[:5000].lower()
        if any(sig.lower() in lower for sig in _BLOCK_SIGNALS):
            return True
        # Instagram serves an empty React shell (only ~7 links, contains /web/lite/)
        # when the session is not authenticated — treat it as a login wall.
        if _LITE_REDIRECT in source:
            return True
        link_count = source.count('href="/')
        if link_count < _MIN_LINKS_REAL_PAGE:
            logger.warning(
                "Instagram: page has only %d internal links — likely not logged in "
                "(configure USER_DATA_DIR + CHROME_PROFILE_PATH in settings)",
                link_count,
            )
            return True
        return False

    # ── Login fallback ────────────────────────────────────────────────────────

    def _try_login(self, driver: WebDriver, config: AppConfig) -> bool:
        """Attempt programmatic login when cookie session is not recognised.

        Returns True if login appears successful, False otherwise.
        """
        username = config.instagram_username
        password = config.instagram_password
        if not username or not password:
            logger.warning("Instagram: no credentials in config — cannot attempt login fallback.")
            return False

        logger.info("Instagram: cookie session invalid — attempting login with username '%s'.", username)
        try:
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            driver.get("https://www.instagram.com/accounts/login/")

            # Wait for the username input to be clickable (JS-rendered form)
            user_field = WebDriverWait(driver, 25).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='username']"))
            )
            time.sleep(2)  # let React fully hydrate

            # Dismiss cookie/consent banner if present
            try:
                for sel in (
                    "button[data-cookiebanner='accept_button']",
                    "[role='dialog'] button:last-child",
                    "button._a9--._a9_1",
                ):
                    try:
                        btn = driver.find_element(By.CSS_SELECTOR, sel)
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(0.6)
                        break
                    except Exception:
                        continue
            except Exception:
                pass

            # Fill username via send_keys (native events — React sees them properly)
            user_field = driver.find_element(By.CSS_SELECTOR, "input[name='username']")
            user_field.click()
            time.sleep(0.3)
            user_field.clear()
            user_field.send_keys(username)
            time.sleep(0.5)

            pass_field = driver.find_element(By.CSS_SELECTOR, "input[name='password']")
            pass_field.click()
            time.sleep(0.3)
            pass_field.clear()
            pass_field.send_keys(password)
            time.sleep(0.5)

            # Submit via Enter key — avoids all click interception issues
            pass_field.send_keys(Keys.RETURN)

            # Wait for redirect away from login page (up to 30 s)
            try:
                WebDriverWait(driver, 30).until(
                    lambda d: "/accounts/login" not in d.current_url
                )
            except Exception:
                cur = driver.current_url
                src = driver.page_source[:3000]
                if "/challenge" in cur or "checkpoint" in cur.lower():
                    logger.warning(
                        "Instagram: 2FA / checkpoint required at %s — log in manually in Chrome first.", cur
                    )
                else:
                    logger.warning(
                        "Instagram: login redirect timed out. Current URL: %s | page snippet: %.300s",
                        cur, src,
                    )
                try:
                    save_debug_html(driver, Path("debug_html"), "instagram_login_failed.html")
                except Exception:
                    pass
                return False

            time.sleep(2)
            logger.info("Instagram: login successful — session active at %s.", driver.current_url)
            return True
        except Exception as exc:
            logger.warning("Instagram: login attempt failed: %s", exc)
            try:
                save_debug_html(driver, Path("debug_html"), "instagram_login_failed.html")
            except Exception:
                pass
            return False

    def _is_logged_in(self, driver: WebDriver) -> bool:
        """Check session by navigating to a protected page that redirects to login if unauthenticated."""
        try:
            # /accounts/edit/ requires auth → deterministic redirect test
            driver.get("https://www.instagram.com/accounts/edit/")
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(1.5)
            url = driver.current_url
            # If we stayed on /accounts/edit/ (or any non-login page), we're in.
            # Note: _detect_block is NOT used here because /web/lite/ appears in
            # the logged-in page source as a script URL (false positive).
            if "/accounts/login" in url or "/login" in url:
                logger.info("Instagram: session check → NOT logged in (redirected to %s)", url)
                return False
            logger.info("Instagram: session check → logged in (%s)", url)
            return True
        except Exception:
            return False

    def _establish_session(self, driver: WebDriver, config: AppConfig) -> bool:
        """
        Establish an authenticated Instagram session using the best available method:

        1. Inject saved cookies from disk  →  verify  →  done if OK
        2. Programmatic login with credentials  →  save cookies  →  done if OK
        3. Fail with a clear error message

        This design avoids GNOME Keyring decryption issues: once the first
        login succeeds the session cookies are stored unencrypted in
        output/instagram_session.json and reused on every subsequent run.
        """
        # ── Strategy 1: cookie file ───────────────────────────────────────────
        if _load_session_cookies(driver):
            if self._is_logged_in(driver):
                logger.info("Instagram: session restored from cookie file.")
                return True
            logger.info("Instagram: saved cookies expired — will re-login.")
            # Delete stale file so next check doesn't re-try it
            try:
                _SESSION_COOKIE_FILE.unlink(missing_ok=True)
            except Exception:
                pass

        # ── Strategy 2: programmatic login ───────────────────────────────────
        if self._try_login(driver, config):
            _save_session_cookies(driver)
            return True

        logger.error(
            "Instagram: could not establish session.\n"
            "  Option A (recommended): log in manually in Chrome once, then run the scraper — "
            "cookies will be auto-saved for future runs.\n"
            "  Option B: set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD in .env and retry.\n"
            "  Option C: set HEADLESS=false to run Chrome visibly (may help with challenges)."
        )
        return False

    # ── Public entry point ────────────────────────────────────────────────────

    def scrape(self, driver: WebDriver, config: AppConfig) -> list[Lead]:
        leads: list[Lead] = []

        # Establish session: cookie file → programmatic login → fail
        if not self._establish_session(driver, config):
            return []

        for keyword in config.instagram_keywords:
            if len(leads) >= config.max_profiles_per_platform:
                break

            # Build prioritized candidate routes
            if self._route_eval:
                candidates = self._route_eval.instagram_route_candidates(keyword)
            else:
                # Fallback: minimal candidate without route tracking
                clean = RouteEvaluator.sanitize_hashtag(keyword)
                if not clean:
                    logger.warning("Instagram: cannot sanitize hashtag '%s', skipping", keyword)
                    continue
                from core.route_evaluator import RouteCandidate as RC
                candidates = [
                    RC(
                        url=f"{self.base_url}/explore/tags/{clean}/",
                        pattern=f"instagram/hashtag/{clean}",
                        priority=1,
                        stability_score=0.65,
                        reason=f"hashtag:{clean}",
                    )
                ]

            if not candidates:
                logger.warning("Instagram: no valid routes for keyword '%s'", keyword)
                continue

            new_leads = self._try_candidates(
                driver, config, keyword, candidates, existing_count=len(leads)
            )
            leads.extend(new_leads)

        # Refresh saved cookies at the end of a successful session
        if leads:
            _save_session_cookies(driver)

        return leads

    # ── Route attempt loop ────────────────────────────────────────────────────

    def _try_candidates(
        self,
        driver: WebDriver,
        config: AppConfig,
        keyword: str,
        candidates: list[RouteCandidate],
        existing_count: int,
    ) -> list[Lead]:
        """Try each candidate in priority order; return on first success."""
        for candidate in candidates:
            if candidate.stability_score < 0.20 and candidate.priority > 1:
                logger.info(
                    "Instagram: skipping penalized route '%s' (score=%.2f)",
                    candidate.pattern,
                    candidate.stability_score,
                )
                continue

            logger.info(
                "Instagram: trying [%s] score=%.2f  url=%s",
                candidate.reason,
                candidate.stability_score,
                candidate.url,
            )

            try:
                new_leads = scrape_with_retry(
                    lambda c=candidate: self._scrape_route(
                        driver, config, keyword, c, existing_count
                    ),
                    max_retries=config.network_retries,
                    base_delay=config.min_delay * 2,
                    label=f"instagram/{candidate.reason}",
                )

                # Record success
                if self._route_eval:
                    self._route_eval.record_success("instagram", candidate.pattern)

                if new_leads:
                    return new_leads

                # Returned 0 leads — may be a soft block; try next candidate
                logger.info(
                    "Instagram: route '%s' returned 0 leads, trying fallback", candidate.reason
                )

            except Exception as exc:
                logger.warning("Instagram: route '%s' failed: %s", candidate.reason, exc)
                if self._route_eval:
                    self._route_eval.record_failure("instagram", candidate.pattern)

        return []

    # ── Single-route scrape ───────────────────────────────────────────────────

    def _scrape_route(
        self,
        driver: WebDriver,
        config: AppConfig,
        keyword: str,
        candidate: RouteCandidate,
        existing_count: int,
    ) -> list[Lead]:
        t0 = time.perf_counter()
        driver.get(candidate.url)

        WebDriverWait(driver, config.page_load_timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Wait for React to hydrate before checking for blocks.
        # Instagram's search/hashtag pages render via JS: the initial HTML has very
        # few links; after ~3 s the full grid is populated.
        time.sleep(3)

        # Check for login wall / block page before spending time scrolling.
        # NOTE: we check only for login signals here, not _detect_block, because
        # /web/lite/ appears as a script URL in logged-in pages (false positive).
        src_early = driver.page_source
        url_now = driver.current_url
        if "/accounts/login" in url_now or any(
            sig.lower() in src_early[:3000].lower()
            for sig in ("Log in to Instagram", "checkpoint_required", "challenge_required")
        ):
            raise RuntimeError(
                f"Instagram block detected on route '{candidate.reason}' "
                "(login wall or rate-limit page)"
            )

        scroll_page(
            driver,
            scrolls=config.scrolls_override,
            min_delay=config.min_delay,
            max_delay=config.max_delay,
        )
        save_debug_html(
            driver,
            config.debug_html_dir,
            f"instagram_{quote(keyword)}.html",
            config.save_debug_html,
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug("Instagram route '%s' loaded in %.0f ms", candidate.reason, elapsed_ms)

        max_leads = config.max_profiles_per_platform - existing_count
        leads = self._parse_profiles(driver.page_source, keyword, max_leads=max_leads)

        # Instagram now redirects hashtag pages to keyword search, which shows
        # post thumbnails (not direct profile links). The sidebar always contributes
        # the logged-in user's handle, so <= 1 unique profile means we only found
        # the nav link. Fall back to visiting each post and extracting the author.
        if len(leads) <= 1:
            logger.info(
                "Instagram: no profiles on search page — trying post-based extraction for '%s'",
                keyword,
            )
            leads = self._posts_to_profiles(driver, config, keyword, max_leads)

        return leads

    def _posts_to_profiles(
        self,
        driver: WebDriver,
        config: AppConfig,
        keyword: str,
        max_leads: int,
    ) -> list[Lead]:
        """Visit each post from the current search page and extract the author profile."""
        from bs4 import BeautifulSoup as _BS
        soup = _BS(driver.page_source, "html.parser")
        post_hrefs = list(dict.fromkeys(
            a["href"] for a in soup.select("a[href^='/p/']")
        ))
        if not post_hrefs:
            return []
        logger.info(
            "Instagram: found %d posts on search page — visiting each for author", len(post_hrefs)
        )
        leads: list[Lead] = []
        seen_handles: set[str] = set()
        for href in post_hrefs:
            if len(leads) >= max_leads:
                break
            post_url = f"{self.base_url}{href}"
            try:
                driver.get(post_url)
                WebDriverWait(driver, config.page_load_timeout).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                time.sleep(1.5)
                # Extract author from og:url: https://instagram.com/{username}/p/{id}/
                post_soup = _BS(driver.page_source, "html.parser")
                og_url_tag = post_soup.find("meta", property="og:url")
                og_url = og_url_tag.get("content", "") if og_url_tag else ""
                m = re.match(r"https://www\.instagram\.com/([a-zA-Z0-9._]{1,30})/p/", og_url)
                if not m:
                    continue
                handle = m.group(1)
                if handle in seen_handles:
                    continue
                seen_handles.add(handle)
                og_title = post_soup.find("meta", property="og:title")
                og_desc = post_soup.find("meta", property="og:description")
                card_text = " ".join(filter(None, [
                    og_title.get("content", "") if og_title else "",
                    og_desc.get("content", "") if og_desc else "",
                ]))
                profile_url = f"{self.base_url}/{handle}/"
                leads.append(self._build_lead(keyword, handle, profile_url, card_text))
                logger.debug("Instagram post-extract: %s from %s", handle, href)
            except Exception as exc:
                logger.debug("Instagram: could not extract author from %s: %s", href, exc)
            finally:
                if len(leads) < max_leads:
                    time.sleep(config.min_delay)
        logger.info("Instagram: post-based extraction → %d profiles for '%s'", len(leads), keyword)
        return leads

    # ── HTML parsing ──────────────────────────────────────────────────────────

    def _parse_profiles(
        self, html: str, keyword: str, max_leads: int
    ) -> list[Lead]:
        soup = soup_from_html(html)
        seen: set[str] = set()
        leads: list[Lead] = []

        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not self._is_profile_href(href):
                continue
            if href in seen:
                continue
            seen.add(href)

            handle = href.strip("/")
            profile_url = f"{self.base_url}/{handle}/"
            parent = a.find_parent(["li", "article", "div"]) or a.parent
            card_text = parent.get_text(" ", strip=True) if parent else handle

            leads.append(self._build_lead(keyword, handle, profile_url, card_text))
            if len(leads) >= max_leads:
                break

        return leads

    def _build_lead(
        self, keyword: str, handle: str, profile_url: str, text: str
    ) -> Lead:
        city, country = detect_location(text)
        emails = extract_emails(text)
        phones = extract_phones(text)
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
            bio=clean_text([text[:500]]),
            lead_type=classify_lead(text),
            interest_signals=extract_interest_signals(text),
            followers=extract_follower_count(text),
            raw_data={"text_sample": text[:1000]},
        )
