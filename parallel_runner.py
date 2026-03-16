"""
Parallel scraper runner.

Runs multiple platform scrapers concurrently, each in its own OS process
with a dedicated Chrome WebDriver instance.

Why processes and not threads?
  Selenium WebDriver is not thread-safe.  Each process has its own Chrome
  instance, independent GIL, and separate memory space — no shared state.

Architecture
------------
  main process         →  spawns N worker processes via ProcessPoolExecutor
  worker (platform X)  →  builds its own driver, scrapes, returns lead dicts
  main process         →  collects results, reconstructs Lead objects, dedupes,
                          persists to DB (single-writer, no contention)

Usage
-----
Run directly to scrape all enabled platforms in parallel:

    python parallel_runner.py

Or from main.py alternative:

    from parallel_runner import parallel_scrape
    leads = parallel_scrape(config)

Anti-ban notes
--------------
- Each platform gets its own Chrome profile clone, so cookies are isolated.
- The cooldown filter (rescrape_cooldown_days) still applies.
- Circuit breakers and route evaluator share a SQLite DB so failures in one
  worker can signal caution in others (via RouteEvaluator.record_failure).
- Recommended max_workers = 2–3 to avoid triggering IP-level rate limits.
  Increase only on dedicated IPs with residential proxies.
"""
from __future__ import annotations

import dataclasses
import logging
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any

from config import AppConfig, load_config
from models import Lead
from scrapers import (
    FacebookScraper,
    InstagramScraper,
    LinkedInScraper,
    PinterestScraper,
    RedditScraper,
    TwitterScraper,
)
from utils.browser import build_driver
from utils.classifiers import classify_lead, extract_interest_signals
from utils.database import (
    finish_run,
    get_recent_profile_urls,
    init_db,
    start_run,
    touch_seen_profiles,
    upsert_leads,
)
from utils.dedupe import dedupe_leads
from utils.exporters import export_leads
from utils.logging_setup import setup_logging
from utils.scoring import score_lead

logger = logging.getLogger(__name__)

# ── Scraper factory ────────────────────────────────────────────────────────────

_SCRAPER_CLASSES = {
    "instagram": InstagramScraper,
    "facebook":  FacebookScraper,
    "linkedin":  LinkedInScraper,
    "pinterest": PinterestScraper,
    "reddit":    RedditScraper,
    "twitter":   TwitterScraper,
}


# ── Worker function (runs in child process) ────────────────────────────────────

def _scrape_platform(platform: str, config_dict: dict) -> list[dict]:
    """
    Top-level function executed in a child process.

    Accepts a plain dict (serialisable) rather than AppConfig directly,
    then reconstructs the config inside the child so dataclass slots work
    correctly across the pickle boundary.

    Returns a list of lead dicts (Lead.to_dict()) — plain dicts survive
    process boundaries reliably.
    """
    import shutil

    setup_logging()
    log = logging.getLogger(__name__)

    # Reconstruct config from dict
    cfg = AppConfig(**{
        k: v for k, v in config_dict.items()
        if k in AppConfig.__dataclass_fields__
    })

    scraper_cls = _SCRAPER_CLASSES.get(platform)
    if scraper_cls is None:
        log.error("Unknown platform: %s", platform)
        return []

    driver, chrome_tmp = build_driver(cfg)
    try:
        scraper = scraper_cls()
        raw_leads: list[Lead] = scraper.scrape(driver, cfg)
        log.info("[%s] returned %d raw leads", platform, len(raw_leads))
    except Exception as exc:
        log.exception("[%s] scraping failed: %s", platform, exc)
        raw_leads = []
    finally:
        driver.quit()
        if chrome_tmp:
            shutil.rmtree(chrome_tmp, ignore_errors=True)

    return [dataclasses.asdict(lead) for lead in raw_leads]


# ── Public API ─────────────────────────────────────────────────────────────────

def parallel_scrape(
    config: AppConfig,
    max_workers: int = 2,
) -> list[Lead]:
    """
    Scrape all enabled platforms concurrently.

    Parameters
    ----------
    config      : AppConfig instance
    max_workers : maximum parallel Chrome processes (recommended 2–3)

    Returns
    -------
    list[Lead] — raw leads from all platforms (not yet deduped)
    """
    enabled = [
        p for p in _SCRAPER_CLASSES
        if getattr(config, f"{p}_enabled", True)
    ]
    if not enabled:
        logger.warning("No platforms enabled — nothing to scrape")
        return []

    # Convert config to plain dict for cross-process serialisation
    config_dict: dict[str, Any] = {
        f: getattr(config, f) for f in config.__dataclass_fields__
    }
    # Paths must be strings for pickle
    for k in ("output_dir", "debug_html_dir", "sqlite_db_path"):
        config_dict[k] = str(config_dict[k])

    all_leads: list[Lead] = []

    logger.info(
        "Parallel scrape: %d platforms × max %d workers",
        len(enabled),
        max_workers,
    )

    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_scrape_platform, platform, config_dict): platform
            for platform in enabled
        }
        for future in as_completed(futures):
            platform = futures[future]
            try:
                lead_dicts = future.result()
                for d in lead_dicts:
                    # Reconstruct Lead from dict, handling Path fields
                    try:
                        lead = Lead(**{
                            k: v for k, v in d.items()
                            if k in Lead.__dataclass_fields__
                        })
                        all_leads.append(lead)
                    except Exception as e:
                        logger.debug("Lead reconstruction failed: %s", e)
                logger.info("[%s] collected %d leads", platform, len(lead_dicts))
            except Exception as exc:
                logger.exception("[%s] worker failed: %s", platform, exc)

    return all_leads


# ── CLI entry point ────────────────────────────────────────────────────────────

def _enrich_lead(lead: Lead) -> Lead:
    text = f"{lead.name} {lead.bio} {lead.category}"
    if not lead.lead_type:
        lead.lead_type = classify_lead(text)
    if not lead.interest_signals:
        lead.interest_signals = extract_interest_signals(text)
    lead.score = score_lead(lead)
    return lead


def main() -> None:
    setup_logging()
    config = load_config()
    init_db(config.sqlite_db_path)
    run_id = start_run(config.sqlite_db_path, notes="Parallel scrape from parallel_runner.py")

    t0 = time.perf_counter()
    raw_leads = parallel_scrape(config, max_workers=2)
    elapsed = time.perf_counter() - t0
    logger.info("Parallel scrape done in %.1fs — %d raw leads", elapsed, len(raw_leads))

    # ── Cooldown filter (same logic as main.py) ───────────────────────────────
    all_fresh: list[Lead] = []
    seen_again: list[str] = []
    for lead in raw_leads:
        recent = get_recent_profile_urls(
            config.sqlite_db_path, lead.source_platform, config.rescrape_cooldown_days
        )
        norm = (lead.profile_url or "").rstrip("/").lower()
        if norm and norm in recent:
            seen_again.append(lead.profile_url)
        else:
            all_fresh.append(lead)

    if seen_again:
        touch_seen_profiles(config.sqlite_db_path, seen_again)

    enriched = [_enrich_lead(lead) for lead in all_fresh]
    deduped = dedupe_leads(enriched)

    export_leads(deduped, config.output_dir)
    upsert_leads(config.sqlite_db_path, deduped, run_id=run_id)
    finish_run(
        config.sqlite_db_path, run_id, "completed",
        len(raw_leads), len(deduped),
    )

    logger.info(
        "Parallel pipeline done: %d raw → %d deduped (%.1fs total)",
        len(raw_leads), len(deduped), elapsed,
    )


if __name__ == "__main__":
    main()
