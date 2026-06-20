"""Sports-Reference College Basketball -> a prospect's final pre-draft season.

The hard part is name -> URL resolution. CBB player slugs are
``firstname-lastname-N``; we probe N=1.. and *verify identity* against the
page's own 'Draft:' meta line (draft year + overall pick — a strong
disambiguator for same-name players) or a school match. Verified misses are
reported, never silently guessed.
"""
import re
from urllib.parse import quote_plus

from unidecode import unidecode

from .cache import NotFound, fetch_text_and_url, get_html
from .htmlutil import soupify

BASE = "https://www.sports-reference.com/cbb"
GEN_SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}


def name_to_slug(name: str) -> str:
    n = unidecode(name).lower().replace("'", "").replace(".", "")
    n = re.sub(r"[^a-z0-9\s-]", "", n)
    parts = [p for p in re.split(r"[\s-]+", n) if p]
    if parts and parts[-1] in GEN_SUFFIX:
        parts = parts[:-1]
    return "-".join(parts)


def _f(d: dict, k: str):
    v = d.get(k, "")
    if v in ("", None):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_meta(soup) -> dict:
    info = {"position": None, "height_in": None, "weight_lb": None,
            "school": None, "rsci_rank": None, "draft_year": None, "draft_pick": None}
    meta = soup.find("div", id="meta")
    if meta is None:
        return info
    ps = [" ".join(p.get_text(" ", strip=True).split()) for p in meta.find_all("p")]
    blob = " | ".join(ps)
    m = re.search(r"\b(\d)-(\d{1,2})\b", blob)
    if m:
        info["height_in"] = int(m.group(1)) * 12 + int(m.group(2))
    m = re.search(r"(\d{2,3})lb", blob)
    if m:
        info["weight_lb"] = int(m.group(1))
    for t in ps:
        low = t.lower()
        if low.startswith("position"):
            info["position"] = t.split(":", 1)[-1].split("|")[0].strip()
        elif low.startswith("school"):
            info["school"] = t.split(":", 1)[-1].strip()
        elif "rsci top 100" in low:
            mm = re.search(r"RSCI Top 100:\s*(\d+)", t)
            if mm:
                info["rsci_rank"] = int(mm.group(1))
        elif low.startswith("draft"):
            mm = re.search(r"(\d{4})\s+NBA draft", t)
            if mm:
                info["draft_year"] = int(mm.group(1))
            mm = re.search(r"(\d+)(?:st|nd|rd|th) overall", t)
            if mm:
                info["draft_pick"] = int(mm.group(1))
    return info


def _season_rows(soup, table_id: str) -> dict:
    table = soup.find("table", id=table_id)
    rows = {}
    if table is None:
        return rows
    for tr in table.select("tbody tr"):
        cells = {c.get("data-stat"): c.get_text(strip=True) for c in tr.find_all(["th", "td"])}
        yr = cells.get("year_id", "")
        if not yr or yr.lower().startswith("career"):
            continue
        rows.setdefault(yr, cells)
    return rows


def _pick_season(seasons: dict, draft_year: int):
    """The final college season is the one ending in the draft year."""
    target = f"{draft_year - 1}-{str(draft_year)[2:]}"
    if target in seasons:
        return target, seasons[target]
    if seasons:
        last = sorted(seasons)[-1]
        return last, seasons[last]
    return None, None


def _school_match(a, b) -> bool:
    if not a or not b:
        return False
    na = unidecode(a).lower().replace("(men)", "").strip()
    nb = unidecode(b).lower().strip()
    return na[:4] == nb[:4] or nb in na or na.split()[0] in nb


