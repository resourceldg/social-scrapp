"""
Profile enricher — visits individual profile pages to extract richer data.

For each lead above min_score that hasn't been enriched yet, opens the profile
URL in the already-running Selenium driver and extracts:
  - followers count  (from og:description / JSON API)
  - full bio text
  - email, phone, website
  - full name

After extraction the lead is re-classified and re-scored.

Reddit subreddits/users are enriched via the public JSON API (no browser needed),
which is much faster and bandwidth-friendly.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import re
import threading
import time
import urllib.request
from typing import Callable

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import AppConfig
from models import Lead
from utils.classifiers import classify_lead, extract_interest_signals
from utils.contact_enricher import ContactEnricher
from utils.helpers import check_url_reachable, detect_location, extract_emails, extract_follower_count, extract_phones, extract_website
from utils.llm_classifier import classify_bio, is_ollama_available
from utils.scoring import score_lead_full, score_lead_with_profile

logger = logging.getLogger(__name__)

# Reddit JSON API user-agent (required by reddit API TOS)
_REDDIT_UA = "social-scrapp/1.0 (profile enricher; contact@scrapp.local)"


def _soup_meta(soup: BeautifulSoup, **attrs) -> str:
    tag = soup.find("meta", attrs=attrs)
    if tag:
        return str(tag.get("content") or tag.get("property") or "").strip()
    return ""


_ollama_checked: bool | None = None  # None = not yet checked
_ollama_lock = threading.Lock()

# Patterns that indicate a useless/synthetic bio (og:description boilerplate,
# LinkedIn mutual-connection snippets, etc.). Strip before classifying.
_JUNK_BIO_PATTERNS = re.compile(
    r"^See Instagram photos and videos from\b"
    r"|^See posts, photos and more on Facebook"
    r"|\band \d+ other mutual connection"
    r"|\bmutual connection",
    re.IGNORECASE,
)


def _clean_bio_for_classification(bio: str) -> str:
    """Return empty string if bio is boilerplate noise; otherwise return bio unchanged."""
    if not bio:
        return bio
    if _JUNK_BIO_PATTERNS.search(bio):
        return ""
    return bio


def _re_enrich(lead: Lead) -> Lead:
    """Re-classify and re-score after bio/followers are updated."""
    clean_bio = _clean_bio_for_classification(lead.bio or "")
    text = f"{lead.name} {clean_bio} {lead.category}"
    lead_type = lead.lead_type or classify_lead(text)
    signals = lead.interest_signals or extract_interest_signals(text)
    updated = dataclasses.replace(lead, lead_type=lead_type, interest_signals=signals)

    # LLM classification: run if Ollama is available and bio is meaningful
    with _ollama_lock:
        if _ollama_checked is None:
            _ollama_checked = is_ollama_available()
            if _ollama_checked:
                logger.info("Ollama available — LLM bio classification enabled.")
            else:
                logger.info("Ollama not available — using rule-based classification only.")
        ollama_active = _ollama_checked

    if ollama_active and clean_bio and len(clean_bio.strip()) >= 20:
        llm = classify_bio(clean_bio, existing_lead_type=updated.lead_type)
        if llm["source"] == "llm":
            logger.debug(
                "LLM classified %s: type=%s intent=%d reason=%s",
                updated.social_handle, llm["lead_type"], llm["buying_intent"], llm["reason"],
            )
            updated = dataclasses.replace(
                updated,
                lead_type=llm["lead_type"],
            )
            # Store buying_intent in engagement_hint for visibility in dashboard
            if llm["buying_intent"] > 0:
                hint = f"intent:{llm['buying_intent']}/10 — {llm['reason']}"
                updated = dataclasses.replace(updated, engagement_hint=hint)

    new_score, new_profile, result = score_lead_full(updated)
    bi = {
        "opportunity_score": result.opportunity_score,
        "buying_power_score": round(result.buying_power_score, 1),
        "specifier_score": round(result.specifier_score, 1),
        "project_signal_score": round(result.project_signal_score, 1),
        "opportunity_classification": result.opportunity_classification,
    }
    raw_data = {**(updated.raw_data or {}), **bi}
    return dataclasses.replace(updated, score=new_score, lead_profile=new_profile, raw_data=raw_data)


class ProfileEnricher:
    """
    Visit individual profile pages and extract richer lead data.

    Parameters
    ----------
    min_score : int
        Only enrich leads with score >= min_score.
    max_leads : int
        Cap total profile visits per session (anti-ban).
    inter_delay : float
        Seconds to wait between profile page loads.
    """

    def __init__(
        self,
        min_score: int = 5,
        max_leads: int = 30,
        inter_delay: float = 3.0,
    ) -> None:
        self.min_score = min_score
        self.max_leads = max_leads
        self.inter_delay = inter_delay
        self._contact_enricher = ContactEnricher()  # uses env vars if configured

    def enrich_batch(
        self,
        driver: WebDriver,
        leads: list[Lead],
        config: AppConfig,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[Lead]:
        """
        Enrich a list of leads in-place.

        Filters to leads with score >= min_score, caps at max_leads, visits
        each profile, and returns the enriched Lead objects.

        Parameters
        ----------
        on_progress : optional callback(current, total, handle)
        """
        candidates = [l for l in leads if l.score >= self.min_score][: self.max_leads]
        total = len(candidates)
        enriched: list[Lead] = []

        for i, lead in enumerate(candidates):
            if on_progress:
                on_progress(i + 1, total, lead.social_handle or lead.profile_url)
            if i > 0:
                time.sleep(self.inter_delay)
            try:
                result = self._enrich_one(driver, lead, config)
                enriched.append(result)
                logger.info(
                    "Enriched [%s/%d] %s/%s  followers=%s score=%d→%d",
                    i + 1, total,
                    lead.source_platform, lead.social_handle,
                    result.followers or "?",
                    lead.score, result.score,
                )
            except Exception as exc:
                logger.warning(
                    "Enrichment failed for %s (%s): %s",
                    lead.profile_url, lead.source_platform, exc,
                )
                enriched.append(lead)

        return enriched

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def _enrich_one(self, driver: WebDriver, lead: Lead, config: AppConfig) -> Lead:
        # R15: quick HTTP check before wasting a full Selenium page load
        if lead.profile_url and not check_url_reachable(lead.profile_url):
            logger.warning(
                "Profile URL appears unreachable, skipping enrichment: %s", lead.profile_url
            )
            return lead

        platform = lead.source_platform
        if platform == "instagram":
            enriched = _re_enrich(self._enrich_instagram(driver, lead, config))
        elif platform == "pinterest":
            enriched = _re_enrich(self._enrich_pinterest(driver, lead, config))
        elif platform == "reddit":
            enriched = _re_enrich(self._enrich_reddit(lead))
        elif platform == "twitter":
            enriched = _re_enrich(self._enrich_twitter(driver, lead, config))
        elif platform == "linkedin":
            enriched = _re_enrich(self._enrich_linkedin(driver, lead, config))
        elif platform == "behance":
            enriched = _re_enrich(self._enrich_behance(driver, lead, config))
        else:
            return lead

        # API contact enrichment: if we have a website domain but no email, try Hunter.io
        if enriched.website and not enriched.email:
            enriched = self._api_enrich_contact(enriched)

        return enriched

    def _api_enrich_contact(self, lead: Lead) -> Lead:
        """Try Hunter.io to find email from website domain + name."""
        from urllib.parse import urlparse as _up
        try:
            domain = _up(lead.website).netloc.lower().lstrip("www.")
        except Exception:
            return lead
        if not domain:
            return lead

        result = self._contact_enricher.enrich(domain=domain, full_name=lead.name)
        if not result.email:
            return lead

        logger.info(
            "API enrichment: found email %s (confidence=%d, source=%s) for %s",
            result.email, result.confidence, result.source, lead.social_handle or lead.name,
        )
        return dataclasses.replace(lead, email=result.email)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _load_and_soup(
        self, driver: WebDriver, url: str, timeout: int, wait_extra: float = 1.5
    ) -> BeautifulSoup:
        driver.get(url)
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(wait_extra)
        return BeautifulSoup(driver.page_source, "html.parser")

    def _extract_contact(self, text: str, lead: Lead) -> dict:
        emails = extract_emails(text)
        phones = extract_phones(text)
        website = extract_website(text)
        city, country = detect_location(text)
        return {
            "email": emails[0] if emails else lead.email,
            "phone": phones[0] if phones else lead.phone,
            "website": website or lead.website,
            "city": city or lead.city,
            "country": country or lead.country,
        }

    # ── Instagram ─────────────────────────────────────────────────────────────

    def _enrich_instagram(self, driver: WebDriver, lead: Lead, config: AppConfig) -> Lead:
        soup = self._load_and_soup(driver, lead.profile_url, config.page_load_timeout)

        # og:description: legacy "2.5M Followers, 300 Following, 1200 Posts - bio…"
        og_desc = _soup_meta(soup, property="og:description")
        og_title = _soup_meta(soup, property="og:title")

        followers = extract_follower_count(og_desc)

        # Name: "Studio Name (@handle) • Instagram photos and videos"
        name = lead.name
        m = re.match(r"^(.+?)\s*\(@", og_title)
        if m:
            name = m.group(1).strip()

        # Bio — Strategy 1: legacy og:description "Z Posts - bio text"
        bio = lead.bio
        m2 = re.search(r"\d+\s+Posts?\s*[-–]\s*(.+)", og_desc)
        if m2:
            bio = m2.group(1).strip()

        # Bio — Strategy 2: "biography" field in JSON embedded by Instagram in <script> tags.
        # Instagram no longer includes bio in og:description; it embeds it as JSON in the page.
        if not bio or _JUNK_BIO_PATTERNS.search(bio or ""):
            src = driver.page_source
            for bio_pat in (
                r'"biography"\s*:\s*"((?:[^"\\]|\\.){5,500})"',
                r'"bio"\s*:\s*"((?:[^"\\]|\\.){5,500})"',
            ):
                m3 = re.search(bio_pat, src)
                if m3:
                    candidate = m3.group(1).replace("\\n", " ").replace('\\"', '"').strip()
                    if candidate and not _JUNK_BIO_PATTERNS.search(candidate):
                        bio = candidate
                        break

            # Also try follower count from JSON if og:description didn't have it
            if not followers:
                for fol_pat in (
                    r'"edge_followed_by"\s*:\s*\{"count"\s*:\s*(\d+)',
                    r'"follower_count"\s*:\s*(\d+)',
                    r'"followed_by_count"\s*:\s*(\d+)',
                ):
                    mf = re.search(fol_pat, src)
                    if mf:
                        count = int(mf.group(1))
                        followers = f"{count:,}" if count < 10_000 else f"{count / 1_000:.1f}K"
                        break

        full_text = f"{og_desc} {og_title} {bio}"
        contact = self._extract_contact(full_text, lead)

        return dataclasses.replace(
            lead,
            name=name,
            followers=followers or lead.followers,
            bio=bio[:500] if bio else lead.bio,
            **contact,
        )

    # ── Pinterest ─────────────────────────────────────────────────────────────

    def _enrich_pinterest(self, driver: WebDriver, lead: Lead, config: AppConfig) -> Lead:
        soup = self._load_and_soup(driver, lead.profile_url, config.page_load_timeout)

        og_desc = _soup_meta(soup, property="og:description")
        meta_desc = _soup_meta(soup, name="description")
        og_title = _soup_meta(soup, property="og:title")

        rich_text = og_desc or meta_desc or lead.bio
        followers = extract_follower_count(rich_text)

        # Pinterest og:title format: "Name (username) | Pinterest"
        name = lead.name
        m = re.match(r"^(.+?)\s*\(", og_title)
        if m:
            name = m.group(1).strip()

        full_text = f"{og_desc} {meta_desc} {og_title}"
        contact = self._extract_contact(full_text, lead)

        return dataclasses.replace(
            lead,
            name=name,
            followers=followers or lead.followers,
            bio=rich_text[:500] if rich_text else lead.bio,
            **contact,
        )

    # ── Reddit (JSON API — no browser request needed) ─────────────────────────

    def _enrich_reddit(self, lead: Lead) -> Lead:
        profile_url = lead.profile_url.rstrip("/")
        is_subreddit = "/r/" in profile_url

        if is_subreddit:
            name_part = profile_url.split("/r/")[-1].split("/")[0]
            api_url = f"https://www.reddit.com/r/{name_part}/about.json"
        else:
            name_part = lead.social_handle
            api_url = f"https://www.reddit.com/user/{name_part}/about.json"

        req = urllib.request.Request(
            api_url, headers={"User-Agent": _REDDIT_UA}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
        except Exception as exc:
            logger.debug("Reddit API failed for %s: %s", api_url, exc)
            return lead

        info = data.get("data", {})

        if is_subreddit:
            subscribers = str(info.get("subscribers", ""))
            bio = (info.get("public_description") or info.get("description") or "").strip()[:500]
            name = info.get("title") or lead.name
            followers = subscribers
        else:
            karma = info.get("total_karma") or info.get("link_karma", 0)
            followers = f"{karma} karma"
            bio = info.get("subreddit", {}).get("public_description", "").strip()[:500]
            name = info.get("name") or lead.name

        contact = self._extract_contact(bio, lead)
        return dataclasses.replace(
            lead,
            name=name or lead.name,
            followers=followers or lead.followers,
            bio=bio or lead.bio,
            **contact,
        )

    # ── Twitter/X ─────────────────────────────────────────────────────────────

    def _enrich_twitter(self, driver: WebDriver, lead: Lead, config: AppConfig) -> Lead:
        soup = self._load_and_soup(driver, lead.profile_url, config.page_load_timeout, wait_extra=2.0)

        og_desc = _soup_meta(soup, property="og:description")
        og_title = _soup_meta(soup, property="og:title")

        followers = extract_follower_count(og_desc)
        bio = og_desc.strip()

        # og:title: "Name (@handle) / X"
        name = lead.name
        m = re.match(r"^(.+?)\s*\(@", og_title)
        if m:
            name = m.group(1).strip()

        contact = self._extract_contact(f"{og_desc} {og_title}", lead)
        return dataclasses.replace(
            lead,
            name=name or lead.name,
            followers=followers or lead.followers,
            bio=bio[:500] if bio else lead.bio,
            **contact,
        )

    # ── Behance ───────────────────────────────────────────────────────────────

    def _enrich_behance(self, driver: WebDriver, lead: Lead, config: AppConfig) -> Lead:
        soup = self._load_and_soup(driver, lead.profile_url, config.page_load_timeout, wait_extra=2.0)

        og_desc = _soup_meta(soup, property="og:description")
        og_title = _soup_meta(soup, property="og:title")
        page_text = soup.get_text(" ", strip=True)

        # Name: og:title → "First Last | Behance" or "Studio Name on Behance"
        name = lead.name
        m = re.match(r"^(.+?)\s*[|–-]", og_title)
        if m:
            name = m.group(1).strip()

        # Followers: Behance embeds profile stats in SSR JSON inside <script> tags.
        # Try multiple patterns in order of reliability.
        followers = ""

        # Pattern 1: JSON in page source — "followers":12345 or "followerCount":12345
        src = driver.page_source
        for pat in (
            r'"followers"\s*:\s*(\d+)',
            r'"followerCount"\s*:\s*(\d+)',
            r'"followersCount"\s*:\s*(\d+)',
        ):
            m2 = re.search(pat, src)
            if m2:
                count = int(m2.group(1))
                followers = f"{count:,}" if count < 10_000 else f"{count / 1000:.1f}K"
                break

        # Pattern 2: visible text "X Followers" on the page
        if not followers:
            followers = extract_follower_count(page_text) or extract_follower_count(og_desc)

        # Bio: Behance og:description is generic ("X is on Behance! …"), prefer
        # the occupation/specialty visible in the page under the name.
        bio = lead.bio
        # Try to find a meaningful bio from the "Pro" badge area or occupation line
        # Behance renders the bio in a <p> near the profile header
        for tag in soup.select("p, [class*='bio'], [class*='occupation'], [class*='UserInfo']"):
            text = tag.get_text(" ", strip=True)
            if text and len(text) > 20 and len(text) < 600:
                # Skip generic Behance boilerplate
                if "is on Behance" not in text and "check out" not in text.lower():
                    bio = text
                    break

        # Fallback bio from og:description (it's short but better than nothing)
        if not bio and og_desc and "is on Behance" not in og_desc:
            bio = og_desc

        full_text = f"{og_desc} {og_title} {page_text[:3000]}"
        contact = self._extract_contact(full_text, lead)

        return dataclasses.replace(
            lead,
            name=name or lead.name,
            followers=followers or lead.followers,
            bio=bio[:500] if bio else lead.bio,
            **contact,
        )

    # ── LinkedIn ──────────────────────────────────────────────────────────────

    def _enrich_linkedin(self, driver: WebDriver, lead: Lead, config: AppConfig) -> Lead:
        # LinkedIn is heavily protected; only use og tags — do not wait for dynamic content
        soup = self._load_and_soup(driver, lead.profile_url, config.page_load_timeout, wait_extra=0.5)

        og_desc = _soup_meta(soup, property="og:description")
        og_title = _soup_meta(soup, property="og:title")

        bio = og_desc.strip() or lead.bio

        name = lead.name
        # og:title often: "Company Name | LinkedIn" or "Full Name - Title | LinkedIn"
        m = re.match(r"^(.+?)\s*[|–-]", og_title)
        if m:
            name = m.group(1).strip()

        contact = self._extract_contact(f"{og_desc} {og_title}", lead)
        return dataclasses.replace(
            lead,
            name=name or lead.name,
            bio=bio[:500] if bio else lead.bio,
            **contact,
        )
