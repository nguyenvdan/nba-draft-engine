"""All-NBA and All-Star selection counts, joined by BBRef player id.

Single-page sources, cached once:
  /awards/all_league.html          -> All-NBA teams by season (players in cols 1-5)
  /awards/all_star_by_player.html  -> All-Star selection totals per player

Counts are keyed by BBRef player id (parsed from each player link's href) so the
join to the draft table is name-independent and robust.
"""
import re
from collections import defaultdict

from .cache import get_html
from .htmlutil import soupify

BASE = "https://www.basketball-reference.com"


def _bbref_id(a) -> str | None:
    if a and a.get("href"):
        m = re.search(r"/players/\w/([^.]+)\.html", a["href"])
        return m.group(1) if m else None
    return None


def all_nba_counts() -> dict:
    """{bbref_id: number of All-NBA (1st/2nd/3rd team) selections}, NBA only."""
    html = get_html(f"{BASE}/awards/all_league.html", "bbref_all_league.html")
    table = soupify(html).find("table", id="awards_all_league")
    counts: dict = defaultdict(int)
    if table is None:
        return dict(counts)
    for tr in table.select("tbody tr"):
        cells = {c.get("data-stat"): c for c in tr.find_all(["th", "td"])}
        lg = cells.get("lg_id")
        if lg is not None and lg.get_text(strip=True) != "NBA":
            continue
        for slot in ("1", "2", "3", "4", "5"):
            c = cells.get(slot)
            if c is None:
                continue
            pid = _bbref_id(c.find("a"))
            if pid:
                counts[pid] += 1
    return dict(counts)


def all_star_counts() -> dict:
    """{bbref_id: number of NBA All-Star selections}."""
    html = get_html(f"{BASE}/awards/all_star_by_player.html", "bbref_all_star_by_player.html")
    table = soupify(html).find("table", id="all_star_by_player")
    counts: dict = {}
    if table is None:
        return counts
    for tr in table.select("tbody tr"):
        cells = tr.find_all(["th", "td"])  # Rk, Player, Tot, NBA, ABA  (no data-stat)
        if len(cells) < 4:
            continue
        pid = _bbref_id(cells[1].find("a"))
        try:
            n_nba = int(cells[3].get_text(strip=True))
        except ValueError:
            continue
        if pid:
            counts[pid] = n_nba
    return counts
