"""NBA Stats API draft-combine measurements via nba_api.

draftcombineplayeranthro  -> height (w/ & w/o shoes), weight, wingspan,
                             standing reach, body fat, hand size
draftcombinedrillresults  -> max & standing vertical, lane agility, 3/4 sprint

One call per endpoint per draft year returns every attendee. Missing values
(stars skip drills) are kept as NaN, never zero. JSON is cached so re-runs and
the offline fallback never hit the API.
"""
import pandas as pd
from nba_api.stats.endpoints import (
    draftcombinedrillresults,
    draftcombineplayeranthro,
)

from .cache import get_json, limiter

ANTHRO_MAP = {
    "HEIGHT_WO_SHOES": "height_wo_shoes_in",
    "HEIGHT_W_SHOES": "height_w_shoes_in",
    "WEIGHT": "weight_lb",
    "WINGSPAN": "wingspan_in",
    "STANDING_REACH": "standing_reach_in",
    "BODY_FAT_PCT": "body_fat_pct",
    "HAND_LENGTH": "hand_length_in",
    "HAND_WIDTH": "hand_width_in",
}
DRILL_MAP = {
    "STANDING_VERTICAL_LEAP": "no_step_vertical_in",
    "MAX_VERTICAL_LEAP": "max_vertical_in",
    "LANE_AGILITY_TIME": "lane_agility_s",
    "THREE_QUARTER_SPRINT": "three_quarter_sprint_s",
}


def season_year(draft_year: int) -> str:
    """Combine season_year = the NBA season the rookies enter.

    Verified: season_year='2019-20' returns 2019 draftees, so draft year D maps
    to f'{D}-{(D+1) % 100:02d}'.
    """
    return f"{draft_year}-{(draft_year + 1) % 100:02d}"


def _fetch_df(endpoint_cls, sy: str, key: str) -> pd.DataFrame:
    def producer():
        limiter.wait()
        df = endpoint_cls(season_year=sy, timeout=45).get_data_frames()[0]
        # Replace NaN with None so the cached JSON is valid/portable.
        return df.where(pd.notna(df), None).to_dict("records")

    return pd.DataFrame(get_json(key, producer))


def scrape_combine_year(draft_year: int) -> pd.DataFrame:
    sy = season_year(draft_year)
    try:
        anthro = _fetch_df(draftcombineplayeranthro.DraftCombinePlayerAnthro,
                           sy, f"nba_combine_anthro_{sy}.json")
        drill = _fetch_df(draftcombinedrillresults.DraftCombineDrillResults,
                          sy, f"nba_combine_drill_{sy}.json")
    except Exception as e:  # combine data absent / API hiccup for some years
        print(f"  [combine] {sy}: {e!r}")
        return pd.DataFrame()

    frames = []
    for df, mapping in ((anthro, ANTHRO_MAP), (drill, DRILL_MAP)):
        if df.empty or "PLAYER_NAME" not in df.columns:
            continue
        keep = [c for c in mapping if c in df.columns]
        sub = df[["PLAYER_NAME"] + keep].rename(columns=mapping)
        frames.append(sub.set_index("PLAYER_NAME"))
    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, axis=1).reset_index().rename(columns={"PLAYER_NAME": "player"})
    for c in out.columns:
        if c != "player":
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out
