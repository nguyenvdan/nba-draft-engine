"""Shared HTML helper.

Sports-Reference sites hide many secondary tables inside HTML comments to deter
scrapers. ``soupify`` surfaces them so the whole page is parseable.
"""
from bs4 import BeautifulSoup, Comment


def soupify(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "lxml")
    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        if "<table" in c:
            c.replace_with(BeautifulSoup(c, "lxml"))
    return soup
