import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path = Path("output")) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

    handlers: list[logging.Handler] = [
        logging.StreamHandler(),
        RotatingFileHandler(
            log_dir / "scraper.log",
            maxBytes=5 * 1024 * 1024,  # 5 MB per file
            backupCount=3,
            encoding="utf-8",
        ),
    ]

    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)

    # Silence noisy third-party loggers
    for noisy in ("selenium", "urllib3", "webdriver_manager"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
