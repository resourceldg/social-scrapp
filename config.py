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
    instagram_keywords: List[str] = field(default_factory=list)
    facebook_keywords: List[str] = field(default_factory=list)
    linkedin_keywords: List[str] = field(default_factory=list)
    pinterest_keywords: List[str] = field(default_factory=list)
    reddit_keywords: List[str] = field(default_factory=list)
    twitter_keywords: List[str] = field(default_factory=list)


DEFAULT_KEYWORDS = {
    "instagram": ["#artecontemporaneo", "#galeriaarte", "#interiordesign"],
    "facebook": ["galerías de arte", "interiorismo", "curaduría"],
    "linkedin": ["architecture studio buenos aires", "hospitality design"],
    "pinterest": ["luxury interiors", "contemporary art interiors"],
    "reddit": ["interior design", "contemporary art", "hospitality design"],
    "twitter": ["interior designer art", "gallery director"],
}


def load_config() -> AppConfig:
    load_dotenv()

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
        instagram_keywords=_parse_csv(os.getenv("INSTAGRAM_KEYWORDS", ""), DEFAULT_KEYWORDS["instagram"]),
        facebook_keywords=_parse_csv(os.getenv("FACEBOOK_KEYWORDS", ""), DEFAULT_KEYWORDS["facebook"]),
        linkedin_keywords=_parse_csv(os.getenv("LINKEDIN_KEYWORDS", ""), DEFAULT_KEYWORDS["linkedin"]),
        pinterest_keywords=_parse_csv(os.getenv("PINTEREST_KEYWORDS", ""), DEFAULT_KEYWORDS["pinterest"]),
        reddit_keywords=_parse_csv(os.getenv("REDDIT_KEYWORDS", ""), DEFAULT_KEYWORDS["reddit"]),
        twitter_keywords=_parse_csv(os.getenv("TWITTER_KEYWORDS", ""), DEFAULT_KEYWORDS["twitter"]),
    )

    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.debug_html_dir.mkdir(parents=True, exist_ok=True)
    config.sqlite_db_path.parent.mkdir(parents=True, exist_ok=True)
    return config
