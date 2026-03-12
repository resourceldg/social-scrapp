from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from pathlib import Path

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

SCRAPER_MAP = {
    "instagram": InstagramScraper,
    "facebook": FacebookScraper,
    "linkedin": LinkedInScraper,
    "pinterest": PinterestScraper,
    "reddit": RedditScraper,
    "twitter": TwitterScraper,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-platform lead scraping pipeline")
    parser.add_argument(
        "--platforms",
        default=",".join(SCRAPER_MAP.keys()),
        help="Comma-separated platform list: instagram,facebook,linkedin,pinterest,reddit,twitter",
    )
    parser.add_argument(
        "--credentials-file",
        default="",
        help="Optional JSON file with per-platform credentials from dashboard forms.",
    )
    return parser.parse_args()


def _load_credentials(credentials_file: str) -> dict:
    if not credentials_file:
        return {}
    path = Path(credentials_file)
    if not path.exists():
        logger.warning("Credentials file not found: %s", credentials_file)
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Credentials file is not valid JSON: %s", credentials_file)
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


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
    args = parse_args()
    config = load_config()
    init_db(config.sqlite_db_path)

    selected_platforms = [p.strip().lower() for p in args.platforms.split(",") if p.strip()]
    valid_platforms = [p for p in selected_platforms if p in SCRAPER_MAP]
    if not valid_platforms:
        raise ValueError("No valid platforms selected. Use: instagram,facebook,linkedin,pinterest,reddit,twitter")

    credentials = _load_credentials(args.credentials_file)
    credential_platforms = [p for p, data in credentials.items() if isinstance(data, dict) and data.get("username")]
    run_note = f"platforms={','.join(valid_platforms)}; credential_usernames_for={','.join(credential_platforms)}"

    run_id = start_run(config.sqlite_db_path, notes=run_note)
    scrapers = [SCRAPER_MAP[name]() for name in valid_platforms]

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
