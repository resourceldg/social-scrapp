from __future__ import annotations

import logging
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple, TypeVar
from urllib.parse import urlparse, urlunparse

from selenium.webdriver.remote.webdriver import WebDriver

EMAIL_REGEX = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
# Requires at least 7 consecutive digit groups to reduce false positives (dates, prices, etc.)
PHONE_REGEX = re.compile(
    r"(?<!\d)"                          # not preceded by a digit
    r"(?:\+\d{1,3}[\s.\-]?)?"          # optional country code (+54, +1, etc.)
    r"(?:\(?\d{2,4}\)?[\s.\-]?)?"      # optional area code
    r"\d{3,4}[\s.\-]?\d{4}"            # core: 3-4 digits + 4 digits
    r"(?!\d)"                           # not followed by a digit
)
URL_REGEX = re.compile(r"\b(?:https?://|www\.)[\w.-]+(?:\.[\w.-]+)+(?:[/\w\-._~:/?#[\]@!$&'()*+,;=]*)?", re.IGNORECASE)

# Matches follower counts in card text:
# "12.5K Followers", "1,234 followers", "500+ connections", "45M seguidores"
_FOLLOWER_RE = re.compile(
    r"([\d][,\d\.]*[\d]?\s*[KkMm]?)\s*(?:[Ff]ollowers?|[Ss]eguidores?|[Cc]onnections?)",
    re.IGNORECASE,
)

# Social media domains excluded from extract_website results
_SOCIAL_DOMAINS = frozenset({
    "instagram.com", "facebook.com", "linkedin.com", "twitter.com",
    "x.com", "pinterest.com", "reddit.com", "tiktok.com", "youtube.com",
    "t.co", "fb.com", "fb.me", "lnkd.in",
})

# Cities BEFORE countries so the most specific match wins
PRIORITY_LOCATIONS = {
    # Cities first
    "buenos aires": ("Buenos Aires", "Argentina"),
    "rosario": ("Rosario", "Argentina"),
    "córdoba": ("Córdoba", "Argentina"),
    "cordoba": ("Córdoba", "Argentina"),
    "madrid": ("Madrid", "España"),
    "barcelona": ("Barcelona", "España"),
    "sevilla": ("Sevilla", "España"),
    "valencia": ("Valencia", "España"),
    "cdmx": ("CDMX", "México"),
    "ciudad de méxico": ("CDMX", "México"),
    "monterrey": ("Monterrey", "México"),
    "guadalajara": ("Guadalajara", "México"),
    "bogotá": ("Bogotá", "Colombia"),
    "bogota": ("Bogotá", "Colombia"),
    "medellín": ("Medellín", "Colombia"),
    "medellin": ("Medellín", "Colombia"),
    "lima": ("Lima", "Perú"),
    "santiago": ("Santiago", "Chile"),
    "miami": ("Miami", "USA"),
    "new york": ("New York", "USA"),
    "nyc": ("New York", "USA"),
    "los angeles": ("Los Angeles", "USA"),
    "são paulo": ("São Paulo", "Brasil"),
    "sao paulo": ("São Paulo", "Brasil"),
    "río de janeiro": ("Río de Janeiro", "Brasil"),
    "rio de janeiro": ("Río de Janeiro", "Brasil"),
    "paris": ("París", "France"),
    "london": ("London", "UK"),
    "dubai": ("Dubai", "UAE"),
    "milan": ("Milán", "Italy"),
    "milán": ("Milán", "Italy"),
    "roma": ("Roma", "Italy"),
    # Countries (fallback)
    "argentina": ("", "Argentina"),
    "españa": ("", "España"),
    "spain": ("", "España"),
    "méxico": ("", "México"),
    "mexico": ("", "México"),
    "chile": ("", "Chile"),
    "uruguay": ("", "Uruguay"),
    "colombia": ("", "Colombia"),
    "perú": ("", "Perú"),
    "peru": ("", "Perú"),
    "brasil": ("", "Brasil"),
    "brazil": ("", "Brasil"),
    "usa": ("", "USA"),
    "united states": ("", "USA"),
    "france": ("", "France"),
    "italy": ("", "Italy"),
    "italia": ("", "Italy"),
    "uk": ("", "UK"),
    "united kingdom": ("", "UK"),
}

logger = logging.getLogger(__name__)

T = TypeVar("T")


def random_delay(min_delay: float, max_delay: float) -> None:
    time.sleep(random.uniform(min_delay, max_delay))


