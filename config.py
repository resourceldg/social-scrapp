from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv


def _parse_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_csv(value: str, fallback: List[str]) -> List[str]:
    if not value:
        return fallback
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(slots=True)
class AppConfig:
    chrome_profile_path: str = ""
    user_data_dir: str = ""
    headless: bool = False
    max_profiles_per_platform: int = 50
    max_results_per_query: int = 20
    min_delay: float = 2.0
    max_delay: float = 6.0
    output_dir: Path = Path("output")
    debug_html_dir: Path = Path("debug_html")
    save_debug_html: bool = True
    sqlite_db_path: Path = Path("output/leads.db")
    rescrape_cooldown_days: int = 7
    max_searches_per_session: int = 10
    page_load_timeout: int = 60
    network_retries: int = 3
    block_images: bool = True
    circuit_open_timeout_s: float = 300.0  # seconds a circuit stays OPEN before going HALF_OPEN
    scrolls_override: int = 4   # set per-session by AdaptiveScheduler; not in .env
    # Enabled flags
    instagram_enabled: bool = True
    facebook_enabled: bool = True
    linkedin_enabled: bool = True
    pinterest_enabled: bool = True
    reddit_enabled: bool = True
    twitter_enabled: bool = True
    behance_enabled: bool = True
    # Keywords
    instagram_keywords: List[str] = field(default_factory=list)
    facebook_keywords: List[str] = field(default_factory=list)
    linkedin_keywords: List[str] = field(default_factory=list)
    pinterest_keywords: List[str] = field(default_factory=list)
    reddit_keywords: List[str] = field(default_factory=list)
    twitter_keywords: List[str] = field(default_factory=list)
    behance_keywords: List[str] = field(default_factory=list)
    # Credentials
    instagram_username: str = ""
    instagram_password: str = ""
    facebook_username: str = ""
    facebook_password: str = ""
    linkedin_username: str = ""
    linkedin_password: str = ""
    twitter_username: str = ""
    twitter_password: str = ""
    pinterest_username: str = ""
    pinterest_password: str = ""
    reddit_username: str = ""
    reddit_password: str = ""
    behance_username: str = ""
    behance_password: str = ""


DEFAULT_KEYWORDS = {
    "instagram": ["#artecontemporaneo", "#galeriaarte", "#interiordesign"],
    "facebook": ["galerías de arte", "interiorismo", "curaduría"],
    "linkedin": ["architecture studio buenos aires", "hospitality design"],
    "pinterest": ["luxury interiors", "contemporary art interiors"],
    "reddit": ["interior design", "contemporary art", "hospitality design"],
    "twitter": ["interior designer art", "gallery director"],
    "behance": [
        "interior design", "architecture", "luxury furniture",
        "art direction", "collectible design", "gallery",
        "interiorismo", "arquitectura", "diseño de interiores",
    ],
}


def load_config() -> AppConfig:
    load_dotenv(override=True)

    config = AppConfig(
        chrome_profile_path=os.getenv("CHROME_PROFILE_PATH", ""),
        user_data_dir=os.getenv("USER_DATA_DIR", ""),
        headless=_parse_bool(os.getenv("HEADLESS", "false")),
        max_profiles_per_platform=int(os.getenv("MAX_PROFILES_PER_PLATFORM", "50")),
        max_results_per_query=int(os.getenv("MAX_RESULTS_PER_QUERY", "20")),
        min_delay=float(os.getenv("MIN_DELAY", "2")),
        max_delay=float(os.getenv("MAX_DELAY", "6")),
        output_dir=Path(os.getenv("OUTPUT_DIR", "output")),
        debug_html_dir=Path("debug_html"),
        save_debug_html=_parse_bool(os.getenv("SAVE_DEBUG_HTML", "true"), default=True),
        sqlite_db_path=Path(os.getenv("SQLITE_DB_PATH", "output/leads.db")),
        rescrape_cooldown_days=int(os.getenv("RESCRAPE_COOLDOWN_DAYS", "7")),
        max_searches_per_session=int(os.getenv("MAX_SEARCHES_PER_SESSION", "10")),
        page_load_timeout=int(os.getenv("PAGE_LOAD_TIMEOUT", "60")),
        network_retries=int(os.getenv("NETWORK_RETRIES", "3")),
        block_images=_parse_bool(os.getenv("BLOCK_IMAGES", "true"), default=True),
        circuit_open_timeout_s=float(os.getenv("CIRCUIT_OPEN_TIMEOUT_S", "300")),
        # Enabled flags
        instagram_enabled=_parse_bool(os.getenv("INSTAGRAM_ENABLED", "true"), default=True),
        facebook_enabled=_parse_bool(os.getenv("FACEBOOK_ENABLED", "true"), default=True),
        linkedin_enabled=_parse_bool(os.getenv("LINKEDIN_ENABLED", "true"), default=True),
        pinterest_enabled=_parse_bool(os.getenv("PINTEREST_ENABLED", "true"), default=True),
        reddit_enabled=_parse_bool(os.getenv("REDDIT_ENABLED", "true"), default=True),
        twitter_enabled=_parse_bool(os.getenv("TWITTER_ENABLED", "true"), default=True),
        behance_enabled=_parse_bool(os.getenv("BEHANCE_ENABLED", "true"), default=True),
        # Keywords
        instagram_keywords=_parse_csv(os.getenv("INSTAGRAM_KEYWORDS", ""), DEFAULT_KEYWORDS["instagram"]),
        facebook_keywords=_parse_csv(os.getenv("FACEBOOK_KEYWORDS", ""), DEFAULT_KEYWORDS["facebook"]),
        linkedin_keywords=_parse_csv(os.getenv("LINKEDIN_KEYWORDS", ""), DEFAULT_KEYWORDS["linkedin"]),
        pinterest_keywords=_parse_csv(os.getenv("PINTEREST_KEYWORDS", ""), DEFAULT_KEYWORDS["pinterest"]),
        reddit_keywords=_parse_csv(os.getenv("REDDIT_KEYWORDS", ""), DEFAULT_KEYWORDS["reddit"]),
        twitter_keywords=_parse_csv(os.getenv("TWITTER_KEYWORDS", ""), DEFAULT_KEYWORDS["twitter"]),
        behance_keywords=_parse_csv(os.getenv("BEHANCE_KEYWORDS", ""), DEFAULT_KEYWORDS["behance"]),
        # Credentials
        instagram_username=os.getenv("INSTAGRAM_USERNAME", ""),
        instagram_password=os.getenv("INSTAGRAM_PASSWORD", ""),
        facebook_username=os.getenv("FACEBOOK_USERNAME", ""),
        facebook_password=os.getenv("FACEBOOK_PASSWORD", ""),
        linkedin_username=os.getenv("LINKEDIN_USERNAME", ""),
        linkedin_password=os.getenv("LINKEDIN_PASSWORD", ""),
        twitter_username=os.getenv("TWITTER_USERNAME", ""),
        twitter_password=os.getenv("TWITTER_PASSWORD", ""),
        pinterest_username=os.getenv("PINTEREST_USERNAME", ""),
        pinterest_password=os.getenv("PINTEREST_PASSWORD", ""),
        reddit_username=os.getenv("REDDIT_USERNAME", ""),
        reddit_password=os.getenv("REDDIT_PASSWORD", ""),
        behance_username=os.getenv("BEHANCE_USERNAME", ""),
        behance_password=os.getenv("BEHANCE_PASSWORD", ""),
    )

    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.debug_html_dir.mkdir(parents=True, exist_ok=True)
    config.sqlite_db_path.parent.mkdir(parents=True, exist_ok=True)
    return config