def _build_line(soup, meta: dict, draft_year: int, url: str) -> dict:
    pg = _season_rows(soup, "players_per_game")
    adv = _season_rows(soup, "players_advanced")
    yr, p = _pick_season(pg, draft_year)
    a = adv.get(yr, {}) if yr else {}
    p = p or {}
    return {
        "college_url": url,
        "school": meta.get("school") or p.get("team_name_abbr"),
        "conference": p.get("conf_abbr"),
        "class": p.get("class"),
        "position": meta.get("position"),
        "height_in_listed": meta.get("height_in"),
        "weight_lb_listed": meta.get("weight_lb"),
        "rsci_rank": meta.get("rsci_rank"),
        "college_season": yr,
        "college_games": _f(p, "games"),
        "college_mpg": _f(p, "mp_per_g"),
        "pts": _f(p, "pts_per_g"),
        "reb": _f(p, "trb_per_g"),
        "ast": _f(p, "ast_per_g"),
        "stl": _f(p, "stl_per_g"),
        "blk": _f(p, "blk_per_g"),
        "tov": _f(p, "tov_per_g"),
        "fg_pct": _f(p, "fg_pct"),
        "fg3_pct": _f(p, "fg3_pct"),
        "ft_pct": _f(p, "ft_pct"),
        "efg_pct": _f(p, "efg_pct"),
        "ts_pct": _f(a, "ts_pct"),
        "usg_pct": _f(a, "usg_pct"),
        "ast_pct": _f(a, "ast_pct"),
        "reb_pct": _f(a, "trb_pct"),
        "per": _f(a, "per"),
        "college_ws": _f(a, "ws"),
        "ws_per_40": _f(a, "ws_per_40"),
        "obpm": _f(a, "obpm"),
        "dbpm": _f(a, "dbpm"),
        "college_bpm": _f(a, "bpm"),
    }


def _verify(meta, draft_year, pick_overall, college_name) -> bool:
    """Confirm a candidate page is the right person via its own 'Draft:' line
    (year + overall pick) or a school match."""
    return (
        (meta["draft_year"] == draft_year and meta["draft_pick"] == pick_overall)
        or (meta["draft_year"] == draft_year and _school_match(meta["school"], college_name))
        or (meta["draft_year"] is None and _school_match(meta["school"], college_name))
    )


def _search_slug(player: str):
    """Resolve a CBB slug via the Sports-Reference search endpoint, which
    302-redirects a unique query to the player page (handles nickname/legal-name
    mismatches, e.g. 'Ja Morant' -> temetrius-morant-1)."""
    text, final = fetch_text_and_url(f"{BASE}/search/search.fcgi?search={quote_plus(player)}")
    if final:
        m = re.search(r"/cbb/players/([^./]+)\.html", final)
        if m:
            return m.group(1)
    if text:  # multi-result page: take the first player hit
        m = re.search(r"/cbb/players/([^./]+)\.html", text)
        if m:
            return m.group(1)
    return None


def resolve_and_scrape(player, draft_year, pick_overall, college_name, max_suffix=5):
    """Return (college_line | None, status)."""
    slug = name_to_slug(player)
    if not slug:
        return None, "empty_slug"
    tried = 0
    for i in range(1, max_suffix + 1):
        cand = f"{slug}-{i}"
        try:
            html = get_html(f"{BASE}/players/{cand}.html", f"cbb_{cand}.html")
        except NotFound:
            continue
        tried += 1
        soup = soupify(html)
        meta = _parse_meta(soup)
        if _verify(meta, draft_year, pick_overall, college_name):
            return _build_line(soup, meta, draft_year, f"{BASE}/players/{cand}.html"), "ok"

    # Fallback: search endpoint (nickname/legal-name and other slug mismatches)
    slug2 = _search_slug(player)
    if slug2 and slug2 != f"{slug}-1":
        try:
            html = get_html(f"{BASE}/players/{slug2}.html", f"cbb_{slug2}.html")
            soup = soupify(html)
            meta = _parse_meta(soup)
            if _verify(meta, draft_year, pick_overall, college_name):
                return _build_line(soup, meta, draft_year, f"{BASE}/players/{slug2}.html"), "ok_search"
        except NotFound:
            pass
    return None, ("no_page" if tried == 0 else "no_verified_match")
