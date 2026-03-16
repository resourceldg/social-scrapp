"""
Entry point for the social lead scraper.

Pipeline:
  1. Network probe → classify connection speed
  2. Build adaptive scheduler plan (platforms + resource limits)
  3. Per-platform loop:
       a. Check circuit breaker
       b. Keyword cap + cooldown filter
       c. Scrape with retry & timing
       d. Update circuit breaker and route evaluator
       e. Collect fresh leads
  4. Enrich → deduplicate → export → persist
  5. Save metrics + route stability report
"""
from __future__ import annotations

import logging
import re
import time
from collections import Counter

from config import load_config
from core.circuit_breaker import CircuitBreaker
from core.metrics import MetricsCollector
from core.network_profiler import NetworkProfiler
from core.route_evaluator import RouteEvaluator
from core.scheduler import AdaptiveScheduler
from models import Lead
from scrapers import (
    BehanceScraper,
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
    get_keyword_candidates,
    get_keyword_stats_df,
    get_recent_profile_urls,
    init_db,
    log_keyword_run,
    propose_keyword_candidates,
    recalculate_keyword_stats,
    save_run_histogram,
    start_run,
    touch_seen_profiles,
    update_keyword_stats,
    upsert_leads,
)
from utils.dedupe import dedupe_leads
from utils.exporters import export_leads
from utils.helpers import scrape_with_retry
from utils.keyword_ranker import rank_keywords, summarise_keyword_performance
from utils.logging_setup import setup_logging
from utils.scoring import score_lead_with_profile

logger = logging.getLogger(__name__)

_PLATFORMS = ["instagram", "facebook", "linkedin", "pinterest", "reddit", "twitter", "behance"]


# ── Lead enrichment ───────────────────────────────────────────────────────────


_JUNK_BIO_RE = re.compile(
    r"^See Instagram photos and videos from\b"
    r"|^See posts, photos and more on Facebook"
    r"|\band \d+ other mutual connection"
    r"|\bmutual connection",
    re.IGNORECASE,
)


def enrich_lead(lead: Lead) -> Lead:
    bio = lead.bio or ""
    if _JUNK_BIO_RE.search(bio):
        bio = ""
    text = f"{lead.name} {bio} {lead.category}"
    if not lead.lead_type:
        lead.lead_type = classify_lead(text)
    if not lead.interest_signals:
        lead.interest_signals = extract_interest_signals(text)
    lead.score, lead.lead_profile = score_lead_with_profile(lead)
    return lead


# ── Summary logging ───────────────────────────────────────────────────────────


