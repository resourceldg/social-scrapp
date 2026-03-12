from __future__ import annotations

import random
import re
import time
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from selenium.webdriver.remote.webdriver import WebDriver

EMAIL_REGEX = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
PHONE_REGEX = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}\b")
URL_REGEX = re.compile(r"\b(?:https?://|www\.)[\w.-]+(?:\.[\w.-]+)+(?:[/\w\-._~:/?#[\]@!$&'()*+,;=]*)?", re.IGNORECASE)

PRIORITY_LOCATIONS = {
    "argentina": ("", "Argentina"),
    "españa": ("", "España"),
    "spain": ("", "España"),
    "méxico": ("", "México"),
    "mexico": ("", "México"),
    "chile": ("", "Chile"),
    "uruguay": ("", "Uruguay"),
    "miami": ("Miami", "USA"),
    "madrid": ("Madrid", "España"),
    "barcelona": ("Barcelona", "España"),
    "cdmx": ("CDMX", "México"),
    "monterrey": ("Monterrey", "México"),
    "bogotá": ("Bogotá", "Colombia"),
    "bogota": ("Bogotá", "Colombia"),
    "buenos aires": ("Buenos Aires", "Argentina"),
}


def random_delay(min_delay: float, max_delay: float) -> None:
    time.sleep(random.uniform(min_delay, max_delay))


def extract_emails(text: str) -> List[str]:
    return sorted(set(EMAIL_REGEX.findall(text or "")))


def extract_phones(text: str) -> List[str]:
    candidates = [p.strip() for p in PHONE_REGEX.findall(text or "")]
    return sorted({c for c in candidates if len(re.sub(r"\D", "", c)) >= 8})


def extract_website(text: str) -> str:
    match = URL_REGEX.search(text or "")
    if not match:
        return ""
    url = match.group(0)
    return url if url.startswith("http") else f"https://{url}"


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