def scroll_page(driver: WebDriver, scrolls: int = 4, min_delay: float = 1.5, max_delay: float = 3.0) -> None:
    """Adaptive scroll that waits for new content instead of fixed delays.

    On slow connections this avoids both:
    - Wasting time when content already loaded (breaks early)
    - Missing content that hasn't loaded yet (polls up to max_delay)
    """
    poll_interval = min(0.4, min_delay * 0.25)

    for _ in range(scrolls):
        prev_height: int = driver.execute_script("return document.body.scrollHeight")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

        waited = 0.0
        content_appeared = False
        while waited < max_delay:
            time.sleep(poll_interval)
            waited += poll_interval
            new_height: int = driver.execute_script("return document.body.scrollHeight")
            if new_height > prev_height:
                # Give JS a brief moment to finish rendering the new nodes
                time.sleep(min_delay * 0.20)
                content_appeared = True
                break

        if not content_appeared:
            # No new content loaded — brief pause to avoid hammering the CPU
            time.sleep(min_delay * 0.15)


def scrape_with_retry(
    fn: Callable[[], T],
    max_retries: int = 3,
    base_delay: float = 5.0,
    label: str = "",
) -> T:
    """Call *fn* and retry on failure with exponential backoff.

    Args:
        fn: Zero-argument callable to execute.
        max_retries: Total attempts (including the first).
        base_delay: Seconds to wait before the second attempt; doubles each time.
        label: Short string shown in log messages (e.g. "Instagram/keyword").

    Returns:
        Whatever *fn* returns on success.

    Raises:
        The last exception if all attempts fail.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "[retry] %s — attempt %d/%d failed, waiting %.0fs: %s",
                    label, attempt + 1, max_retries, delay, exc,
                )
                time.sleep(delay)
            else:
                logger.exception("[retry] %s — all %d attempts failed: %s", label, max_retries, exc)
    raise last_exc  # type: ignore[misc]


def normalize_url(url: str) -> str:
    """Strip query params, fragments, and trailing slash for reliable deduplication."""
    try:
        p = urlparse(url.lower().strip())
        return urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), "", "", ""))
    except Exception:
        return url.lower().strip().rstrip("/")


def check_url_reachable(url: str, timeout: int = 5) -> bool:
    """
    Quick HTTP HEAD check to verify a URL is reachable before a full Selenium visit.

    - Returns True immediately for social-media domains (they require browser + session
      cookies to return meaningful status codes — a plain HEAD just gets a redirect or
      a 200 login page, so we conservatively assume reachable and let the scraper handle
      login-wall detection).
    - Returns False for connection errors, HTTP 4xx/5xx, or malformed URLs.
    - Returns True for 2xx/3xx responses, treating redirects as reachable.
    """
    if not url:
        return False
    try:
        netloc = urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return False
    # Social media — can't reliably judge from a HEAD; assume reachable
    if any(netloc == d or netloc.endswith("." + d) for d in _SOCIAL_DOMAINS):
        return True
    try:
        req = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": "Mozilla/5.0 (compatible; profile-checker/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status < 400
    except urllib.error.HTTPError as exc:
        return exc.code < 400
    except Exception:
        return False


def extract_follower_count(text: str) -> str:
    """Extract follower/connection count from card text if present, else empty string."""
    m = _FOLLOWER_RE.search(text or "")
    return m.group(1).strip() if m else ""


def extract_emails(text: str) -> List[str]:
    return sorted(set(EMAIL_REGEX.findall(text or "")))


def extract_phones(text: str) -> List[str]:
    candidates = [p.strip() for p in PHONE_REGEX.findall(text or "")]
    return sorted({c for c in candidates if len(re.sub(r"\D", "", c)) >= 8})


def _is_social_url(url: str) -> bool:
    try:
        netloc = urlparse(url).netloc.lower().lstrip("www.")
        return any(netloc == d or netloc.endswith("." + d) for d in _SOCIAL_DOMAINS)
    except Exception:
        return False


def extract_website(text: str) -> str:
    """Return the first non-social-media URL found in text."""
    for match in URL_REGEX.finditer(text or ""):
        url = match.group(0)
        if _is_social_url(url):
            continue
        return url if url.startswith("http") else f"https://{url}"
    return ""


def detect_location(text: str) -> Tuple[str, str]:
    lowered = (text or "").lower()
    for key, result in PRIORITY_LOCATIONS.items():
        if key in lowered:
            return result
    return "", ""


def save_debug_html(driver: WebDriver, debug_dir: Path, filename: str, enabled: bool = True) -> None:
    if not enabled:
        return
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / filename).write_text(driver.page_source, encoding="utf-8")


def clean_text(chunks: Iterable[Optional[str]]) -> str:
    values = [c.strip() for c in chunks if c and c.strip()]
    return " ".join(values)
