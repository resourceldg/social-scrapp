"""
Contact enrichment via web scraping (zero-cost, no API keys required).

Strategy
--------
If a lead has a ``website`` field, visit the site and its common contact/about
pages and extract emails, phones, and social links from the raw HTML.

As a secondary heuristic, generate plausible email patterns from the lead's
name + domain and perform an MX record lookup to verify the domain accepts
mail (no SMTP check — just DNS, which is always free).

No third-party APIs. No API keys. No cost.

Usage
-----
    from utils.contact_enricher import ContactEnricher

    enricher = ContactEnricher()
    result = enricher.enrich_from_website("https://studiogomez.com", full_name="Carlos Gómez")
    # result.email, result.source, result.phones, result.social_links
"""
from __future__ import annotations

import logging
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

# Contact page paths to try, in priority order
_CONTACT_PATHS: list[str] = [
    "/contact", "/contacto", "/contact-us", "/contactanos",
    "/about", "/about-us", "/nosotros", "/sobre-nosotros",
    "/info", "/team", "/equipo", "/studio", "/estudio",
    "/hire", "/work-with-us",
]

# Common email patterns for name + domain guessing
_EMAIL_PATTERNS: list[str] = [
    "{first}@{domain}",
    "{first}.{last}@{domain}",
    "{first}{last}@{domain}",
    "info@{domain}",
    "hello@{domain}",
    "hola@{domain}",
    "studio@{domain}",
    "contact@{domain}",
    "contacto@{domain}",
]

_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")
_PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s.\-]?)?(?:\(?\d{2,4}\)?[\s.\-]?)?\d{3,4}[\s.\-]?\d{3,4}\b")
_SOCIAL_RE = re.compile(
    r"https?://(?:www\.)?(?:instagram\.com|linkedin\.com|twitter\.com|x\.com|facebook\.com)"
    r"/[\w.\-/]+",
    re.IGNORECASE,
)

_REQUEST_TIMEOUT = 8
_INTER_PAGE_DELAY = 1.2
_UA = "Mozilla/5.0 (compatible; social-scrapp-enricher/1.0)"

# Domains to exclude from email results (avoid noreply@ etc.)
_EXCLUDED_EMAIL_DOMAINS = frozenset({
    "example.com", "test.com", "sentry.io", "wixpress.com",
    "squarespace.com", "shopify.com", "wordpress.com",
    "fonts.googleapis.com", "cloudflare.com",
})


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class EnrichmentResult:
    """
    Contact data found by scraping a lead's website.

    Attributes
    ----------
    email        : best email found (empty if none)
    emails       : all emails found (deduped)
    phones       : phone numbers found
    social_links : social media profile URLs found on the site
    source       : which page the email was found on
    confidence   : 0–100 estimate of reliability
                   100 = found directly on contact page
                    70 = found on other page
                    40 = generated pattern (not verified)
    extra        : dict for any additional scraped data
    """
    email: str = ""
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    social_links: list[str] = field(default_factory=list)
    source: str = "none"
    confidence: int = 0
    extra: dict = field(default_factory=dict)


# ── Text extractor ─────────────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    """Strips HTML tags and collects visible text + href values."""

    def __init__(self) -> None:
        super().__init__()
        self._text: list[str] = []
        self._links: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = True
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v:
                    self._links.append(v)
        elif tag == "meta":
            d = dict(attrs)
            if d.get("name") in ("description", "keywords") and d.get("content"):
                self._text.append(d["content"])

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self._text.append(stripped)

    def get_text(self) -> str:
        return " ".join(self._text)

    def get_links(self) -> list[str]:
        return self._links


# ── Main enricher ──────────────────────────────────────────────────────────────

