from __future__ import annotations

from bs4 import BeautifulSoup


def soup_from_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")
