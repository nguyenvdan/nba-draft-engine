"""Basketball-Reference draft pages -> pick # + realized NBA career outcomes.

One page per draft year (/draft/NBA_{year}.html, table id='stats') yields pick,
player, college label, AND pre-aggregated career outcome columns
(seasons, G, WS, WS/48, BPM, VORP) — so no per-player NBA fetch is needed.
"""
import re
from datetime import datetime

import pandas as pd

from .cache import NotFound, get_html
from .htmlutil import soupify

BASE = "https://www.basketball-reference.com"


def _txt(cell) -> str:
    return cell.get_text(strip=True) if cell is not None else ""


def _num(cell):
    t = _txt(cell)
    if t == "":
        return None
    try:
        return float(t)
    except ValueError:
        return None


def scrape_draft_year(year: int) -> pd.DataFrame:
    html = get_html(f"{BASE}/draft/NBA_{year}.html", f"bbref_draft_{year}.html")
    table = soupify(html).find("table", id="stats")
    if table is None:
        return pd.DataFrame()
    rows = []
    for tr in table.select("tbody tr"):
        cells = {c.get("data-stat"): c for c in tr.find_all(["th", "td"])}
        pick = _txt(cells.get("pick_overall"))
        if not pick.isdigit():  # round-separator / repeated-header ("Pk") rows
            continue
        player_cell = cells.get("player")
        bbref_id = None
        if player_cell is not None:
            a = player_cell.find("a")
            if a and a.get("href"):
                m = re.search(r"/players/\w/([^.]+)\.html", a["href"])
                bbref_id = m.group(1) if m else None
        rows.append({
            "draft_year": year,
            "pick_overall": int(float(pick)),
            "drafted_by": _txt(cells.get("team_id")),
            "player": _txt(player_cell),
            "bbref_id": bbref_id,
            "college_name": _txt(cells.get("college_name")),
            "years_in_league": _num(cells.get("seasons")),
            "career_games": _num(cells.get("g")),
            "career_ws": _num(cells.get("ws")),
            "ws_per_48": _num(cells.get("ws_per_48")),
            "career_bpm": _num(cells.get("bpm")),
            "vorp": _num(cells.get("vorp")),
        })
    return pd.DataFrame(rows)


def draft_date(year: int):
    """Exact draft date from the draft-page meta. Dates vary (2020 was November),
    so we read the real date rather than assuming late June."""
    html = get_html(f"{BASE}/draft/NBA_{year}.html", f"bbref_draft_{year}.html")
    meta = soupify(html).find("div", id="meta")
    if meta is None:
        return None
    m = re.search(r"Date\s*:\s*[A-Za-z]+,\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})",
                  meta.get_text(" ", strip=True))
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%B %d, %Y").date()
    except ValueError:
        return None


def player_birthdate(bbref_id: str):
    """Birthdate from a BBRef player page's necro-birth span, or None."""
    if not bbref_id:
        return None
    url = f"{BASE}/players/{bbref_id[0]}/{bbref_id}.html"
    try:
        html = get_html(url, f"bbref_player_{bbref_id}.html")
    except NotFound:
        return None
    span = soupify(html).find("span", id="necro-birth")
    if span and span.get("data-birth"):
        try:
            return datetime.strptime(span["data-birth"], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def exact_age_at_draft(bbref_id: str, draft_dt):
    """Age in years at the draft date from DOB; None if either is missing."""
    bd = player_birthdate(bbref_id)
    if bd and draft_dt:
        return round((draft_dt - bd).days / 365.25, 2)
    return None