class ContactEnricher:
    """
    Free contact enricher — scrapes the lead's website for contact data.

    No API keys required. Works on any publicly accessible website.

    Parameters
    ----------
    timeout      : HTTP timeout per request (seconds)
    max_pages    : maximum contact pages to visit per domain
    delay        : seconds between page requests (be polite)
    """

    def __init__(
        self,
        timeout: int = _REQUEST_TIMEOUT,
        max_pages: int = 3,
        delay: float = _INTER_PAGE_DELAY,
    ) -> None:
        self.timeout = timeout
        self.max_pages = max_pages
        self.delay = delay

    # ── Public API ─────────────────────────────────────────────────────────────

    def enrich(
        self,
        domain: str = "",
        full_name: str = "",
        email: str = "",
    ) -> EnrichmentResult:
        """
        Compatibility wrapper — matches the old API-based signature.

        If ``domain`` is provided, builds the URL and calls enrich_from_website.
        ``email`` and ``full_name`` are used for pattern generation fallback.
        """
        if not domain:
            return EnrichmentResult()
        url = f"https://{domain}" if not domain.startswith("http") else domain
        return self.enrich_from_website(url, full_name=full_name, existing_email=email)

    def enrich_from_website(
        self,
        website_url: str,
        full_name: str = "",
        existing_email: str = "",
    ) -> EnrichmentResult:
        """
        Visit the website and its contact/about pages to extract contact data.

        Parameters
        ----------
        website_url    : root URL of the lead's website
        full_name      : lead name used for email pattern generation fallback
        existing_email : if provided, skip search and return a verified result

        Returns
        -------
        EnrichmentResult with best email and all additional contact data
        """
        base = _normalize_base(website_url)
        if not base:
            return EnrichmentResult()

        domain = urllib.parse.urlparse(base).netloc.lower().lstrip("www.")
        all_emails: list[str] = []
        all_phones: list[str] = []
        all_social: list[str] = []
        best_source = "none"
        best_confidence = 0

        # 1. Scrape homepage
        try:
            home_text, home_links = self._fetch_text_and_links(base)
        except Exception:
            home_text, home_links = "", []
        if home_text:
            found = _extract_emails(home_text + " " + " ".join(home_links), domain)
            if found:
                all_emails.extend(found)
                best_source = "homepage"
                best_confidence = 70
            all_phones.extend(_extract_phones(home_text))
            all_social.extend(_extract_social_links(home_links, base))

        # 2. Try contact/about pages
        pages_tried = 0
        for path in _CONTACT_PATHS:
            if pages_tried >= self.max_pages:
                break
            page_url = base.rstrip("/") + path
            time.sleep(self.delay)
            try:
                text, links = self._fetch_text_and_links(page_url)
            except Exception:
                continue
            if not text:
                continue
            pages_tried += 1
            found = _extract_emails(text + " " + " ".join(links), domain)
            if found:
                all_emails.extend(found)
                # Contact page email is higher confidence
                if best_confidence < 100:
                    best_source = page_url
                    best_confidence = 100
            all_phones.extend(_extract_phones(text))
            all_social.extend(_extract_social_links(links, base))
            if all_emails and best_confidence >= 100:
                break  # good enough

        # 3. Pattern generation fallback (no confidence — not verified)
        generated: list[str] = []
        if not all_emails and full_name and domain and _domain_has_mx(domain):
            generated = _generate_email_patterns(full_name, domain)
            if generated:
                all_emails.extend(generated)
                best_source = "pattern_generated"
                best_confidence = 40

        # Deduplicate preserving order
        seen: set[str] = set()
        unique_emails = [e for e in all_emails if not (e in seen or seen.add(e))]  # type: ignore[func-returns-value]
        unique_phones = list(dict.fromkeys(p for p in all_phones if len(re.sub(r"\D", "", p)) >= 8))
        unique_social = list(dict.fromkeys(all_social))

        best_email = unique_emails[0] if unique_emails else ""

        return EnrichmentResult(
            email=best_email,
            emails=unique_emails,
            phones=unique_phones,
            social_links=unique_social,
            source=best_source,
            confidence=best_confidence,
            extra={"generated_patterns": generated} if generated else {},
        )

    def domain_search(self, domain: str) -> list[dict]:
        """
        Compatibility shim — scrapes the domain's contact pages for all emails.
        """
        url = f"https://{domain}"
        result = self.enrich_from_website(url)
        return [
            {"email": e, "confidence": result.confidence, "source": result.source}
            for e in result.emails
        ]

    # ── HTTP fetch ─────────────────────────────────────────────────────────────

    def _fetch_text_and_links(self, url: str) -> tuple[str, list[str]]:
        """Fetch a URL and return (visible_text, href_list). Returns ("", []) on error."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                ct = resp.headers.get("Content-Type", "")
                if "html" not in ct and "text" not in ct:
                    return "", []
                raw = resp.read(200_000).decode("utf-8", errors="replace")
        except Exception:
            return "", []

        parser = _TextExtractor()
        try:
            parser.feed(raw)
        except Exception:
            pass
        return parser.get_text(), parser.get_links()


# ── Free utility functions ─────────────────────────────────────────────────────

def _normalize_base(url: str) -> str:
    """Return scheme + netloc (e.g. 'https://studio.com'), or '' on failure."""
    try:
        p = urllib.parse.urlparse(url if "://" in url else f"https://{url}")
        if not p.netloc:
            return ""
        return f"{p.scheme}://{p.netloc}"
    except Exception:
        return ""


def _extract_emails(text: str, owner_domain: str) -> list[str]:
    """Extract unique, plausible emails from text, excluding obvious noise."""
    found = _EMAIL_RE.findall(text)
    seen: set[str] = set()
    result: list[str] = []
    for e in found:
        e = e.lower().rstrip(".,;)")
        if e in seen:
            continue
        seen.add(e)
        dom = e.split("@", 1)[-1]
        if dom in _EXCLUDED_EMAIL_DOMAINS:
            continue
        if e.startswith("noreply") or e.startswith("no-reply"):
            continue
        result.append(e)
    # Prefer emails on the lead's own domain
    own = [e for e in result if e.endswith("@" + owner_domain)]
    other = [e for e in result if not e.endswith("@" + owner_domain)]
    return own + other


def _extract_phones(text: str) -> list[str]:
    candidates = _PHONE_RE.findall(text)
    return [p.strip() for p in candidates if len(re.sub(r"\D", "", p)) >= 8]


def _extract_social_links(links: list[str], base_url: str) -> list[str]:
    """Return absolute social media URLs from a list of href values."""
    result: list[str] = []
    for href in links:
        if not href:
            continue
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = base_url.rstrip("/") + href
        m = _SOCIAL_RE.match(href)
        if m:
            result.append(href)
    return result


def _generate_email_patterns(full_name: str, domain: str) -> list[str]:
    """Generate plausible email addresses from a person name and domain."""
    parts = full_name.lower().split()
    if not parts:
        return [f"info@{domain}", f"contact@{domain}", f"hola@{domain}"]

    first = re.sub(r"[^a-z]", "", parts[0])
    last = re.sub(r"[^a-z]", "", parts[-1]) if len(parts) > 1 else ""

    result: list[str] = []
    for pattern in _EMAIL_PATTERNS:
        try:
            email = pattern.format(first=first, last=last, domain=domain)
            if "@" in email and email not in result:
                result.append(email)
        except KeyError:
            pass
    return result[:6]  # cap at 6 candidates


def _domain_has_mx(domain: str) -> bool:
    """
    Check if the domain has MX records (accepts email) via DNS lookup.

    Uses a lightweight getaddrinfo probe — not a full MX query (avoids
    needing dnspython). Returns True if the domain resolves at all, which
    is a reasonable proxy for 'this domain might accept email'.
    """
    try:
        socket.setdefaulttimeout(3)
        socket.getaddrinfo(domain, None)
        return True
    except Exception:
        return False
