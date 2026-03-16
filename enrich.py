"""
Profile enrichment entry point.

Loads unenriched leads from the DB, opens Chrome with the configured session,
visits each profile page, and saves the enriched data back.

Usage:
    python enrich.py                          # default: score>=20, max 30 leads
    python enrich.py --min-score 15 --max 50
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict

from config import load_config
from models import Lead
from utils.browser import build_driver
from utils.database import (
    get_unenriched_leads,
    init_db,
    mark_leads_enriched,
    update_enriched_lead,
)
from utils.logging_setup import setup_logging
from utils.profile_enricher import ProfileEnricher


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich lead profiles")
    parser.add_argument("--min-score", type=int, default=3, help="Minimum score to enrich")
    parser.add_argument("--max", type=int, default=50, help="Max profiles to visit")
    parser.add_argument("--delay", type=float, default=3.0, help="Seconds between profile loads")
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger(__name__)

    config = load_config()
    init_db(config.sqlite_db_path)

    rows = get_unenriched_leads(config.sqlite_db_path, min_score=args.min_score, limit=args.max)
    if not rows:
        logger.info("No unenriched leads found (score >= %d). Nothing to do.", args.min_score)
        return

    logger.info("Enriching %d leads (score >= %d)…", len(rows), args.min_score)

    leads = [
        Lead(
            source_platform=r["source_platform"],
            search_term=r.get("search_term") or "",
            name=r.get("name") or "",
            social_handle=r.get("social_handle") or "",
            profile_url=r.get("profile_url") or "",
            email=r.get("email") or "",
            phone=r.get("phone") or "",
            website=r.get("website") or "",
            city=r.get("city") or "",
            country=r.get("country") or "",
            bio=r.get("bio") or "",
            category=r.get("category") or "",
            lead_type=r.get("lead_type") or "",
            interest_signals=(
                json.loads(r["interest_signals"])
                if r.get("interest_signals") and r["interest_signals"] not in ("[]", "")
                else []
            ),
            followers=r.get("followers") or "",
            engagement_hint=r.get("engagement_hint") or "",
            score=r.get("score") or 0,
        )
        for r in rows
    ]

    enricher = ProfileEnricher(
        min_score=args.min_score,
        max_leads=args.max,
        inter_delay=args.delay,
    )

    driver, tmp_dir = build_driver(config)
    enriched_urls: list[str] = []

    try:
        def on_progress(current: int, total: int, handle: str) -> None:
            logger.info("[%d/%d] Enriching: %s", current, total, handle)

        enriched_leads = enricher.enrich_batch(driver, leads, config, on_progress=on_progress)

        for lead in enriched_leads:
            if lead.profile_url:
                update_enriched_lead(config.sqlite_db_path, lead)
                enriched_urls.append(lead.profile_url)

        mark_leads_enriched(config.sqlite_db_path, enriched_urls)
        logger.info("Enrichment complete — %d leads updated.", len(enriched_urls))

    except Exception:
        logger.exception("Enrichment run failed")
        sys.exit(1)
    finally:
        driver.quit()
        if tmp_dir:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