def print_summary(leads: list[Lead]) -> None:
    by_platform = Counter(l.source_platform for l in leads)
    logger.info("==== Lead generation summary ====")
    logger.info("Total leads (deduped): %d", len(leads))
    for platform, count in sorted(by_platform.items()):
        logger.info("  - %s: %d", platform, count)

    top = sorted(leads, key=lambda l: l.score, reverse=True)[:10]
    logger.info("Top leads by score:")
    for lead in top:
        logger.info(
            "  [%3d] %-10s %s → %s",
            lead.score,
            lead.source_platform,
            lead.name or lead.social_handle,
            lead.profile_url,
        )


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    setup_logging()
    config = load_config()
    init_db(config.sqlite_db_path)
    run_id = start_run(config.sqlite_db_path, notes="Automated scrape from main.py")

    # Sync keyword quality metrics from current (post-enrichment) lead scores
    # before UCB ranking runs, so the ranker sees accurate post-enrichment quality.
    _n_updated = recalculate_keyword_stats(config.sqlite_db_path)
    if _n_updated:
        logger.info("keyword_stats: refreshed %d rows from enriched lead scores", _n_updated)

    # ── Phase 1: network profiling ────────────────────────────────────────────
    profiler = NetworkProfiler()
    initial_speed = profiler.probe_initial_speed()
    logger.info("Network speed: %s", initial_speed.value)

    # ── Phase 2: per-platform infrastructure ─────────────────────────────────
    route_eval = RouteEvaluator(config.sqlite_db_path.parent / "route_stats.db")
    metrics = MetricsCollector(config.output_dir)
    breakers: dict[str, CircuitBreaker] = {
        p: CircuitBreaker(platform=p, failure_threshold=4, open_timeout_s=config.circuit_open_timeout_s)
        for p in _PLATFORMS
    }

    # ── Phase 3: build scraper instances ─────────────────────────────────────
    _all_scrapers: list[tuple[str, object]] = [
        ("instagram", InstagramScraper(route_evaluator=route_eval)),
        ("facebook",  FacebookScraper()),
        ("linkedin",  LinkedInScraper()),
        ("pinterest", PinterestScraper()),
        ("reddit",    RedditScraper()),
        ("twitter",   TwitterScraper()),
        ("behance",   BehanceScraper()),
    ]
    active = [
        (name, s) for name, s in _all_scrapers
        if getattr(config, f"{name}_enabled", True)
    ]

    # ── Phase 4: adaptive scheduler ───────────────────────────────────────────
    scheduler = AdaptiveScheduler(profiler, breakers, config, metrics)
    tasks = scheduler.build_plan(active)

    # ── Phase 5: browser ─────────────────────────────────────────────────────
    driver, _chrome_tmp_dir = build_driver(config)
    all_leads: list[Lead] = []
    total_skipped = 0
    _platform_capped_kws: dict[str, list[str]] = {}  # platform → keywords used this run

    try:
        for task in tasks:
            platform = task.name
            breaker = breakers[platform]

            if not breaker.allow_request():
                logger.warning("[%s] circuit OPEN — skipping", platform)
                metrics.record_circuit_break(platform)
                continue

            # ── Keyword cap (anti-ban layer 1) ────────────────────────────
            kw_attr = f"{platform}_keywords"
            config_kws: list[str] = getattr(config, kw_attr, [])

            # Merge hashtag-derived candidates (run_count=0 → max UCB priority)
            _db_candidates = get_keyword_candidates(config.sqlite_db_path, platform)
            _new_cands = [k for k in _db_candidates if k not in set(config_kws)]
            if _new_cands:
                logger.info(
                    "Keyword discovery [%s]: +%d candidates: %s",
                    platform, len(_new_cands),
                    ", ".join(_new_cands[:6]) + ("…" if len(_new_cands) > 6 else ""),
                )
            ranker_kws = list(dict.fromkeys(list(config_kws) + _db_candidates))

            # Rank by UCB performance before capping — best keywords run first
            ranked_kws = rank_keywords(config.sqlite_db_path, platform, ranker_kws)
            capped_kws = ranked_kws[: task.max_keywords]
            setattr(config, kw_attr, capped_kws)
            if len(ranker_kws) > task.max_keywords:
                logger.info(
                    "Anti-ban [%s]: keywords capped %d → %d (UCB-ranked)",
                    platform, len(ranker_kws), task.max_keywords,
                )

            # Propagate task-level scroll depth to scraper config
            config.scrolls_override = task.scrolls_per_page

            _active_driver = driver

            # ── Cooldown filter (anti-ban layer 2) ────────────────────────
            recent_urls = get_recent_profile_urls(
                config.sqlite_db_path, platform, config.rescrape_cooldown_days
            )
            logger.info(
                "Anti-ban [%s]: %d profiles in cooldown window",
                platform, len(recent_urls),
            )

            # ── Scrape ────────────────────────────────────────────────────
            t0 = time.perf_counter()
            scraper = task.scraper
            try:
                raw_leads: list[Lead] = scrape_with_retry(
                    lambda s=scraper, d=_active_driver: s.scrape(d, config),
                    max_retries=config.network_retries,
                    base_delay=task.retry_base_delay,
                    label=platform,
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000
                profiler.record_page_load(elapsed_ms)
                breaker.record_success()
                route_eval.record_success(platform, f"{platform}/search")
                metrics.record_page_load(platform, elapsed_ms)

            except Exception as exc:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                profiler.record_page_load(elapsed_ms, timed_out=True)
                breaker.record_failure(str(exc)[:80])
                route_eval.record_failure(platform, f"{platform}/search")
                metrics.record_page_load(platform, elapsed_ms, timed_out=True)
                metrics.record_keyword(platform, leads=0, success=False)
                logger.exception("[%s] scraper failed: %s", platform, exc)
                # Restore keywords before next iteration
                setattr(config, kw_attr, config_kws)
                continue

            # Restore original keywords list for next run
            setattr(config, kw_attr, config_kws)

            logger.info("[%s] returned %d raw leads", platform, len(raw_leads))

            # ── Cooldown split (anti-ban layer 3) ─────────────────────────
            fresh: list[Lead] = []
            seen_again: list[str] = []
            for lead in raw_leads:
                norm = (lead.profile_url or "").rstrip("/").lower()
                if norm and norm in recent_urls:
                    seen_again.append(lead.profile_url)
                else:
                    fresh.append(lead)

            if seen_again:
                touch_seen_profiles(config.sqlite_db_path, seen_again)
                total_skipped += len(seen_again)
                logger.info(
                    "Anti-ban [%s]: %d on cooldown (touched), %d fresh",
                    platform, len(seen_again), len(fresh),
                )

            all_leads.extend(fresh)
            metrics.record_keyword(platform, leads=len(fresh), success=True)
            # Save which keywords ran — stats updated after scoring in Phase 6
            _platform_capped_kws[platform] = capped_kws

    except Exception:
        finish_run(config.sqlite_db_path, run_id, "failed", len(all_leads), 0)
        raise
    finally:
        driver.quit()
        if _chrome_tmp_dir:
            import shutil as _shutil
            try:
                _shutil.rmtree(_chrome_tmp_dir, ignore_errors=True)
                logger.debug("Cleaned up cloned Chrome profile: %s", _chrome_tmp_dir)
            except Exception:
                pass

    # ── Phase 6: enrich + deduplicate + persist ───────────────────────────────
    enriched = [enrich_lead(lead) for lead in all_leads]
    deduped = dedupe_leads(enriched)

    export_leads(deduped, config.output_dir)
    upsert_leads(config.sqlite_db_path, deduped, run_id=run_id)

    # ── Keyword performance stats (after scoring so avg_score is real) ────────
    from collections import defaultdict as _dd
    for _plat, _kws in _platform_capped_kws.items():
        _kw_leads: dict[str, list] = _dd(list)
        for _l in enriched:
            if _l.source_platform == _plat and _l.search_term:
                _kw_leads[_l.search_term].append(_l)
        for _kw, _kw_lead_list in _kw_leads.items():
            update_keyword_stats(config.sqlite_db_path, _plat, _kw, _kw_lead_list)
            log_keyword_run(config.sqlite_db_path, run_id, _plat, _kw, _kw_lead_list)
        for _kw in _kws:
            if _kw not in _kw_leads:
                update_keyword_stats(config.sqlite_db_path, _plat, _kw, [])
                log_keyword_run(config.sqlite_db_path, run_id, _plat, _kw, [])

    # ── Hashtag discovery: propose keyword candidates for next run ────────────
    import re as _re
    from collections import Counter as _Counter

    _NOISE_TAGS: frozenset[str] = frozenset([
        "love", "instagood", "photooftheday", "beautiful", "follow", "like",
        "fashion", "style", "photo", "happy", "beauty", "cute", "travel",
        "instagram", "photography", "repost", "nature", "life", "fitness",
        "food", "music", "summer", "sunset", "fun", "friends",
        "art", "design", "home", "decor",  # too generic for niche targeting
    ])
    _tag_re = _re.compile(r'#([a-z]\w{2,29})', _re.IGNORECASE)

    _plat_tag_counts: dict[str, _Counter] = {}
    for _l in enriched:
        if _l.score < 30:
            continue
        # Extract hashtags from bio and raw_data text fields
        _raw = _l.raw_data if isinstance(_l.raw_data, dict) else {}
        _text = " ".join(filter(None, [
            _l.bio or "",
            str(_raw.get("post_text", "") or ""),
            str(_raw.get("caption", "") or ""),
            str(_raw.get("description", "") or ""),
        ]))
        for _tag in _tag_re.findall(_text.lower()):
            if _tag not in _NOISE_TAGS and 3 <= len(_tag) <= 30:
                _plat_tag_counts.setdefault(_l.source_platform, _Counter())[_tag] += 1

    # Only propose hashtags that appear in ≥2 high-scoring leads (noise filter)
    for _plat, _counter in _plat_tag_counts.items():
        _candidates = [f"#{tag}" for tag, cnt in _counter.items() if cnt >= 2]
        if _candidates:
            _n = propose_keyword_candidates(config.sqlite_db_path, _plat, _candidates)
            if _n:
                logger.info(
                    "Hashtag discovery [%s]: %d new candidates proposed: %s",
                    _plat, _n,
                    ", ".join(_candidates[:8]) + ("…" if len(_candidates) > 8 else ""),
                )

    # Snapshot score distribution for this run (feeds evolution charts in dashboard)
    save_run_histogram(config.sqlite_db_path, run_id, deduped)

    finish_run(
        config.sqlite_db_path,
        run_id,
        "completed",
        len(all_leads) + total_skipped,
        len(deduped),
    )

    # ── Phase 7: reporting ────────────────────────────────────────────────────
    logger.info(
        "Anti-ban summary: %d on cooldown, %d fresh processed, %d deduped",
        total_skipped, len(all_leads), len(deduped),
    )
    print_summary(deduped)
    metrics.log_summary()
    metrics.save_report()
    route_eval.log_report()

    # ── Keyword performance report ─────────────────────────────────────────
    for _plat in {t.name for t in tasks}:
        summary = summarise_keyword_performance(config.sqlite_db_path, _plat)
        logger.info("Keyword performance [%s]:\n%s", _plat, summary)


if __name__ == "__main__":
    main()
