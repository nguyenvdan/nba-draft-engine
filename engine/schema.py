"""Canonical Prospect schema + the outcome-tier heuristic.

This is the single source of truth for the column set written to
data/prospects.csv. Field provenance and every proxy/estimate are documented in
data/provenance.md. `*` in comments below marks proxy / sparse / estimated fields.
"""
from __future__ import annotations

import re

import pandas as pd
from unidecode import unidecode

# Ordered, grouped column set for the committed dataset.
PROSPECT_COLUMNS: list[str] = [
    # --- identity / context ---
    "prospect_id", "player", "draft_year", "pick_overall", "drafted_by", "level",
    "position", "school", "conference", "class", "rsci_rank",
    "age_at_draft", "age_source",          # age_at_draft is class-estimated for most historical rows*
    # --- listed measurements (CBB meta block) ---
    "height_in_listed", "weight_lb_listed",
    # --- college production (final pre-draft season) ---
    "college_season", "college_games", "college_mpg",
    "pts", "reb", "ast", "stl", "blk", "tov",
    "fg_pct", "fg3_pct", "ft_pct", "efg_pct", "ts_pct",
    "usg_pct", "ast_pct", "reb_pct",
    # --- college advanced ---
    "per", "college_ws", "ws_per_40", "obpm", "dbpm", "college_bpm",
    # --- combine measurements (nba_api; missing for skipped drills) ---
    "height_wo_shoes_in", "height_w_shoes_in", "weight_lb", "wingspan_in",
    "standing_reach_in", "max_vertical_in", "no_step_vertical_in",
    "lane_agility_s", "three_quarter_sprint_s", "body_fat_pct",
    "hand_length_in", "hand_width_in",
    # --- consensus (proxy; curated overlay, mostly null for historical) ---
    "mock_rank", "bigboard_rank", "mock_low", "mock_high",
    # --- outcomes (NBA career; historical labels only) ---
    "career_games", "career_ws", "ws_per_48", "vorp", "career_bpm",
    "years_in_league", "all_star_count", "all_nba_count",
    "outcome_tier", "outcome_provisional",
    # --- provenance / traceability ---
    "bbref_id", "college_url", "data_flags",
]

# Class -> approximate age at a late-June draft. ESTIMATE, flagged via age_source.
CLASS_AGE_ESTIMATE = {"FR": 19.2, "SO": 20.2, "JR": 21.2, "SR": 22.2}

OUTCOME_TIERS = ["bust", "role_player", "starter", "all_star", "superstar"]


def slugify(name: str) -> str:
    s = unidecode(str(name)).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def make_prospect_id(player: str, draft_year) -> str:
    return f"{slugify(player)}-{draft_year}"


def _f(v):
    """Coerce to float or None."""
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def assign_outcome_tier(row: dict) -> str:
    """Coarse realized-career label for the comparable model's base rates.

    Driven mainly by cumulative value (career Win Shares, VORP) with a rate gate
    (WS/48) and accolades where available. This is a *documented heuristic*, not
    ground truth. Recent classes are provisional (see outcome_provisional); their
    careers are truncated, so a low tier is not yet meaningful.
    """
    ws = _f(row.get("career_ws")) or 0.0
    vorp = _f(row.get("vorp")) or 0.0
    ws48 = _f(row.get("ws_per_48")) or 0.0
    yrs = _f(row.get("years_in_league")) or 0.0
    games = _f(row.get("career_games")) or 0.0
    allstar = _f(row.get("all_star_count")) or 0.0
    allnba = _f(row.get("all_nba_count")) or 0.0

    if allnba >= 1 or ws >= 80 or vorp >= 25:
        return "superstar"
    if allstar >= 1 or ws >= 45 or vorp >= 12:
        return "all_star"
    if ws >= 22 or vorp >= 4 or (yrs >= 6 and ws48 >= 0.08):
        return "starter"
    if games >= 150 or yrs >= 4 or ws >= 4:
        return "role_player"
    return "bust"


def outcome_provisional(draft_year: int, current_year: int = 2026, maturity: int = 7) -> bool:
    """True if the career is too young for its outcome tier to be trusted."""
    return int(draft_year) > current_year - maturity


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Reindex to the canonical column order; missing -> NA, extras dropped."""
    for col in PROSPECT_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df[PROSPECT_COLUMNS]
