from __future__ import annotations

import logging
from collections import Counter

from config import load_config
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
from utils.database import finish_run, init_db, start_run, upsert_leads
from utils.dedupe import dedupe_leads
from utils.exporters import export_leads
from utils.logging_setup import setup_logging
from utils.scoring import score_lead

logger = logging.getLogger(__name__)


def enrich_lead(lead: Lead) -> Lead:
    text = f"{lead.name} {lead.bio} {lead.category}"
    if not lead.lead_type:
        lead.lead_type = classify_lead(text)
    if not lead.interest_signals:
        lead.interest_signals = extract_interest_signals(text)
    lead.score = score_lead(lead)
    return lead


def print_summary(leads: list[Lead]) -> None:
    by_platform = Counter(l.source_platform for l in leads)
    print("\n==== Lead generation summary ====")
    print(f"Total leads (deduped): {len(leads)}")
    for platform, count in sorted(by_platform.items()):
        print(f"- {platform}: {count}")

    top = sorted(leads, key=lambda l: l.score, reverse=True)[:10]
    print("\nTop leads:")
    for lead in top:
        print(f"[{lead.score:3}] {lead.source_platform:<10} {lead.name or lead.social_handle} -> {lead.profile_url}")


def main() -> None:
    setup_logging()
    config = load_config()
    init_db(config.sqlite_db_path)
    run_id = start_run(config.sqlite_db_path, notes="Automated scrape from main.py")

    scrapers = [
        InstagramScraper(),
        FacebookScraper(),
        LinkedInScraper(),
        PinterestScraper(),
        RedditScraper(),
        TwitterScraper(),
    ]

    driver = build_driver(config)
    all_leads: list[Lead] = []

    try:
        for scraper in scrapers:
            logger.info("Running scraper: %s", scraper.platform)
            leads = scraper.scrape(driver, config)
            logger.info("%s returned %s rows", scraper.platform, len(leads))
            all_leads.extend(leads)
    except Exception:
        finish_run(config.sqlite_db_path, run_id, "failed", len(all_leads), 0)
        raise
    finally:
        driver.quit()

    enriched = [enrich_lead(lead) for lead in all_leads]
    deduped = dedupe_leads(enriched)

    export_leads(deduped, config.output_dir)
    upsert_leads(config.sqlite_db_path, deduped, run_id=run_id)
    finish_run(config.sqlite_db_path, run_id, "completed", len(all_leads), len(deduped))
    print_summary(deduped)


if __name__ == "__main__":
    main()
