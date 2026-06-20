"""Orchestrate the three sources into the uniform Prospect table.

Per draft year: scrape draft outcomes (BBRef) -> fuzzy-join combine (nba_api)
-> resolve + scrape each college player's final season (CBB). Unresolved college
joins are collected into an unmatched report for human review (the brief's
name-edge-case check), never silently dropped or guessed.
"""
import pandas as pd

from ..schema import (
    CLASS_AGE_ESTIMATE,
    assign_outcome_tier,
    ensure_columns,
    make_prospect_id,
    outcome_provisional,
)
from . import join, scrape_awards, scrape_bbref, scrape_cbb, scrape_combine


def _level(college_name, resolved: bool) -> str:
    if resolved:
        return "NCAA"
    if not college_name or not str(college_name).strip():
        return "non-NCAA"  # international / G-League / prep (no college line expected)
    return "unresolved"    # had a college label but we could not verify the page


def build(years, picks=None, current_year=2026, do_combine=True, top_pick_age=20, verbose=True):
    rows, unmatched = [], []
    # Accolade maps (single-page sources), joined by BBRef player id.
    all_nba = scrape_awards.all_nba_counts()
    all_star = scrape_awards.all_star_counts()
    for y in years:
        draft = scrape_bbref.scrape_draft_year(y)
        if draft.empty:
            if verbose:
                print(f"[{y}] no draft table found")
            continue
        if picks:
            draft = draft[draft["pick_overall"] <= picks]
        combine = scrape_combine.scrape_combine_year(y) if do_combine else pd.DataFrame()
        draft_dt = scrape_bbref.draft_date(y)  # exact date for top-pick age computation

        n_college = n_resolved = n_combine = 0
        for _, d in draft.iterrows():
            row = {
                "prospect_id": make_prospect_id(d["player"], y),
                "player": d["player"],
                "draft_year": y,
                "pick_overall": d["pick_overall"],
                "drafted_by": d["drafted_by"],
                "bbref_id": d["bbref_id"],
                "career_games": d["career_games"],
                "career_ws": d["career_ws"],
                "ws_per_48": d["ws_per_48"],
                "career_bpm": d["career_bpm"],
                "vorp": d["vorp"],
                "years_in_league": d["years_in_league"],
            }

            cm = join.match_combine(d["player"], combine)
            if cm:
                row.update(cm)
                n_combine += 1

            college_name = d["college_name"]
            college_line = None
            if college_name and str(college_name).strip():
                n_college += 1
                college_line, status = scrape_cbb.resolve_and_scrape(
                    d["player"], y, int(d["pick_overall"]), college_name)
                if college_line:
                    row.update(college_line)
                    n_resolved += 1
                else:
                    unmatched.append({
                        "player": d["player"], "draft_year": y,
                        "pick_overall": int(d["pick_overall"]),
                        "college_name": college_name, "reason": status,
                    })

            row["level"] = _level(college_name, college_line is not None)

            cls = row.get("class")
            if cls in CLASS_AGE_ESTIMATE:
                row["age_at_draft"] = CLASS_AGE_ESTIMATE[cls]
                row["age_source"] = "class_estimate"

            pid = d["bbref_id"]
            # Hybrid age: exact DOB-derived age for top picks; class estimate otherwise.
            if pid and int(d["pick_overall"]) <= top_pick_age:
                exact = scrape_bbref.exact_age_at_draft(pid, draft_dt)
                if exact is not None:
                    row["age_at_draft"] = exact
                    row["age_source"] = "reported"
            row["all_nba_count"] = int(all_nba.get(pid, 0)) if pid else 0
            row["all_star_count"] = int(all_star.get(pid, 0)) if pid else 0

            row["outcome_tier"] = assign_outcome_tier(row)
            row["outcome_provisional"] = outcome_provisional(y, current_year)
            rows.append(row)

        if verbose:
            print(f"[{y}] picks={len(draft)} college_listed={n_college} "
                  f"resolved={n_resolved} combine_matched={n_combine}")

    df = ensure_columns(pd.DataFrame(rows))
    unmatched_df = pd.DataFrame(
        unmatched, columns=["player", "draft_year", "pick_overall", "college_name", "reason"])
    return df, unmatched_df
